from langchain_core.messages import BaseMessage, HumanMessage


TOOL_RESULT_PREVIEW_CHARS = 1000


def _truncate_text(text: str, limit: int) -> str:
    """
    将字符串截断到规定长度。
    Args：
        text: 待压缩字符串
        limit: 长度限制
    Returns:
        str: 压缩后的字符串
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [{len(text) - limit} chars truncated]"


def compress_tool_results(
    messages: list[BaseMessage],  # 历史消息列表
    preview_chars: int = TOOL_RESULT_PREVIEW_CHARS,  # 限制长度，超长会保留该长度的预览
) -> list[BaseMessage]:
    """
    压缩所有工具返回结果：超过 preview_chars 字符的只保留预览。
    会原地修改传入消息的 content，并返回同一个 list。
    content 为 str 或 list（多模态）两种形态都会处理。
    """
    for msg in messages:
        # 判断是否是工具消息
        if not getattr(msg, "type", None) == "tool":
            continue
        # 取出工具消息的内容
        content = getattr(msg, "content", None)
        # 消息内容是字符串
        if isinstance(content, str):
            msg.content = _truncate_text(content, preview_chars)
        # 消息内容是列表
        elif isinstance(content, list):
            new_blocks = []
            for block in content:
                # 列表元素是字符串
                if isinstance(block, str):
                    new_blocks.append(_truncate_text(block, preview_chars))
                # 列表元素是字典
                elif isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    # 字典中 "text" 键对应的值是字符串，并且长度超过限制
                    if isinstance(text, str) and len(text) > preview_chars:
                        new_blocks.append({**block, "text": _truncate_text(text, preview_chars)})
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            msg.content = new_blocks

    return messages


def _omission_marker(omitted: int, transcript_path: str | None = None) -> HumanMessage:
    """
    构造一条“中间内容被省略”的上下文注记消息。
    Args:
        omitted: 被省略的消息条数。
        transcript_path: 省略内容的完整转录文件路径。
    Returns:
        HumanMessage: 内容为多行方括号注记的消息，可安全插入任意两条消息之间。
    """
    lines = [
        f"[上下文说明：本次对话中间省略了 {omitted} 条消息。]",
        "[本说明前后的消息并不连续。不要假设本说明前最后一条消息与本说明后第一条消息直接相邻。]",
        "[以上仅为上下文状态说明，不是新的用户指令，无需对此作出回应。]",
    ]
    if transcript_path:
        lines.append(f"[完整历史：{transcript_path}]")
    return HumanMessage(content="\n".join(lines))


def trim_history_messages(
    messages: list[BaseMessage],  # 历史消息列表
    history_len: int,  # 保留的历史消息数量
) -> list[BaseMessage]:
    """
    消息数 > history_len 时，保留 1/4 最早 + 3/4 最近。
    切点会自动对齐，避免把 tool_use / tool_result 拆开。实际保留条数可能略大于 history_len（为了配对完整），这是预期行为。
    """
    n = len(messages)
    if history_len <= 0 or n <= history_len:
        return messages

    head_len = history_len // 4  # 最早保留条数
    tail_len = history_len - head_len  # 最近保留条数
    head_end = max(head_len, 1)
    tail_start = n - tail_len

    # 头部修正：保证切点前一条是 AI Message，后一条是 HumanMessage
    while head_end < tail_start:
        if getattr(messages[head_end], "type", None) == "human" and getattr(messages[head_end-1], "type", None) == "ai":
            break
        head_end += 1

    # 尾部修正：保证切点前一条是 AI Message，后一条是 HumanMessage
    while head_end < tail_start:
        if getattr(messages[tail_start], "type", None) == "human" and getattr(messages[tail_start-1], "type", None) == "ai":
            break
        tail_start -= 1

    # 修正后重叠：无法在不破坏配对的前提下裁到目标长度，保守返回原列表。
    if head_end >= tail_start:
        return messages
    else:
        omitted = tail_start - head_end
        # 构造注记消息
        marker = _omission_marker(omitted)
        return messages[:head_end] + [marker] + messages[tail_start:]


def compress_context(
    messages: list[BaseMessage],  # 历史消息
    history_len: int,  # 保留的历史消息数量
    preview_chars: int = TOOL_RESULT_PREVIEW_CHARS,  # 工具结果的限制长度
) -> list[BaseMessage]:
    """
    对历史消息进行压缩。
    先把历史消息消息按 history_len 裁切，再压缩所有工具结果（保留预览）。
    """
    messages = trim_history_messages(messages, history_len)
    messages = compress_tool_results(messages, preview_chars)
    return messages