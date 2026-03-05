"""文件内容提取服务 - 从上传的文件中提取文本"""
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 8000  # 最大提取字符数，避免上下文过长


def extract_text_from_base64(file_base64: str, file_name: str) -> str:
    """从 base64 编码的文件中提取文本内容

    支持: .txt, .md, .csv, .json, .py, .js, .html, .xml, .log, .pdf
    """
    try:
        file_bytes = base64.b64decode(file_base64)
        suffix = Path(file_name).suffix.lower()

        if suffix == ".pdf":
            return _extract_pdf(file_bytes)
        elif suffix in (".txt", ".md", ".csv", ".json", ".py", ".js", ".ts",
                         ".html", ".xml", ".log", ".yaml", ".yml", ".toml",
                         ".ini", ".cfg", ".conf", ".sh", ".sql", ".java",
                         ".go", ".rs", ".cpp", ".c", ".h", ".css", ".jsx",
                         ".tsx", ".vue", ".svelte"):
            text = file_bytes.decode("utf-8", errors="replace")
            if len(text) > MAX_TEXT_LENGTH:
                text = text[:MAX_TEXT_LENGTH] + f"\n...(文件内容已截断，共 {len(file_bytes)} 字节)"
            return text
        else:
            logger.info(f"不支持的文件类型: {suffix}, 文件名: {file_name}")
            return ""
    except Exception as e:
        logger.warning(f"文件内容提取失败 ({file_name}): {e}")
        return ""


def _extract_pdf(file_bytes: bytes) -> str:
    """从 PDF 中提取文本"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        texts = []
        total_len = 0
        for page in doc:
            page_text = page.get_text()
            if total_len + len(page_text) > MAX_TEXT_LENGTH:
                remaining = MAX_TEXT_LENGTH - total_len
                if remaining > 0:
                    texts.append(page_text[:remaining])
                texts.append(f"\n...(PDF 内容已截断，共 {len(doc)} 页)")
                break
            texts.append(page_text)
            total_len += len(page_text)
        doc.close()
        return "\n".join(texts)
    except ImportError:
        logger.warning("PyMuPDF 未安装，无法提取 PDF 内容。请安装: pip install PyMuPDF")
        return "[无法提取 PDF 内容，请安装 PyMuPDF]"
    except Exception as e:
        logger.warning(f"PDF 提取失败: {e}")
        return ""
