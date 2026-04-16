"""Skill 注册表 — 版本管理 + metrics 追踪 + 自动优化调度"""
import json
import logging
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# Skill 名称只允许字母、数字、连字符、下划线
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
# 版本号只允许 semver 格式或简单数字点分格式（如 1.0.0, 2.1.0-beta）
_SAFE_VERSION_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_skill_name(name: str) -> None:
    """校验 skill 名称，防止路径遍历"""
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError(f"非法的 Skill 名称: {name!r}（仅允许字母、数字、连字符、下划线）")


def _validate_version(version: str) -> None:
    """校验版本号，防止路径遍历"""
    if not version or not _SAFE_VERSION_RE.match(version):
        raise ValueError(f"非法的版本号: {version!r}（仅允许字母、数字、点、连字符、下划线）")


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
            try:
                info = self._read_skill_info(skill_dir)
                if info:
                    results.append(info)
            except Exception as e:
                logger.warning(f"读取 Skill {skill_dir.name} 失败: {e}")
        return results

    def get_skill(self, name: str) -> Optional[dict]:
        """获取单个 Skill 的详细信息"""
        _validate_skill_name(name)
        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            return None
        try:
            return self._read_skill_info(skill_dir)
        except Exception as e:
            logger.error(f"读取 Skill {name} 失败: {e}")
            return None

    def get_skill_content(self, name: str, version: Optional[str] = None, include_references: bool = False) -> Optional[str]:
        """获取 Skill 内容（指定版本或当前版本）

        Args:
            name: Skill 名称
            version: 指定版本号，None 为当前版本
            include_references: 是否追加 references/ 目录下的参考文档
        """
        _validate_skill_name(name)
        skill_dir = self.skills_dir / name
        if version:
            _validate_version(version)
            path = skill_dir / f"SKILL.v{version}.md"
        else:
            path = skill_dir / "SKILL.md"
        # 防御性检查：确保路径在 skills 目录内
        if not str(path.resolve()).startswith(str(self.skills_dir.resolve())):
            raise ValueError("路径遍历检测: 拒绝访问 skills 目录之外的文件")
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8")
            if include_references:
                refs = self._read_references(skill_dir)
                if refs:
                    content += "\n\n" + refs
            return content
        except Exception as e:
            logger.error(f"读取 {path} 失败: {e}")
            return None

    def get_skill_reference(self, name: str, ref_file: str) -> Optional[str]:
        """获取 Skill 的单个参考文档

        Args:
            name: Skill 名称
            ref_file: 参考文件名（如 technical_reference.md）
        """
        _validate_skill_name(name)
        # ref_file 只允许 .md 文件名，防止路径遍历
        if not re.match(r"^[a-zA-Z0-9_-]+\.md$", ref_file):
            raise ValueError(f"非法的参考文件名: {ref_file!r}")
        ref_path = self.skills_dir / name / "references" / ref_file
        if not str(ref_path.resolve()).startswith(str(self.skills_dir.resolve())):
            raise ValueError("路径遍历检测: 拒绝访问 skills 目录之外的文件")
        if not ref_path.exists():
            return None
        try:
            return ref_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"读取参考文档 {ref_path} 失败: {e}")
            return None

    def list_skill_references(self, name: str) -> list[str]:
        """列出 Skill 的所有参考文档文件名"""
        _validate_skill_name(name)
        ref_dir = self.skills_dir / name / "references"
        if not ref_dir.exists():
            return []
        return sorted(f.name for f in ref_dir.glob("*.md"))

    def save_new_version(self, name: str, content: str, changelog: str = "") -> dict:
        """保存新版本的 Skill（当前版本存档，新内容写入 SKILL.md）"""
        _validate_skill_name(name)
        skill_dir = self.skills_dir / name
        current_path = skill_dir / "SKILL.md"

        if not current_path.exists():
            raise FileNotFoundError(f"Skill {name} not found")

        # 读取当前版本号
        current_content = current_path.read_text(encoding="utf-8")
        current_fm = _parse_frontmatter(current_content)
        current_version = current_fm.get("version", "1.0.0")

        # 先读取 manifest（必须在写入新内容之前，否则初始化会读到新版本）
        manifest = self._read_manifest(skill_dir)

        # 计算新版本号（patch bump）
        parts = current_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        new_version = ".".join(parts)

        # 更新 frontmatter 中的版本号
        new_fm = _parse_frontmatter(content)
        if new_fm.get("version") and new_fm["version"] != current_version:
            # 内容已包含一个不同于当前版本的版本号，使用它
            new_version = new_fm["version"]
        else:
            # 替换 frontmatter 中的版本号为自动 bump 的新版本
            content = re.sub(
                r"(version:\s*)\S+",
                f"version: {new_version}",
                content,
                count=1,
            )

        # 准备新 manifest
        import copy
        new_manifest = copy.deepcopy(manifest)
        new_manifest["versions"].append({
            "version": new_version,
            "created_at": datetime.now(UTC).isoformat(),
            "changelog": changelog,
            "status": "canary",  # 新版本先作为 canary
        })
        for v in new_manifest["versions"]:
            if v["version"] == current_version:
                v["status"] = "archived"
        new_manifest["current_version"] = new_version

        # 原子写入：先写临时文件，再 rename（同文件系统上 os.replace 是原子的）
        archive_path = skill_dir / f"SKILL.v{current_version}.md"
        tmp_skill = skill_dir / "SKILL.md.tmp"
        tmp_manifest = skill_dir / "manifest.json.tmp"
        try:
            shutil.copy2(current_path, archive_path)
            tmp_skill.write_text(content, encoding="utf-8")
            tmp_manifest.write_text(
                json.dumps(new_manifest, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # 原子替换
            os.replace(str(tmp_skill), str(current_path))
            os.replace(str(tmp_manifest), str(skill_dir / "manifest.json"))
        except Exception:
            # 回滚：清理临时文件和存档
            archive_path.unlink(missing_ok=True)
            tmp_skill.unlink(missing_ok=True)
            tmp_manifest.unlink(missing_ok=True)
            raise

        logger.info(f"Skill {name}: {current_version} → {new_version} (canary)")
        return {
            "skill_name": name,
            "old_version": current_version,
            "new_version": new_version,
            "status": "canary",
        }

    def promote_version(self, name: str, version: str) -> bool:
        """将 canary 版本升级为 production"""
        _validate_skill_name(name)
        _validate_version(version)
        skill_dir = self.skills_dir / name
        manifest = self._read_manifest(skill_dir)

        # 验证目标版本存在
        found = False
        for v in manifest["versions"]:
            if v["version"] == version:
                found = True
                break
        if not found:
            raise ValueError(f"版本 {version} 不存在于 Skill {name} 中")

        for v in manifest["versions"]:
            if v["version"] == version:
                v["status"] = "production"
            elif v.get("status") == "production":
                v["status"] = "archived"
        manifest["current_version"] = version
        self._write_manifest(skill_dir, manifest)

        # 同步到远程 OpenClaw Gateway
        self._sync_to_gateway(name)

        logger.info(f"Skill {name}: 升级 {version} 为 production，已同步到 Gateway")
        return True

    def rollback_version(self, name: str) -> Optional[str]:
        """回滚到上一个 production 版本"""
        _validate_skill_name(name)
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
        if not archive_path.exists():
            raise FileNotFoundError(
                f"存档文件 SKILL.v{target_version}.md 不存在，无法回滚"
            )
        shutil.copy2(archive_path, skill_dir / "SKILL.md")

        # 标记当前版本为 rolled_back
        for v in manifest["versions"]:
            if v["version"] == manifest.get("current_version"):
                v["status"] = "rolled_back"
        target["status"] = "production"
        manifest["current_version"] = target_version
        self._write_manifest(skill_dir, manifest)

        # 同步到远程 OpenClaw Gateway
        self._sync_to_gateway(name)

        logger.info(f"Skill {name}: 回滚到 {target_version}，已同步到 Gateway")
        return target_version

    def _sync_to_gateway(self, name: str):
        """将本地 SKILL.md 同步到远程 OpenClaw Gateway"""
        try:
            from app.services.openclaw_skills_service import openclaw_skills_service
            content = self.get_skill_content(name)
            if content:
                openclaw_skills_service.create_or_update_skill(
                    name=name,
                    skill_md_content=content,
                    enabled=True,
                )
                logger.info(f"Skill {name} 已同步到远程 Gateway")
        except Exception as e:
            logger.error(f"同步 Skill {name} 到 Gateway 失败: {e}")
            raise

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

        # 检查是否有 references 目录
        has_references = (skill_dir / "references").is_dir()
        reference_files = sorted(f.name for f in (skill_dir / "references").glob("*.md")) if has_references else []

        return {
            "name": fm.get("name", skill_dir.name),
            "description": fm.get("description", ""),
            "current_version": fm.get("version", "1.0.0"),
            "archived_versions": archived_versions,
            "manifest": manifest,
            "has_references": has_references,
            "reference_files": reference_files,
        }

    def _read_manifest(self, skill_dir: Path) -> dict:
        manifest_path = skill_dir / "manifest.json"
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"manifest.json 损坏，重新初始化: {e}")
        # 初始化 manifest
        skill_path = skill_dir / "SKILL.md"
        fm = _parse_frontmatter(skill_path.read_text(encoding="utf-8")) if skill_path.exists() else {}
        return {
            "current_version": fm.get("version", "1.0.0"),
            "versions": [
                {
                    "version": fm.get("version", "1.0.0"),
                    "created_at": datetime.now(UTC).isoformat(),
                    "changelog": "初始版本",
                    "status": "production",
                }
            ],
        }

    def _read_references(self, skill_dir: Path) -> str:
        """读取 skill 的所有 references/*.md 并拼接"""
        ref_dir = skill_dir / "references"
        if not ref_dir.is_dir():
            return ""
        parts = []
        for ref_file in sorted(ref_dir.glob("*.md")):
            try:
                content = ref_file.read_text(encoding="utf-8")
                parts.append(f"\n---\n## Reference: {ref_file.stem}\n\n{content}")
            except Exception as e:
                logger.warning(f"读取参考文档 {ref_file} 失败: {e}")
        return "\n".join(parts)

    def _write_manifest(self, skill_dir: Path, manifest: dict):
        manifest_path = skill_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# 单例
skill_registry = SkillRegistry()
