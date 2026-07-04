"""快手电商 Agent 网关 —— P5(D2)复购下单的执行接缝(本期 = STUB)。

⚠️ 这是**交接契约**:真正的下单未来只能由本系统受控 Agent 执行,
并且必须在用户已授权的、**用户自有的快手账号**下运行;后端**永不**处理支付凭据、
永不扣款。本文件是后端侧调用该 skill 的唯一接缝。

本期(P5 SCAFFOLD)skill 契约尚未就绪 → `place_order` 直接 `raise NotImplementedError`。
`reorder_intent_service.confirm_reorder_intent` 捕获它并让 API 返回 HTTP 501,
**绝不**把意图标成 order_placed —— 财务路径在代码上可证为惰性(inert)。

────────────────────────────────────────────────────────────────────────
快手电商 skill 契约(团队需提供的接口形态,实现期对齐)
────────────────────────────────────────────────────────────────────────
调用方向:backend(本网关)──▶ 本系统 Agent action runtime ──▶ 快手账号动作(用户授权)

入参(EXPECTED INPUT):
    supplement_id: int          本系统补剂定义 id(用于把订单回链健康对象)
    quantity: int               下单数量(>0)
    user_kuaishou_account_ref:  用户已授权的快手账号引用(opaque token / openid,
        str                     由账号授权层提供;后端不存密码/支付凭据)
    confirmation_token: str     本次逐笔强确认的一次性 token(human-in-the-loop 证明,
                                绑定到 ReorderIntent.id + user_id,服务端签发,防重放)
    brand: str | None           品牌(SKU 选择辅助)
    spec: str | None            规格

出参(EXPECTED OUTPUT,dict):
    {
        "status": "placed" | "failed",
        "order_id": str | None,            # 快手订单号,成功时非空
        "estimated_delivery": str | None,  # ISO 日期,可空
        "error": str | None,               # status=failed 时的非敏感原因
    }

鉴权(AUTH):
    Agent action 以用户自有快手账号身份运行;后端只传 account_ref +
    一次性 confirmation_token,**不传** 支付密码 / 银行卡 / 任何支付凭据。

回调(CALLBACK,异步下单态时):
    若 skill 异步落单,回调 POST /api/v1/reorder-intents/{id}/order-callback
    (本期未实现;同步返回即可。回调需带 confirmation_token 校验 + 幂等)。

失败语义:
    - 契约/网关层不可恢复错误 → 抛 `KuaishouSkillError`(service 记 order_failed + notes)。
    - 业务下单失败(库存/价格变动)→ 返回 {"status":"failed", "error": ...}(service 同上)。
"""
from __future__ import annotations

from typing import Optional


class KuaishouSkillError(Exception):
    """快手电商 skill 调用失败(网关/契约层不可恢复错误)。

    service 捕获后把 ReorderIntent 置 order_failed 并记 notes —— 不假装成功。
    与 NotImplementedError 区分:后者是「本期 skill 未就绪」的财务硬门(API→501)。
    """


async def place_order(
    *,
    supplement_id: int,
    quantity: int,
    user_kuaishou_account_ref: str,
    confirmation_token: str,
    brand: Optional[str] = None,
    spec: Optional[str] = None,
) -> dict:
    """调快手电商 skill 下单。**本期 = STUB,恒抛 NotImplementedError(财务硬门)。**

    契约(入参/出参/鉴权/回调)见模块 docstring —— 团队据此实现该 skill 后,
    把本函数体换成真实的 Agent action 调用。在此之前,任何走到这里的 confirm
    都会经 service 捕获 → API 返回 501,**不**进入 order_placed,无可执行支付路径。

    Returns(契约就绪后):
        {"status": "placed"|"failed", "order_id": str|None,
         "estimated_delivery": str|None, "error": str|None}

    Raises:
        NotImplementedError: 本期恒抛 —— skill 契约未就绪(财务硬边界,API 转 501)。
        KuaishouSkillError: 契约就绪后,网关/契约层不可恢复错误时抛。
    """
    raise NotImplementedError(
        "快手电商 skill 契约未就绪:P5 仅搭建到下单接缝为止,真实下单由团队开发的"
        "快手电商 Agent action(用户自有账号)执行。在 action 就绪并通过财务安全评审前,"
        "本网关恒抛 NotImplementedError —— 后端不下单、不扣款、不处理支付凭据。"
    )
