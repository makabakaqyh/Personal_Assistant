# Personal Assistant

基于 **FastAPI、Gradio、LangChain 和 MCP** 构建的个人智能助手，支持流式对话、会话记忆、文件上传、知识库管理和工具调用。

项目默认使用阿里云百炼 DashScope 的 **Qwen Plus** 作为对话模型，并使用本地 Sentence-Transformers 模型生成向量，通过 **FAISS + BM25** 混合检索知识库内容。

## 功能

- **流式聊天**：通过 Gradio 实时展示模型输出。
- **多轮会话记忆**：使用 SQLite 保存消息，并自动生成会话摘要。
- **知识库管理**：创建、删除、上传和检索知识库。
- **混合检索**：结合 FAISS 向量检索和 BM25 关键词检索。
- **本地文件工具**：通过 MCP Server 让 Agent 读取、写入和管理工作目录中的文件。
- **可选 Web 工具**：配置高德地图 MCP 服务后，可扩展地图相关能力。
- **常用文档支持**：知识库支持 `.docx`、`.pdf`、`.csv`、`.txt` 和 `.md` 文件。

## 环境要求

- Python 3.10 或更高版本，推荐 Python 3.11
- 可用的 DashScope API Key
- 首次运行需要加载本地 Embedding 模型

## 安装

克隆项目并创建虚拟环境：

```bash
git clone <your-repository-url>
cd Personal_Assistant

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```bash
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn gradio requests httpx sqlalchemy \
  langchain langchain-core langchain-openai langchain-community \
  langchain-text-splitters langchain-classic langchain-mcp-adapters \
  sentence-transformers faiss-cpu jieba docx2txt pypdf unstructured \
  python-multipart mcp
```

PowerShell 中可以使用同样内容的一行命令：

```powershell
python -m pip install fastapi uvicorn gradio requests httpx sqlalchemy langchain langchain-core langchain-openai langchain-community langchain-text-splitters langchain-classic langchain-mcp-adapters sentence-transformers faiss-cpu jieba docx2txt pypdf unstructured python-multipart mcp
```

## 配置

项目通过环境变量读取密钥。

### 必填配置

`DASHSCOPE_API_KEY`：DashScope API Key。

Linux / macOS：

```bash
export DASHSCOPE_API_KEY="your-dashscope-api-key"
```

Windows PowerShell：

```powershell
$env:DASHSCOPE_API_KEY = "your-dashscope-api-key"
```

### 可选配置

`AMAP_API_KEY`：高德地图 MCP 服务的 Key。配置后，Agent 会自动加载高德地图 MCP 工具。

Linux / macOS：

```bash
export AMAP_API_KEY="your-amap-api-key"
```

Windows PowerShell：

```powershell
$env:AMAP_API_KEY = "your-amap-api-key"
```

默认配置位于 [config.py](config.py)，包括：

- 后端地址：`127.0.0.1:6605`
- 对话模型：`qwen-plus`
- 本地 Embedding 模型：`model/embedding_model`
- SQLite 数据库：`database/db/database.db`

## 启动

需要启动两个进程。

### 1. 启动 FastAPI 后端

```bash
python app_server.py
```

后端默认地址：

```text
http://127.0.0.1:6605
```

也可以使用 Uvicorn 启动：

```bash
uvicorn app_server:app --host 127.0.0.1 --port 6605
```

### 2. 启动 Gradio 前端

在另一个终端中激活同一个虚拟环境，然后执行：

```bash
python web_ui.py
```

打开终端输出的 Gradio 地址，通常是：

```text
http://127.0.0.1:7860
```

前端包含两个页面：

- **聊天机器人**：调整历史消息数量、temperature、最大输出长度和流式输出。
- **知识库管理**：创建知识库、上传文件、设置文本切分参数并删除知识库。

## API 接口

后端接口基地址为 `http://127.0.0.1:6605`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/chat/agent_chat` | Agent 流式聊天 |
| `GET` | `/knowledgebase/list_kbs` | 获取知识库列表 |
| `POST` | `/knowledgebase/create_kb` | 创建知识库 |
| `DELETE` | `/knowledgebase/delete_kb` | 删除知识库 |
| `POST` | `/knowledgebase/upload_docs` | 上传文件并向量化 |
| `POST` | `/knowledgebase/search_kb` | 检索知识库内容 |

创建知识库示例：

```bash
curl -X POST "http://127.0.0.1:6605/knowledgebase/create_kb" \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"demo","kb_info":"示例知识库"}'
```

检索知识库示例：

```bash
curl -X POST "http://127.0.0.1:6605/knowledgebase/search_kb" \
  -H "Content-Type: application/json" \
  -d '{"kb_name":"demo","query":"项目的主要功能是什么？"}'
```

`/chat/agent_chat` 接口会持续返回 JSON 数据块，常见事件类型包括：

- `answer`：模型输出内容
- `tool_start`：Agent 开始调用工具
- `error`：处理过程中的错误信息

## 项目结构

```text
.
├── app_server.py              # FastAPI 后端入口
├── web_ui.py                  # Gradio 前端入口
├── config.py                  # 路径、模型和 MCP 配置
├── api_client/                # 前端调用后端 API 的客户端
├── chat/                      # 对话路由、Agent 循环和提示词
├── knowledgebase/             # 知识库路由及知识库运行数据
├── memory/                    # 会话消息和摘要记忆
├── database/                  # SQLAlchemy 模型和 SQLite 数据库
├── model/embedding_model/     # 本地 Sentence-Transformers Embedding 模型
├── tools/                     # LangChain 工具和 MCP 文件服务
├── utils/                     # 文件加载和通用工具
└── workspace/                 # 用户上传文件和 Agent 工作目录
```
