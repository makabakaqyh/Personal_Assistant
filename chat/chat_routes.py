import json
from fastapi import APIRouter, Body, Form, Depends
from fastapi.responses import StreamingResponse
from typing import AsyncIterable
from sqlalchemy.orm import Session

from chat.agent_loop import agent_loop
from database.database import get_db


# 创建路由组
chat_router = APIRouter(prefix="/chat", tags=["对话"])


async def _agent_chat_iterator(
    session_id: str,  # 会话 ID
    query: str,  # 用户问题
    files: list[dict],  # 用户上文件的元数据
    history_len: int,  # 保留最近历史消息的数量
    temperature: float,  # LLM 生成温度
    max_tokens: int,  # LLM 生成的最大 token 数
    db: Session,  # 数据库会话
) -> AsyncIterable[bytes]:
    """
    构造提示词，并以流式方式返回模型生成结果。
    Yields:
        AsyncIterable[bytes]: 模型输出数据块的异步生成器，数据块为 JSON 格式并编码为 UTF-8 字节
    """
    try:
        # 异步流式调用模型
        async for event in agent_loop(
            session_id=session_id,
            query=query,
            files=files,
            history_len=history_len,
            temperature=temperature,
            max_tokens=max_tokens,
            db=db,
        ):
            # 把 python 对象转换为 JSON 字符串，保留中文，最后把整个字符串变成字节
            yield json.dumps(event, ensure_ascii=False).encode("utf-8")
    except Exception as e:
        yield json.dumps({
            "type": "error",
            "content": f"LLM 调用失败：{type(e).__name__}: {e}",
        }, ensure_ascii=False).encode("utf-8")


@chat_router.post("/agent_chat")  # FastAPI 的路由装饰器，POST /agent_chat 请求会交给 agent_chat()
async def agent_chat(
        session_id: str = Body(..., description="会话 ID"),
        files: list[dict] = Body([], description="上传文件的元数据"),
        query: str = Body("", description="用户问题"),
        history_len: int = Body(..., description="保留最近历史消息的数量"),
        temperature: float = Body(..., description="LLM 采样温度"),
        max_tokens: int = Body(..., description="LLM 输出的最大 token 数"),
        db: Session = Depends(get_db),
):
    """
    处理 Agent 聊天请求，并以流式方式返回模型回复。
    Returns:
        StreamingResponse: 模型生成结果的流式 HTTP 响应。
    """
    # 调用异步流式生成器生成模型回复，并通过 StreamingResponse 将每个 yield 出来的字节数据块实时返回给前端。
    return StreamingResponse(
        _agent_chat_iterator(
            session_id=session_id,
            query=query,
            files=files,
            history_len=history_len,
            temperature=temperature,
            max_tokens=max_tokens,
            db=db,
        ),
        media_type="application/json"  # 响应内容为 JSON
    )
