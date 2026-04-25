"""
文档加载器

支持多种格式的健康知识文档导入：
- 纯文本 (.txt)
- Markdown (.md)
- JSON 格式的课程/文章
- 公众号文章 HTML
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentLoader:
    """
    文档加载器

    负责从各种格式加载和预处理健康知识文档
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        初始化文档加载器

        Args:
            chunk_size: 文档分块大小（字符数）
            chunk_overlap: 分块重叠大小
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def load_text_file(self, file_path: str, source: str = None) -> List[Dict[str, Any]]:
        """
        加载纯文本文件

        Args:
            file_path: 文件路径
            source: 来源标识（默认使用文件名）

        Returns:
            文档列表
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            source = source or os.path.basename(file_path)
            chunks = self._split_text(content)

            documents = []
            for i, chunk in enumerate(chunks):
                documents.append({
                    "content": chunk,
                    "title": f"{source} - Part {i+1}",
                    "category": "general",
                    "metadata": {
                        "file_path": file_path,
                        "chunk_index": i,
                        "total_chunks": len(chunks)
                    }
                })

            logger.info(f"从 {file_path} 加载了 {len(documents)} 个文档块")
            return documents

        except Exception as e:
            logger.error(f"加载文件失败 {file_path}: {e}")
            return []

    def load_markdown_file(self, file_path: str, source: str = None) -> List[Dict[str, Any]]:
        """
        加载 Markdown 文件，按标题分块

        Args:
            file_path: 文件路径
            source: 来源标识

        Returns:
            文档列表
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            source = source or os.path.basename(file_path)

            # 按标题分块
            sections = self._split_markdown_by_headers(content)

            documents = []
            for section in sections:
                # 如果章节太长，进一步分块
                if len(section["content"]) > self.chunk_size:
                    chunks = self._split_text(section["content"])
                    for i, chunk in enumerate(chunks):
                        documents.append({
                            "content": chunk,
                            "title": f"{section['title']} - Part {i+1}" if section['title'] else f"Section {len(documents)+1}",
                            "category": self._infer_category(section["title"], chunk),
                            "metadata": {
                                "file_path": file_path,
                                "header_level": section.get("level", 0),
                                "original_title": section["title"]
                            }
                        })
                else:
                    documents.append({
                        "content": section["content"],
                        "title": section["title"] or f"Section {len(documents)+1}",
                        "category": self._infer_category(section["title"], section["content"]),
                        "metadata": {
                            "file_path": file_path,
                            "header_level": section.get("level", 0)
                        }
                    })

            logger.info(f"从 {file_path} 加载了 {len(documents)} 个文档块")
            return documents

        except Exception as e:
            logger.error(f"加载 Markdown 文件失败 {file_path}: {e}")
            return []

    def load_json_articles(self, file_path: str, source: str = None) -> List[Dict[str, Any]]:
        """
        加载 JSON 格式的文章集合

        预期 JSON 格式:
        [
            {
                "title": "文章标题",
                "content": "文章内容",
                "category": "分类",
                "author": "作者",
                "date": "发布日期"
            },
            ...
        ]

        Args:
            file_path: JSON 文件路径
            source: 来源标识

        Returns:
            文档列表
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                articles = json.load(f)

            if not isinstance(articles, list):
                articles = [articles]

            source = source or os.path.basename(file_path)

            documents = []
            for article in articles:
                content = article.get("content", "")
                title = article.get("title", "")

                if not content.strip():
                    continue

                # 如果内容太长，分块处理
                if len(content) > self.chunk_size:
                    chunks = self._split_text(content)
                    for i, chunk in enumerate(chunks):
                        documents.append({
                            "content": chunk,
                            "title": f"{title} - Part {i+1}" if title else f"Article {len(documents)+1}",
                            "category": article.get("category", self._infer_category(title, chunk)),
                            "metadata": {
                                "author": article.get("author", ""),
                                "date": article.get("date", ""),
                                "original_title": title,
                                "chunk_index": i
                            }
                        })
                else:
                    documents.append({
                        "content": content,
                        "title": title or f"Article {len(documents)+1}",
                        "category": article.get("category", self._infer_category(title, content)),
                        "metadata": {
                            "author": article.get("author", ""),
                            "date": article.get("date", "")
                        }
                    })

            logger.info(f"从 {file_path} 加载了 {len(documents)} 个文档")
            return documents

        except Exception as e:
            logger.error(f"加载 JSON 文件失败 {file_path}: {e}")
            return []

    def load_directory(
        self,
        directory: str,
        source: str = None,
        recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        加载目录下的所有支持的文档

        Args:
            directory: 目录路径
            source: 来源标识
            recursive: 是否递归加载子目录

        Returns:
            文档列表
        """
        if not os.path.isdir(directory):
            logger.error(f"目录不存在: {directory}")
            return []

        source = source or os.path.basename(directory)
        all_documents = []

        for root, dirs, files in os.walk(directory):
            if not recursive and root != directory:
                break

            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()

                if file_ext == '.txt':
                    docs = self.load_text_file(file_path, source)
                elif file_ext == '.md':
                    docs = self.load_markdown_file(file_path, source)
                elif file_ext == '.json':
                    docs = self.load_json_articles(file_path, source)
                else:
                    continue

                all_documents.extend(docs)

        logger.info(f"从目录 {directory} 总共加载了 {len(all_documents)} 个文档")
        return all_documents

    def load_from_text(
        self,
        text: str,
        title: str = "",
        category: str = "general",
        source: str = "manual_input"
    ) -> List[Dict[str, Any]]:
        """
        从文本字符串加载文档

        Args:
            text: 文本内容
            title: 标题
            category: 分类
            source: 来源

        Returns:
            文档列表
        """
        if not text.strip():
            return []

        chunks = self._split_text(text)

        documents = []
        for i, chunk in enumerate(chunks):
            documents.append({
                "content": chunk,
                "title": f"{title} - Part {i+1}" if len(chunks) > 1 else title,
                "category": category or self._infer_category(title, chunk),
                "metadata": {
                    "source": source,
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            })

        return documents

    def _split_text(self, text: str) -> List[str]:
        """
        将长文本分割成小块

        使用重叠分块策略，保持上下文连贯性
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []

        # 优先按段落分割
        paragraphs = text.split('\n\n')
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # 如果单个段落超过 chunk_size，进一步分割
                if len(para) > self.chunk_size:
                    # 按句子分割
                    sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                    current_chunk = ""
                    for sent in sentences:
                        if len(current_chunk) + len(sent) + 1 <= self.chunk_size:
                            current_chunk += (" " if current_chunk else "") + sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sent
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        # 添加重叠
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = [chunks[0]]
            for i in range(1, len(chunks)):
                # 获取前一个 chunk 的末尾部分作为上下文
                prev_chunk = chunks[i-1]
                overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
                overlapped_chunks.append(overlap_text + "\n...\n" + chunks[i])
            chunks = overlapped_chunks

        return chunks

    def _split_markdown_by_headers(self, content: str) -> List[Dict[str, Any]]:
        """
        按 Markdown 标题分割文档
        """
        # 匹配标题行
        header_pattern = r'^(#{1,6})\s+(.+)$'
        lines = content.split('\n')

        sections = []
        current_section = {"title": "", "content": "", "level": 0}

        for line in lines:
            header_match = re.match(header_pattern, line)
            if header_match:
                # 保存当前节
                if current_section["content"].strip():
                    sections.append(current_section)

                # 开始新节
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_section = {"title": title, "content": "", "level": level}
            else:
                current_section["content"] += line + "\n"

        # 添加最后一节
        if current_section["content"].strip():
            sections.append(current_section)

        return sections

    def _infer_category(self, title: str, content: str) -> str:
        """
        根据标题和内容推断分类
        """
        text = (title + " " + content[:200]).lower()

        # 健康分类关键词映射
        category_keywords = {
            "sleep": ["睡眠", "入睡", "失眠", "熬夜", "sleep", "休息", "起床"],
            "exercise": ["运动", "健身", "跑步", "锻炼", "exercise", "训练", "体能", "有氧", "力量"],
            "nutrition": ["饮食", "营养", "食物", "吃", "nutrition", "维生素", "蛋白质", "碳水"],
            "mental_health": ["心理", "情绪", "压力", "焦虑", "抑郁", "冥想", "放松"],
            "chronic_disease": ["鼻炎", "咽炎", "糖尿病", "高血压", "慢性", "过敏"],
            "children_health": ["儿童", "孩子", "青少年", "近视", "发育", "免疫"],
            "heart_health": ["心脏", "心率", "心血管", "血压", "heart"],
            "weight_management": ["减肥", "体重", "减脂", "增肌", "BMI", "body"]
        }

        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return category

        return "general"


# 单例实例
document_loader = DocumentLoader()
