"""
化验指标异常规则。

Twin.labs.flagged_abnormal 已经是收集到的异常项列表。这一层做两件事：
1. 按医学严重度对异常项升级（例如肝酶 >3x ULN 比 1.5x ULN 严重）
2. 识别关联模式（肝酶三联升高 = 肝细胞损伤提示）
"""

from typing import Any, Dict, List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import HealthTwin


# ─────────────────────── 通用工具 ─────────────────────────


def _find_item(
    abnormals: List[Dict[str, Any]], name_keywords: List[str]
) -> Optional[Dict[str, Any]]:
    """在异常项列表里按中文/英文关键字查找匹配项。"""
    for item in abnormals:
        name = (item.get("item_name") or "").lower()
        for kw in name_keywords:
            if kw.lower() in name:
                return item
    return None


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _uric_acid_umol(raw: float) -> float:
    """血尿酸归一化到 μmol/L。<25 视为 mg/dL 换算(×59.48);否则当 μmol/L。

    尿酸实测范围:mg/dL ~1-25(极值肿瘤溶解 ~20)、μmol/L ~120-1000。25 是干净分界——
    边界 [25,50) 对两种单位都不合理(疑数据错),保守当 μmol/L(其值远低于 420,不会假告警)。
    """
    return raw * 59.48 if raw < 25 else raw


def _find_standard_hba1c(abnormals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """只匹配标准糖化 (NGSP A1c, code=glucose_hba1c), 排除总糖化 HbA1。

    历史误判: 子串匹配 ``"糖化血红蛋白" in name`` 会把「糖化血红蛋白A1」(总糖化 HbA1,
    参考 6.3–9.0%, 与标准 A1c 是不同指标) 也吞进来 —— 它的正常值 7.0% 落进 ≥6.5%
    的糖尿病阈值, 产生假 CRITICAL 告警。这里改用 biomarker 归一化层的 ``resolve_code``,
    它把「糖化血红蛋白A1c」→ glucose_hba1c、「糖化血红蛋白A1」→ glucose_hba1_total
    精确分流 (见 app/biomarkers/definitions.py)。

    安全兜底 (不让本规则单点依赖 resolve_code, 避免漏报真糖尿病):
      - resolve_code 明确判成 glucose_hba1_total → 是总糖化, 直接跳过。
      - resolve_code 没认成糖化 (例如英文 "Hemoglobin A1c" 被最长子串规则判成 hemoglobin)
        时, 用关键字「a1c / hba1c」补救识别标准 A1c —— 这两个标记里都含 "c", 天然排除了
        总糖化的「A1」「HbA1」形态。
    """
    from app.biomarkers.definitions import resolve_code

    for item in abnormals:
        name = item.get("item_name") or ""
        code = resolve_code(name)
        if code == "glucose_hba1c":
            return item
        if code == "glucose_hba1_total":
            continue  # 总糖化 HbA1, 明确排除
        low = name.lower()
        if "a1c" in low or "hba1c" in low:
            return item
    return None


# ─────────────────────── 肝酶三联 ─────────────────────────


@register
def liver_enzyme_pattern(twin: HealthTwin) -> Optional[Alert]:
    """
    肝细胞损伤模式识别：ALT / AST / GGT 同时升高。

    经典阈值（ULN ≈ 40 U/L）：
      - < 1.5× ULN: mild（无需停药，但要复查）
      - 1.5-3×: moderate（检查原因）
      - 3-5×: high（可能需要停药评估）
      - ≥5×: critical（立即就医）
    """
    abns = twin.labs.flagged_abnormal or []
    if not abns:
        return None

    alt = _find_item(abns, ["谷丙转氨酶", "ALT", "丙氨酸氨基转移酶"])
    ast = _find_item(abns, ["谷草转氨酶", "AST", "天冬氨酸氨基转移酶"])
    ggt = _find_item(abns, ["谷氨酰转肽酶", "GGT", "γ-谷氨酰转移酶", "γ-GT"])

    # 至少两项升高才触发
    hits = [x for x in (alt, ast, ggt) if x is not None]
    if len(hits) < 2:
        return None

    # 估算最高倍数（ULN 假设为 40）
    def ratio(item: Optional[Dict[str, Any]]) -> Optional[float]:
        if not item:
            return None
        v = _as_float(item.get("value"))
        return v / 40.0 if v is not None else None

    max_ratio = max(filter(None, [ratio(alt), ratio(ast), ratio(ggt)]), default=None)

    if max_ratio is None:
        return None

    if max_ratio >= 5:
        severity = Severity.CRITICAL
        requires_doc = True
        action = "立即就诊消化/肝病专科评估原因（病毒性肝炎、药物性肝损、脂肪肝进展、胆管问题等），期间避免一切肝毒性药物和酒精。"
    elif max_ratio >= 3:
        severity = Severity.HIGH
        requires_doc = True
        action = "2 周内复查肝功能；排查近期新用药、保健品、酒精摄入；超声筛查脂肪肝/胆管。就诊内科或消化科。"
    elif max_ratio >= 1.5:
        severity = Severity.MEDIUM
        requires_doc = False
        action = "4-6 周后复查；减少饱和脂肪/糖/酒精；评估补剂中有无已知肝毒成分（红曲米、kava、高剂量绿茶提取物等）。"
    else:
        severity = Severity.LOW
        requires_doc = False
        action = "1-3 个月后复查；保持规律饮食运动即可。"

    parts = []
    for name, item in (("ALT", alt), ("AST", ast), ("GGT", ggt)):
        if item:
            parts.append(f"{name} {item.get('value')} {item.get('unit', '')}".strip())

    msg_head = "、".join(parts)

    return Alert(
        rule_id="labs.liver_enzyme_pattern",
        category="labs",
        severity=severity,
        title="肝酶组合升高",
        message=(
            f"检出肝酶升高（{msg_head}）。同时 ≥2 项升高提示肝细胞或胆管层面的损伤。"
            f"最高倍数约为 ULN 的 {max_ratio:.1f}×。常见原因："
            "脂肪肝、酒精、药物/保健品、病毒性肝炎、胆管梗阻等。"
        ),
        action=action,
        data_citation={"alt": alt, "ast": ast, "ggt": ggt, "max_ratio_over_uln": round(max_ratio, 2)},
        references=[
            "https://www.aasld.org/sites/default/files/2019-06/AASLD-LFTs-Guidance.pdf",
        ],
        requires_medical_attention=requires_doc,
    )


# ─────────────────────── 血脂 ─────────────────────────────


@register
def ldl_high(twin: HealthTwin) -> Optional[Alert]:
    """LDL 偏高 —— 从 flagged_abnormal 或 labs 顶层字段中取。"""
    abns = twin.labs.flagged_abnormal or []
    ldl_item = _find_item(abns, ["LDL", "低密度脂蛋白"])
    ldl_val = _as_float(ldl_item.get("value")) if ldl_item else twin.labs.ldl

    if ldl_val is None:
        return None

    if ldl_val >= 4.9:  # mmol/L, 约 190 mg/dL
        severity = Severity.HIGH
        level = "极高"
        action = "就诊心内科评估是否启动他汀类治疗；同时改善饮食（减饱和脂肪，增膳食纤维）；有家族性高胆固醇需家系筛查。"
    elif ldl_val >= 4.1:  # 约 160 mg/dL
        severity = Severity.MEDIUM
        level = "偏高"
        action = "3 个月生活方式调整（地中海饮食、每周 150 分钟有氧）后复查；评估心血管 10 年风险。"
    elif ldl_val >= 3.4:  # 约 130 mg/dL
        severity = Severity.LOW
        level = "轻度偏高"
        action = "改善饮食结构即可，半年后复查。"
    else:
        return None

    return Alert(
        rule_id="labs.ldl_high",
        category="labs",
        severity=severity,
        title=f"LDL {level}",
        message=(
            f"低密度脂蛋白胆固醇（LDL-C）{ldl_val} mmol/L。LDL 是心血管风险的核心指标，"
            "持续偏高会加速动脉粥样硬化。"
        ),
        action=action,
        data_citation={"ldl": ldl_val},
        references=[
            "https://www.acc.org/latest-in-cardiology/ten-points-to-remember/2018/11/09/14/28/2018-guideline-on-management-of-blood-cholesterol",
        ],
    )


# ─────────────────────── 血糖 ─────────────────────────────


@register
def hba1c_diabetes_range(twin: HealthTwin) -> Optional[Alert]:
    """糖化血红蛋白进入糖尿病/前期区间。"""
    abns = twin.labs.flagged_abnormal or []
    item = _find_standard_hba1c(abns)
    val = _as_float(item.get("value")) if item else twin.labs.hba1c
    if val is None:
        return None

    if val >= 6.5:
        return Alert(
            rule_id="labs.hba1c_diabetes",
            category="labs",
            severity=Severity.HIGH,
            title="糖化血红蛋白达糖尿病标准",
            message=f"HbA1c {val}%，≥6.5% 是糖尿病的诊断阈值。",
            action="就诊内分泌科确认诊断（需两次非同日检测或伴高血糖症状），启动饮食、运动和可能的药物干预。",
            data_citation={"hba1c": val},
            references=["https://diabetesjournals.org/care/article/47/Supplement_1/S20/153952/"],
            requires_medical_attention=True,
        )
    if val >= 5.7:
        return Alert(
            rule_id="labs.hba1c_prediabetes",
            category="labs",
            severity=Severity.MEDIUM,
            title="糖化血红蛋白进入糖尿病前期",
            message=f"HbA1c {val}%。5.7-6.4% 为糖尿病前期，干预得当可以逆转。",
            action="减重 5-7%、每周 150 分钟中等强度有氧；限制精制碳水和含糖饮料；3-6 个月后复查。",
            data_citation={"hba1c": val},
        )
    return None


# ─────────────────────── 肾功能 ─────────────────────────


@register
def kidney_function_decline(twin: HealthTwin) -> Optional[Alert]:
    """eGFR 或肌酐提示肾功能下降。"""
    abns = twin.labs.flagged_abnormal or []
    egfr_item = _find_item(abns, ["eGFR", "肾小球滤过率"])
    creat_item = _find_item(abns, ["肌酐", "Cr", "Creatinine"])

    egfr = _as_float(egfr_item.get("value")) if egfr_item else None
    creat = _as_float(creat_item.get("value")) if creat_item else None

    if egfr is not None and egfr < 60:
        if egfr < 30:
            sev, level, action = (
                Severity.HIGH,
                "显著下降",
                "尽快就诊肾内科；避免肾毒性药物（某些抗生素、NSAID、造影剂）；根据 GFR 调整药物剂量。",
            )
        elif egfr < 45:
            sev, level, action = (
                Severity.MEDIUM,
                "中度下降",
                "就诊肾内科；控制血压 < 130/80；限制蛋白摄入；避免 NSAID。",
            )
        else:
            sev, level, action = (
                Severity.MEDIUM,
                "轻度下降",
                "复查确认；控制血压、血糖；避免肾毒性药物。",
            )
        return Alert(
            rule_id="labs.egfr_decline",
            category="labs",
            severity=sev,
            title=f"肾功能{level}",
            message=f"eGFR {egfr} ml/min/1.73m²，低于 60 提示慢性肾病（CKD）风险。",
            action=action,
            data_citation={"egfr": egfr, "creatinine": creat},
            requires_medical_attention=(sev >= Severity.HIGH),
        )

    return None


# ─────────────────────── 白细胞 ─────────────────────────


@register
def wbc_pattern_lymphocytosis(twin: HealthTwin) -> Optional[Alert]:
    """
    淋巴细胞比例升高 + 中性粒细胞比例下降。
    常见于病毒感染后恢复期、慢性炎症或血液系统问题。
    """
    abns = twin.labs.flagged_abnormal or []
    lymph = _find_item(abns, ["淋巴细胞比例", "淋巴细胞百分"])
    neut = _find_item(abns, ["中性粒细胞比例", "中性粒细胞百分"])
    if not lymph or not neut:
        return None

    lymph_v = _as_float(lymph.get("value"))
    neut_v = _as_float(neut.get("value"))
    if lymph_v is None or neut_v is None:
        return None

    if lymph_v > 40 and neut_v < 50:
        return Alert(
            rule_id="labs.wbc_lymphocytosis",
            category="labs",
            severity=Severity.LOW,
            title="白细胞分类倒置：淋巴细胞偏高",
            message=(
                f"淋巴细胞比例 {lymph_v}% / 中性粒细胞比例 {neut_v}%。"
                "这种模式常见于病毒感染后恢复期或慢性免疫激活，单次偏移通常无需紧张。"
            ),
            action="若伴发热/乏力/体重下降/淋巴结肿大，建议复查血常规 + 外周血涂片；否则 1-3 个月后复查。",
            data_citation={"lymphocyte_pct": lymph_v, "neutrophil_pct": neut_v},
        )
    return None


# ─────────────────────── 红细胞系整体偏高 ─────────────────


@register
def red_cell_elevation(twin: HealthTwin) -> Optional[Alert]:
    """红细胞系统整体偏高 —— HGB 与 HCT **同向**超上限才触发(互相佐证)。

    单点红细胞值常被腕式伪影/脱水污染,只在 HGB+HCT 两项同时超标时才提示,降伪阳。
    性别感知上限(成人):男 HGB>170 g/L & HCT>50%;女 HGB>150 g/L & HCT>45%。
    Twin 无性别字段 → 用男性(更高)阈值,保守少报。

    R4:非急症 → MEDIUM;行动=血液科评估 + 复查,排除脱水/OSA/真红;明确非诊断,不给药/剂量。
    """
    hgb = _as_float(twin.labs.hemoglobin)
    hct = _as_float(twin.labs.hematocrit)
    if hgb is None or hct is None:
        return None

    # 性别未知 → 男性阈值(更高,保守)。Twin 当前无性别字段。
    hgb_uln, hct_uln = 170.0, 50.0

    if not (hgb > hgb_uln and hct > hct_uln):
        return None

    return Alert(
        rule_id="labs.red_cell_elevation",
        category="labs",
        severity=Severity.MEDIUM,
        title="红细胞系统整体偏高",
        message=(
            f"血红蛋白 {hgb:g} g/L、红细胞压积 {hct:g}% 同向偏高。"
            "红细胞系整体升高常见于脱水、慢性缺氧(含睡眠呼吸暂停/吸烟/高原),"
            "少数为真性红细胞增多症。单项升高可能是伪影,两项同向更值得关注(非诊断)。"
        ),
        action=(
            "建议复查血常规确认;到血液科评估排除脱水、慢性缺氧/睡眠呼吸暂停、真性红细胞增多等。"
            "近期可保证充足饮水。具体处置以医生意见为准。"
        ),
        data_citation={
            "hemoglobin": hgb, "hematocrit": hct,
            "hgb_uln": hgb_uln, "hct_uln": hct_uln,
        },
    )


# ─────────────────────── 其他异常项的 fallback ─────────


@register
def labs_data_stale(twin: HealthTwin) -> Optional[Alert]:
    """化验数据超过 6 个月未更新 —— 提醒复查。"""
    from datetime import date

    last_date = twin.labs.last_exam_date
    if last_date is None:
        return None

    if isinstance(last_date, str):
        try:
            last_date = date.fromisoformat(last_date)
        except ValueError:
            return None

    days_old = (date.today() - last_date).days
    if days_old < 180:
        return None

    months = days_old // 30
    return Alert(
        rule_id="labs.data_stale",
        category="labs",
        severity=Severity.INFO,
        title=f"化验数据已 {months} 个月未更新",
        message=(
            f"最近一次化验是 {last_date}（{months} 个月前）。"
            "超过 6 个月的化验数据可能已不反映当前状态，基于旧数据的告警可能不再准确。"
        ),
        action="建议安排一次复查（肝功能、血常规、血脂、血糖），更新后系统会自动用最新数据重新评估。",
        data_citation={"last_exam_date": str(last_date), "days_old": days_old},
    )


@register
def uric_acid_high(twin: HealthTwin) -> Optional[Alert]:
    """高尿酸血症 —— 血尿酸升高(痛风/尿酸性肾病/代谢综合征/心血管风险并存)。

    阈值用《中国高尿酸血症与痛风诊疗指南(2019)》性别中立标准 420 μmol/L(≈7 mg/dL)定义高尿酸血症
    —— twin.labs 无性别字段,故不用性别特异阈值。单位自动归一见 `_uric_acid_umol`(mg/dL↔μmol/L)。
    非急症 → 最高 MEDIUM,绝不 CRITICAL。
    R4:行动为生活方式 + 「降尿酸治疗由医生决定」,不出药名/剂量、不下痛风诊断。
    """
    abns = twin.labs.flagged_abnormal or []
    ua_item = _find_item(abns, ["尿酸", "uric"])
    ua_raw = _as_float(ua_item.get("value")) if ua_item else _as_float(twin.labs.uric_acid)
    if ua_raw is None or ua_raw <= 0:
        return None

    ua = _uric_acid_umol(ua_raw)  # → μmol/L(自动判别 mg/dL)
    from_flag = ua_item is not None

    if ua >= 540:  # ≈9 mg/dL,显著升高
        severity = Severity.MEDIUM
        level = "显著升高"
        extra = "显著升高会增加痛风急性发作、尿酸性肾结石与肾损伤风险。"
    elif ua >= 420:  # 高尿酸血症定义
        severity = Severity.MEDIUM
        level = "偏高（高尿酸血症)"
        extra = "高尿酸常与代谢综合征、高血压、心血管风险并存。"
    elif from_flag and ua >= 360:  # 化验已标异常的临界值(性别敏感参考下沿)
        severity = Severity.LOW
        level = "临界偏高"
        extra = "尚未达高尿酸血症标准,关注趋势。"
    else:
        return None

    return Alert(
        rule_id="labs.uric_acid_high",
        category="labs",
        severity=severity,
        title=f"血尿酸{level}",
        message=f"血尿酸 {round(ua)} μmol/L（约 {round(ua / 59.48, 1)} mg/dL）。{extra}",
        action=(
            "减少高嘌呤摄入(动物内脏/红肉/海鲜/浓肉汤)、限酒(尤其啤酒)与含果糖饮料、每日饮水 2L 以上;"
            "BMI 偏高者减重。反复关节红肿热痛或已确诊痛风,请就诊风湿科评估是否需要降尿酸治疗(用药由医生决定)。"
        ),
        data_citation={"uric_acid_umol_l": round(ua), "raw": ua_raw, "from_flagged": from_flag},
        references=["中华医学会内分泌学分会《中国高尿酸血症与痛风诊疗指南(2019)》"],
    )


@register
def uncategorized_abnormal_summary(twin: HealthTwin) -> Optional[Alert]:
    """
    通用 catch-all：对尚未被上面规则识别的异常项做温和提醒。
    避免和具体规则重复 —— 只在至少有未识别异常项时触发。
    """
    abns = twin.labs.flagged_abnormal or []
    if not abns:
        return None

    # 已被其他规则精确覆盖的关键字
    covered = [
        "谷丙转氨酶", "谷草转氨酶", "谷氨酰转肽酶", "ALT", "AST", "GGT",
        "LDL", "低密度",
        "eGFR", "肾小球", "肌酐",
        "淋巴细胞比例", "中性粒细胞比例",
    ]

    def _covered(item: Dict[str, Any]) -> bool:
        name = item.get("item_name") or ""
        if any(kw in name for kw in covered):
            return True
        # 尿酸: **值感知**去重 —— 只在 uric_acid_high 会触发(归一化 ≥360)时才算已覆盖;
        # 否则(flagged 但 <360、或低尿酸/数据缺失)让它落到本兜底,**绝不静默丢**(评审 BLOCKING:
        # 加 "尿酸" 进静态 covered 会把规则不触发的 flagged 尿酸一并抹掉 → under-alarm)。
        if "尿酸" in name or "uric" in name.lower():
            ua_raw = _as_float(item.get("value"))
            return ua_raw is not None and ua_raw > 0 and _uric_acid_umol(ua_raw) >= 360
        # 糖化只把「标准 A1c」算作已覆盖 (hba1c_diabetes_range 处理); 总糖化 HbA1 不是
        # 该规则的指标, 不能因子串「糖化血红蛋白」被当成已覆盖而静默丢弃 —— 让它落到本兜底。
        from app.biomarkers.definitions import resolve_code
        return resolve_code(name) == "glucose_hba1c"

    remaining = [it for it in abns if not _covered(it)]
    if not remaining:
        return None

    names = [it.get("item_name") for it in remaining[:5] if it.get("item_name")]
    if not names:
        return None

    return Alert(
        rule_id="labs.uncategorized_abnormal",
        category="labs",
        severity=Severity.LOW,
        title=f"化验单还有 {len(remaining)} 项异常未分类",
        message=(
            f"以下指标在最近化验中被标记异常：{'、'.join(names)}"
            f"{'...' if len(remaining) > 5 else ''}。"
            "它们尚未被 Safety Guardian 的规则库精确覆盖，暂未能自动裁决严重度。"
        ),
        action="建议就诊医生逐项解读，或请 AI 助理分析（Phase 1.5 长期分析师会自动处理）。",
        data_citation={"uncategorized_items": [it.get("item_name") for it in remaining]},
    )
