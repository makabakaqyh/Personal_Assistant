from datetime import datetime
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage

from database.database_crud import search_history_messages, search_recent_summary, search_current_summary


def _row_to_message(row: dict) -> BaseMessage:
    """
    把数据库消息行转换成 LangChain 消息对象。
    """
    role = row["role"]
    if role == "user":
        return HumanMessage(content=row["content"] or "")
    if role == "assistant":
        return AIMessage(
            content=row["content"] or "",
            tool_calls=row["tool_calls"] or [],
        )
    if role == "tool":
        return ToolMessage(
            content=row["content"] or "",
            tool_call_id=row["tool_call_id"],
            name=row["tool_name"] or "",
        )


def get_history_messages(session_id: str, db: Session) -> tuple[list[BaseMessage], int]:
    """
    根据会话 ID 查询该会话的所有上下文消息，并还原为对话上下文。
    Args:
        session_id: 会话 ID
        db: 数据库会话
    Returns:
        list[dict]: 消息字典列表，按 seq 升序
        int: 最后一条消息的 seq，没有消息时返回 0
    """
    try:
        rows, last_seq = search_history_messages(session_id, db)
        return [_row_to_message(r) for r in rows], last_seq
    except Exception as e:
        return [], 0


def get_current_summary(session_id: str, db: Session) -> str:
    """
    加载当前会话摘要，并排列成字符串。
    Args:
        session_id: 当前会话 ID
        db: 数据库会话
    Returns:
        str: 当前会话摘要
    """
    try:
        summary = search_current_summary(session_id, db)
        if not summary:
            return "暂无会话摘要。"

        content = summary.get("summary") or "无摘要内容。"
        update_time = summary.get("update_time")
        if isinstance(update_time, datetime):
            time_str = update_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = "未知时间"
        old_summary = f"- 会话时间：{time_str}\n  会话摘要：{content}"
        return old_summary
    except Exception as e:
        return f"当前会话摘要获取失败。"


def get_recent_summary(session_id: str, db: Session) -> str:
    """
    加载近期会话摘要，并排列成字符串。
    Args:
        session_id: 当前会话 ID
        db: 数据库会话
    Returns:
        str: 最近几次会话摘要
    """
    try:
        summaries = search_recent_summary(session_id, db)
        if not summaries:
            return "暂无历史会话摘要。"
        parts = []
        for item in summaries:
            summary = item.get("summary") or "无摘要内容。"
            update_time = item.get("update_time")
            if isinstance(update_time, datetime):
                time_str = update_time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = "未知时间"
            parts.append(f"- 会话时间：{time_str}\n  会话摘要：{summary}")
        return "\n".join(parts)
    except Exception as e:
        return f"近期会话摘要获取失败。"



# def get_user_profile():
#     """
#     加载用户结构化档案。
#     Returns:
#
#     """
#     # 存储用户结构化档案的文件路径
#     profile_path = os.path.join(MEMORY_FILE_DIR, "user_profile.json")
#     if not profile_path.exists():
#         return {}
#     # 读取文件
#     with open(profile_path, "r", encoding="utf-8") as f:
#         profiles = json.load(f)
#
#     return profiles

