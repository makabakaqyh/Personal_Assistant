# from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from typing import Any


DESTRUCTIVE_TOOLS = frozenset({"delete_file", "delete_dir"})
APPROVAL_TIMEOUT_SECONDS = 300


def _base_tool_name(tool_name: str) -> str:
    """
    去掉大模型返回的工具名前缀，只保留最核心的基础名字。
    """
    return tool_name.rsplit(".", 1)[-1].rsplit("__", 1)[-1]


def is_destructive_tool(tool_name: str) -> bool:
    """
    检查工具是否具有破坏性。
    """
    return _base_tool_name(tool_name) in DESTRUCTIVE_TOOLS


def validate_tool_args(tool_name: str, tool: Any, args: Any) -> str | None:
    """
    检查 LLM 提供的工具调用参数。
    Args:
        tool_name: 工具名
        tool: 工具名对应的工具对象
        args: 工具调用参数
    """
    # 检查工具是否存在
    if tool is None:
        return f"未知工具：{tool_name}。"
    # 检查参数格式
    if not isinstance(args, dict):
        return "工具参数必须是 JSON 对象。"
    # 获取工具的参数结构
    schema = getattr(tool, "args_schema", None)
    if schema is None or isinstance(schema, dict):
        return None
    # 校验参数是否符合工具的 args_schema 定义
    try:
        if hasattr(schema, "model_validate"):
            schema.model_validate(args)  # Pydantic v2
        elif hasattr(schema, "parse_obj"):
            schema.parse_obj(args)  # Pydantic v1
    except Exception as exc:
        return f"工具参数校验失败：{exc}。"
    return None


@dataclass
class PendingApproval:
    """
    审批请求的数据类。
    """
    approval_id: str  # 审批请求 ID
    session_id: str  # 会话 ID
    tool_call_id: str  # 工具调用 ID
    tool_name: str  # 工具名称
    tool_args: dict[str, Any]  # 工具调用参数
    # 用于实现 Agent 执行流的异步阻塞与唤醒（等待人工审批）。必须用 default_factory 现场创建，避免多个审批实例共享同一个 Event
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool | None = None  # 是否批准
    reason: str | None = None  # 拒绝原因


class ApprovalManager:
    """
    管理所有审批。
    """
    def __init__(self):
        # 保存所有审批请求的字典
        self._pending: dict[str, PendingApproval] = {}
        # 异步互斥锁
        self._lock = asyncio.Lock()

    async def create(
        self,
        session_id: str,  # 会话 ID
        tool_call_id: str,  # 工具调用 ID
        tool_name: str,  # 工具名称
        tool_args: dict[str, Any],  # 工具调用参数
    ) -> PendingApproval:
        """
        创建审批请求。
        """
        request = PendingApproval(
            approval_id=secrets.token_urlsafe(18),  # 生成一个安全随机数作为 approval_id
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        # 获取异步互斥锁，把当前的审批请求存入审批请求字典，操作完成后自动释放锁
        async with self._lock:
            self._pending[request.approval_id] = request
        return request

    async def wait(
        self,
        request: PendingApproval,  # 审批请求
        timeout: int = APPROVAL_TIMEOUT_SECONDS,  # 等待时间
    ) -> tuple[bool, str | None]:
        """
        挂起当前协程，等待前端用户对该审批请求的处理结果。
        如果在超时时间内未收到处理结果，将自动判定为超时并拒绝。
        """
        try:
            # 挂起，等待审批
            await asyncio.wait_for(request.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False, "用户审批超时。"
        finally:
            # 从审批请求字典中删除当前审批请求
            async with self._lock:
                self._pending.pop(request.approval_id, None)
        # 审批通过
        if request.approved is True:
            return True, None
        # 审批被拒绝
        else:
            return False, request.reason or "用户拒绝了该操作。"

    async def resolve(
        self,
        approval_id: str,  # 审批请求 ID
        session_id: str,  # 会话 ID
        approved: bool,  # 是否批准
        reason: str | None = None,  # 拒绝原因
    ) -> None:
        """
        将审批结果写入审批请求并唤醒挂起的协程。
        """
        async with self._lock:
            request = self._pending.get(approval_id)
            if request is None:
                raise KeyError("审批请求不存在或已经过期。")
            if request.session_id != session_id:
                raise PermissionError("审批请求不属于当前会话。")
            if request.event.is_set():
                raise RuntimeError("该审批请求已经处理。")
            # 修改审批请求中的内容
            request.approved = approved
            request.reason = reason
            # 解除挂起状态，唤醒挂起的协程
            request.event.set()


approval_manager = ApprovalManager()
