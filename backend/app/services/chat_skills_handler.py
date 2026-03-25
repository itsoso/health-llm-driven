import re
import logging
from typing import Optional

from app.config import settings
from app.services.openclaw_skills_service import openclaw_skills_service

logger = logging.getLogger(__name__)


class ChatSkillsHandler:
    """Handles OpenClaw skills management commands extracted from chat messages."""

    def try_handle_skill_command(self, message: str, is_admin: bool) -> Optional[str]:
        """检测并处理技能管理命令，返回响应文本或 None（非技能命令）"""
        if not is_admin:
            return None

        text = message.strip()

        # 1. 检测 SKILL.md 内容安装（包含 frontmatter）
        if text.startswith("---") and "\nname:" in text:
            return self._install_skill_from_content(text)

        # 2. 列出已安装技能
        if re.match(r"^(列出|查看|显示)(已安装|所有)?(技能|skills?)", text, re.IGNORECASE):
            return self._list_skills_response()

        # 3. ClawHub 搜索
        m = re.match(r"^(搜索|search)\s*(技能|skills?)?\s*(.+)", text, re.IGNORECASE)
        if m:
            return self._clawhub_search_response(m.group(3).strip())

        # 4. ClawHub 安装
        m = re.match(r"^(从\s*clawhub\s*)?(安装|install)\s*(技能|skills?)?\s*(.+)", text, re.IGNORECASE)
        if m:
            slug = m.group(4).strip()
            # 如果看起来是 clawhub slug (含斜杠)
            if "/" in slug:
                return self._clawhub_install_response(slug)

        # 5. 删除技能
        m = re.match(r"^(删除|卸载|remove|uninstall)\s*(技能|skills?)?\s*(.+)", text, re.IGNORECASE)
        if m:
            return self._delete_skill_response(m.group(3).strip())

        # 6. 启用/禁用技能
        m = re.match(r"^(启用|enable)\s*(技能|skills?)?\s*(.+)", text, re.IGNORECASE)
        if m:
            return self._toggle_skill_response(m.group(3).strip(), True)
        m = re.match(r"^(禁用|disable)\s*(技能|skills?)?\s*(.+)", text, re.IGNORECASE)
        if m:
            return self._toggle_skill_response(m.group(3).strip(), False)

        # 7. 重启 Gateway
        if re.match(r"^(重启|restart)\s*(gateway|网关)", text, re.IGNORECASE):
            return self._restart_gateway_response()

        # 8. Gateway 状态
        if re.match(r"^(gateway|网关)\s*(状态|status)", text, re.IGNORECASE):
            return self._gateway_status_response()

        return None

    def _install_skill_from_content(self, content: str) -> str:
        """从 SKILL.md 内容安装技能"""
        try:
            # 解析 frontmatter 获取 name
            info = openclaw_skills_service._parse_frontmatter(content)
            name = info.get("name", "").strip()
            if not name:
                return "安装失败：SKILL.md 缺少 `name` 字段。请确保 frontmatter 中包含 `name: your-skill-name`。"

            # 解析 metadata 获取所需环境变量
            env = {}
            # 简单提取 env 需求
            if "HEALTH_API_URL" in content:
                env["HEALTH_API_URL"] = settings.health_api_base_url
            if "HEALTH_API_TOKEN" in content:
                env["HEALTH_API_TOKEN"] = "<需要配置API Key>"

            result = openclaw_skills_service.create_or_update_skill(
                name=name,
                skill_md_content=content,
                enabled=True,
                env=env if env else None,
            )
            desc = info.get("description", "")
            version = info.get("version", "")
            lines = [f"技能 **{name}** 安装成功！"]
            if desc:
                lines.append(f"- 描述: {desc}")
            if version:
                lines.append(f"- 版本: {version}")
            lines.append(f"- 状态: {'已启用' if result.get('enabled') else '已禁用'}")
            if env:
                lines.append(f"- 环境变量: {', '.join(env.keys())}")
            lines.append('\n⚠️ 请**重启 Gateway** 使新技能生效（发送「重启 Gateway」）。')
            return "\n".join(lines)
        except Exception as e:
            return f"安装失败: {e}"

    def _list_skills_response(self) -> str:
        """列出已安装技能"""
        try:
            skills = openclaw_skills_service.list_skills()
            if not skills:
                return "当前没有已安装的技能。"
            lines = [f"已安装 **{len(skills)}** 个技能：\n"]
            for s in skills:
                status = "✅ 启用" if s["enabled"] else "⏸️ 禁用"
                lines.append(f"- **{s['name']}** {status}")
                if s.get("description"):
                    lines.append(f"  {s['description']}")
            return "\n".join(lines)
        except Exception as e:
            return f"获取技能列表失败: {e}"

    def _clawhub_search_response(self, query: str) -> str:
        """搜索 ClawHub"""
        try:
            result = openclaw_skills_service.clawhub_search(query)
            return f"**ClawHub 搜索「{query}」结果：**\n\n```\n{result}\n```\n\n如需安装，发送：`安装 <slug>`（例如：`安装 author/skill-name`）"
        except Exception as e:
            return f"搜索失败: {e}"

    def _clawhub_install_response(self, slug: str) -> str:
        """从 ClawHub 安装"""
        try:
            result = openclaw_skills_service.clawhub_install(slug)
            return f"**从 ClawHub 安装 `{slug}`：**\n\n```\n{result}\n```\n\n⚠️ 请**重启 Gateway** 使新技能生效（发送「重启 Gateway」）。"
        except Exception as e:
            return f"安装失败: {e}"

    def _delete_skill_response(self, name: str) -> str:
        """删除技能"""
        try:
            ok = openclaw_skills_service.delete_skill(name)
            if ok:
                return f"技能 **{name}** 已删除。\n\n⚠️ 请**重启 Gateway** 使变更生效。"
            return f"技能 **{name}** 不存在。"
        except Exception as e:
            return f"删除失败: {e}"

    def _toggle_skill_response(self, name: str, enabled: bool) -> str:
        """启用/禁用技能"""
        try:
            ok = openclaw_skills_service.toggle_skill(name, enabled)
            if ok:
                status = "启用" if enabled else "禁用"
                return f"技能 **{name}** 已{status}。\n\n⚠️ 请**重启 Gateway** 使变更生效。"
            return f"技能 **{name}** 配置不存在。"
        except Exception as e:
            return f"操作失败: {e}"

    def _restart_gateway_response(self) -> str:
        """重启 Gateway"""
        try:
            result = openclaw_skills_service.restart_gateway()
            return f"Gateway 重启完成：{result}"
        except Exception as e:
            return f"重启失败: {e}"

    def _gateway_status_response(self) -> str:
        """Gateway 状态"""
        try:
            status = openclaw_skills_service.get_gateway_status()
            return f"**Gateway 状态**\n- 运行: {status['status']}\n- 启动时间: {status['uptime']}"
        except Exception as e:
            return f"获取状态失败: {e}"
