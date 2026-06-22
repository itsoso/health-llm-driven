"""外卖下单 OpenClaw skill 网关 —— P5 external-action `food_order` 的执行接缝(本期 = STUB)。

⚠️ 这是**交接契约**:真正的下单由另一团队开发的「外卖 OpenClaw skill」执行,
该 skill 在用户已授权的、**用户自有的外卖账号**下运行,后端**永不**处理支付凭据、
永不扣款、永不替用户下单。本文件是后端侧调用该 skill 的唯一接缝。

本期(P5)skill 契约尚未就绪 → `place_order` 直接 `raise NotImplementedError`。
write_intent_service 的 food_order confirm 分支**根本不调本网关**(确认只产出良性
"acknowledged" 草稿态,绝无任何下单/支付代码路径)—— 本网关在,是为了:
  1. 把外卖 skill 契约钉在代码里(团队据此实现);
  2. 让财务路径在代码上可证为惰性(inert):整个仓库里唯一能"下单"的入口恒抛
     NotImplementedError,没有任何调用方能走到真实下单/支付。

────────────────────────────────────────────────────────────────────────
外卖 skill 契约(团队需提供的接口形态,实现期对齐)
────────────────────────────────────────────────────────────────────────
调用方向:backend(本网关)──▶ OpenClaw Gateway ──▶ 外卖 skill(用户账号)

入参(EXPECTED INPUT):
    user_id: int                本系统用户 id(把订单回链健康对象 + 审计)
    dish_summary: str           菜品/套餐摘要(用户已确认的可见摘要,非处方)
    merchant: str | None        商家名(SKU 选择辅助)
    delivery_address_ref: str   用户已授权的配送地址引用(opaque token,由 OpenClaw
        | None                  账号绑定层提供;后端不存明文地址即可 —— L3 数据按 user_id 隔离)
    confirmation_token: str     本次逐笔强确认的一次性 token(human-in-the-loop 证明,
                                绑定到 WriteIntent.id + user_id,服务端签发,防重放)

出参(EXPECTED OUTPUT,dict):
    {
        "status": "placed" | "failed",
        "order_id": str | None,            # 外卖订单号,成功时非空
        "estimated_delivery": str | None,  # ISO 时间,可空
        "error": str | None,               # status=failed 时的非敏感原因
    }

鉴权(AUTH):
    skill 以用户自有外卖账号身份运行(OpenClaw 账号绑定);后端只传 address_ref +
    一次性 confirmation_token,**不传** 支付密码 / 银行卡 / 任何支付凭据。

失败语义:
    - 契约/网关层不可恢复错误 → 抛 `FoodOrderSkillError`(调用方记 failed + notes)。
    - 业务下单失败(售罄/打烊)→ 返回 {"status":"failed", "error": ...}。
"""
from __future__ import annotations

from typing import Optional


class FoodOrderSkillError(Exception):
    """外卖 skill 调用失败(网关/契约层不可恢复错误)。

    调用方捕获后把意图置 failed 并记 notes —— 不假装成功。
    与 NotImplementedError 区分:后者是「本期 skill 未就绪」的财务硬门(API→501)。
    """


async def place_order(
    *,
    user_id: int,
    dish_summary: str,
    merchant: Optional[str] = None,
    delivery_address_ref: Optional[str] = None,
    confirmation_token: str = "",
) -> dict:
    """调外卖 skill 下单。**本期 = STUB,恒抛 NotImplementedError(财务硬门)。**

    契约(入参/出参/鉴权)见模块 docstring —— 团队据此实现该 skill 后,把本函数体
    换成真实的 OpenClaw skill 调用。在此之前,**没有任何调用方**会走到这里下单:
    food_order 的 confirm 分支不调本函数,只产出良性 acknowledged 草稿态。

    Returns(契约就绪后):
        {"status": "placed"|"failed", "order_id": str|None,
         "estimated_delivery": str|None, "error": str|None}

    Raises:
        NotImplementedError: 本期恒抛 —— skill 契约未就绪(财务硬边界,API 转 501)。
        FoodOrderSkillError: 契约就绪后,网关/契约层不可恢复错误时抛。
    """
    raise NotImplementedError(
        "外卖 skill 契约未就绪:P5 仅搭建到下单接缝为止,真实下单由团队开发的"
        "外卖 OpenClaw skill(用户自有账号)执行。在 skill 就绪并通过财务安全评审前,"
        "本网关恒抛 NotImplementedError —— 后端不下单、不扣款、不处理支付凭据。"
    )
