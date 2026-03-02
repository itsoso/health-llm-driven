"""OpenClaw 多模型分析客户端"""
import asyncio
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

OPENCLAW_ANALYZE_URL = "https://base.executor.life/api/openclaw/analyze"
OPENCLAW_STATUS_URL = "https://base.executor.life/api/openclaw/status"
OPENCLAW_ANALYZE_API_KEY = "oc-kuaishou-2026"
OPENCLAW_KIM_USER_ID = "baokun"

POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 18  # 180 seconds max (多模型分析通常需要60-120秒)


class OpenClawAnalyzeClient:
    """OpenClaw 多模型分析客户端：提交 prompt → 轮询结果"""

    async def analyze(self, prompt: str) -> Dict[str, Any]:
        """
        提交分析并轮询结果。

        Returns:
            {
                "status": "completed" | "partial" | "timeout" | "error",
                "model_results": [...],
                "aggregation": "..."
            }
        """
        batch_id = await self._submit(prompt)
        if not batch_id:
            return {"status": "error", "model_results": [], "aggregation": "提交分析失败"}

        return await self._poll(batch_id)

    async def _submit(self, prompt: str) -> Optional[str]:
        """提交分析请求，返回 batch_id"""
        payload = {
            "prompt": prompt,
            "kim_user_id": OPENCLAW_KIM_USER_ID,
            "api_key": OPENCLAW_ANALYZE_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(OPENCLAW_ANALYZE_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    batch_id = data.get("batch_id")
                    logger.info(f"[OpenClaw分析] 提交成功: batch_id={batch_id}")
                    return batch_id
                else:
                    logger.error(f"[OpenClaw分析] 提交失败: {data}")
                    return None
        except Exception as e:
            logger.error(f"[OpenClaw分析] 提交异常: {e}")
            return None

    async def _poll(self, batch_id: str) -> Dict[str, Any]:
        """轮询分析结果"""
        url = f"{OPENCLAW_STATUS_URL}/{batch_id}"
        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                status = data.get("status", "")
                logger.info(f"[OpenClaw分析] 轮询 {attempt}/{MAX_POLL_ATTEMPTS}: status={status}")

                if status in ("completed", "partial"):
                    return {
                        "status": status,
                        "model_results": data.get("model_results", []),
                        "aggregation": data.get("aggregation", ""),
                    }
            except Exception as e:
                logger.warning(f"[OpenClaw分析] 轮询异常 ({attempt}): {e}")

        return {
            "status": "timeout",
            "model_results": [],
            "aggregation": "分析超时，请稍后在运动记录中查看结果。",
        }
