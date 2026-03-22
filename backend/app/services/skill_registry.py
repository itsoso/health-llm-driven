"""Skill 注册表 — 版本管理 + metrics 追踪 + 自动优化调度"""
import json
import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_frontmatter(content: str) -> dict:
    """从 SKILL.md 解析 YAML frontmatter"""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    # 简单解析，不引入 pyyaml 依赖
    fm = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("-") and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val:
                fm[key] = val
    return fm


class SkillRegistry:
    """管理本地 Skills 目录的版本和元数据"""

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = skills_dir

    def list_skills(self) -> list[dict]:
        """列出所有已安装的 Skill 及其版本信息"""
        results = []
        if not self.skills_dir.exists():
            return results

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            info = self._read_skill_info(skill_dir)
            if info:
                results.append(info)
        return results

    def get_skill(self, name: str) -> Optional[dict]:
        """获取单个 Skill 的详细信息"""
        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            return None
        return self._read_skill_info(skill_dir)

    def get_skill_content(self, name: str, version: Optional[str] = None) -> Optional[str]:
        """获取 Skill 内容（指定版本或当前版本）"""
        skill_dir = self.skills_dir / name
        if version:
            path = skill_dir / f"SKILL.v{version}.md"
            if not path.exists():
                return None
            return path.read_text(encoding="utf-8")
        else:
            path = skill_dir / "SKILL.md"
            if not path.exists():
                return None
            return path.read_text(encoding="utf-8")

    def save_new_version(self, name: str, content: str, changelog: str = "") -> dict:
        """保存新版本的 Skill（当前版本存档，新内容写入 SKILL.md）"""
        skill_dir = self.skills_dir / name
        current_path = skill_dir / "SKILL.md"

        if not current_path.exists():
            raise FileNotFoundError(f"Skill {name} not found")

        # 读取当前版本号
        current_content = current_path.read_text(encoding="utf-8")
        current_fm = _parse_frontmatter(current_content)
        current_version = current_fm.get("version", "1.0.0")

        # 存档当前版本
        archive_path = skill_dir / f"SKILL.v{current_version}.md"
        shutil.copy2(current_path, archive_path)

        # 计算新版本号（patch bump）
        parts = current_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)

        # 更新 frontmatter 中的版本号
        new_fm = _parse_frontmatter(content)
        if new_fm.get("version") and new_fm["version"] != new_version:
            # 内容已包含版本号，使用它
            new_version = new_fm["version"]
        else:
            # 替换或插入版本号
            content = re.sub(
                r"(version:\s*)\S+",
                f"version: {new_version}",
                content,
                count=1,
            )

        # 写入新内容
        current_path.write_text(content, encoding="utf-8")

        # 更新 manifest
        manifest = self._read_manifest(skill_dir)
        manifest["versions"].append({
            "version": new_version,
            "created_at": datetime.utcnow().isoformat(),
            "changelog": changelog,
            "status": "canary",  # 新版本先作为 canary
        })
        # 把之前的 production 保留标记
        for v in manifest["versions"]:
            if v["version"] == current_version:
                v["status"] = "archived"
        manifest["current_version"] = new_version
        self._write_manifest(skill_dir, manifest)

        logger.info(f"Skill {name}: {current_version} → {new_version} (canary)")
        return {
            "skill_name": name,
            "old_version": current_version,
            "new_version": new_version,
            "status": "canary",
        }

    def promote_version(self, name: str, version: str) -> bool:
        """将 canary 版本升级为 production"""
        skill_dir = self.skills_dir / name
        manifest = self._read_manifest(skill_dir)
        for v in manifest["versions"]:
            if v["version"] == version:
                v["status"] = "production"
            elif v.get("status") == "production":
                v["status"] = "archived"
        manifest["current_version"] = version
        self._write_manifest(skill_dir, manifest)
        logger.info(f"Skill {name}: 升级 {version} 为 production")
        return True

    def rollback_version(self, name: str) -> Optional[str]:
        """回滚到上一个 production 版本"""
        skill_dir = self.skills_dir / name
        manifest = self._read_manifest(skill_dir)

        # 找到最近的 archived 版本
        archived = [
            v for v in manifest["versions"]
            if v.get("status") in ("archived", "production")
            and v["version"] != manifest.get("current_version")
        ]
        if not archived:
            return None

        target = archived[-1]
        target_version = target["version"]

        # 恢复存档的 SKILL.md
        archive_path = skill_dir / f"SKILL.v{target_version}.md"
        if archive_path.exists():
            shutil.copy2(archive_path, skill_dir / "SKILL.md")

        # 标记当前版本为 rolled_back
        for v in manifest["versions"]:
            if v["version"] == manifest.get("current_version"):
                v["status"] = "rolled_back"
        target["status"] = "production"
        manifest["current_version"] = target_version
        self._write_manifest(skill_dir, manifest)

        logger.info(f"Skill {name}: 回滚到 {target_version}")
        return target_version

    # ---- 内部方法 ----

    def _read_skill_info(self, skill_dir: Path) -> Optional[dict]:
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            return None

        content = skill_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        manifest = self._read_manifest(skill_dir)

        # 列出所有存档版本
        archived_versions = sorted(
            [f.stem.replace("SKILL.v", "") for f in skill_dir.glob("SKILL.v*.md")]
        )

        return {
            "name": fm.get("name", skill_dir.name),
            "description": fm.get("description", ""),
            "current_version": fm.get("version", "1.0.0"),
            "archived_versions": archived_versions,
            "manifest": manifest,
        }

    def _read_manifest(self, skill_dir: Path) -> dict:
        manifest_path = skill_dir / "manifest.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        # 初始化 manifest
        skill_path = skill_dir / "SKILL.md"
        fm = _parse_frontmatter(skill_path.read_text(encoding="utf-8")) if skill_path.exists() else {}
        return {
            "current_version": fm.get("version", "1.0.0"),
            "versions": [
                {
                    "version": fm.get("version", "1.0.0"),
                    "created_at": datetime.utcnow().isoformat(),
                    "changelog": "初始版本",
                    "status": "production",
                }
            ],
        }

    def _write_manifest(self, skill_dir: Path, manifest: dict):
        manifest_path = skill_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# 单例
skill_registry = SkillRegistry()
