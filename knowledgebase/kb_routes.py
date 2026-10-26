import os
import shutil
from typing import List
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document
from langchain.embeddings.base import Embeddings
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from fastapi import HTTPException, APIRouter, Body, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
import jieba
import re

from config import EMBEDDING_MODEL_PATH, KB_DIR, KB_FILE_DIR
from database.database import get_db
from database.database_crud import add_kb_to_db, del_kb_from_db, list_kb_from_db
from utils.data_loader import get_loader


# 创建路由组
kb_router = APIRouter(prefix="/knowledgebase", tags=["知识库"])


class LocalEmbeddingModel(Embeddings):
    """
    本地 Embedding 模型，用于知识库文档的向量化。
    """

    def __init__(self, model_path):
        """
        初始化本地 Embedding 模型。
        Args:
            model_path (str): 模型路径或 Hugging Face 模型名称。
        """
        # 加载模型
        self.model = SentenceTransformer(model_path)

    def embed_documents(self, texts):
        """
        文档向量化。将一批文档转换为向量表示。
        Args:
            texts (list[str]): 待编码的文档文本列表。
        Returns:
            list[list[float]]: 每个文档对应的向量列表。
        """
        # 对多个文本进行批量编码
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True  # 对向量做 L2 归一化，归一化后，余弦相似度可以直接用点积计算，提高检索效率
        )
        # 将 numpy 数组转换为 Python 列表。
        return embeddings.tolist()

    def embed_query(self, text):
        """
        查询向量化。将用户查询转换为向量。
        Args:
            text (str): 用户查询文本。
        Returns:
            list[float]: 查询文本对应的向量。
        """
        # 对单个查询文本进行编码
        embedding = self.model.encode(
            text,
            normalize_embeddings=True
        )
        # 将 numpy 数组转换为 Python 列表
        return embedding.tolist()


# 初始化 Embedding 模型
embedding_model = LocalEmbeddingModel(EMBEDDING_MODEL_PATH)


def validate_kb_name(kb_name: str) -> str:
    """
    校验知识库名称。
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", kb_name):
        raise HTTPException(
            status_code=400,
            detail="知识库名称只能包含字母、数字、下划线和连字符。"
        )
    return kb_name


@kb_router.get("/list_kbs")
async def list_kbs(db: Session = Depends(get_db)):
    """
    向前端返回知识库列表。
    Returns:
        JSON: 知识库列表
    """
    try:
        return {"knowledgebases": list_kb_from_db(db)}
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="知识库获取失败。"
        )


@kb_router.post("/create_kb")
async def create_kb(
        kb_name: str = Body(..., description="知识库名称"),
        kb_info: str = Body("", description="知识库描述"),
        db: Session = Depends(get_db)  # 数据库会话，由依赖注入自动提供
):
    """
    根据前端请求创建知识库（使用 FAISS 向量库作为知识库），并将新建的知识库信息保存到数据库中。
    Returns:
        JSON: 返回信息
    """
    # 校验知识库名称
    kb_name = validate_kb_name(kb_name)
    # 构造知识库路径
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    # 检查知识库是否已经存在
    if os.path.exists(kb_path):
        raise HTTPException(status_code=400, detail="知识库已经存在。")
    # 创建一个临时文档，用于创建 FAISS 向量库
    doc = Document(page_content="init", metadata={})
    # 构建 FAISS 向量库
    vector_store = FAISS.from_documents(
        documents=[doc],
        embedding=embedding_model,
        distance_strategy=DistanceStrategy.EUCLIDEAN_DISTANCE,
        normalize_L2=True
    )
    # 获取向量库中所有文档的 ID
    ids = list(vector_store.docstore._dict.keys())
    # 从 FAISS 向量库中删除临时文档及其向量
    vector_store.delete(ids)
    # 保存空 FAISS 向量库
    vector_store.save_local(kb_path)
    # 将新建的知识库信息保存到数据库
    add_kb_to_db(db, kb_name, kb_info)

    return {"message": f"知识库 {kb_name} 创建成功！"}


@kb_router.delete("/delete_kb")
async def delete_kb(kb_name: str, db: Session = Depends(get_db)):
    """
    根据前端请求删除知识库，同时删除它对应的 FAISS 向量库文件、原始文档文件，并将知识库信息从数据库中删除。
    Args:
        kb_name (str): 知识库名称
        db (Session): 数据库会话，由依赖注入自动提供
    Returns:
        JSON: 返回信息
    """
    # 校验知识库名称
    kb_name = validate_kb_name(kb_name)
    # 知识库路径
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    # 知识库原始文件路径
    kb_file_path = os.path.join(KB_FILE_DIR, kb_name)
    # 检查知识库是否存在
    if os.path.exists(kb_path):
        # 删除知识库
        shutil.rmtree(kb_path)
    else:
        raise HTTPException(status_code=404, detail=f"知识库 {kb_name} 不存在！")
    # 删除知识库原始文件
    if os.path.exists(kb_file_path):
        shutil.rmtree(kb_file_path)
    # 删除数据库信息
    del_kb_from_db(db, kb_name)

    return {"message": f"知识库 {kb_name} 删除成功！"}


@kb_router.post("/upload_docs")
async def upload_docs(
        files: List[UploadFile] = File(..., description="上传的文件"),
        kb_name: str = Form(..., description="知识库名称"),
        chunk_size: int = Form(128, description="文档切分时每个文本块的最大字符长度"),
        chunk_overlap: int = Form(20, description="相邻文本块之间的重叠字符数量"),
):
    """
    向知识库上传文件。
    Returns:
        JSON: 返回信息
    """
    # 校验知识库名称
    kb_name = validate_kb_name(kb_name)
    # 知识库路径
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    # 知识库原始文件路径
    kb_file_path = os.path.join(KB_FILE_DIR, kb_name)
    # 检查知识库是否存在
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail=f"知识库 {kb_name} 不存在！")
    # 创建存储知识库原始文件的目录
    os.makedirs(kb_file_path, exist_ok=True)

    updated_file = []
    for file in files:
        # 原始文件的保存路径
        file_path = os.path.join(kb_file_path, file.filename)
        # 读取原始文件
        file_content = file.file.read()
        # 写入文件
        with open(file_path, "wb") as f:
            f.write(file_content)
        # 获取对应的文档加载器
        loader = get_loader(file_path)
        # 将文档加载为一个文档对象列表
        docs = loader.load()
        # 创建文本切割器
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ".", ",", "，", "。", ""],
        )
        # 将文档分割为多个块
        chunks = text_splitter.split_documents(docs)
        # 加载知识库
        vectorstore = FAISS.load_local(kb_path, embedding_model, allow_dangerous_deserialization=True)
        # 将文件内容向量化并添加到知识库
        vectorstore.add_documents(chunks)
        # 保存更新后的知识库
        vectorstore.save_local(kb_path)
        # 记录上传文件
        updated_file.append(file.filename)

    return {"message": f"文件 {updated_file} 已加入知识库 {kb_name}！"}


def mixed_tokenizer(text):
    """
    对中英文混合文本进行分词。
    Args:
        text: 输入文本
    Returns:
        list[str]: 分词结果组成的列表
    """
    # 中文分词
    words = jieba.lcut_for_search(text)
    # 英文分词
    words = [w.lower() for w in words if w.strip()]

    return words


@kb_router.post("/search_kb")
async def search_kb(
        kb_name: str = Body(..., description="知识库名称"),
        query: str = Body(..., description="问题"),
):
    """
    根据用户问题从从知识库中召回相关片段。
    Returns:
        list[dict]: 召回的相关片段
    """
    # 校验知识库名称
    kb_name = validate_kb_name(kb_name)
    # 知识库路径
    kb_path = os.path.join(KB_DIR, f"{kb_name}.faiss")
    if not os.path.exists(kb_path):
        raise HTTPException(status_code=404, detail="知识库不存在！")

    # 加载知识库
    vector_store = FAISS.load_local(kb_path, embedding_model, allow_dangerous_deserialization=True)
    # 创建 FAISS 检索器，返回最相似的 3 个chunk
    faiss_retriever = vector_store.as_retriever(search_kwargs={"k": 3})

    # 获取所有文档 list[Document]
    docs = list(vector_store.docstore._dict.values())
    # 创建 BM25 检索器
    bm25_retriever = BM25Retriever.from_documents(
        docs,
        preprocess_func=mixed_tokenizer,  # 分词函数
    )
    bm25_retriever.k = 2  # 设置 BM25 检索器返回的文档数量

    # 创建混合检索器，按两个检索方式的加权综合最终排名
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, faiss_retriever], weights=[0.3, 0.7]
    )

    # 执行检索
    contexts = ensemble_retriever.invoke(query)
    contexts = [
        {
            "source": context.metadata.get("source", ""),
            "page": context.metadata.get("page", ""),
            "page_content": context.page_content
        } for context in contexts
    ]
    return contexts
