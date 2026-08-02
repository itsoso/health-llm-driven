"""Skills Hub 客户端 — 从 GitHub 仓库动态发现和加载社区 Skills"""
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

from app.utils.runtime_data import is_production, skills_hub_cache_dir

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


class SkillsHubClient:
    """从 GitHub 仓库获取社区健康 Skills"""

    # 默认 Hub 仓库（可通过环境变量覆盖）
    DEFAULT_HUB_REPO = "health-skills-hub/community"
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
    GITHUB_API_BASE = "https://api.github.com"

    CACHE_TTL = 86400  # 24 小时缓存

    def __init__(self, hub_repo: Optional[str] = None):
        self.hub_repo = hub_repo or self.DEFAULT_HUB_REPO
        self.CACHE_DIR = skills_hub_cache_dir()

    def get_taxonomy(self) -> dict:
        """获取 Hub 的技能分类（taxonomy.yaml）"""
        cache_file = self._cache_file("taxonomy.json")
        if self._is_cache_valid(cache_file):
            return json.loads(cache_file.read_text(encoding="utf-8"))

        url = f"{self.GITHUB_RAW_BASE}/{self.hub_repo}/main/catalog/taxonomy.yaml"
        try:
            content = self._fetch_url(url)
            # 简单 YAML 解析（不引入 pyyaml 依赖）
            taxonomy = self._parse_simple_yaml(content)
            cache_file.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2), encoding="utf-8")
            return taxonomy
        except Exception as e:
            logger.error(f"获取 Hub taxonomy 失败: {e}")
            # 返回缓存（即使过期）
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
            return {"domains": [], "error": str(e)}

    def search_skills(self, keyword: str) -> list[dict]:
        """搜索 Hub 中的 Skills"""
        taxonomy = self.get_taxonomy()
        results = []
        keyword_lower = keyword.lower()

        for domain in taxonomy.get("domains", []):
            domain_name = domain.get("name", "")
            for skill in domain.get("skills", []):
                skill_name = skill.get("name", "")
                skill_desc = skill.get("description", "")
                if (
                    keyword_lower in skill_name.lower()
                    or keyword_lower in skill_desc.lower()
                    or keyword_lower in domain_name.lower()
                ):
                    results.append({
                        "domain": domain_name,
                        "name": skill_name,
                        "description": skill_desc,
                        "installed": (SKILLS_DIR / skill_name).exists(),
                        "source": "hub",
                    })

        return results

    def list_domains(self) -> list[dict]:
        """列出 Hub 的所有领域分类"""
        taxonomy = self.get_taxonomy()
        return [
            {
                "name": d.get("name", ""),
                "description": d.get("description", ""),
                "skill_count": len(d.get("skills", [])),
            }
            for d in taxonomy.get("domains", [])
        ]

    def fetch_skill(self, domain: str, skill_name: str) -> Optional[str]:
        """从 Hub 获取单个 Skill 的 SKILL.md 内容"""
        cache_file = self._cache_file(f"{domain}_{skill_name}.md")
        if self._is_cache_valid(cache_file):
            return cache_file.read_text(encoding="utf-8")

        url = f"{self.GITHUB_RAW_BASE}/{self.hub_repo}/main/skills/{domain}/{skill_name}/SKILL.md"
        try:
            content = self._fetch_url(url)
            cache_file.write_text(content, encoding="utf-8")
            return content
        except Exception as e:
            logger.error(f"获取 Hub Skill {domain}/{skill_name} 失败: {e}")
            if cache_file.exists():
                return cache_file.read_text(encoding="utf-8")
            return None

    def install_skill(self, domain: str, skill_name: str) -> dict:
        """从 Hub 安装 Skill 到本地 skills 目录"""
        if is_production():
            return {
                "success": False,
                "error": "hub_skill_mutation_disabled",
            }

        # 检查是否已存在
        local_dir = SKILLS_DIR / skill_name
        if local_dir.exists():
            return {"success": False, "error": f"Skill {skill_name} 已存在，请先卸载"}

        # 获取 SKILL.md
        content = self.fetch_skill(domain, skill_name)
        if not content:
            return {"success": False, "error": f"无法从 Hub 获取 Skill {skill_name}"}

        # 写入本地
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # 尝试获取 references
        for ref_name in ["technical_reference.md", "thresholds_and_evidence.md"]:
            ref_url = (
                f"{self.GITHUB_RAW_BASE}/{self.hub_repo}/main/"
                f"skills/{domain}/{skill_name}/references/{ref_name}"
            )
            try:
                ref_content = self._fetch_url(ref_url)
                ref_dir = local_dir / "references"
                ref_dir.mkdir(exist_ok=True)
                (ref_dir / ref_name).write_text(ref_content, encoding="utf-8")
            except Exception:
                pass  # references 是可选的

        # 标记来源
        meta = {"source": "hub", "domain": domain, "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        (local_dir / ".hub_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        logger.info(f"从 Hub 安装 Skill: {domain}/{skill_name}")
        return {"success": True, "skill_name": skill_name, "domain": domain}

    def uninstall_skill(self, skill_name: str) -> dict:
        """卸载 Hub 安装的 Skill（仅允许删除 Hub 来源的）"""
        if is_production():
            return {
                "success": False,
                "error": "hub_skill_mutation_disabled",
            }

        local_dir = SKILLS_DIR / skill_name
        if not local_dir.exists():
            return {"success": False, "error": f"Skill {skill_name} 不存在"}

        meta_file = local_dir / ".hub_meta.json"
        if not meta_file.exists():
            return {"success": False, "error": f"Skill {skill_name} 不是从 Hub 安装的，不允许通过 Hub 卸载"}

        shutil.rmtree(local_dir)
        logger.info(f"卸载 Hub Skill: {skill_name}")
        return {"success": True, "skill_name": skill_name}

    def list_installed_hub_skills(self) -> list[dict]:
        """列出所有从 Hub 安装的 Skills"""
        results = []
        if not SKILLS_DIR.exists():
            return results
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            meta_file = skill_dir / ".hub_meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    results.append({
                        "name": skill_dir.name,
                        "domain": meta.get("domain", "unknown"),
                        "installed_at": meta.get("installed_at", ""),
                    })
                except Exception:
                    results.append({"name": skill_dir.name, "domain": "unknown"})
        return results

    # ---- 内部方法 ----

    def _cache_file(self, name: str) -> Path:
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return self.CACHE_DIR / name

    def _fetch_url(self, url: str, timeout: int = 15) -> str:
        """获取 URL 内容"""
        req = Request(url, headers={"User-Agent": "HealthSkillsHub/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """检查缓存文件是否有效"""
        if not cache_file.exists():
            return False
        age = time.time() - cache_file.stat().st_mtime
        return age < self.CACHE_TTL

    @staticmethod
    def _parse_simple_yaml(content: str) -> dict:
        """极简 YAML 解析（仅支持 domains/skills 结构，不引入 pyyaml）"""
        # 回退：如果是 JSON 格式直接解析
        content = content.strip()
        if content.startswith("{"):
            return json.loads(content)

        # 简单按行解析 taxonomy
        domains = []
        current_domain = None
        current_skill = None

        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            if stripped.startswith("- name:") and indent <= 2:
                # 新 domain
                current_domain = {"name": stripped.split(":", 1)[1].strip().strip('"'), "skills": []}
                domains.append(current_domain)
                current_skill = None
            elif stripped.startswith("description:") and current_domain and not current_skill:
                current_domain["description"] = stripped.split(":", 1)[1].strip().strip('"')
            elif stripped.startswith("- name:") and indent > 2 and current_domain:
                # 新 skill
                current_skill = {"name": stripped.split(":", 1)[1].strip().strip('"')}
                current_domain["skills"].append(current_skill)
            elif stripped.startswith("description:") and current_skill:
                current_skill["description"] = stripped.split(":", 1)[1].strip().strip('"')

        return {"domains": domains}


# 单例
skills_hub_client = SkillsHubClient()
