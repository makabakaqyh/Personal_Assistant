from langchain.tools import tool
import httpx


# 知识库接口地址
knowledgebase_url = "http://127.0.0.1:6605/knowledgebase"


@tool
async def list_knowledge_bases() -> str:
    """
    获取当前可用的知识库列表。
    当需要判断应该查询哪个知识库，或者不知道有哪些知识来源时调用。
    """
    try:
        # 创建一个异步 HTTP 客户端
        async with httpx.AsyncClient() as client:
            # 发送 GET 请求
            response = await client.get(knowledgebase_url + "/list_kbs", timeout=5.0)
        # 检查响应状态码
        if response.status_code == 200:
            kbs = response.json()["knowledgebases"]
            result = "当前可用知识库：\n"
            for kb in kbs:
                result += (
                    f"- 名称: {kb['kb_name']}\n"
                    f"  描述: {kb['kb_info']}\n"
                )
            return result
        else:
            return f"查询失败！{response.json().get('detail', '')}"
    except Exception as e:
        return f"请求失败！{type(e).__name__}: {e}"


@tool
async def search_knowledge_base(kb_name: str, query: str) -> str:
    """
    查询指定知识库中的相关文档。
    当用户问题需要参考个人资料、上传文件、论文、技术文档时调用。
    Args:
        kb_name: 要查询的知识库名称
        query: 用户的问题
    """
    try:
        # 创建一个异步 HTTP 客户端
        async with httpx.AsyncClient() as client:
            # 发送 POST 请求
            response = await client.post(knowledgebase_url + "/search_kb", json={"kb_name": kb_name, "query": query})
        # 检查响应状态码
        if response.status_code == 200:
            docs = response.json()
            if not docs:
                return "没有找到相关文档。"
            result = ""
            for i, doc in enumerate(docs):
                result += f"""
                - 文档{i + 1}
                  来源: {doc.get("source", "")}
                  页码: {doc.get("page", "")}
                  内容:
                  {doc.get("page_content", "")}
                """
            return result
        else:
            return f"查询失败！{response.json().get('detail', '')}"
    except Exception as e:
        return f"请求失败！{type(e).__name__}: {e}"
