from app.services.episode.protocol_registry import ProtocolAction
from app.services.episode.validator import (
    _BLOCKED_FALLBACK,
    _REDACTED_PLACEHOLDER,
    validate_actions,
    validate_text,
)


def test_validate_text_blocks_blacklist_and_replaces_output():
    result = validate_text("请给我一个处方，并调整降压药剂量 mg/kg")
    assert result.ok is False
    assert result.action == "replace"
    assert "超出我作为健康助理的安全边界" in result.safe_text
    assert result.disclaimer


def test_validate_text_appends_disclaimer_for_graylist_terms():
    result = validate_text("这个补剂可能有什么副作用？")
    assert result.ok is True
    assert result.action == "append_disclaimer"
    assert result.disclaimer
    assert result.safe_text.endswith(result.disclaimer)


def test_validate_actions_sets_disclaimer_for_graylist_keyword():
    actions = [
        ProtocolAction(
            template_id="test.action",
            action_type="intervention",
            title="关注副作用",
        )
    ]
    result = validate_actions(actions)
    assert result.ok is True
    assert result.disclaimer


# ─────────── 2026-07-12 prod 误杀修复: 否定/转诊先判 + 句级遮蔽 ───────────
# 根因: 综合分析合成里的边界话术 ("就医确诊"/"不构成诊断"/"请勿自行停药")
# 被无上下文子串匹配整篇替换成拒答模板 (agent_messages 6186/6188 实证).


class TestBoundaryLanguagePasses:
    """边界话术 (R4 转诊/否定语境) 不再触发整篇拒答."""

    def test_referral_before_term_passes(self):
        # prod 实际拦截场景: 感染期综合分析里的转诊句
        result = validate_text("如症状持续超过三天, 请及时就医确诊。")
        assert result.ok is True
        assert _BLOCKED_FALLBACK not in result.safe_text
        assert "就医确诊" in result.safe_text

    def test_negated_enumeration_passes(self):
        # 顿号列举: 否定要传播到整个列举
        result = validate_text("请勿自行停药、加药或换药, 一切调整先和医生商量。")
        assert result.ok is True
        assert "请勿自行停药、加药或换药" in result.safe_text

    def test_not_constitute_diagnosis_passes(self):
        result = validate_text("以上分析仅供参考, 不构成诊断。")
        assert result.ok is True
        assert "不构成诊断" in result.safe_text

    def test_otc_adjacent_negation_passes(self):
        # 单字否定紧邻: "非处方药" 是 OTC, 不是模型开处方
        result = validate_text("生理盐水鼻腔冲洗属于非处方护理手段。")
        assert result.ok is True
        assert "非处方" in result.safe_text

    def test_cannot_cure_passes(self):
        result = validate_text("高血压无法治愈, 但可以长期稳定控制。")
        assert result.ok is True
        assert "无法治愈" in result.safe_text

    def test_question_deferral_passes(self):
        result = validate_text("是否需要调整降压药剂量, 请与你的主治医生确认。")
        assert result.ok is True
        assert "降压药剂量" in result.safe_text

    def test_doctor_guidance_passes(self):
        result = validate_text("请在医生指导下停药, 不要自己做决定。")
        assert result.ok is True
        assert "医生指导下停药" in result.safe_text

    def test_nominal_enumeration_with_trailing_deferral_passes(self):
        # 名词化 + 后置医方转诊 (LLM 边界话术高频句式): 转诊词在逗号后
        result = validate_text("任何加药、减药或换药的决定, 都必须由医生做出。")
        assert result.ok is True
        assert "换药的决定" in result.safe_text

    def test_nominal_whether_and_timing_pass(self):
        assert validate_text("停药与否, 请听主治医生的安排。").ok is True
        assert validate_text("停药时机由医生评估决定。").ok is True

    def test_comprehensive_synthesis_with_boundary_language_survives(self):
        # 模拟 prod 被误杀的综合分析形态: 多 specialist 合成 + 结尾边界话术
        synthesis = (
            "当前你的身体处于急性感染期与慢性缺氧风险叠加状态。\n"
            "**1. 急性期硬约束: 绝对禁练**\n"
            "你当前有鼻炎发作及舌尖溃疡, HRV 36ms 低于基线 52ms 达 1.8σ。\n"
            "**2. 营养与补水**\n"
            "今日目标: 蛋白质 90g, 饮水 2500ml, 保证 8 小时睡眠窗口。\n"
            "如发热超过 38.5°C 或症状持续加重, 请及时就医确诊; "
            "本分析不构成诊断, 用药调整请遵医嘱。"
        )
        result = validate_text(synthesis)
        assert result.ok is True
        assert _BLOCKED_FALLBACK not in result.safe_text
        assert "绝对禁练" in result.safe_text
        assert "就医确诊" in result.safe_text


class TestGenuinePrescriptionStillBlocked:
    """真处方式/裁决式内容仍然硬拦截 (fail-closed 对抗 battery)."""

    def test_imperative_stop_medication_blocked(self):
        result = validate_text("建议你立即停药。")
        assert result.ok is False
        assert result.action == "replace"
        assert "立即停药" not in result.safe_text

    def test_negation_cut_by_comma_still_blocked(self):
        # 否定在前一 clause, 被逗号切断 → 不能洗白
        result = validate_text("请勿犹豫，立即停药。")
        assert result.ok is False

    def test_double_negation_still_blocked(self):
        # "不得不停药" = 双重否定 = 肯定
        result = validate_text("从数据看你可能不得不停药。")
        assert result.ok is False

    def test_post_context_doctor_does_not_whitewash(self):
        # 后文的"咨询医生"不能救前面的处方指令
        result = validate_text("建议先停药再咨询医生的意见和安排。")
        assert result.ok is False

    def test_bare_directive_then_doctor_still_blocked(self):
        # 裸指令 + 后置医方词: 不满足名词化条件, 不放行
        assert validate_text("停药后咨询医生").ok is False
        assert validate_text("建议停药的同时告知医生").ok is False

    # ── 2026-07-12 安全评审阻断项回归 ──

    def test_question_without_deferral_blocked(self):
        # 评审阻断#1: 裸疑问词 = 无医生参与的停药建议, 不能洗白
        assert validate_text("你要不要停药看看效果？").ok is False
        assert validate_text("是否停药看看，我觉得可以试试。").ok is False

    def test_relayed_prescription_via_referral_noun_blocked(self):
        # 评审阻断#2: 转诊名词 + 转述具体处方指令, 不能洗白处方/剂量类术语
        assert validate_text("医生让你把降压药剂量加倍。").ok is False
        assert validate_text("医院给你的方案是把降压药剂量翻倍。").ok is False
        assert validate_text("根据你的血糖趋势，医生会考虑加药到每天两次。").ok is False
        assert validate_text("药师说你可以先停药三天。").ok is False
        assert validate_text("就医后医生一般会直接给你换药到二甲双胍。").ok is False

    def test_guided_referral_does_not_whitewash_delivered_directive(self):
        # 复审残留阻断: consult 短语只是铺垫, 术语是助理另行下达的指令
        assert validate_text("跟医生沟通后把降压药剂量加倍。").ok is False
        assert validate_text("和医生商量后我建议你直接停药三天。").ok is False
        assert validate_text("由医生评估后我给你把胰岛素调整到20单位。").ok is False
        assert validate_text("在医生指导下你可以自行停药三天。").ok is False
        assert validate_text("由药师确认后直接加药到每天两次。").ok is False

    def test_guided_referral_direct_governance_still_passes(self):
        # consult 短语直接管辖术语 (短连接尾) 的合法指导语境保留
        assert validate_text("请在医生指导下停药, 不要自己做决定。").ok is True
        assert validate_text("遵医嘱停药即可, 不需要额外操作。").ok is True
        assert validate_text("由医生决定是否加药。").ok is True
        assert validate_text("与主治医生商量后再决定停药与否。").ok is True
        # 护栏 (安全评审第三轮): 这两句钉死已接受的残留边界 —— 若有人想把
        # 立刻/需要 等情态词加进 _DELIVERY_MARKERS 清残留, 这里立刻红,
        # 阻止合法转诊句被误杀 (退回 2026-07-12 prod 误杀)。
        assert validate_text("由医生决定是否需要立刻停药。").ok is True
        assert validate_text("由医生判断是否需要减药。").ok is True

    def test_mg_kg_variants_blocked(self):
        # 评审 backlog: 全角斜杠/空格变体归一
        assert validate_text("布洛芬按 5mg／kg 服用即可。").ok is False
        assert validate_text("布洛芬按 5 mg / kg 服用即可。").ok is False

    def test_diagnostic_class_bare_referral_still_passes(self):
        # 诊断类术语 (诊断/确诊/处方) 保留裸转诊名词洗白 (prod 误杀主场景)
        assert validate_text("医生开的处方请按时服用, 不要漏服。").ok is True
        assert validate_text("由专科医生诊断后再做打算。").ok is True

    def test_recommended_dose_blocked(self):
        result = validate_text("这个药的推荐剂量是每天两片, 你直接按这个吃。")
        assert result.ok is False

    def test_asserted_diagnosis_blocked(self):
        result = validate_text("综合以上数据, 你已确诊为代谢综合征。")
        assert result.ok is False

    def test_mg_kg_dosing_blocked(self):
        result = validate_text("布洛芬按 10mg/kg 服用即可, 不用担心。")
        assert result.ok is False

    def test_short_fully_violating_text_falls_back_to_full_template(self):
        # 遮蔽后剩余内容不足 → 保持旧行为: 整篇拒答模板
        result = validate_text("停药吧。")
        assert result.ok is False
        assert _BLOCKED_FALLBACK in result.safe_text


class TestSentenceLevelRedaction:
    """长合成中单句越界 → 只遮蔽该句, 其余保留."""

    def test_single_violating_sentence_redacted_rest_kept(self):
        text = (
            "你的 HRV 处于近 90 天低位, 恢复优先级最高。\n"
            "睡眠结构显示深睡不足, 建议 22:30 前入睡并保持卧室黑暗。\n"
            "血压偏高的问题, 建议直接停药观察一周。\n"
            "饮水目标 2500ml, 今天已完成 60%。"
        )
        result = validate_text(text)
        assert result.ok is False
        assert result.action == "replace"
        # 越界句被占位符替换, 不泄露
        assert "停药观察" not in result.safe_text
        assert _REDACTED_PLACEHOLDER in result.safe_text
        # 其余合成保留, 不再整篇拒答
        assert _BLOCKED_FALLBACK not in result.safe_text
        assert "恢复优先级最高" in result.safe_text
        assert "饮水目标 2500ml" in result.safe_text
        assert result.disclaimer

    def test_matched_terms_still_reported_for_audit(self):
        result = validate_text(
            "第一句是正常的恢复建议, 保持规律作息和充足睡眠即可, 不用焦虑。\n"
            "第二句越界: 你已确诊为高血压, 推荐剂量每天一片。\n"
            "第三句正常: 建议每天步行 8000 步, 保持记录。"
        )
        assert result.ok is False
        assert "确诊" in result.matched_terms
        assert "推荐剂量" in result.matched_terms


class TestValidateActionsNegationAware:
    def test_negated_action_title_not_blocked(self):
        actions = [
            ProtocolAction(
                template_id="test.reminder",
                action_type="intervention",
                title="提醒: 请勿自行停药",
            )
        ]
        result = validate_actions(actions)
        assert result.ok is True
        assert not result.blocked_actions
        assert result.disclaimer  # 灰名单"药"仍触发 disclaimer

    def test_prescriptive_action_still_blocked(self):
        actions = [
            ProtocolAction(
                template_id="test.bad",
                action_type="intervention",
                title="今天开始停药",
            )
        ]
        result = validate_actions(actions)
        assert result.ok is False
        assert result.blocked_actions == [0]
