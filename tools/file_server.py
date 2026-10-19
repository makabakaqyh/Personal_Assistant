from pathlib import Path
from datetime import datetime
import shutil
from docx import Document
from mcp.server.fastmcp import FastMCP
import os

from config import WORKSPACE_DIR


# ======================================================================================================================
# 创建 MCP Server
# ======================================================================================================================
# 创建一个 MCP Server 实例，"file_server" 只是这个服务的名字
mcp = FastMCP("file_server")


# ======================================================================================================================
# 项目路径与基础配置
# ======================================================================================================================
# 文件备份区域，修改已有文件前，把原文件备份到这里
BACKUP_DIR = os.path.join(WORKSPACE_DIR, "backups")
# 创建备份文件夹
os.makedirs(BACKUP_DIR, exist_ok=True)

# 文件类型白名单
# 只允许 Agent 操作这些类型的文件。这是一个安全措施：即使 LLM 想去操作 .exe、.dll、.bat 等文件，MCP Server 也会拒绝
ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".py", ".docx"}

# 敏感文件黑名单
# 即使这些文件位于 workspace 中，也不允许访问
DENIED_NAMES = {".env", ".git", ".ssh"}

# 最大读入限制
# 最大允许读取 10MB。防止 Agent 一次把超大文件整个读入上下文，导致内存或 Token 爆炸
MAX_READ_SIZE = 10 * 1024 * 1024

# 最大写入限制
# 最大允许写入 200 万个字符。也是为了防止模型意外生成极大内容，或出现异常循环时不断写入
MAX_WRITE_CHARS = 200_0000


# ======================================================================================================================
# 安全措施
# ======================================================================================================================
def _resolve_safe_path(path: str) -> Path:
    """
    将 Agent 给出的路径转换为绝对路径，并确保最终路径仍然位于 workspace 内。
    Args:
        path: 相对路径 / 绝对路径
    Returns:
        Path: 绝对路径

    """
    if "\x00" in path:
        raise ValueError("path 不能包含空字符。")

    # 转为绝对路径
    target = Path(os.path.join(WORKSPACE_DIR, path)).resolve(strict=False)
    workspace = Path(WORKSPACE_DIR).resolve(strict=False)
    # 检查目标路径是否在工作区域内，如果 target 不在 WORKSPACE_DIR 里面，会抛出 ValueError 异常
    if not target.is_relative_to(workspace):
        raise PermissionError("禁止访问 workspace 之外的路径。")

    # 转为相对路径
    relative = target.relative_to(workspace)
    # 检查文件名是不是敏感文件。target.name 返回路径最后的文件名
    for part in relative.parts:
        if part.lower() in DENIED_NAMES:
            raise PermissionError(f"禁止访问敏感文件: {part}。")

    return target


def _validate_extension(path: Path):
    """
    检查文件后缀是否在白名单中。
    """
    # 取文件后缀
    suffix = path.suffix.lower()
    # 如果不在允许的文件类型里，就拒绝
    if suffix not in ALLOWED_EXTENSIONS:
        raise PermissionError(f"不允许处理此文件类型: {suffix}。")


# 修改前自动备份
def _backup_file(path: Path):
    """
    如果目标文件已经存在，就复制一份到备份目录。
    """
    # 如果文件不存在，不用备份
    if not path.exists():
        return

    # 获取当前时间，格式例如：20261008_154500
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 备份文件名
    backup_name = f"{path.stem}_{timestamp}{path.suffix}"
    # 复制文件，并尽量保留原文件的时间等元数据
    shutil.copy2(path, os.path.join(BACKUP_DIR, backup_name))


# ======================================================================================================================
# MCP Tools
# ======================================================================================================================
@mcp.tool()  # 将 python 函数注册成 MCP 工具
def list_files(path: str) -> dict:
    """
    列出 workspace 中指定目录下的文件和文件夹。
    Args:
        path: 相对于 workspace 的文件路径，不允许越界到 workspace 外。
    Returns:
        成功：{"success": True, "items": list[str]}
            每项格式为 "[DIR] 名称" 或 "[FILE] 名称"。
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - 只列一层，不递归子目录。
    - 结果顺序不保证稳定（取决于文件系统），如需排序请自行处理。
    - 会包含隐藏文件和隐藏目录。
    - 路径不存在返回 FileNotFoundError；目标不是目录返回 NotADirectoryError。
    """
    try:
        # 路径检查
        target = _resolve_safe_path(path)
        # 路径是否存在
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"目录不存在。"
            }
        # 是否是目录
        if not target.is_dir():
            return {
                "success": False,
                "error_type": "NotADirectoryError",
                "error": f"目标不是目录。"
            }
        result = []
        # 遍历目录
        for item in target.iterdir():
            kind = "DIR" if item.is_dir() else "FILE"
            result.append(
                f"[{kind}] {item.name}"
            )
        # 返回结果
        return {
            "success": True,
            "items": result
        }
    except PermissionError as e:
        return {
            "success": False,
            "error_type": "PermissionError",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def read_file(path: str) -> dict:
    """
    读取 workspace 中的文件。
    支持的文件类型：".txt", ".md", ".json", ".py", ".docx"。
    Args:
        path: 相对于 workspace 的文件路径，不允许越界到 workspace 外。
    Returns:
        成功：{"success": True, "content": str}
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - .docx 只读取正文段落，不包含表格、页眉页脚、文本框、脚注、图片。
    - .docx 返回的 content 中每段格式为 "[ParagraphN] 文本"，N 从 1 开始。
      该 N 可直接作为 delete_paragraph / replace_paragraph / append_text_to_paragraph 的 paragraph_index 使用。
    - 空段落也会被编号，显示为 "[ParagraphN] "（N 后无文本），且计入编号。
    - 普通文本文件按 UTF-8 原样读取，不做解析。
    - 非 UTF-8 编码可能触发 UnicodeDecodeError。
    - 文件超过 MAX_READ_SIZE 返回 FileTooLargeError。
    - 路径不存在返回 FileNotFoundError；目标不是文件返回 NotAFileError；扩展名不在白名单返回 PermissionError。
    """
    try:
        # 路径检查
        target = _resolve_safe_path(path)
        # 文件是否存在
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在。"
            }
        # 是否是文件
        if not target.is_file():
            return {
                "success": False,
                "error_type": "NotAFileError",
                "error": f"目标不是文件。"
            }
        # 检查文件类型
        try:
            _validate_extension(target)
        except PermissionError as e:
            return {
                "success": False,
                "error_type": "PermissionError",
                "error": str(e)
            }
        # 检查文件大小
        if target.stat().st_size > MAX_READ_SIZE:
            return {
                "success": False,
                "error_type": "FileTooLargeError",
                "error": f"文件过大，拒绝读取。"
            }

        # 读取文件
        if target.suffix.lower() == ".docx":
            # Word 文件
            doc = Document(str(target))
            paragraphs = []
            # 遍历 Word 中正文里的所有段落
            for index, paragraph in enumerate(doc.paragraphs, start=1):
                paragraphs.append(f"[Paragraph{index}] {paragraph.text}")
            content = "\n\n".join(paragraphs)
        else:
            # 普通文本文件
            content = target.read_text(encoding="utf-8")
        return {
            "success": True,
            "content": content
        }
    except PermissionError as e:
        return {
            "success": False,
            "error_type": "PermissionError",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def write_file(path: str, content: str, overwrite: bool = False) -> dict:
    """
    向文件写入内容，若不存在则创建。
    支持的文件类型：".txt", ".md", ".json", ".py", ".docx"。
    默认禁止覆盖已有文件，如果文件已存在，需要明确设置 overwrite=True。
    Args：
        path: 相对于 workspace 的文件路径，不允许越界到 workspace 外。
        content: 要写入的内容。
        overwrite: 是否允许覆盖已有文件，默认 False。文件已存在且 overwrite=False 时返回 FileExistsError，不会写入。
    Returns：
        成功：{"success": True, "overwritten": bool}
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - .docx 写入规则：content 按 splitlines() 拆行，每行生成一个段落，空行会生成空段落。不是“写入一整段连续文字”。
    - 普通文本文件按 UTF-8 原样写入，不做 JSON / CSV 校验。
    - 父目录不存在会自动创建。
    - 目标路径已存在且不是文件返回 NotAFileError；扩展名不在白名单返回 PermissionError。
    """
    try:
        # 检查写入内容大小
        if len(content) > MAX_WRITE_CHARS:
            return {
                "success": False,
                "error_type": "ContentTooLargeError",
                "error": f"写入内容过大，最大允许 {MAX_WRITE_CHARS} 个字符。"
            }
        # 路径检查
        target = _resolve_safe_path(path)
        # 检查文件类型
        try:
            _validate_extension(target)
        except PermissionError as e:
            return {
                "success": False,
                "error_type": "PermissionError",
                "error": str(e)
            }
        # 是否是文件
        if target.exists() and not target.is_file():
            return {
                "success": False,
                "error_type": "NotAFileError",
                "error": f"目标不是文件。"
            }
        # 如果文件已经存在，但没有明确允许覆盖
        if target.exists() and not overwrite:
            return {
                "success": False,
                "error_type": "FileExistsError",
                "error": f"文件已存在，如需覆盖，请设置 overwrite=True。"
            }
        # 保证父目录存在
        target.parent.mkdir(parents=True, exist_ok=True)
        # 如果要覆盖已有文件，则先备份
        if target.exists():
            _backup_file(target)
        # 写入文件
        if target.suffix.lower() == ".docx":
            doc = Document()
            for paragraph in content.splitlines():
                doc.add_paragraph(paragraph)
            doc.save(str(target))
        # 写普通文本文件
        else:
            target.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "overwritten": overwrite
        }
    except PermissionError as e:
        return {
            "success": False,
            "error_type": "PermissionError",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def append_paragraph(path: str, content: str) -> dict:
    """
    在 .docx 文档末尾追加一个新段落。
    Args：
        path: 相对于 workspace 的 .docx 文件路径，不允许越界到 workspace 外。
        content: 新段落的文本内容，整段作为单个段落写入（不会按换行拆段）。
    Returns：
        成功：{"success": True, "path": str, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - 只支持 .docx，其他扩展名返回 UnsupportedFileType。
    - 本工具会在文档末尾“新建段落”。如果要在已有段落末尾追加文字、不新建段落，请用 append_text_to_paragraph。
    - 路径不存在返回 FileNotFoundError。
    """
    try:
        target = _resolve_safe_path(path)
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在。"
            }
        if target.suffix.lower() != ".docx":
            return {
                "success": False,
                "error_type": "UnsupportedFileType",
                "error": "append_paragraph 只支持 .docx 文件。"
            }
        # 备份
        _backup_file(target)
        # 读取
        doc = Document(str(target))
        # 追加
        doc.add_paragraph(content)
        # 保存
        doc.save(str(target))
        return {
            "success": True,
            "path": path,
            "message": "段落追加成功。"
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def delete_paragraph(path: str, paragraph_index: int) -> dict:
    """
    删除 .docx 文档中的指定段落。
    paragraph_index 从 1 开始。
    Args：
        path: 相对于 workspace 的 .docx 文件路径。
        paragraph_index: 段落编号，从 1 开始，对应 read_file 返回的 "[ParagraphN]" 中的 N。
        编号基于 doc.paragraphs 的物理顺序，包含空段落，不包含表格、页眉页脚、文本框内的段落。超出范围返回 ParagraphIndexError。
    Returns：
        成功：{"success": True, "path": str, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    建议流程：
    1. 先调用 read_file 读取文档，拿到目标段落的 [ParagraphN]；
    2. 再调用本工具，paragraph_index=N。
    注意：
    - 只支持 .docx，其他扩展名返回 UnsupportedFileType。
    - 删除会连同该段落的文字、run、样式一起移除。
    - 路径不存在返回 FileNotFoundError。
    """
    try:
        target = _resolve_safe_path(path)
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在: {path}。"
            }
        if target.suffix.lower() != ".docx":
            return {
                "success": False,
                "error_type": "UnsupportedFileType",
                "error": "delete_paragraph 只支持 .docx 文件。"
            }
        # 备份
        _backup_file(target)
        # 读取
        doc = Document(str(target))
        paragraphs = doc.paragraphs
        if paragraph_index < 1 or paragraph_index > len(paragraphs):
            return {
                "success": False,
                "error_type": "ParagraphIndexError",
                "error": f"段落编号超出范围，当前共有 {len(paragraphs)} 个段落。"
            }
        # 选中段落
        paragraph = paragraphs[paragraph_index - 1]
        # 删除段落
        p = paragraph._element
        p.getparent().remove(p)
        # 保存
        doc.save(str(target))
        return {
            "success": True,
            "path": path,
            "message": f"已删除 Paragraph{paragraph_index}。"
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def replace_paragraph(path: str, paragraph_index: int, new_text: str) -> dict:
    """
    替换 .docx 文档中指定段落的全部文本。
    paragraph_index 从 1 开始。
    Args：
        path: 相对于 workspace 的 .docx 文件路径。
        paragraph_index: 段落编号，从 1 开始，对应 read_file 返回的 "[ParagraphN]" 中的 N。
        编号基于 doc.paragraphs 的物理顺序，包含空段落，不包含表格、页眉页脚、文本框内的段落。超出范围返回 ParagraphIndexError。
        new_text: 替换后的段落文本。
    Returns：
        成功：{"success": True, "path": str, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    建议流程：
    1. 先调用 read_file 读取文档，确认目标段落的 [ParagraphN] 和原内容；
    2. 再调用本工具，paragraph_index=N。
    注意：
    - 只支持 .docx，其他扩展名返回 UnsupportedFileType。
    - 本操作会清除该段落原有字符格式（加粗、斜体、字号、颜色、超链接等），仅保留纯文本。属于破坏性修改。
    - 路径不存在返回 FileNotFoundError。
    """
    try:
        target = _resolve_safe_path(path)
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在: {path}。"
            }
        if target.suffix.lower() != ".docx":
            return {
                "success": False,
                "error_type": "UnsupportedFileType",
                "error": "replace_paragraph 只支持 .docx 文件。"
            }
        # 备份
        _backup_file(target)
        # 读取
        doc = Document(str(target))
        paragraphs = doc.paragraphs
        if paragraph_index < 1 or paragraph_index > len(paragraphs):
            return {
                "success": False,
                "error_type": "ParagraphIndexError",
                "error": f"段落编号超出范围，当前共有 {len(paragraphs)} 个段落。"
            }
        # 修改段落内容
        paragraphs[paragraph_index - 1].text = new_text
        # 保存
        doc.save(str(target))
        return {
            "success": True,
            "path": path,
            "message": f"Paragraph{paragraph_index} 替换成功。"
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def append_text_to_paragraph(path: str, paragraph_index: int, content: str) -> dict:
    """
    在 .docx 文档中指定段落末尾追加文字。
    paragraph_index 从 1 开始。
    Args：
        path: 相对于 workspace 的 .docx 文件路径。
        paragraph_index: 段落编号，从 1 开始，对应 read_file 返回的 "[ParagraphN]" 中的 N。
        编号基于 doc.paragraphs 的物理顺序，包含空段落，不包含表格、页眉页脚、文本框内的段落。超出范围返回 ParagraphIndexError。
        content: 要追加的文字。
    Returns：
        成功：{"success": True, "path": str, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    与 append_paragraph 的区别：
    - append_paragraph：在文档末尾“新建一个段落”；
    - 本工具：在“已有段落末尾”追加一个 run，不产生新段落。
    注意：
    - 只支持 .docx，其他扩展名返回 UnsupportedFileType。
    - 追加内容不会自动添加空格或换行；如需分隔，请在 content 中自行包含空格或换行。
    - 路径不存在返回 FileNotFoundError。
    """
    try:
        target = _resolve_safe_path(path)
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在: {path}。"
            }
        if target.suffix.lower() != ".docx":
            return {
                "success": False,
                "error_type": "UnsupportedFileType",
                "error": "该工具只支持 .docx 文件。"
            }
        _backup_file(target)
        doc = Document(str(target))
        paragraphs = doc.paragraphs
        if paragraph_index < 1 or paragraph_index > len(paragraphs):
            return {
                "success": False,
                "error_type": "ParagraphIndexError",
                "error": f"段落编号超出范围，当前共有 {len(paragraphs)} 个段落"
            }
        paragraph = paragraphs[paragraph_index - 1]
        paragraph.add_run(content)
        doc.save(str(target))
        return {
            "success": True,
            "path": path,
            "message": f"已向 Paragraph{paragraph_index} 追加内容。"
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def delete_file(path: str) -> dict:
    """
    删除 workspace 中的指定文件（不删除目录）。
    Args：
        path: 相对于 workspace 的文件路径，不允许越界到 workspace 外。
    Returns：
        成功：{"success": True, "path": str, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - 只删除文件；目标为目录时返回 NotAFileError，不会递归删除目录。
    - 路径不存在返回 FileNotFoundError。
    - 扩展名不在白名单返回 PermissionError。
    - 本操作不可撤销（除备份外），调用前请确认路径正确。
    """
    try:
        # 路径检查
        target = _resolve_safe_path(path)
        # 文件是否存在
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"文件不存在: {path}。"
            }
        # 是否是文件（不允许删目录）
        if not target.is_file():
            return {
                "success": False,
                "error_type": "NotAFileError",
                "error": "目标不是文件，delete_file 只删除文件。"
            }
        # 检查文件类型
        try:
            _validate_extension(target)
        except PermissionError as e:
            return {
                "success": False,
                "error_type": "PermissionError",
                "error": str(e)
            }
        # 删除前备份
        _backup_file(target)
        # 执行删除
        target.unlink()
        return {
            "success": True,
            "path": path,
            "message": "文件删除成功。"
        }
    except PermissionError as e:
        return {
            "success": False,
            "error_type": "PermissionError",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


@mcp.tool()
def delete_dir(path: str) -> dict:
    """
    递归删除 workspace 中的目录及其全部内容。破坏性操作，不可恢复。
    Args：
        path: 相对于 workspace 的目录路径。
    Returns：
        成功：{"success": True, "path": str, "removed_files": int, "removed_dirs": int, "message": str}
        失败：{"success": False, "error_type": str, "error": str}
    注意：
    - 递归删除：目录下所有文件、子目录、子目录中的文件都会被删除。
    - 不允许删除 workspace 根目录本身，会返回 PermissionError。
    - 目标是符号链接时拒绝删除，返回 SymbolicLinkError，避免误删链接指向的外部目录。
    - 路径不存在返回 FileNotFoundError；目标不是目录返回 NotADirectoryError。
    - 调用前请先 list_files 确认目录内容，避免误删。
    """
    try:
        target = _resolve_safe_path(path)
        # 路径是否存在
        if not target.exists():
            return {
                "success": False,
                "error_type": "FileNotFoundError",
                "error": f"目录不存在: {path}。"
            }
        # 是否是目录
        if not target.is_dir():
            return {
                "success": False,
                "error_type": "NotADirectoryError",
                "error": "目标不是目录。"
            }
        # 拒绝删除 workspace 根目录
        if target.resolve() == Path(WORKSPACE_DIR).resolve():
            return {
                "success": False,
                "error_type": "PermissionError",
                "error": "禁止删除 workspace 根目录。"
            }
        # 拒绝删除符号链接目录，避免 rmtree 行为不直观
        if target.is_symlink():
            return {
                "success": False,
                "error_type": "SymbolicLinkError",
                "error": "目标是符号链接，拒绝递归删除。"
            }
        # 统计将删除的文件数和目录数（用于返回信息）
        removed_files = sum(1 for p in target.rglob("*") if p.is_file())
        removed_dirs = sum(1 for p in target.rglob("*") if p.is_dir())
        # 递归删除
        shutil.rmtree(target)
        return {
            "success": True,
            "path": path,
            "removed_files": removed_files,
            "removed_dirs": removed_dirs,
            "message": f"目录及其中 {removed_files} 个文件、{removed_dirs} 个子目录已删除。"
        }
    except PermissionError as e:
        return {
            "success": False,
            "error_type": "PermissionError",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": type(e).__name__,
            "error": str(e)
        }


# ======================================================================================================================
# 启动 MCP Server
# ======================================================================================================================
if __name__ == "__main__":
    # 只有直接运行这个文件时，才启动 MCP Server。
    # 如果这个文件只是被其他 Python 文件 import，不会自动启动服务器。
    mcp.run()
