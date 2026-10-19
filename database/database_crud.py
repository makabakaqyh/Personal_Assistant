from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from database.database import KnowledgeBase, ConversationMessage, ConversationSummary


def add_kb_to_db(db: Session, kb_name: str, kb_info: str) -> None:
    """
    将知识库信息加入数据库，如果已经存在，则更新描述信息。
    Args:
        db (Session): 数据库会话
        kb_name (str): 知识库名称
        kb_info (str): 知识库描述
    """
    try:
        # 查询是否存在相同名称的知识库（不区分大小写）
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.kb_name.ilike(kb_name)).first()
        if kb is None:
            # 如果不存在，创建新的知识库实例
            kb = KnowledgeBase(kb_name=kb_name, kb_info=kb_info)
            # 把这个对象加入数据库 session，准备插入
            db.add(kb)
        else:
            # 如果存在，更新知识库信息
            kb.kb_info = kb_info
        # 提交事务
        db.commit()
    except Exception as e:
        # 回滚
        db.rollback()
        raise


def del_kb_from_db(db: Session, kb_name: str) -> None:
    """
    从数据库中删除某个知识库的信息。
    Args:
        db (Session): 数据库会话
        kb_name (str): 知识库名称
    """
    try:
        # 查询是否存在指定名称的知识库（区分大小写）
        kb_to_delete = db.query(KnowledgeBase).filter_by(kb_name=kb_name).first()
        if kb_to_delete:
            # 如果存在，删除知识库
            db.delete(kb_to_delete)
            db.commit()
    except Exception as e:
        db.rollback()
        raise


def list_kb_from_db(db: Session) -> list[dict]:
    """
    查询所有知识库信息。
    Args:
        db (Session): 数据库会话
    Returns:
        list[dict]: 知识库信息字典的列表
    """
    # 查询所有知识库
    all_kbs = db.query(KnowledgeBase).all()
    # 将结果转换为列表
    kbs_list = [
        {
            "kb_name": kb.kb_name,
            "kb_info": kb.kb_info
        }
        for kb in all_kbs
    ]
    return kbs_list


def search_history_messages(session_id: str, db: Session) -> tuple[list[dict], int]:
    """
    查询属于同一个会话的所有消息，按 seq 升序排列。
    Args:
        session_id: 会话 ID
        db: 数据库会话
    Returns:
        list[dict]: 消息字典列表，按 seq 升序
        int: 最后一条消息的 seq，没有消息时返回 0
    """
    # 在数据库查询属于 session_id 的所有消息
    rows = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.seq.asc())
        .all()
    )
    # 将结果转换为列表
    messages = [
        {
            "seq": r.seq,
            "role": r.role,
            "content": r.content,
            "tool_calls": r.tool_calls,
            "tool_call_id": r.tool_call_id,
            "tool_name": r.tool_name,
            "create_time": r.create_time,
        }
        for r in rows
    ]
    # 获取最后一条消息的 seq
    last_seq = rows[-1].seq if rows else 0
    return messages, last_seq


def search_current_summary(session_id: str, db: Session) -> dict:
    """
    从数据库查询当前会话摘要。
    Args:
        session_id: 当前会话 ID
        db (Session): 数据库会话
    Returns:
        dict: 当前会话摘要字典
    """
    # 在数据库查询当前会话的摘要
    summary = (
        db.query(ConversationSummary)
        .filter(ConversationSummary.session_id == session_id)
        .first()
    )
    # 将结果转换为字典
    if summary is None:
        # 没有找到返回空字典
        return {}
    recent_summaries = {
        "update_time": summary.update_time,
        "summary": summary.summary,
    }
    return recent_summaries


def save_current_summary(summary: str, session_id: str, db: Session) -> dict:
    """
    将当前会话摘要保存到数据库。
    Args:
        summary: 绘画摘要
        session_id: 当前会话 ID
        db: 数据库会话
    """
    try:
        # 查询当前会话是否已有摘要
        summary_row = (
            db.query(ConversationSummary)
            .filter(ConversationSummary.session_id == session_id)
            .first()
        )
        if summary_row is None:
            # 如果不存在则创建
            summary_row = ConversationSummary(
                session_id=session_id,
                summary=summary,
            )
            db.add(summary_row)
        else:
            # 如果存在则更新
            summary_row.summary = summary
        db.commit()
        db.refresh(summary_row)
    except Exception:
        db.rollback()
        raise


def search_recent_summary(session_id: str, db: Session) -> list[dict]:
    """
    从数据库查询近期会话摘要。
    Args:
        session_id: 当前会话 ID
        db (Session): 数据库会话
    Returns:
        list[dict]: 最近几次会话摘要字典的列表
    """
    # 在数据库查询最近的三次会话摘要
    summaries = (
        db.query(ConversationSummary)
        .filter(ConversationSummary.session_id != session_id)
        .order_by(ConversationSummary.update_time.desc())
        .limit(5)
        .all()
    )
    # 将结果转换为列表
    recent_summaries = [
        {
            "update_time": summary.update_time,
            "summary": summary.summary,
        }
        for summary in summaries
    ]
    return recent_summaries


def save_human_message(
        human_message: HumanMessage,  # 要保存的用户消息
        session_id: str,  # 会话 ID
        seq: int,  # 当前这条消息在会话内的消息顺序
        db: Session,  # 数据库会话
) -> None:
    """
    保存一条 HumanMessage 到会话消息表。
    """
    # 构造一条数据
    row = ConversationMessage(
        session_id=session_id,
        seq=seq,
        role="user",
        content=human_message.content,
        tool_calls=None,
        tool_call_id=None,
        tool_name=None,
    )
    try:
        # 准备插入
        db.add(row)
        # 提交
        db.commit()
    except Exception as e:
        db.rollback()
        raise


def save_ai_message(
    ai_message: AIMessage,  # 要保存的 AI 消息
    session_id: str,  # 会话 ID
    seq: int,  # 当前这条消息在会话内的消息顺序
    db: Session,  # 数据库会话
) -> None:
    """
    保存一条 AIMessage 到会话消息表。
    """
    # 构造一条数据
    row = ConversationMessage(
        session_id=session_id,
        seq=seq,
        role="assistant",
        content=getattr(ai_message, "content", None),
        tool_calls=getattr(ai_message, "tool_calls", None),
        tool_call_id=None,
        tool_name=None,
    )
    try:
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        raise


def save_tool_message(
    tool_message: ToolMessage,  # 要保存的工具返回消息
    session_id: str,  # 会话 ID
    seq: int,  # 当前这条消息在会话内的消息顺序
    db: Session,  # 数据库会话
) -> None:
    """
    保存一条 ToolMessage 到会话消息表。
    """
    row = ConversationMessage(
        session_id=session_id,
        seq=seq,
        role="tool",
        content=tool_message.content,
        tool_calls=None,
        tool_call_id=tool_message.tool_call_id,
        tool_name=getattr(tool_message, "name", None),
    )
    try:
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        raise





