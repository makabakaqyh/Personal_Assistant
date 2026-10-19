from sqlalchemy.orm import Session
from langchain_core.messages import BaseMessage

from database.database_crud import save_human_message, save_ai_message, save_tool_message, save_current_summary


def save_message(message: BaseMessage, session_id: str, seq: int, db: Session):
    """
    根据 LangChain 消息类型将消息保存到数据库。
    支持 HumanMessage / AIMessage / ToolMessage。
    """
    try:
        if message.type == "human":
            return save_human_message(message, session_id, seq, db)
        if message.type == "ai":
            return save_ai_message(message, session_id, seq, db)
        if message.type == "tool":
            return save_tool_message(message, session_id, seq, db)
        raise ValueError(f"不支持的消息类型: {message.type}")
    except Exception as e:
        raise


def save_summary(summary: str, session_id: str, db: Session):
    """
    保存新的会话摘要。
    Args:
        summary: 会话摘要
        session_id: 会话 ID
        db: 数据库会话
    """
    if summary is None:
        summary = ""
    try:
        # 将新会话摘要入库
        save_current_summary(summary, session_id, db)
    except Exception as e:
        raise








