import json
import requests
import uuid
import os
from pathlib import Path
import shutil
from datetime import datetime

from config import UPLOADED_FILE_DIR


# Agent 聊天接口地址
chat_with_agent_url = "http://127.0.0.1:6605/chat/agent_chat"


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


def chat_with_agent(input, _history, history_len, temperature, max_tokens, stream, session_id):
    """
    向后端发送对话请求。
    Args:
        input (dict): 用户输入，包含以下键：
            - "text" (str): 用户输入的文本内容。
            - "files" (list[str]): 上传文件的临时路径列表。
        _history (list[dict]): 聊天历史记录，每个元素为字典，包含：
            - "role" (str): 角色，值为 "user" 或 "assistant"。
            - "content" (str | dict): 消息内容，可能是纯文本字符串，也可能是包含 "text" 和 "files" 的字典。
        history_len (int): 保留最近历史消息的数量。
        temperature (float): 生成温度，控制随机性。
        max_tokens (int): 生成的最大 token 数。
        stream (bool): 是否启用流式输出。
        session_id (str): 当前用户会话的唯一标识符。
    """
    query = f'{input["text"]}'
    # 读取文件对象
    file_metadata = []
    for file_path in input["files"]:
        metadata = persist_uploaded_file(file_path)
        file_metadata.append(metadata)
    # 构建 JSON 数据
    data = {
        "session_id": session_id,
        "files": file_metadata,
        "query": query,
        "history_len": history_len,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        # 向后端接口发送post请求，以流式方式接收响应
        response = requests.post(chat_with_agent_url, json=data, stream=True)
        if response.status_code == 200:  # 请求成功
            chunks = ""
            if stream:  # 流式显示
                # 不断从响应里读取后端发送过来的数据块
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:  # 防止收到空块
                        data = json.loads(chunk)  # 将 JSON 字符串解析为字典
                        event_type = data.get("type")
                        if event_type == "answer":
                            chunks += data["content"]
                        elif event_type == "tool_start":
                            chunks += "🔧 " + data["content"]
                        elif event_type == "error":
                            chunks += data.get("content", "后端返回未知错误。")
                        else:
                            chunks += data.get("content", data.get("answer", str(data)))
                        # 返回后函数不结束，可以继续流式返回
                        yield chunks
            else:  # 非流式显示
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:  # 防止收到空块
                        data = json.loads(chunk)
                        event_type = data.get("type")
                        if event_type == "answer":
                            chunks += data["content"]
                        elif event_type == "tool_start":
                            chunks += "🔧 " + data["content"]
                        elif event_type == "error":
                            chunks += data.get("content", "后端返回未知错误。")
                        else:
                            chunks += data.get("content", data.get("answer", str(data)))
                yield chunks
        else:
            yield f"[{response.status_code}] chat_with_agent请求失败，请检查后台服务器是否正常运行。"
    except Exception as e:
        yield f"后端请求失败：{type(e).__name__}: {e}"
