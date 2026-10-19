import json
import os
import pymupdf
from docx import Document
import shutil

from config import WORKSPACE_DIR


def get_file_content(file_path):
    """
    读取文件内容，以字符串形式返回
    Args:
        file_path (str): 文件路径
    Returns:
        str: 文件内容
    """
    # 读取文件扩展名
    filename = os.path.basename(file_path)
    file_extension = os.path.splitext(filename)[1].lower()
    # 读取文件内容
    if file_extension in ('.txt', '.csv', '.md', '.py'):
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
    elif file_extension == '.json':
        with open(file_path, "r", encoding="utf-8") as f:
            # 把 JSON 解析成 Python 对象，每层嵌套缩进 4 个空格，保留中文
            file_content = json.dumps(json.load(f), indent=4, ensure_ascii=False)
    elif file_extension == '.pdf':
        file_content = ""
        # 打开 PDF
        with pymupdf.open(file_path) as pdf_document:
            # 逐页读取
            for page_num in range(pdf_document.page_count):
                page = pdf_document[page_num]
                # 读取一页文字
                file_content += page.get_text() + "\n"
    elif file_extension == '.docx':
        file_content = ""
        document = Document(file_path)
        # 遍历所有段落
        for paragraph in document.paragraphs:
            # 读取段落文字
            file_content += paragraph.text + "\n"
    else:
        file_content = f"格式不支持，无法读取。"

    return file_content


def read_documents(files, uuid):
    """
    处理前端发送的文件，将其保存到临时存储路径并读取
    Args:
        files (List[UploadFile]): UploadFile 列表
        uuid: 会话 ID
    Returns:
        str: 文件内容
    """
    # 定义临时存储路径
    session_file_storage_path = os.path.join(WORKSPACE_DIR, "temp_file", uuid)
    os.makedirs(session_file_storage_path, exist_ok=True)
    try:
        result = []
        if files:
            # 遍历 UploadFile 列表
            for file in files:
                file_path = os.path.join(session_file_storage_path, file.filename)
                # 保存文件到指定路径
                with open(file_path, "wb") as f:
                    f.write(file.file.read())
        # 遍历目录中的所有文件并读取内容
        for filename in os.listdir(session_file_storage_path):
            file_path = os.path.join(session_file_storage_path, filename)
            if os.path.isfile(file_path):
                # 读取文件内容，返回字符串
                file_content = get_file_content(file_path)
                # 直接将路径和内容拼接到结果字符串
                result.append(f"document:\n{file_path}\ncontent:\n{file_content}\n")
        return "".join(result)
    finally:
        # 清理临时目录
        shutil.rmtree(session_file_storage_path, ignore_errors=True)
