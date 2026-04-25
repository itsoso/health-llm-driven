#!/usr/bin/env python3
"""
上传张展晖课程到知识库

使用增强版文档加载器，支持：
- 保留标题层级结构
- 面包屑导航
- 丰富的元数据
"""

import sys
import os
import requests
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# API 配置
API_BASE_URL = "http://localhost:8000"
# 请替换为你的管理员 token
ADMIN_TOKEN = "your_admin_token_here"  # 需要先登录获取


def upload_course_file(file_path: str, source_id: str, title: str = None):
    """
    上传单个课程文件

    Args:
        file_path: Markdown 文件路径
        source_id: 来源标识（如 'zhang_zhanhui_01'）
        title: 课程标题（默认使用文件名）
    """
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return False

    # 读取文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 默认标题
    if not title:
        title = Path(file_path).stem.replace('_', ' ').replace('-', ' ')

    # 根据文件名推断目标人群
    target_audience = []
    filename_lower = Path(file_path).stem.lower()

    if '减肥' in filename_lower or '减脂' in filename_lower:
        target_audience.extend(['减脂人群', '减肥者'])
    if '跑步' in filename_lower or 'running' in filename_lower:
        target_audience.extend(['跑步爱好者', '耐力运动员'])
    if '心率' in filename_lower or 'heart' in filename_lower:
        target_audience.extend(['运动爱好者', '健身人群'])
    if '力量' in filename_lower or 'strength' in filename_lower:
        target_audience.extend(['力量训练者', '增肌人群'])

    # 默认目标人群
    if not target_audience:
        target_audience = ['运动爱好者', '健康管理者']

    # 准备请求数据
    data = {
        "content": content,
        "title": title,
        "author": "张展晖",
        "source": source_id,
        "difficulty": "intermediate",  # 可根据实际情况调整
        "target_audience": target_audience,
        "course_metadata": {
            "platform": "得到",
            "course_type": "运动科学",
            "file_name": Path(file_path).name
        }
    }

    # 发送请求
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }

    print(f"\n📤 正在上传: {title}")
    print(f"   来源: {source_id}")
    print(f"   目标人群: {', '.join(target_audience)}")
    print(f"   文件大小: {len(content) / 1024:.1f} KB")

    try:
        response = requests.post(
            f"{API_BASE_URL}/knowledge/documents/course",
            headers=headers,
            json=data,
            timeout=120  # 2分钟超时
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ 上传成功!")
            print(f"   文档块数: {result.get('documents_added', 0)}")
            print(f"   向量数: {result.get('embeddings_added', 0)}")
            return True
        else:
            print(f"❌ 上传失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print(f"❌ 请求超时（文件可能太大）")
        return False
    except Exception as e:
        print(f"❌ 上传出错: {e}")
        return False


def upload_course_directory(directory: str, source_prefix: str = "zhang_zhanhui"):
    """
    批量上传目录下的所有课程文件

    Args:
        directory: 课程文件目录
        source_prefix: 来源前缀
    """
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在: {directory}")
        return

    # 查找所有 Markdown 文件
    md_files = sorted(Path(directory).glob("*.md"))

    if not md_files:
        print(f"❌ 目录中没有找到 Markdown 文件: {directory}")
        return

    print(f"📚 找到 {len(md_files)} 个课程文件")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(md_files, 1):
        source_id = f"{source_prefix}_{i:02d}"

        if upload_course_file(str(file_path), source_id):
            success_count += 1
        else:
            fail_count += 1

        print("-" * 60)

    print("\n" + "=" * 60)
    print(f"📊 上传完成:")
    print(f"   成功: {success_count}")
    print(f"   失败: {fail_count}")
    print(f"   总计: {len(md_files)}")


def test_search(query: str = "如何根据心率训练"):
    """
    测试知识库搜索
    """
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "query": query,
        "n_results": 3,
        "source": "zhang_zhanhui"
    }

    print(f"\n🔍 测试搜索: {query}")

    try:
        response = requests.post(
            f"{API_BASE_URL}/knowledge/search",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ 找到 {result.get('count', 0)} 个相关结果")

            for i, doc in enumerate(result.get('results', [])[:3], 1):
                print(f"\n结果 {i}:")
                print(f"  标题: {doc.get('title', 'N/A')}")
                print(f"  面包屑: {doc.get('metadata', {}).get('breadcrumb', 'N/A')}")
                print(f"  内容预览: {doc.get('content', '')[:100]}...")
        else:
            print(f"❌ 搜索失败: {response.status_code}")

    except Exception as e:
        print(f"❌ 搜索出错: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="上传张展晖课程到知识库")
    parser.add_argument("--file", help="单个文件路径")
    parser.add_argument("--dir", help="课程文件目录")
    parser.add_argument("--source", default="zhang_zhanhui", help="来源标识前缀")
    parser.add_argument("--title", help="课程标题（仅用于单文件上传）")
    parser.add_argument("--token", help="管理员 token")
    parser.add_argument("--test", action="store_true", help="测试搜索功能")

    args = parser.parse_args()

    # 设置 token
    if args.token:
        ADMIN_TOKEN = args.token

    if ADMIN_TOKEN == "your_admin_token_here":
        print("⚠️  请先设置管理员 token!")
        print("   方法1: 在脚本中修改 ADMIN_TOKEN 变量")
        print("   方法2: 使用 --token 参数")
        print("\n如何获取 token:")
        print("   1. 访问 http://localhost:8000/docs")
        print("   2. 使用 /auth/login 接口登录")
        print("   3. 复制返回的 access_token")
        sys.exit(1)

    if args.test:
        # 测试搜索
        test_search()
    elif args.file:
        # 上传单个文件
        source_id = f"{args.source}_01"
        upload_course_file(args.file, source_id, args.title)
    elif args.dir:
        # 批量上传目录
        upload_course_directory(args.dir, args.source)
    else:
        print("请指定 --file 或 --dir 参数")
        print("示例:")
        print("  # 上传单个文件")
        print("  python upload_zhang_zhanhui_course.py --file ./courses/01_心肺功能.md --token YOUR_TOKEN")
        print("\n  # 批量上传目录")
        print("  python upload_zhang_zhanhui_course.py --dir ./courses/zhang_zhanhui --token YOUR_TOKEN")
        print("\n  # 测试搜索")
        print("  python upload_zhang_zhanhui_course.py --test --token YOUR_TOKEN")
