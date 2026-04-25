"""
测试增强版文档加载器

验证：
1. Markdown 层级解析
2. 面包屑生成
3. 关键概念提取
4. 智能分块
5. 元数据完整性
"""

import pytest
from app.services.knowledge.document_loader_enhanced import EnhancedDocumentLoader


# 测试用的 Markdown 内容
SAMPLE_COURSE_CONTENT = """# 心率区间训练法

> 科学的心率训练是提高运动效果、避免过度训练的关键

## 一、心率训练基础

### 1.1 为什么要监测心率

1. **客观反映运动强度**
   - 配速会受天气、坡度、状态影响
   - 心率是身体真实负荷的反映

2. **避免过度训练**
   - 高心率持续时间过长会导致疲劳累积
   - 科学分配训练强度

### 1.2 最大心率计算

**常用公式：**
```
最大心率 = 220 - 年龄
```

**更精确公式（Tanaka）：**
```
最大心率 = 208 - 0.7 × 年龄
```

## 二、五区心率训练法

### 2.1 心率区间划分

| 区间 | 强度 | 最大心率% | 特点 | 训练效果 |
|------|------|----------|------|---------|
| Zone 1 | 恢复区 | 50-60% | 很轻松 | 主动恢复 |
| Zone 2 | 有氧区 | 60-70% | 可聊天 | 燃脂、建立有氧基础 |
| Zone 3 | 有氧耐力区 | 70-80% | 说话断续 | 提高有氧耐力 |

### 2.2 Zone 2 - 有氧基础区（60-70%）⭐重点

- **感觉**：轻松，可以正常聊天
- **用途**：建立有氧基础，燃烧脂肪
- **时长**：30-120分钟
- **比例**：应占总训练量的80%
- **效果**：
  - 提高脂肪供能效率
  - 增加毛细血管密度
  - 改善心脏效率
"""


class TestEnhancedDocumentLoader:
    """测试增强版文档加载器"""

    def test_initialization(self):
        """测试初始化"""
        loader = EnhancedDocumentLoader(
            chunk_size=1800,
            chunk_overlap=300,
            preserve_hierarchy=True
        )

        assert loader.chunk_size == 1800
        assert loader.chunk_overlap == 300
        assert loader.preserve_hierarchy is True

    def test_parse_markdown_hierarchy(self):
        """测试 Markdown 层级解析"""
        loader = EnhancedDocumentLoader()
        sections = loader._parse_markdown_hierarchy(SAMPLE_COURSE_CONTENT)

        # 应该解析出多个节
        assert len(sections) > 0

        # 检查第一节
        first_section = sections[0]
        assert "title" in first_section
        assert "level" in first_section
        assert "breadcrumb" in first_section
        assert "content" in first_section

        # 检查面包屑
        # 应该有类似 ["心率区间训练法", "一、心率训练基础", "1.1 为什么要监测心率"] 的结构
        zone2_sections = [s for s in sections if "Zone 2" in s["title"]]
        if zone2_sections:
            section = zone2_sections[0]
            assert len(section["breadcrumb"]) >= 2
            assert "心率区间训练法" in section["breadcrumb"]

    def test_extract_key_concepts(self):
        """测试关键概念提取"""
        loader = EnhancedDocumentLoader()

        # 测试不同标题
        concepts1 = loader._extract_key_concepts("五区心率训练法")
        assert "心率" in concepts1 or "训练" in concepts1

        concepts2 = loader._extract_key_concepts("Zone 2 - 有氧基础区（60-70%）")
        assert "Zone" in concepts2 or "有氧" in concepts2

        # 应该提取数字
        assert any(c.isdigit() for c in concepts2)

    def test_load_course_markdown(self):
        """测试加载课程 Markdown"""
        loader = EnhancedDocumentLoader(chunk_size=1000)

        documents = loader.load_course_markdown(
            content=SAMPLE_COURSE_CONTENT,
            source="test_course",
            author="张展晖",
            difficulty="intermediate",
            target_audience=["跑步爱好者", "运动爱好者"]
        )

        # 应该生成多个文档
        assert len(documents) > 0

        # 检查文档结构
        doc = documents[0]
        assert "content" in doc
        assert "title" in doc
        assert "category" in doc
        assert "metadata" in doc

        # 检查元数据
        metadata = doc["metadata"]
        assert metadata["source"] == "test_course"
        assert metadata["author"] == "张展晖"
        assert metadata["difficulty"] == "intermediate"
        assert "跑步爱好者" in metadata["target_audience"]
        assert "breadcrumb" in metadata
        assert "key_concepts" in metadata

    def test_category_inference(self):
        """测试分类推断"""
        loader = EnhancedDocumentLoader()

        # 心肺训练相关
        category1 = loader._infer_category_enhanced(
            "心率区间训练法",
            "Zone 2 有氧训练 心率 跑步",
            ["心率", "Zone 2", "有氧"]
        )
        assert category1 == "cardio_training"

        # 力量训练相关
        category2 = loader._infer_category_enhanced(
            "力量训练方法",
            "肌肉 增肌 重量 深蹲",
            ["力量", "肌肉"]
        )
        assert category2 == "strength_training"

        # 减脂相关
        category3 = loader._infer_category_enhanced(
            "如何科学减脂",
            "减肥 体重 体脂 燃脂",
            ["减脂", "体重"]
        )
        assert category3 == "weight_management"

    def test_smart_chunking(self):
        """测试智能分块"""
        loader = EnhancedDocumentLoader(chunk_size=500, chunk_overlap=100)

        # 创建一个长文本
        long_text = "# 主标题\n\n" + ("这是一段测试文本。" * 100)

        chunks = loader._split_text_smart(long_text, "主标题")

        # 应该被分成多块
        assert len(chunks) > 1

        # 每块不应超过 chunk_size 太多
        for chunk in chunks:
            assert len(chunk) <= loader.chunk_size * 1.2  # 允许20%的超出

    def test_overlap_addition(self):
        """测试重叠添加"""
        loader = EnhancedDocumentLoader(chunk_size=1000, chunk_overlap=200)

        chunks = ["第一块内容" * 50, "第二块内容" * 50, "第三块内容" * 50]
        overlapped = loader._add_overlap(chunks)

        # 除了第一块，其他块应该包含 "[...接上文...]"
        assert "[...接上文...]" not in overlapped[0]
        if len(overlapped) > 1:
            assert "[...接上文...]" in overlapped[1]

    def test_breadcrumb_hierarchy(self):
        """测试面包屑层级结构"""
        loader = EnhancedDocumentLoader()
        sections = loader._parse_markdown_hierarchy(SAMPLE_COURSE_CONTENT)

        # 找到深层级的节
        deep_sections = [s for s in sections if s["level"] >= 3]

        if deep_sections:
            section = deep_sections[0]

            # 面包屑应该包含父级标题
            assert len(section["breadcrumb"]) >= 2

            # parent_titles 应该比 breadcrumb 少一个（当前标题）
            assert len(section["parent_titles"]) == len(section["breadcrumb"]) - 1

            # 面包屑的最后一个应该是当前标题
            assert section["breadcrumb"][-1] == section["title"]

    def test_metadata_completeness(self):
        """测试元数据完整性"""
        loader = EnhancedDocumentLoader()

        documents = loader.load_course_markdown(
            content=SAMPLE_COURSE_CONTENT,
            source="test_source",
            author="测试作者",
            difficulty="advanced",
            target_audience=["专业运动员"],
            course_metadata={"platform": "得到", "course_type": "运动科学"}
        )

        doc = documents[0]
        metadata = doc["metadata"]

        # 检查所有必需的元数据字段
        required_fields = [
            "source", "author", "difficulty", "target_audience",
            "breadcrumb", "section_level", "parent_titles",
            "key_concepts", "chunk_index", "total_chunks"
        ]

        for field in required_fields:
            assert field in metadata, f"缺少元数据字段: {field}"

        # 检查自定义元数据
        assert metadata.get("platform") == "得到"
        assert metadata.get("course_type") == "运动科学"

    def test_empty_content_handling(self):
        """测试空内容处理"""
        loader = EnhancedDocumentLoader()

        # 空字符串
        documents = loader.load_course_markdown(content="", source="test")
        assert len(documents) == 0

        # 只有空白字符
        documents = loader.load_course_markdown(content="   \n\n  ", source="test")
        assert len(documents) == 0

    def test_no_headers_fallback(self):
        """测试无标题时的后备方案"""
        loader = EnhancedDocumentLoader(chunk_size=500)

        # 没有 Markdown 标题的纯文本
        plain_text = "这是一段没有标题的文本。" * 100

        documents = loader.load_course_markdown(
            content=plain_text,
            source="test_plain",
            author="测试"
        )

        # 应该使用后备分块方案
        assert len(documents) > 0

        # 检查是否标记为 fallback_mode
        assert documents[0]["metadata"].get("fallback_mode") is True


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
