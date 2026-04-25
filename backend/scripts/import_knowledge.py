#!/usr/bin/env python3
"""
知识库导入脚本

用于将知识库目录中的内容批量导入到向量数据库
支持冯雪健康课程和皮皮妈妈免疫健康等知识源

使用方法:
    python scripts/import_knowledge.py --source feng_xue
    python scripts/import_knowledge.py --source pipi_mama
    python scripts/import_knowledge.py --source all
    python scripts/import_knowledge.py --list  # 列出可用的知识源
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.knowledge.document_loader import document_loader
from app.services.knowledge.vectorstore import vector_store

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 知识库目录
KNOWLEDGE_BASE_DIR = project_root / "knowledge_base"

# 知识源配置
KNOWLEDGE_SOURCES = {
    "feng_xue": {
        "name": "冯雪健康课程",
        "description": "北京协和医院心血管专家冯雪的家庭健康管理课程",
        "directory": KNOWLEDGE_BASE_DIR / "feng_xue",
        "categories": ["cardiovascular", "exercise", "weight_management", "sleep", "nutrition", "emergency"]
    },
    "pipi_mama": {
        "name": "皮皮妈妈免疫健康",
        "description": "皮皮妈妈公众号的家庭免疫健康知识",
        "directory": KNOWLEDGE_BASE_DIR / "pipi_mama",
        "categories": ["immune_basics", "cold_fever", "allergy", "children_health"]
    },
    "exercise_science": {
        "name": "运动科学",
        "description": "基于《跑步治愈》和运动生理学的科学训练知识",
        "directory": KNOWLEDGE_BASE_DIR / "exercise_science",
        "categories": ["running", "heart_rate_training", "strength_training", "recovery", "sports_nutrition"]
    },
    "general": {
        "name": "通用健康知识",
        "description": "通用健康管理知识",
        "directory": KNOWLEDGE_BASE_DIR / "general",
        "categories": ["immune_basics", "children_health", "cold_fever", "allergy", "vaccination", "nutrition_immunity"]
    },
    "exercise_science": {
        "name": "运动科学",
        "description": "专业运动科学知识（跑步治愈等）",
        "directory": KNOWLEDGE_BASE_DIR / "exercise_science",
        "categories": ["running", "strength", "recovery", "injury_prevention"]
    },
    "general": {
        "name": "通用健康知识",
        "description": "通用健康知识库",
        "directory": KNOWLEDGE_BASE_DIR / "general",
        "categories": ["general"]
    }
}


def list_sources():
    """列出所有可用的知识源"""
    print("\n📚 可用的知识源:")
    print("-" * 60)

    for source_id, config in KNOWLEDGE_SOURCES.items():
        exists = config["directory"].exists()
        status = "✅" if exists else "❌ (目录不存在)"

        print(f"\n  {source_id} {status}")
        print(f"    名称: {config['name']}")
        print(f"    描述: {config['description']}")
        print(f"    目录: {config['directory']}")

        if exists:
            files = list(config["directory"].glob("*.md"))
            print(f"    文件: {len(files)} 个 Markdown 文件")

    print("\n" + "-" * 60)
    print("使用示例: python scripts/import_knowledge.py --source feng_xue")
    print()


def import_source(source_id: str, force: bool = False) -> dict:
    """
    导入指定的知识源

    Args:
        source_id: 知识源 ID
        force: 是否强制重新导入（先删除旧数据）

    Returns:
        导入结果
    """
    if source_id not in KNOWLEDGE_SOURCES:
        logger.error(f"未知的知识源: {source_id}")
        return {"success": False, "error": f"未知的知识源: {source_id}"}

    config = KNOWLEDGE_SOURCES[source_id]
    source_dir = config["directory"]

    if not source_dir.exists():
        logger.error(f"知识源目录不存在: {source_dir}")
        return {"success": False, "error": f"目录不存在: {source_dir}"}

    logger.info(f"开始导入知识源: {config['name']} ({source_id})")

    # 检查向量存储是否可用
    if not vector_store.is_available():
        logger.error("向量存储服务不可用")
        return {"success": False, "error": "向量存储服务不可用"}

    # 如果强制导入，先删除旧数据
    if force:
        logger.info(f"删除旧的 {source_id} 知识数据...")
        delete_result = vector_store.delete_by_source(source_id)
        if delete_result.get("success"):
            logger.info(f"已删除 {delete_result.get('deleted_count', 0)} 条旧记录")

    # 加载文档
    all_documents = []

    for md_file in sorted(source_dir.glob("*.md")):
        # 跳过 README 文件
        if md_file.name.lower() == "readme.md":
            continue

        logger.info(f"  加载文件: {md_file.name}")

        # 使用 Markdown 加载器
        docs = document_loader.load_markdown_file(
            str(md_file),
            source=source_id
        )

        # 添加额外元数据
        for doc in docs:
            doc["metadata"]["source_name"] = config["name"]
            doc["metadata"]["file_name"] = md_file.name

        all_documents.extend(docs)
        logger.info(f"    -> 解析出 {len(docs)} 个文档块")

    if not all_documents:
        logger.warning(f"没有找到可导入的文档")
        return {"success": True, "documents_added": 0, "message": "没有找到可导入的文档"}

    # 添加到向量存储
    logger.info(f"正在添加 {len(all_documents)} 个文档块到向量存储...")

    result = vector_store.add_documents(all_documents, source=source_id)

    if result.get("success"):
        logger.info(f"✅ 成功导入 {result.get('documents_added', 0)} 个文档块")
    else:
        logger.error(f"导入失败: {result.get('error', '未知错误')}")

    return result


def import_all(force: bool = False) -> dict:
    """导入所有知识源"""
    results = {}
    total_docs = 0

    for source_id in KNOWLEDGE_SOURCES:
        source_dir = KNOWLEDGE_SOURCES[source_id]["directory"]
        if source_dir.exists():
            result = import_source(source_id, force=force)
            results[source_id] = result
            if result.get("success"):
                total_docs += result.get("documents_added", 0)

    return {
        "success": True,
        "total_documents": total_docs,
        "results": results
    }


def show_stats():
    """显示知识库统计信息"""
    if not vector_store.is_available():
        print("❌ 向量存储服务不可用")
        return

    stats = vector_store.get_stats()

    print("\n📊 知识库统计信息:")
    print("-" * 40)
    print(f"  总文档数: {stats.get('total_documents', 0)}")

    by_source = stats.get("by_source", {})
    if by_source:
        print("\n  按来源分布:")
        for source, count in by_source.items():
            source_name = KNOWLEDGE_SOURCES.get(source, {}).get("name", source)
            print(f"    - {source_name}: {count}")

    by_category = stats.get("by_category", {})
    if by_category:
        print("\n  按分类分布:")
        for category, count in sorted(by_category.items()):
            print(f"    - {category}: {count}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="知识库导入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/import_knowledge.py --list           # 列出可用的知识源
  python scripts/import_knowledge.py --source feng_xue     # 导入冯雪课程
  python scripts/import_knowledge.py --source pipi_mama    # 导入皮皮妈妈
  python scripts/import_knowledge.py --source all          # 导入所有
  python scripts/import_knowledge.py --source all --force  # 强制重新导入
  python scripts/import_knowledge.py --stats          # 显示统计信息
        """
    )

    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有可用的知识源"
    )

    parser.add_argument(
        "--source", "-s",
        type=str,
        help="要导入的知识源 (feng_xue, pipi_mama, exercise_science, general, all)"
    )

    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新导入（先删除旧数据）"
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="显示知识库统计信息"
    )

    args = parser.parse_args()

    if args.list:
        list_sources()
        return

    if args.stats:
        show_stats()
        return

    if args.source:
        if args.source == "all":
            result = import_all(force=args.force)
        else:
            result = import_source(args.source, force=args.force)

        if result.get("success"):
            print(f"\n✅ 导入完成!")
            show_stats()
        else:
            print(f"\n❌ 导入失败: {result.get('error')}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
