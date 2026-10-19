import requests
import gradio as gr


# 知识库接口地址
knowledgebase_url = "http://127.0.0.1:6605/knowledgebase"


def list_kbs():
    """
    向后端发送查询知识库请求。
    Returns:
        dict: 更新前端组件属性的字典
    """
    # 定义 API 的 URL
    list_kbs_url = knowledgebase_url + "/list_kbs"  # 请确保端口和路径正确
    try:
        # 发送 GET 请求
        response = requests.get(list_kbs_url, timeout=5)
        # 检查响应状态码
        if response.status_code == 200:
            kb_list = response.json()  # 将 JSON 格式的知识库列表解析为 python 字典
            kb_names = [kb["kb_name"] for kb in kb_list["knowledgebases"]]
            return gr.update(choices=kb_names)
        else:
            return gr.update(choices=[])
    except Exception:
        return gr.update(choices=[])


def create_kb(kb_name, kb_info):
    """
    向后端发送创建知识库请求。
    Args:
        kb_name (str): 知识库名称
        kb_info (str): 知识库描述
    Returns:
        tuple(dict, dict, dict): 更新前端组件属性的字典的元组
    """
    if not kb_name:
        return gr.update(value="知识库名不能为空。", visible=True), gr.update(value=""), gr.update(value="")
    # 定义 API 的 URL
    url = knowledgebase_url + "/create_kb"
    # 构建 JSON 数据
    data = {
        "kb_name": kb_name,
        "kb_info": kb_info
    }
    try:
        # 发送 POST 请求
        response = requests.post(url, json=data)
        # 检查响应状态码
        if response.status_code == 200:
            return gr.update(value=response.json().get("message"), visible=True
                             ), gr.update(value=""), gr.update(value="")
        else:
            return gr.update(value=f"知识库创建失败！{response.json().get('detail', '')}", visible=True
                             ), gr.update(value=""), gr.update(value="")
    except Exception as e:
        return gr.update(value=f"后端请求失败：{type(e).__name__}: {e}", visible=True
                         ), gr.update(value=""), gr.update(value="")


def delete_kb(kb_name):
    """
    向后端发送删除知识库请求。
    Args:
        kb_name (str): 知识库名称
    Returns:
        tuple(dict, dict): 更新前端组件属性的字典的元组
    """
    if not kb_name:
        return gr.update(value="请选择知识库。", visible=True), gr.update(value="")
    # 定义 API 的 URL
    url = knowledgebase_url + "/delete_kb"
    try:
        # 发送 POST 请求
        response = requests.delete(url, params={"kb_name": kb_name})
        # 检查响应状态码
        if response.status_code == 200:
            return gr.update(value=response.json().get("message"), visible=True), gr.update(value="")
        else:
            return gr.update(value=f"知识库删除失败！{response.json().get('detail', '')}", visible=True
                             ), gr.update(value="")
    except Exception as e:
        return gr.update(value=f"后端请求失败：{type(e).__name__}: {e}", visible=True), gr.update(value="")


def upload_docs(kb_name, file_upload, chunk_size, chunk_overlap):
    """
    向后端发送上传知识库文件请求。
    Args:
        kb_name (str): 选择的知识库名称
        file_upload list[str]: 选择上传到知识库的文件
        chunk_size (int): 文档切分时每个文本块的最大字符长度
        chunk_overlap (int): 相邻文本块之间的重叠字符数量
    Returns:
        tuple(dict, dict): 更新前端组件属性的字典
    """
    if not kb_name:
        return gr.update(value="请选择知识库。", visible=True), gr.update(value=[])
    if not file_upload:
        return gr.update(value="请选择要上传的文件。", visible=True), gr.update(value=[])
    # 定义 API 的 URL
    upload_docs_url = knowledgebase_url + "/upload_docs"
    data = {
        'kb_name': kb_name,
        'chunk_size': chunk_size,
        'chunk_overlap': chunk_overlap
    }
    files = []
    try:
        # 构建文件和表单数据
        for file_path in file_upload:
            files.append(("files", open(file_path, "rb")))
        # 发送 POST 请求
        response = requests.post(upload_docs_url, files=files, data=data)
        # 检查响应状态码
        if response.status_code == 200:
            return gr.update(value=response.json().get("message"), visible=True), gr.update(value=[])
        else:
            return gr.update(value=f"文件上传失败！{response.json().get('detail', '')}", visible=True
                             ), gr.update(value=[])
    except Exception as e:
        return gr.update(value=f"后端请求失败：{type(e).__name__}: {e}", visible=True), gr.update(value=[])
    finally:
        # 无论成功失败，都关闭文件
        for _, f in files:
            f.close()


def update(file):
    """
    显示用户选择的文件。
    Args:
        file: 用户选择文件的临时路径列表
    Returns:
        tuple(dict, dict): 更新前端组件属性的字典的元组
    """
    # 选择的文件列表
    selected_files = []
    if file:
        for f in file:
            # 将新选中的文件添加到列表中
            if f not in selected_files:
                selected_files.append(f)
    return gr.update(value=selected_files, visible=True)




