"""OpenClaw Skills 远程管理服务

通过 SSH 连接 OpenClaw 服务器，管理 Skills 文件和配置。
"""
import json
import logging
from typing import Optional
import paramiko
from app.config import settings

logger = logging.getLogger(__name__)

# OpenClaw 服务器配置
OPENCLAW_SSH_HOST = settings.openclaw_ssh_host
OPENCLAW_SSH_PORT = settings.openclaw_ssh_port
OPENCLAW_SSH_USER = "root"
OPENCLAW_SKILLS_DIR = "/root/.openclaw/skills"
OPENCLAW_CONFIG_PATH = "/root/.openclaw/openclaw.json"


class OpenClawSkillsService:
    """通过 SSH 管理 OpenClaw 服务器上的 Skills"""

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """创建 SSH 连接"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=OPENCLAW_SSH_HOST,
            port=OPENCLAW_SSH_PORT,
            username=OPENCLAW_SSH_USER,
            timeout=10,
        )
        return client

    def _exec(self, client: paramiko.SSHClient, cmd: str) -> tuple[str, str]:
        """执行远程命令，返回 (stdout, stderr)"""
        _, stdout, stderr = client.exec_command(cmd, timeout=15)
        return stdout.read().decode(), stderr.read().decode()

    def _read_remote_file(self, client: paramiko.SSHClient, path: str) -> Optional[str]:
        """读取远程文件内容"""
        out, err = self._exec(client, f"cat {path} 2>/dev/null")
        return out if out else None

    def _write_remote_file(self, client: paramiko.SSHClient, path: str, content: str):
        """写入远程文件"""
        sftp = client.open_sftp()
        try:
            with sftp.open(path, "w") as f:
                f.write(content)
        finally:
            sftp.close()

    def _read_config(self, client: paramiko.SSHClient) -> dict:
        """读取 openclaw.json 配置"""
        raw = self._read_remote_file(client, OPENCLAW_CONFIG_PATH)
        if not raw:
            return {}
        return json.loads(raw)

    def _write_config(self, client: paramiko.SSHClient, config: dict):
        """写入 openclaw.json 配置"""
        self._write_remote_file(
            client, OPENCLAW_CONFIG_PATH, json.dumps(config, indent=2, ensure_ascii=False)
        )

    # ── 公开 API ─────────────────────────────────────────

    def list_skills(self) -> list[dict]:
        """列出所有已安装的 Skills"""
        client = self._get_ssh_client()
        try:
            # 列出 skills 目录
            out, _ = self._exec(client, f"ls -1 {OPENCLAW_SKILLS_DIR} 2>/dev/null")
            skill_names = [n.strip() for n in out.strip().split("\n") if n.strip()]

            # 读取配置中的 entries
            config = self._read_config(client)
            entries = config.get("skills", {}).get("entries", {})

            results = []
            for name in skill_names:
                skill_md = self._read_remote_file(
                    client, f"{OPENCLAW_SKILLS_DIR}/{name}/SKILL.md"
                )
                entry = entries.get(name, {})
                # 解析 frontmatter
                info = self._parse_frontmatter(skill_md) if skill_md else {}
                results.append({
                    "name": name,
                    "description": info.get("description", ""),
                    "version": info.get("version", ""),
                    "enabled": entry.get("enabled", False),
                    "has_env": bool(entry.get("env")),
                    "env_keys": list(entry.get("env", {}).keys()),
                })
            return results
        finally:
            client.close()

    def get_skill(self, name: str) -> Optional[dict]:
        """获取单个 Skill 详情（含 SKILL.md 内容和配置）"""
        client = self._get_ssh_client()
        try:
            skill_md = self._read_remote_file(
                client, f"{OPENCLAW_SKILLS_DIR}/{name}/SKILL.md"
            )
            if not skill_md:
                return None

            config = self._read_config(client)
            entry = config.get("skills", {}).get("entries", {}).get(name, {})

            info = self._parse_frontmatter(skill_md)
            return {
                "name": name,
                "description": info.get("description", ""),
                "version": info.get("version", ""),
                "skill_md": skill_md,
                "config_entry": entry,
            }
        finally:
            client.close()

    def create_or_update_skill(
        self,
        name: str,
        skill_md_content: str,
        enabled: bool = True,
        env: Optional[dict] = None,
        api_key: Optional[str] = None,
    ) -> dict:
        """创建或更新一个 Skill

        Args:
            name: Skill 名称（目录名）
            skill_md_content: SKILL.md 完整内容
            enabled: 是否启用
            env: 环境变量字典
            api_key: API Key
        """
        client = self._get_ssh_client()
        try:
            # 1. 创建目录
            self._exec(client, f"mkdir -p {OPENCLAW_SKILLS_DIR}/{name}")

            # 2. 写入 SKILL.md
            self._write_remote_file(
                client, f"{OPENCLAW_SKILLS_DIR}/{name}/SKILL.md", skill_md_content
            )

            # 3. 更新 openclaw.json 的 skills.entries
            config = self._read_config(client)
            if "skills" not in config:
                config["skills"] = {}
            if "entries" not in config["skills"]:
                config["skills"]["entries"] = {}

            entry = {"enabled": enabled}
            if api_key:
                entry["apiKey"] = api_key
            if env:
                entry["env"] = env
            config["skills"]["entries"][name] = entry

            self._write_config(client, config)

            return {"name": name, "status": "ok", "enabled": enabled}
        finally:
            client.close()

    def delete_skill(self, name: str) -> bool:
        """删除一个 Skill（目录 + 配置项）"""
        client = self._get_ssh_client()
        try:
            # 检查是否存在
            out, _ = self._exec(
                client, f"test -d {OPENCLAW_SKILLS_DIR}/{name} && echo yes || echo no"
            )
            if "yes" not in out:
                return False

            # 1. 删除目录
            self._exec(client, f"rm -rf {OPENCLAW_SKILLS_DIR}/{name}")

            # 2. 从配置中移除
            config = self._read_config(client)
            entries = config.get("skills", {}).get("entries", {})
            if name in entries:
                del entries[name]
                self._write_config(client, config)

            return True
        finally:
            client.close()

    def toggle_skill(self, name: str, enabled: bool) -> bool:
        """启用/禁用一个 Skill"""
        client = self._get_ssh_client()
        try:
            config = self._read_config(client)
            entries = config.get("skills", {}).get("entries", {})
            if name not in entries:
                return False
            entries[name]["enabled"] = enabled
            self._write_config(client, config)
            return True
        finally:
            client.close()

    def restart_gateway(self) -> str:
        """重启 OpenClaw Gateway 使配置生效"""
        client = self._get_ssh_client()
        try:
            out, err = self._exec(client, "systemctl restart openclaw 2>&1")
            result = out or err
            # 检查状态
            status_out, _ = self._exec(
                client, "systemctl is-active openclaw 2>&1"
            )
            return f"restart: {result.strip()}, status: {status_out.strip()}"
        finally:
            client.close()

    def get_gateway_status(self) -> dict:
        """获取 Gateway 运行状态"""
        client = self._get_ssh_client()
        try:
            status_out, _ = self._exec(client, "systemctl is-active openclaw 2>&1")
            uptime_out, _ = self._exec(
                client,
                "systemctl show openclaw --property=ActiveEnterTimestamp 2>&1",
            )
            return {
                "status": status_out.strip(),
                "uptime": uptime_out.strip(),
            }
        finally:
            client.close()

    def clawhub_search(self, query: str) -> str:
        """在 ClawHub 上搜索公共 Skills"""
        client = self._get_ssh_client()
        try:
            out, err = self._exec(
                client,
                f'clawhub search "{query}" --no-input 2>&1',
            )
            return out or err
        finally:
            client.close()

    def clawhub_install(self, slug: str) -> str:
        """从 ClawHub 安装公共 Skill"""
        client = self._get_ssh_client()
        try:
            out, err = self._exec(
                client,
                f"cd /root/.openclaw && clawhub install {slug} --dir skills --no-input --force 2>&1",
            )
            return out or err
        finally:
            client.close()

    # ── 辅助方法 ─────────────────────────────────────────

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """解析 SKILL.md 的 YAML frontmatter"""
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        fm = parts[1].strip()
        result = {}
        for line in fm.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                result[key.strip()] = val.strip()
        return result


openclaw_skills_service = OpenClawSkillsService()
