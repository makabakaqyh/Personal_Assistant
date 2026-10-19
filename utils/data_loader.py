import os
from fastapi import HTTPException
from langchain_community.document_loaders import (Docx2txtLoader, PyPDFLoader, TextLoader, CSVLoader,
                                                  UnstructuredMarkdownLoader)


def get_loader(file_path):
    """
    根据文件格式选择适当的 loader，返回 langchain 的文档加载器
    Args:
        file_path (str): 文件路径
    Returns:
         Document Loader: 文档加载器
    """
    _, file_extension = os.path.splitext(file_path)
    if file_extension == ".docx":
        loader = Docx2txtLoader(file_path)
    elif file_extension == ".pdf":
        loader = PyPDFLoader(file_path)
    elif file_extension == ".csv":
        loader = CSVLoader(file_path)
    elif file_extension == ".txt":
        loader = TextLoader(file_path, encoding='utf-8')
    elif file_extension == ".md":
        loader = UnstructuredMarkdownLoader(file_path)
    else:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    return loader
