import json
from pydantic import BaseModel
from typing import AsyncIterable
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage, AIMessage
from sqlalchemy.orm import Session
from langchain_core.messages import BaseMessage

from config import CHAT_MODEL_NAME, API_KEY, BASE_URL
from tools.kb_search import list_knowledge_bases, search_knowledge_base
from context.prompt import chat_system_prompt, memory_prompt, uploaded_file_prompt, chat_user_prompt, summary_prompt
from context.context_compression import compress_context
from memory.memory_retriever import get_history_messages, get_recent_summary, get_current_summary
from memory.memory_manager import save_message, save_summary
from tools.mcp_servers import all_mcp_tools
from chat.tool_approvals import (validate_tool_args, approval_manager, is_destructive_tool,
                                 APPROVAL_TIMEOUT_SECONDS)


# 本地 Langchain Tool 注册
kb_tools = [
    list_knowledge_bases,
    search_knowledge_base
]


def _format_files(files: list[dict]) -> str:
    """
    将用户上传文件的元数据列表转换为字符串。
    Args:
        files: 用户上文件的元数据
    Returns:
        str: 转换后的字符串
    """
    if not files:
        return "无"
    lines = []
    for f in files:
        lines.append(f'- 工作目录中的文件名: {f["workspace_filename"]}, '
                     f'原始文件名: {f["original_filename"]}, uploaded_time: {f["uploaded_time"]}')
    return "\n".join(lines)


def _build_summary_messages(turn_messages: list[BaseMessage]) -> str:
    """
    将本轮的新消息转换为结构化 JSON。
    Args:
        turn_messages: 新消息列表
    Returns:
        str: JSON 字符串格式的本轮新消息
    """
    result = []
    for message in turn_messages:
        if message.type == "human":
            result.append({
                "role": "user",
                "content": message.content,
            })
        elif message.type == "ai":
            item = {
                "role": "assistant",
                "content": message.content,
            }
            # 只有确实存在工具调用时才加入
            if message.tool_calls:
                item["tool_calls"] = message.tool_calls
            result.append(item)
        elif message.type == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.name,
                "content": message.content,
            })
    return json.dumps(result, ensure_ascii=False, indent=4)


class SummaryResult(BaseModel):
    """
    定义摘要结果的数据模型类，让大模型返回结构化输出。
    """
    summary: str


async def _summarize_turn(
        session_id: str,  # 当前会话 ID
        turn_messages: list[BaseMessage],  # 当前会话中新增的消息列表
        db: Session,  # 数据库会话
) -> str:
    """
    根据本轮新增消息更新会话摘要。
    Returns:
         str: 总结出的新摘要
    """
    # 初始化摘要模型
    summary_llm = ChatOpenAI(
        model=CHAT_MODEL_NAME,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0,
        max_tokens=1000,
        extra_body={"enable_thinking": False},
    )
    # 要求模型返回 SummaryResult 结构
    structured_llm = summary_llm.with_structured_output(SummaryResult)

    # 获取当前会话的旧摘要
    old_summary = get_current_summary(session_id, db)
    # 将 LangChain 消息列表转换为 JSON 字符串
    summary_messages = _build_summary_messages(turn_messages)
    # 构造摘要提示词
    prompt = summary_prompt.format_messages(
        old_summary=old_summary,
        new_message=summary_messages,
    )

    # 异步调用摘要模型
    result = await structured_llm.ainvoke(prompt)

    # 提取摘要文本
    if isinstance(result, SummaryResult):
        new_summary = result.summary
    else:
        raise TypeError(f"摘要模型返回了不支持的类型: {type(result)}")

    return new_summary


async def _invoke_tool(tool, tool_args: dict) -> any:
    """
    调用工具，获取工具返回值。
    Args:
        tool: 要调用的工具
        tool_args: 工具调用参数
    Returns:
        工具调用结果
    """
    try:
        raw_result = await tool.ainvoke(tool_args)
        # MCP 工具：langchain-mcp-adapters 返回(content, artifact)
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            content, artifact = raw_result
            # 优先取结构化结果
            if artifact and "structured_content" in artifact:
                tool_result = artifact["structured_content"]
            # 如果没有结构化结果，就使用普通内容
            else:
                tool_result = content
        # LangChain 工具就直接使用返回值
        else:
            tool_result = raw_result
        return tool_result
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e),
        }


async def agent_loop(
        session_id: str,  # 会话 ID
        query: str,  # 用户问题
        files: list[dict],  # 用户上文件的元数据
        history_len: int,  # 保留最近历史消息的数量
        temperature: float,  # LLM 生成温度
        max_tokens: int,  # LLM 生成的最大 token 数
        db: Session,  # 数据库会话
) -> AsyncIterable[dict]:
    """
    Agent 循环
    Returns:
        AsyncIterable[dict]: 模型输出字典的异步生成器
    """
    # 初始化聊天模型 ======================================================================================================
    # 创建 LLM 客户端
    llm = ChatOpenAI(
        model=CHAT_MODEL_NAME,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"enable_thinking": False},
    )

    # 获取记忆 ==========================================================================================================
    # 历史消息列表（返回历史消息列表和最后一条消息在会话中的顺序）
    history_messages, last_seq = get_history_messages(session_id, db)
    # 压缩历史消息
    history_messages = compress_context(history_messages, history_len)

    # 近期会话摘要
    conversation_summaries = get_recent_summary(session_id, db)
    # 长期记忆（返回一个消息列表）
    memory = memory_prompt.format_messages(
        conversation_summaries=conversation_summaries,  # 近期会话摘要
        facts=None,  # 事实
    )

    # 生成提示词 =========================================================================================================
    # 系统提示词（返回一个消息列表）
    system_prompt = chat_system_prompt.format_messages()
    # 构造消息列表
    messages = system_prompt + memory + history_messages

    # 使用 turn_messages 收集本轮的新消息，用于更新本轮会话摘要
    turn_messages = []
    # 如果用户上传文件
    if files:
        # 用户上传的文件（返回一个消息列表）
        user_file = uploaded_file_prompt.format_messages(
            files=_format_files(files)
        )
        # 把用户上传的文件入库
        save_message(user_file[0], session_id, last_seq + 1, db)
        last_seq += 1
        # 加入消息列表
        messages.append(user_file[0])
        # 收集进本轮消息
        turn_messages.append(user_file[0])

    # 用户提示词（返回一个消息列表）
    user_prompt = chat_user_prompt.format_messages(
        query=query,  # 用户问题
    )
    # 把用户问题入库
    save_message(user_prompt[0], session_id, last_seq + 1, db)
    last_seq += 1
    # 加入消息列表
    messages.append(user_prompt[0])
    # 收集进本轮消息
    turn_messages.append(user_prompt[0])

    # 启动本地 MCP Server 并绑定工具 =======================================================================================
    async with all_mcp_tools() as mcp_tools:
        # 合并 LangChain 工具和本地/远程 MCP 工具
        all_tools = kb_tools + mcp_tools
        # 绑定工具
        llm_with_tools = llm.bind_tools(all_tools)
        # 工具调用时，根据名称找到对应工具
        tool_map = {tool.name: tool for tool in all_tools}

        # Agent Loop ===================================================================================================
        for attempt in range(20):
            final_chunk = None
            # 流式调用 LLM
            async for chunk in llm_with_tools.astream(messages):
                if chunk.content:
                    yield {"type": "answer", "content": chunk.content}
                # 累积 AIMessageChunk。AIMessageChunk 可以相加
                final_chunk = chunk if final_chunk is None else final_chunk + chunk
            # 流式调用结束后，把累积的 chunk 转成完整 AIMessage
            if final_chunk is not None:
                response = AIMessage(
                    content=final_chunk.content,
                    tool_calls=final_chunk.tool_calls or [],
                    invalid_tool_calls=final_chunk.invalid_tool_calls or [],
                    additional_kwargs=final_chunk.additional_kwargs or {},
                    response_metadata=final_chunk.response_metadata or {},
                    usage_metadata=final_chunk.usage_metadata,
                    id=final_chunk.id,
                )
            else:
                raise RuntimeError("LLM 流式返回为空")
            # 把 AI 消息入库
            save_message(response, session_id, last_seq + 1, db)
            last_seq += 1
            # 把 AI 消息加入消息列表
            messages.append(response)
            # 收集进本轮消息
            turn_messages.append(response)

            if response.tool_calls:
                # 有工具调用，执行工具
                for tool_call in response.tool_calls:
                    tool_call_id = tool_call["id"]
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool = tool_map.get(tool_name)
                    yield {
                        "type": "tool_start",
                        "content": f"正在调用工具 {tool_name} ...\n",
                    }
                    # 检查工具参数
                    validation_error = validate_tool_args(tool_name=tool_name, tool=tool, args=tool_args)
                    if validation_error:
                        # 参数校验失败
                        tool_result = {
                            "success": False,
                            "error_type": "InvalidToolArgs",
                            "error": validation_error,
                        }
                    # 破坏性操作请求人工审批
                    elif is_destructive_tool(tool_name):
                        approval = await approval_manager.create(
                            session_id=session_id,
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            tool_args=tool_args,
                        )
                        # 把事件发给前端
                        yield {
                            "type": "require_approval",
                            "approval_id": approval.approval_id,
                            "session_id": session_id,
                            "tool_call_id": tool_call_id,
                            "tool_name": tool_name,
                            "args": tool_args,
                            "expires_in": APPROVAL_TIMEOUT_SECONDS,
                            "content": f"工具 {tool_name} 请求删除操作，请确认后再继续。",
                        }
                        # 挂起，等待审批结果
                        approved, reason = await approval_manager.wait(approval)
                        # 审批通过
                        if approved:
                            # 调用工具，获取工具返回值
                            tool_result = await _invoke_tool(tool, tool_args)
                        # 审批被拒绝
                        else:
                            tool_result = {
                                "success": False,
                                "error_type": "HumanApprovalDenied",
                                "error": reason or "用户未批准该操作。",
                            }
                    # 普通工具调用
                    else:
                        tool_result = await _invoke_tool(tool, tool_args)
                    tool_message = ToolMessage(
                        content=json.dumps(tool_result, ensure_ascii=False, default=str),
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    # 把工具返回结果入库
                    save_message(tool_message, session_id, last_seq + 1, db)
                    last_seq += 1
                    # 把工具返回结果加入消息列表
                    messages.append(tool_message)
                    # 收集进本轮消息
                    turn_messages.append(tool_message)
            else:
                # 无工具调用，结束 Agent Loop
                break
        else:
            # 循环全部用完
            yield {"type": "error", "content": "Agent 尝试次数达上限，已强制终止。"}

    # 提取事实 ==========================================================================================================

    # 更新会话摘要 =======================================================================================================
    # 总结新摘要
    new_summary = await _summarize_turn(
        session_id=session_id,
        turn_messages=turn_messages,
        db=db,
    )
    # 将新摘要入库
    save_summary(new_summary, session_id, db)
