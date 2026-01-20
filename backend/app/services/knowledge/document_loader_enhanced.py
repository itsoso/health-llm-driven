"""
增强版文档加载器

专门优化运动科学课程（如张展晖课程）的处理：
1. 保留 Markdown 标题层级和面包屑上下文
2. 更大的 chunk_size（1500-2000）适配完整知识点
3. 丰富的元数据（作者、难度、目标人群、关键概念）
4. 智能识别课程结构（章节、小节、知识点）
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class EnhancedDocumentLoader:
    """
    增强版文档加载器
    
    专为运动科学课程优化，支持：
    - 标题层级保留和面包屑导航
    - 更大的分块大小
    - 丰富的元数据
    - 智能课程结构识别
    """
    
    def __init__(
        self, 
        chunk_size: int = 1800,  # 增大到 1800，适配完整知识点
        chunk_overlap: int = 300,  # 相应增大重叠
        preserve_hierarchy: bool = True  # 保留层级结构
    ):
        """
        初始化增强版文档加载器
        
        Args:
            chunk_size: 文档分块大小（字符数），默认 1800
            chunk_overlap: 分块重叠大小，默认 300
            preserve_hierarchy: 是否保留标题层级结构
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.preserve_hierarchy = preserve_hierarchy
    
    def load_course_markdown(
        self,
        file_path: str = None,
        content: str = None,
        source: str = None,
        author: str = None,
        difficulty: str = "intermediate",  # beginner/intermediate/advanced
        target_audience: List[str] = None,
        course_metadata: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        加载课程 Markdown 文件，专为运动科学课程优化
        
        Args:
            file_path: 文件路径（与 content 二选一）
            content: 文本内容（与 file_path 二选一）
            source: 来源标识（如 "zhang_zhanhui"）
            author: 作者名称
            difficulty: 难度级别
            target_audience: 目标人群列表（如 ["初学者", "跑步爱好者"]）
            course_metadata: 额外的课程元数据
            
        Returns:
            文档列表，每个文档包含丰富的元数据
        """
        # 读取内容
        if file_path:
            if not os.path.exists(file_path):
                logger.error(f"文件不存在: {file_path}")
                return []
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                source = source or os.path.basename(file_path).replace('.md', '')
            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {e}")
                return []
        
        if not content or not content.strip():
            logger.error("内容为空")
            return []
        
        # 解析 Markdown 结构
        sections = self._parse_markdown_hierarchy(content)
        
        if not sections:
            logger.warning("未找到 Markdown 标题结构，使用普通分块")
            return self._fallback_chunking(content, source, author, difficulty, target_audience)
        
        # 构建文档列表
        documents = []
        
        for section in sections:
            # 构建面包屑路径
            breadcrumb = " > ".join(section["breadcrumb"])
            
            # 准备内容（包含标题和内容）
            full_content = f"# {section['title']}\n\n{section['content']}"
            
            # 如果内容太长，需要分块
            if len(full_content) > self.chunk_size:
                chunks = self._split_text_smart(full_content, section["title"])
                
                for i, chunk in enumerate(chunks):
                    doc = self._create_document(
                        content=chunk,
                        title=f"{section['title']} (Part {i+1}/{len(chunks)})",
                        breadcrumb=breadcrumb,
                        section_info=section,
                        source=source,
                        author=author,
                        difficulty=difficulty,
                        target_audience=target_audience,
                        chunk_index=i,
                        total_chunks=len(chunks),
                        course_metadata=course_metadata
                    )
                    documents.append(doc)
            else:
                doc = self._create_document(
                    content=full_content,
                    title=section['title'],
                    breadcrumb=breadcrumb,
                    section_info=section,
                    source=source,
                    author=author,
                    difficulty=difficulty,
                    target_audience=target_audience,
                    course_metadata=course_metadata
                )
                documents.append(doc)
        
        logger.info(f"从课程内容加载了 {len(documents)} 个文档块")
        return documents
    
    def _parse_markdown_hierarchy(self, content: str) -> List[Dict[str, Any]]:
        """
        解析 Markdown 层级结构，保留标题层级关系
        
        Returns:
            [
                {
                    "title": "心率区间训练法",
                    "level": 1,
                    "content": "...",
                    "breadcrumb": ["心率区间训练法"],
                    "parent_titles": [],
                    "key_concepts": ["心率", "训练", "区间"]
                },
                {
                    "title": "五区心率训练法",
                    "level": 2,
                    "content": "...",
                    "breadcrumb": ["心率区间训练法", "五区心率训练法"],
                    "parent_titles": ["心率区间训练法"],
                    "key_concepts": ["Zone 1", "Zone 2", "有氧"]
                }
            ]
        """
        lines = content.split('\n')
        sections = []
        
        # 标题栈，用于追踪层级
        title_stack = []  # [(level, title), ...]
        
        current_section = None
        current_content_lines = []
        
        header_pattern = r'^(#{1,6})\s+(.+)$'
        
        for line in lines:
            header_match = re.match(header_pattern, line)
            
            if header_match:
                # 保存上一个节
                if current_section and current_content_lines:
                    current_section["content"] = '\n'.join(current_content_lines).strip()
                    if current_section["content"]:
                        sections.append(current_section)
                
                # 解析新标题
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                
                # 更新标题栈
                # 移除所有大于等于当前级别的标题
                title_stack = [(l, t) for l, t in title_stack if l < level]
                title_stack.append((level, title))
                
                # 构建面包屑
                breadcrumb = [t for _, t in title_stack]
                parent_titles = breadcrumb[:-1]
                
                # 提取关键概念
                key_concepts = self._extract_key_concepts(title)
                
                # 创建新节
                current_section = {
                    "title": title,
                    "level": level,
                    "breadcrumb": breadcrumb,
                    "parent_titles": parent_titles,
                    "key_concepts": key_concepts,
                    "content": ""
                }
                current_content_lines = []
            else:
                # 累积内容
                current_content_lines.append(line)
        
        # 保存最后一节
        if current_section and current_content_lines:
            current_section["content"] = '\n'.join(current_content_lines).strip()
            if current_section["content"]:
                sections.append(current_section)
        
        return sections
    
    def _extract_key_concepts(self, title: str) -> List[str]:
        """
        从标题中提取关键概念
        
        例如："五区心率训练法" -> ["心率", "训练", "五区"]
        """
        # 常见的运动科学关键词
        keywords = [
            "心率", "Zone", "区间", "训练", "有氧", "无氧", "乳酸", "阈值",
            "恢复", "燃脂", "耐力", "速度", "力量", "VO2Max", "最大摄氧量",
            "静息心率", "储备心率", "Karvonen", "配速", "跑步", "运动",
            "减脂", "增肌", "体能", "营养", "补给", "拉伸", "热身",
            "HIIT", "间歇", "节奏跑", "LSD", "长距离", "马拉松"
        ]
        
        concepts = []
        title_lower = title.lower()
        
        for keyword in keywords:
            if keyword.lower() in title_lower or keyword in title:
                concepts.append(keyword)
        
        # 提取数字（如 Zone 2, 80%, 10公里）
        numbers = re.findall(r'\d+', title)
        concepts.extend(numbers[:3])  # 最多保留3个数字
        
        return concepts[:5]  # 最多返回5个关键概念
    
    def _create_document(
        self,
        content: str,
        title: str,
        breadcrumb: str,
        section_info: Dict[str, Any],
        source: str,
        author: str = None,
        difficulty: str = "intermediate",
        target_audience: List[str] = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
        course_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        创建文档对象，包含丰富的元数据
        """
        # 推断分类
        category = self._infer_category_enhanced(title, content, section_info.get("key_concepts", []))
        
        # 构建元数据（ChromaDB 只支持 str, int, float, bool, None）
        metadata = {
            "source": source,
            "author": author,
            "difficulty": difficulty,
            "target_audience": ", ".join(target_audience) if target_audience else "",
            "breadcrumb": breadcrumb,
            "section_level": section_info.get("level", 0),
            "parent_titles": " > ".join(section_info.get("parent_titles", [])),
            "key_concepts": ", ".join(section_info.get("key_concepts", [])),
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "created_at": datetime.now().isoformat()
        }
        
        # 合并额外的课程元数据
        if course_metadata:
            metadata.update(course_metadata)
        
        return {
            "content": content,
            "title": title,
            "category": category,
            "metadata": metadata
        }
    
    def _split_text_smart(self, text: str, section_title: str = "") -> List[str]:
        """
        智能分块，保持知识点完整性
        
        优先级：
        1. 按小标题分割（###, ####）
        2. 按段落分割
        3. 按句子分割
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        
        # 尝试按小标题分割
        sub_header_pattern = r'\n(#{3,6}\s+.+)\n'
        parts = re.split(sub_header_pattern, text)
        
        if len(parts) > 1:
            # 有小标题，按小标题分块
            current_chunk = parts[0]  # 第一部分（标题之前的内容）
            
            for i in range(1, len(parts), 2):
                if i + 1 < len(parts):
                    sub_header = parts[i]
                    sub_content = parts[i + 1]
                    section = f"\n{sub_header}\n{sub_content}"
                    
                    if len(current_chunk) + len(section) <= self.chunk_size:
                        current_chunk += section
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = section
            
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
        else:
            # 没有小标题，按段落分割
            chunks = self._split_by_paragraphs(text)
        
        # 添加重叠
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks)
        
        return chunks
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割文本"""
        paragraphs = text.split('\n\n')
        chunks = []
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
                
                # 如果单个段落太长，按句子分割
                if len(para) > self.chunk_size:
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
        
        return chunks
    
    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """添加重叠上下文"""
        overlapped_chunks = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            
            # 获取前一个 chunk 的末尾部分
            overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
            
            # 尝试在句子边界截断
            sentences = re.split(r'([。！？.!?]\s*)', overlap_text)
            if len(sentences) > 2:
                # 保留最后几个完整句子
                overlap_text = ''.join(sentences[-4:])
            
            overlapped_chunks.append(f"{overlap_text}\n\n[...接上文...]\n\n{chunks[i]}")
        
        return overlapped_chunks
    
    def _infer_category_enhanced(
        self,
        title: str,
        content: str,
        key_concepts: List[str]
    ) -> str:
        """
        增强版分类推断，结合标题、内容和关键概念
        """
        text = (title + " " + " ".join(key_concepts) + " " + content[:300]).lower()
        
        # 运动科学课程专用分类
        category_keywords = {
            "cardio_training": ["心率", "有氧", "心肺", "耐力", "zone", "区间", "跑步", "配速"],
            "strength_training": ["力量", "肌肉", "增肌", "重量", "训练", "深蹲", "卧推"],
            "exercise_physiology": ["生理", "代谢", "乳酸", "vo2max", "最大摄氧量", "阈值"],
            "nutrition": ["营养", "饮食", "蛋白质", "碳水", "脂肪", "补给", "能量"],
            "recovery": ["恢复", "休息", "睡眠", "拉伸", "按摩", "疲劳"],
            "weight_management": ["减脂", "减肥", "体重", "体脂", "增重", "塑形"],
            "goal_setting": ["目标", "计划", "训练计划", "周期", "进阶"],
            "injury_prevention": ["损伤", "预防", "康复", "疼痛", "关节", "保护"],
            "performance": ["表现", "成绩", "提升", "突破", "比赛", "竞技"]
        }
        
        for category, keywords in category_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score >= 2:  # 至少匹配2个关键词
                return category
        
        return "exercise_science"  # 默认分类
    
    def _fallback_chunking(
        self,
        content: str,
        source: str,
        author: str = None,
        difficulty: str = "intermediate",
        target_audience: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        当无法解析 Markdown 结构时的后备分块方案
        """
        chunks = self._split_by_paragraphs(content)
        
        documents = []
        for i, chunk in enumerate(chunks):
            doc = {
                "content": chunk,
                "title": f"{source} - Part {i+1}/{len(chunks)}",
                "category": "exercise_science",
                "metadata": {
                    "source": source,
                    "author": author,
                    "difficulty": difficulty,
                    "target_audience": ", ".join(target_audience) if target_audience else "",
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "fallback_mode": True,
                    "created_at": datetime.now().isoformat()
                }
            }
            documents.append(doc)
        
        return documents


# 创建实例（可配置不同的参数）
enhanced_loader = EnhancedDocumentLoader(
    chunk_size=1800,
    chunk_overlap=300,
    preserve_hierarchy=True
)

# 为张展晖课程创建专用加载器
zhang_zhanhui_loader = EnhancedDocumentLoader(
    chunk_size=2000,  # 更大的分块，适配完整的训练方法讲解
    chunk_overlap=400,
    preserve_hierarchy=True
)
