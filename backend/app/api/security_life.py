"""资产防御与布局 API"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.security_life import (
    SecurityLifeProfile,
    SecurityLifeAsset,
    SecurityLifeProperty,
    SecurityLifeBasket,
    SecurityLifeCashLayer,
    SecurityLifeChecklistItem,
    SecurityLifeRedLineStatus,
)
from app.schemas.security_life import (
    ProfileUpdate, ProfileResponse,
    AssetUpdate, AssetResponse, PropertyResponse,
    PropertyCreate, PropertyUpdate,
    BasketUpdate, BasketResponse, BasketListResponse,
    CashLayerUpdate, CashLayerResponse,
    ChecklistItemCreate, ChecklistItemUpdate, ChecklistItemResponse, ChecklistListResponse,
    RedLineUpdate, RedLineResponse,
    DashboardResponse,
)
from app.api.deps import get_current_user_required

router = APIRouter()

BASKET_IDS = ["survival_cash", "global_growth", "stable_anchor", "extreme_hedge"]
CASH_LAYERS = ["T0", "T7", "T30"]


# ── Profile ──────────────────────────────────────────────

@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取或自动创建用户防御配置"""
    profile = db.query(SecurityLifeProfile).filter(
        SecurityLifeProfile.user_id == current_user.id
    ).first()
    if not profile:
        profile = SecurityLifeProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新防御配置"""
    profile = db.query(SecurityLifeProfile).filter(
        SecurityLifeProfile.user_id == current_user.id
    ).first()
    if not profile:
        profile = SecurityLifeProfile(user_id=current_user.id)
        db.add(profile)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile


# ── Assets (两层资产) ────────────────────────────────────

def _get_or_create_asset(db: Session, user_id: int) -> SecurityLifeAsset:
    asset = db.query(SecurityLifeAsset).filter(
        SecurityLifeAsset.user_id == user_id
    ).first()
    if not asset:
        asset = SecurityLifeAsset(user_id=user_id)
        db.add(asset)
        db.commit()
        db.refresh(asset)
    return asset


def _compute_asset_response(asset: SecurityLifeAsset) -> dict:
    """计算第一层总额和第二层占比"""
    first_layer = (asset.career_valuation or 0)
    for p in asset.properties:
        first_layer += p.valuation or 0
    total = first_layer + (asset.second_layer_total or 0)
    share = ((asset.second_layer_total or 0) / total * 100) if total > 0 else None
    return {"first_layer_total": first_layer, "second_layer_share": share}


@router.get("/assets", response_model=AssetResponse)
def get_assets(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取两层资产"""
    asset = _get_or_create_asset(db, current_user.id)
    computed = _compute_asset_response(asset)
    resp = AssetResponse.model_validate(asset)
    resp.first_layer_total = computed["first_layer_total"]
    resp.second_layer_share = computed["second_layer_share"]
    return resp


@router.put("/assets", response_model=AssetResponse)
def update_assets(
    data: AssetUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新职业/股权 & 第二层总额"""
    asset = _get_or_create_asset(db, current_user.id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)

    computed = _compute_asset_response(asset)
    resp = AssetResponse.model_validate(asset)
    resp.first_layer_total = computed["first_layer_total"]
    resp.second_layer_share = computed["second_layer_share"]
    return resp


# ── Properties ───────────────────────────────────────────

@router.post("/properties", response_model=PropertyResponse)
def add_property(
    data: PropertyCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """添加房产"""
    asset = _get_or_create_asset(db, current_user.id)
    prop = SecurityLifeProperty(
        asset_id=asset.id,
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.put("/properties/{prop_id}", response_model=PropertyResponse)
def update_property(
    prop_id: int,
    data: PropertyUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新房产"""
    prop = db.query(SecurityLifeProperty).filter(
        SecurityLifeProperty.id == prop_id
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="房产不存在")
    if prop.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(prop, key, value)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/properties/{prop_id}")
def delete_property(
    prop_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除房产"""
    prop = db.query(SecurityLifeProperty).filter(
        SecurityLifeProperty.id == prop_id
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="房产不存在")
    if prop.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")

    db.delete(prop)
    db.commit()
    return {"message": "已删除"}


# ── Baskets (资产篮子) ───────────────────────────────────

def _ensure_baskets(db: Session, user_id: int) -> List[SecurityLifeBasket]:
    """确保4个篮子都存在"""
    existing = db.query(SecurityLifeBasket).filter(
        SecurityLifeBasket.user_id == user_id
    ).all()
    existing_ids = {b.basket_id for b in existing}

    for bid in BASKET_IDS:
        if bid not in existing_ids:
            db.add(SecurityLifeBasket(user_id=user_id, basket_id=bid))

    if len(existing_ids) < len(BASKET_IDS):
        db.commit()

    return db.query(SecurityLifeBasket).filter(
        SecurityLifeBasket.user_id == user_id
    ).all()


@router.get("/baskets", response_model=BasketListResponse)
def get_baskets(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取四大篮子"""
    baskets = _ensure_baskets(db, current_user.id)
    total = sum(b.amount or 0 for b in baskets)
    return BasketListResponse(
        baskets=[BasketResponse.model_validate(b) for b in baskets],
        total=total,
    )


@router.put("/baskets/{basket_id}", response_model=BasketResponse)
def update_basket(
    basket_id: str,
    data: BasketUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新篮子金额/自定义区间"""
    if basket_id not in BASKET_IDS:
        raise HTTPException(status_code=400, detail=f"无效篮子ID: {basket_id}")

    _ensure_baskets(db, current_user.id)
    basket = db.query(SecurityLifeBasket).filter(
        SecurityLifeBasket.user_id == current_user.id,
        SecurityLifeBasket.basket_id == basket_id,
    ).first()

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(basket, key, value)

    db.commit()
    db.refresh(basket)
    return basket


# ── Cash Layers (三层现金水库) ────────────────────────────

@router.get("/cash-layers", response_model=List[CashLayerResponse])
def get_cash_layers(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取三层现金"""
    layers = db.query(SecurityLifeCashLayer).filter(
        SecurityLifeCashLayer.user_id == current_user.id
    ).all()
    return layers


@router.put("/cash-layers", response_model=List[CashLayerResponse])
def update_cash_layers(
    data: CashLayerUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """批量更新三层现金"""
    for item in data.layers:
        if item.layer not in CASH_LAYERS:
            raise HTTPException(status_code=400, detail=f"无效层级: {item.layer}")

    for item in data.layers:
        existing = db.query(SecurityLifeCashLayer).filter(
            SecurityLifeCashLayer.user_id == current_user.id,
            SecurityLifeCashLayer.layer == item.layer,
        ).first()

        if existing:
            existing.amount = item.amount
            existing.institution = item.institution
            existing.note = item.note
        else:
            db.add(SecurityLifeCashLayer(
                user_id=current_user.id,
                layer=item.layer,
                amount=item.amount,
                institution=item.institution,
                note=item.note,
            ))

    db.commit()
    return db.query(SecurityLifeCashLayer).filter(
        SecurityLifeCashLayer.user_id == current_user.id
    ).all()


# ── Checklist (90天清单) ──────────────────────────────────

# 默认清单模板 (GPT Pro 5系统 × 3阶段)
DEFAULT_CHECKLIST = [
    # 第 0-2 周
    {"id": "c01", "phase": "0-2", "system_id": 2, "label": "按流动性分类资产：T+0 / T+7 / T+30 / 不可动",
     "detail": "按 流动性/币种/对手方/司法辖区/所有权结构 五维展开一张家庭资产负债表"},
    {"id": "c02", "phase": "0-2", "system_id": 3, "label": "按对手方汇总敞口：银行 A/B、券商 A/B、保险、非标管理人",
     "detail": "设定「单一机构暴露上限」（银行/券商/理财/信托各一条）"},
    {"id": "c03", "phase": "0-2", "system_id": 2, "label": "标注：哪些资产「看起来是钱、但其实取不出来」",
     "detail": "理财/信托/私募/非标 的展期、赎回限制、底层穿透"},
    {"id": "c04", "phase": "0-2", "system_id": 1, "label": "网络安全：重要账户独立密码、2FA、硬件 Key（如 YubiKey）",
     "detail": "金融账户使用独立手机+独立手机号，不装娱乐/不连公共 Wi-Fi"},
    {"id": "c05", "phase": "0-2", "system_id": 1, "label": "72 小时应急包 + 证件离线备份完成",
     "detail": "水、常用药、慢病药、现金、充电电源、应急照明、简易食品；U 盘加密/纸质复印件分地点存放"},
    {"id": "c06", "phase": "0-2", "system_id": 1, "label": "家人反诈训练 + 家庭联络树 + 交通替代路线",
     "detail": "任何「公安/银行/客服」来电一律挂断后回拨官方电话；集合点、联系人清单"},
    # 第 3-6 周
    {"id": "c07", "phase": "3-6", "system_id": 2, "label": "把生活费储备做到 18–24 个月（T+0/T+7/T+30 分层到账）",
     "detail": "T+0 覆盖 3-6 月，T+7 覆盖 6-12 月，T+30 覆盖 6-12 月"},
    {"id": "c08", "phase": "3-6", "system_id": 2, "label": "每家银行/对手方设暴露上限（参考 50 万存款保险逻辑拆分）",
     "detail": "存款保险不覆盖理财/信托/资管产品——这类属于对手方风险更高的层"},
    {"id": "c09", "phase": "3-6", "system_id": 3, "label": "清理高不确定性非标与「期限错配」产品",
     "detail": "梳理并减少「会锁死的钱」，宁可少赚也要能动"},
    {"id": "c10", "phase": "3-6", "system_id": 1, "label": "检查高端医疗险（覆盖海外）与定期寿险",
     "detail": "资产配置若不把重疾概率、家庭照护、继承执行成本算进去，都是纸面收益"},
    {"id": "c11", "phase": "3-6", "system_id": 3, "label": "复核所有个人担保/代持/抽屉协议",
     "detail": "高管最容易忽略的雷：税务穿透、关联交易、利益冲突"},
    {"id": "c12", "phase": "3-6", "system_id": 4, "label": "房产杠杆评估：非核心投资盘逐步压缩",
     "detail": "下行周期杠杆是脆弱性放大器，降杠杆优先级高于加仓"},
    # 第 7-12 周
    {"id": "c13", "phase": "7-12", "system_id": 5, "label": "香港身份：评估高才通/优才并开始材料准备",
     "detail": "收入证明、税单、学历认证；A 类首次逗留 36 个月，B/C 类 24 个月"},
    {"id": "c14", "phase": "7-12", "system_id": 5, "label": "飞香港开户（中银香港+汇丰/渣打）；开立境外券商账户",
     "detail": "账户体系与分仓规则：至少两家机构、交易仓与长期仓分离"},
    {"id": "c15", "phase": "7-12", "system_id": 5, "label": "开始建立境外可用资金池（合规通道与真实用途申报）",
     "detail": "年度便利化额度管理（等值 5 万美元/人/年），资金来源/用途/税务凭证链条可解释"},
    {"id": "c16", "phase": "7-12", "system_id": 3, "label": "权益仓采用核心-卫星架构上线",
     "detail": "核心仓：全球宽基指数；卫星仓：AI/科技主题（上限权益仓 20-30%）"},
    {"id": "c17", "phase": "7-12", "system_id": 3, "label": "建立定投：海外券商自动定投标普 500/纳指 100",
     "detail": "主题仓暴涨止盈回核心仓；暴跌也不影响家庭系统运行"},
    {"id": "c18", "phase": "7-12", "system_id": 1, "label": "黄金入库：少量实物金条存放在非银行的物理安全处",
     "detail": "防信用崩塌/地缘冲突的极端对冲"},
    {"id": "c19", "phase": "7-12", "system_id": 4, "label": "若需「第二落点」：距核心城市1-2小时、医疗强、交通强，优先租非买",
     "detail": "避险需要可达性、医疗与稳定供应链，而不是「远」"},
]


@router.post("/checklist/init", response_model=ChecklistListResponse)
def init_checklist(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """初始化默认清单项（幂等操作）"""
    existing_defaults = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.user_id == current_user.id,
        SecurityLifeChecklistItem.is_default == True,
    ).all()
    existing_ids = {item.default_item_id for item in existing_defaults}

    for idx, item_def in enumerate(DEFAULT_CHECKLIST):
        if item_def["id"] not in existing_ids:
            db.add(SecurityLifeChecklistItem(
                user_id=current_user.id,
                phase=item_def["phase"],
                system_id=item_def["system_id"],
                label=item_def["label"],
                detail=item_def.get("detail"),
                is_default=True,
                default_item_id=item_def["id"],
                sort_order=idx,
            ))

    db.commit()
    return _get_checklist_response(db, current_user.id)


def _get_checklist_response(db: Session, user_id: int) -> ChecklistListResponse:
    items = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.user_id == user_id
    ).order_by(SecurityLifeChecklistItem.phase, SecurityLifeChecklistItem.sort_order).all()

    completed_count = sum(1 for i in items if i.completed)
    phases = {}
    systems = {}
    for i in items:
        # Phase stats
        if i.phase not in phases:
            phases[i.phase] = {"total": 0, "completed": 0}
        phases[i.phase]["total"] += 1
        if i.completed:
            phases[i.phase]["completed"] += 1
        # System stats
        sid = str(i.system_id)
        if sid not in systems:
            systems[sid] = {"total": 0, "completed": 0}
        systems[sid]["total"] += 1
        if i.completed:
            systems[sid]["completed"] += 1

    return ChecklistListResponse(
        items=[ChecklistItemResponse.model_validate(i) for i in items],
        total=len(items),
        completed_count=completed_count,
        phases=phases,
        systems=systems,
    )


@router.get("/checklist", response_model=ChecklistListResponse)
def get_checklist(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取清单（自动初始化默认项）"""
    existing = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.user_id == current_user.id,
    ).count()
    if existing == 0:
        return init_checklist(current_user=current_user, db=db)
    return _get_checklist_response(db, current_user.id)


@router.post("/checklist", response_model=ChecklistItemResponse)
def add_checklist_item(
    data: ChecklistItemCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """添加自定义清单项"""
    max_order = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.user_id == current_user.id
    ).count()

    item = SecurityLifeChecklistItem(
        user_id=current_user.id,
        phase=data.phase,
        system_id=data.system_id,
        label=data.label,
        detail=data.detail,
        is_default=False,
        sort_order=max_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    item_id: int,
    data: ChecklistItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新清单项"""
    item = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="清单项不存在")
    if item.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改")

    update_data = data.model_dump(exclude_unset=True)
    if "completed" in update_data:
        if update_data["completed"] and not item.completed:
            update_data["completed_at"] = datetime.now(timezone.utc)
        elif not update_data["completed"]:
            update_data["completed_at"] = None

    # 默认项只允许修改 completed 和 sort_order
    if item.is_default:
        allowed = {"completed", "completed_at", "sort_order"}
        update_data = {k: v for k, v in update_data.items() if k in allowed}

    for key, value in update_data.items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/checklist/{item_id}")
def delete_checklist_item(
    item_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除自定义清单项（默认项不可删除）"""
    item = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="清单项不存在")
    if item.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")
    if item.is_default:
        raise HTTPException(status_code=400, detail="默认项不可删除")

    db.delete(item)
    db.commit()
    return {"message": "已删除"}


@router.patch("/checklist/{item_id}/toggle", response_model=ChecklistItemResponse)
def toggle_checklist_item(
    item_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """切换清单项完成状态"""
    item = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="清单项不存在")
    if item.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    item.completed = not item.completed
    item.completed_at = datetime.now(timezone.utc) if item.completed else None
    db.commit()
    db.refresh(item)
    return item


# ── Red Lines (三条红线) ──────────────────────────────────

def _ensure_red_lines(db: Session, user_id: int) -> List[SecurityLifeRedLineStatus]:
    existing = db.query(SecurityLifeRedLineStatus).filter(
        SecurityLifeRedLineStatus.user_id == user_id
    ).all()
    existing_ids = {r.line_id for r in existing}

    for lid in [1, 2, 3]:
        if lid not in existing_ids:
            db.add(SecurityLifeRedLineStatus(user_id=user_id, line_id=lid))

    if len(existing_ids) < 3:
        db.commit()

    return db.query(SecurityLifeRedLineStatus).filter(
        SecurityLifeRedLineStatus.user_id == user_id
    ).order_by(SecurityLifeRedLineStatus.line_id).all()


@router.get("/red-lines", response_model=List[RedLineResponse])
def get_red_lines(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取三条红线状态"""
    return _ensure_red_lines(db, current_user.id)


@router.put("/red-lines/{line_id}", response_model=RedLineResponse)
def update_red_line(
    line_id: int,
    data: RedLineUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新红线状态"""
    if line_id not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="无效红线ID")

    _ensure_red_lines(db, current_user.id)
    rl = db.query(SecurityLifeRedLineStatus).filter(
        SecurityLifeRedLineStatus.user_id == current_user.id,
        SecurityLifeRedLineStatus.line_id == line_id,
    ).first()

    rl.status = data.status
    rl.value_json = data.value_json
    rl.checked_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(rl)
    return rl


# ── Dashboard (总览) ──────────────────────────────────────

@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取总览数据（全部 KPI）"""
    uid = current_user.id

    # Profile
    profile = db.query(SecurityLifeProfile).filter(
        SecurityLifeProfile.user_id == uid
    ).first()
    monthly_expense = profile.monthly_expense if profile else 0

    # Assets
    asset = db.query(SecurityLifeAsset).filter(
        SecurityLifeAsset.user_id == uid
    ).first()
    first_layer = 0
    second_layer = 0
    if asset:
        first_layer = asset.career_valuation or 0
        for p in asset.properties:
            first_layer += p.valuation or 0
        second_layer = asset.second_layer_total or 0
    total_asset = first_layer + second_layer
    second_share = (second_layer / total_asset * 100) if total_asset > 0 else None

    # Baskets
    baskets = db.query(SecurityLifeBasket).filter(
        SecurityLifeBasket.user_id == uid
    ).all()
    basket_total = sum(b.amount or 0 for b in baskets)

    # Cash Layers
    cash_layers = db.query(SecurityLifeCashLayer).filter(
        SecurityLifeCashLayer.user_id == uid
    ).all()

    # 现金跑道 = 生存现金桶 / 月支出
    survival = next((b for b in baskets if b.basket_id == "survival_cash"), None)
    survival_amount = survival.amount if survival else 0
    cash_runway = (survival_amount / monthly_expense) if monthly_expense > 0 else None

    # Checklist
    all_items = db.query(SecurityLifeChecklistItem).filter(
        SecurityLifeChecklistItem.user_id == uid
    ).all()
    checklist_total = len(all_items)
    checklist_completed = sum(1 for i in all_items if i.completed)

    # Red Lines
    red_lines = _ensure_red_lines(db, uid)

    # 自动计算红线 1（现金流跑道）
    rl1 = next((r for r in red_lines if r.line_id == 1), None)
    if rl1 and cash_runway is not None:
        rl1.status = "met" if cash_runway >= 18 else ("partial" if cash_runway >= 12 else "unmet")
        rl1.value_json = json.dumps({"months": round(cash_runway, 1)})
        db.commit()

    return DashboardResponse(
        red_lines=[RedLineResponse.model_validate(r) for r in red_lines],
        first_layer_total=first_layer,
        second_layer_total=second_layer,
        second_layer_share=second_share,
        basket_total=basket_total,
        baskets=[BasketResponse.model_validate(b) for b in baskets],
        cash_layers=[CashLayerResponse.model_validate(c) for c in cash_layers],
        cash_runway_months=round(cash_runway, 1) if cash_runway else None,
        checklist_total=checklist_total,
        checklist_completed=checklist_completed,
        monthly_expense=monthly_expense,
    )
