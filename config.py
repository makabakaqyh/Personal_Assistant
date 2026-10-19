import os

# ======================================================================================================================
# 路径配置
# ======================================================================================================================
# 项目根目录（本文件所在目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# 工作目录
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace")
# 保存用户上传文件的目录
UPLOADED_FILE_DIR = os.path.join(WORKSPACE_DIR, "uploaded_file")
# 知识库目录
KB_DIR = os.path.join(PROJECT_ROOT, "knowledgebase", "kb")
# 存储知识库原始文档的目录
KB_FILE_DIR = os.path.join(PROJECT_ROOT, "knowledgebase", "kb_raw_files")
# 数据库目录
DB_DIR = os.path.join(PROJECT_ROOT, "database", "db")
# 数据库文件
_db_file = os.path.join(DB_DIR, "database.db")
# 数据库连接 URI
DATABASE_URI = "sqlite:///" + _db_file.replace("\\", "/")
# 确保必要的目录存在
for _dir in (UPLOADED_FILE_DIR, KB_DIR, DB_DIR, KB_FILE_DIR):
    os.makedirs(_dir, exist_ok=True)

# ======================================================================================================================
# 模型配置
# ======================================================================================================================
API_KEY = os.getenv("DASHSCOPE_API_KEY")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CHAT_MODEL_NAME = "qwen-plus"
#  本地 Embedding 模型路径
EMBEDDING_MODEL_PATH = os.path.join(PROJECT_ROOT, "model", "embedding_model")

# ======================================================================================================================
# 远程 MCP Server 配置
# ======================================================================================================================
WEB_MCP_CONNECTIONS = {}
# 高德地图 MCP Server
if os.getenv("AMAP_API_KEY"):
    WEB_MCP_CONNECTIONS.update({
        "amap_server": {
            "url": f"https://mcp.amap.com/mcp?key={os.getenv('AMAP_API_KEY')}",
            "transport": "streamable_http",  # 通信方式
        }
    })

