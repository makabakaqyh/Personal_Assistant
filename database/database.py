from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint, JSON, Float, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from config import DATABASE_URI

# 创建数据库引擎，这里使用的是 SQLite，如果数据库不存在会自动创建
engine = create_engine(DATABASE_URI, echo=False)
# 创建 ORM（对象关系映射） 基类，所有模型都将继承自这个基类
Base = declarative_base()


class KnowledgeBase(Base):
    """
    定义知识库表模型。
    """
    __tablename__ = 'knowledge_bases'  # 数据库表名

    id = Column(Integer, primary_key=True, autoincrement=True, comment="知识库 ID")  # 主键
    kb_name = Column(String(50), nullable=False, comment="知识库名称")
    kb_info = Column(String(200), nullable=False, comment="知识库简介")


class ConversationMessage(Base):
    """
    定义会话消息表模型。
    一条记录对应一条模型可见消息（user / assistant / tool）。
    通过 session_id + seq 可以还原整个会话的消息序列。
    """
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="消息 ID")
    session_id = Column(String(50), nullable=False, index=True, comment="所属会话 ID")
    seq = Column(Integer, nullable=False, comment="会话内消息顺序，从1开始单调递增")
    role = Column(String(20), nullable=False, comment="消息角色：user / assistant / tool")
    content = Column(JSON, nullable=True, comment="消息内容，文本或多模态结构；tool_calls 消息可为空")
    tool_calls = Column(JSON, nullable=True, comment="assistant 的工具调用列表")
    tool_call_id = Column(String(64), nullable=True, comment="tool 结果对应的调用 ID")
    tool_name = Column(String(64), nullable=True, comment="工具名，仅 tool 消息使用")
    create_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    # 联合唯一约束：保证 (session_id, seq) 这一组合在整张表里不重复，可以加速查询
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_msg_session_seq"),)


class ConversationSummary(Base):
    """
    定义会话摘要表模型。
    """
    __tablename__ = "conversation_summary"  # 数据库表名

    session_id = Column(String(50), nullable=False, primary_key=True, comment="会话 ID")  # 主键
    summary = Column(Text, nullable=False, comment="会话摘要")
    update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


# class UserFact(Base):
#     """
#     保存用户事实的表模型。
#     """
#     __tablename__ = "user_fact"
#
#     id = Column(Integer, primary_key=True, autoincrement=True, comment="事实 ID")
#     predicate = Column(String(100), nullable=False, index=True, comment="事实谓词")
#     value = Column(String(500), nullable=False, comment="事实")
#     create_time = Column(DateTime, nullable=False, default=datetime.utcnow, comment="系统记录该事实的时间")


# 根据 ORM 模型创建所有表
Base.metadata.create_all(engine)

# 工厂函数，返回根据数据库引擎创建会话的方法
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)


def get_db():
    """
    为每个请求创建一个数据库会话（Session），请求处理完后自动关闭，避免连接泄漏。
    Returns:
        (Session): 数据库会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
