from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import WORKSPACE_DIR
from chat.chat_routes import chat_router
from knowledgebase.kb_routes import kb_router

# 创建后端应用对象
app = FastAPI()

# 添加 CORS 中间件，允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源访问
    allow_credentials=True,  # 允许携带 Cookie、Authorization 等凭证
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 挂载路由
app.include_router(chat_router)
app.include_router(kb_router)

# 挂载静态文件目录。把本地的 MEDIA_DIR 目录，通过 HTTP 的 /media 路径暴露出去
app.mount("/media", StaticFiles(directory=WORKSPACE_DIR), name="media")

# 程序主入口
if __name__ == "__main__":
    # 运行服务器进程，监听端口http://127.0.0.1:6605
    uvicorn.run(app, host="127.0.0.1", port=6605, log_level="warning")
