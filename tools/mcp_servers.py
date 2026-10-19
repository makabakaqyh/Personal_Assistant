import sys
from contextlib import AsyncExitStack, asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from config import PROJECT_ROOT, WEB_MCP_CONNECTIONS


# MCP 连接配置
# 这是一个 "Server 名 → 连接参数" 的字典，客户端靠它决定如何拉起每个 MCP Server
mcp_connections = {
    "file_server": {
        "command": sys.executable,  # 使用当前进程的解释器，绝对路径
        "args": ["-m", "tools.file_server"],  # 传给 command 的参数列表
        "transport": "stdio",  # 本地子进程通信
        "cwd": PROJECT_ROOT,  # 子进程的工作目录
    }
}
# 加入远程 MCP Server
mcp_connections.update(WEB_MCP_CONNECTIONS)

# 创建 MCP 客户端
mcp_client = MultiServerMCPClient(mcp_connections)


@asynccontextmanager  # 允许使用 yield 编写一个异步上下文管理器，从而通过 async with 管理资源的创建和释放
async def all_mcp_tools():
    """
    连接所有已配置的 MCP Server，获取每个 Server 提供的工具，将所有工具合并成一个列表，并在使用结束后自动关闭连接。
    """
    # 创建一个异步退出栈，用于统一管理多个异步上下文资源，代码块结束时，AsyncExitStack 会按后进先出的逆序自动执行所有清理动作。
    async with AsyncExitStack() as stack:
        all_tools = []
        # 遍历所有 MCP Server。
        for server_name in mcp_connections:
            # 获取指定 MCP Server 的异步会话上下文管理器，将其交给 AsyncExitStack 管理
            session = await stack.enter_async_context(mcp_client.session(server_name))
            # 获取该 Server 提供的工具
            tools = await load_mcp_tools(session, server_name=server_name)
            # 合并所有工具
            all_tools.extend(tools)
        yield all_tools
