"""饮食记录图片 URL 签名 —— 单一真源。

原本内联在 `app/api/diet.py::_diet_response_image_url`。D1(garmin-sync 治理 Wave 3)把
diet 读维度迁进程内直读时抽到这里,让 api 层的 `_convert_to_response` 与 service 层
(`agent_read_tools._diet_record_to_response`)共用**同一实现**。

为何必须共享而非复刻:签名 URL 内嵌 `expires=now+TTL`,**非确定性** → golden-master 无法
逐字节比对该字段(两次调用签名必不同)。若 api 与 reader 各持一份复刻,规范路径前缀逻辑
一旦漂移将**静默且测不出**。共用同一函数对象 → 该字段安全 by construction(零漂移)。
"""
from __future__ import annotations

from urllib.parse import urlsplit


def diet_response_image_url(image_url: str | None, owner_id: int) -> str | None:
    """仅对 owner 编码在路径里的规范路径签名(Sign only canonical paths whose owner is
    encoded in the path itself)。"""
    from app.services.private_uploads import refresh_private_upload_url

    if not image_url:
        return None
    path = urlsplit(str(image_url)).path
    canonical_prefix = f"/api/v1/upload/files/diet/{int(owner_id)}/"
    if not path.startswith(canonical_prefix):
        return None
    return refresh_private_upload_url(image_url, "diet", owner_id)
