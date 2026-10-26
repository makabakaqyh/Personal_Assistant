import json
import requests
import uuid
import os
from pathlib import Path
import shutil
from datetime import datetime
import gradio as gr


from config import UPLOADED_FILE_DIR


# Agent 聊天接口地址
chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"
# 处理用户审批结果的接口地址
tool_approval_url = "http://127.0.0.1:6605/chat/tool_approvals"


def persist_uploaded_file(file_path: str) -> dict:
    """
    把 Gradio 临时文件复制到持久化目录。
    Args:
        file_path: 文件临时路径
        session_id: 当前会话 ID
    Returns:
        dict: 元数据字典
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"临时文件不存在: {file_path}")

    # 文件扩展名
    ext = file_path.suffix
    # 持久化目录中的对应文件名
    workspace_filename = "file_" + str(uuid.uuid4()) + ext
    # 原始文件名（带扩展名）
    original_name = file_path.name

    # 目标目录
    dest_path = os.path.join(UPLOADED_FILE_DIR, f"{workspace_filename}")
    # 从 Gradio 缓存目录将文件复制到工作目录，保留 Gradio 临时文件供界面展示
    shutil.copy2(file_path, dest_path)
    # 从 Gradio 缓存目录将文件复制到工作目录，保留 Gradio 临时文件供界面展示
    shutil.copy2(file_path, dest_path)

    metadata = {
        "workspace_filename": workspace_filename,
        "original_filename": original_name,
        "uploaded_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return metadata


def chat_with_agent(input_data, history, history_len, temperature, max_tokens, stream, session_id):
    """
    向后端发送对话请求。
    Args:
        input_data (dict): 用户输入，包含以下键：
            - "text" (str): 用户输入的文本内容。
            - "files" (list[str]): 上传文件的临时路径列表。
        history (list[dict]): 聊天历史记录，每个元素为字典，包含：
            - "role" (str): 角色，值为 "user" 或 "assistant"。
            - "content" (str | dict): 消息内容，可能是纯文本字符串，也可能是包含 "text" 和 "files" 的字典。
        history_len (int): 保留最近历史消息的数量。
        temperature (float): 生成温度，控制随机性。
        max_tokens (int): 生成的最大 token 数。
        stream (bool): 是否启用流式输出。
        session_id (str): 当前用户会话的唯一标识符。
    """
    # 提取用户输入的文本
    query = input_data.get("text") or ""
    # 处理文件对象
    file_metadata = []
    for file_path in input_data["files"]:
        metadata = persist_uploaded_file(file_path)
        file_metadata.append(metadata)

    # 浅拷贝历史消息
    history = list(history or [])
    # 将用户文本追加进历史消息
    history.append({"role": "user", "content": query})
    # 预先占位 assistant 消息
    assistant_index = len(history)
    history.append({"role": "assistant", "content": "🧠 正在生成回答 ...\n"})
    # 更新聊天记录，并清空输入框
    yield list(history), {"text": "", "files": []}

    # 构建 JSON 数据
    payload = {
        "session_id": session_id,
        "files": file_metadata,
        "query": query,
        "history_len": history_len,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        # 向后端接口发送post请求，以流式方式接收响应
        response = requests.post(chat_with_agent_url, json=payload, stream=True)
        # 自动检查 HTTP 响应的状态码
        response.raise_for_status()
        assistant_content = ""
        # 不断从响应里读取后端发送过来的数据块
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:  # 防止收到空块
                event = json.loads(chunk)  # 将 JSON 字符串解析为字典
                event_type = event.get("type")
                if event_type == "answer":
                    assistant_content += event.get("content", "")
                elif event_type == "tool_start":
                    assistant_content += "🔧 " + event.get("content", "")
                elif event_type == "require_approval":
                    approval_id = event["approval_id"]
                    tool_name = event.get("tool_name", "")
                    args = json.dumps(event.get("args", {}), ensure_ascii=False, indent=2)
                    # 临时生成一个审批说明
                    approval_text = (
                        "\n\n### ⚠️风险操作需要批准\n"
                        f"工具：`{tool_name}`\n"
                        f"参数：\n```json\n{args}\n```\n"
                    )
                    # 在历史消息中注入消息内容和交互按钮
                    history[assistant_index] = {
                        "role": "assistant",
                        "content": assistant_content + approval_text,
                        "options": [
                            {"label": "✅ 允许", "value": f"hitl_approve:{approval_id}"},
                            {"label": "❌ 拒绝", "value": f"hitl_reject:{approval_id}"}
                        ],
                    }
                elif event_type == "error":
                    assistant_content += "❌ " + event.get("content", "后端返回未知错误。")
                else:
                    assistant_content += event.get("content", event.get("answer", str(event)))
                # 审批完成后移除消息内的按钮
                if event_type != "require_approval":
                    history[assistant_index] = {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                # 流式显示，返回后函数不结束，可以继续流式返回。审批请求必须立即显示。
                if stream or event_type == "require_approval":
                    yield list(history), gr.skip()
        # 非流式显示
        if not stream:
            yield list(history), gr.skip()
    except Exception as e:
        history[assistant_index] = {
            "role": "assistant",
            "content": f"后端请求失败：{type(e).__name__}: {e}"
        }
        yield list(history), gr.skip()


def handle_approval_option(
    session_id,  # 会话 ID
    event: gr.SelectData,  # Gradio 自动注入的第三个参数，里面有用户点击的信息
):
    """
    向后端发送审批结果。
    """
    value = str(event.value)
    if value.startswith("hitl_approve:"):
        approved = True
        approval_id = value.split(":", 1)[1]
    elif value.startswith("hitl_reject:"):
        approved = False
        approval_id = value.split(":", 1)[1]
    else:
        return
    # 向后端发送审批结果
    try:
        response = requests.post(
            f"{tool_approval_url}/{approval_id}",
            json={
                "session_id": session_id,
                "approved": approved,
            },
            timeout=10,
        )
        # 自动检查 HTTP 响应的状态码
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"审批提交失败：{e}。") from e
