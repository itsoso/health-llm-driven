"""
CPIC Level-A 药物基因组对照表 (纯数据)。

这是数据驱动地把 SafetyGuardian 的 PGx 覆盖从手写 9 条扩展到「全量
CPIC Level-A 中 phenotype 可由单标签/关键词判定」的对。引擎规则在 pgx.py 的
``pgx_cpic_table_check`` 里迭代本表。

设计约束（accuracy > volume）：
- 只收 CPIC **Level-A** 的 gene-drug 对（cpicpgx.org 维护的等级）。
- 只收 phenotype 能由上游基因报告的 ``result_label`` / ``genotype`` 字符串
  **关键词命中**判定的对。需要复杂 star-allele / copy-number calling 才能定
  phenotype 的（如全 CYP2D6 拷贝数 activity score）一律不收 —— 我们信任上游
  报告给的 phenotype 标签，不自己做定型。
- 已被 pgx.py **专属手写规则**覆盖的精确对在本表里**排除**，避免双报：
  CYP2D6×可待因/曲马多、CYP2C19×氯吡格雷、CYP2C9/VKORC1×华法林、
  SLCO1B1×辛伐他汀、G6PD×(伯氨喹/呋喃妥因/磺胺/达普松/亚甲蓝)、
  HLA-B×阿巴卡韦、DPYD×氟尿嘧啶/卡培他滨、ALDH2×酒精、MTHFR×叶酸。
- action 一律是「与处方医生/药师讨论调整」类**就医导向**，绝不写「自行停药」。
- phenotype 关键词没命中 → 不报（保守触发）。

每项字段：
  gene                基因名（大写，与 _find_variant_by_gene 比对）
  phenotype_keywords  命中 result_label / genotype 的关键词（中英），任一命中即视为高风险 phenotype
  phenotype_exclude_keywords  (可选) 否定/反向词；引擎先查 exclude，命中任一即跳过该项不报
                      （避免 "non-expresser" 命中 "express"、"no MH risk" 命中 "risk" 等反向假阳性）
  phenotype_label     人类可读的 phenotype 概述（填入 message）
  drug_keywords       药名同义词（中英），任一命中 _med_names 即视为在服
  severity            Severity 名（字符串，引擎转 enum）
  action              就医导向的可执行建议
  message_template    {gene}/{genotype}/{phenotype}/{drugs} 占位
  cpic_url            真实存在的 cpicpgx.org guideline URL
"""

from __future__ import annotations

from typing import Any, Dict, List

# HLA 类等位基因 keyword 复用（result_label / genotype 里出现即视为阳性携带）
_HLA_B1502 = ["15:02", "1502"]
_HLA_A3101 = ["31:01", "3101"]
_HLA_B5801 = ["58:01", "5801"]

# poor / intermediate metabolizer 类（CYP 系列“代谢慢”一侧）
_PM_IM = [
    "poor", "intermediate", "pm", "im",
    "慢代谢", "弱代谢", "中间代谢", "代谢差", "代谢减弱", "酶活性降低",
]
# ultrarapid / rapid（CYP 系列“代谢快”一侧）
_UM_RM = ["ultra", "rapid", "um", "rm", "超快代谢", "快代谢", "ultrarapid"]
# 酶/转运体功能缺陷一侧（DPYD/TPMT/NUDT15/G6PD 等“活性低”）。
# 只放表型词：裸合子词（纯合/杂合）会命中该基因下挂的良性变异，故剔除——
# 要求与代谢表型词共现才触发。
_DEFICIENT = [
    "poor", "intermediate", "deficien", "缺陷", "缺乏", "活性降低",
    "功能降低", "中间", "低活性",
]


CPIC_LEVEL_A_PAIRS: List[Dict[str, Any]] = [
    # ─────────── 巯基嘌呤类 × TPMT / NUDT15（活性低→骨髓抑制）───────────
    {
        "gene": "TPMT",
        "phenotype_keywords": _DEFICIENT,
        "phenotype_label": "TPMT 酶活性降低（中间/低活性代谢者）",
        "drug_keywords": [
            "硫唑嘌呤", "azathioprine", "巯基嘌呤", "6-巯基嘌呤", "巯嘌呤",
            "mercaptopurine", "6-mp", "硫鸟嘌呤", "thioguanine", "6-tg",
        ],
        "severity": "CRITICAL",
        "action": "与处方医生/血液或风湿科讨论按 CPIC 大幅减量（中间代谢减量、低活性可降至常规剂量很小比例）并加强血常规监测；切勿自行调整。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。硫唑嘌呤/巯基嘌呤类经 TPMT 灭活，活性降低者标准剂量易蓄积引发严重（可致命）骨髓抑制。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-thiopurines-and-tpmt/",
    },
    {
        "gene": "NUDT15",
        "phenotype_keywords": _DEFICIENT,
        "phenotype_label": "NUDT15 活性降低（中间/低活性代谢者，东亚人高发）",
        "drug_keywords": [
            "硫唑嘌呤", "azathioprine", "巯基嘌呤", "6-巯基嘌呤", "巯嘌呤",
            "mercaptopurine", "6-mp", "硫鸟嘌呤", "thioguanine", "6-tg",
        ],
        "severity": "CRITICAL",
        "action": "与处方医生讨论按 CPIC NUDT15 指南减量并密切监测血常规；东亚人群该位点风险尤高，切勿自行用药。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。NUDT15 低活性者使用硫唑嘌呤/巯基嘌呤类发生重度白细胞减少、脱发等骨髓毒性风险显著升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-thiopurines-and-tpmt/",
    },

    # ─────────── HLA-B*15:02 × 卡马西平/奥卡西平/苯妥英（SJS/TEN）───────────
    {
        "gene": "HLA-B",
        "phenotype_keywords": _HLA_B1502,
        "phenotype_label": "HLA-B*15:02 阳性携带（东南亚/汉族高发）",
        "drug_keywords": [
            "卡马西平", "carbamazepine", "奥卡西平", "oxcarbazepine",
            "苯妥英", "phenytoin", "磷苯妥英", "fosphenytoin",
        ],
        "severity": "CRITICAL",
        "action": "立即联系处方神经/精神科医生评估换药——HLA-B*15:02 阳性者上述药物有致命 SJS/TEN（重症皮疹）风险，CPIC 列为禁用；若已出现皮疹/黏膜破溃/发热请急诊。",
        "message_template": "{gene} 报告 {phenotype}。{drugs} 在 HLA-B*15:02 阳性者中诱发 Stevens-Johnson 综合征/中毒性表皮坏死松解症（可致命）的风险显著升高，CPIC 指南列为禁用。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-carbamazepine-and-hla-b/",
    },

    # ─────────── HLA-A*31:01 × 卡马西平（DRESS/SJS）───────────
    {
        "gene": "HLA-A",
        "phenotype_keywords": _HLA_A3101,
        "phenotype_label": "HLA-A*31:01 阳性携带",
        "drug_keywords": ["卡马西平", "carbamazepine"],
        "severity": "HIGH",
        "action": "与处方医生讨论改用替代抗癫痫/情绪稳定药——HLA-A*31:01 阳性者卡马西平诱发 DRESS、SJS/TEN 等严重皮肤反应风险升高；出现皮疹/发热及时就医。",
        "message_template": "{gene} 报告 {phenotype}。卡马西平在 HLA-A*31:01 阳性者中诱发 DRESS、SJS/TEN 等严重皮肤不良反应的风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-carbamazepine-and-hla-b/",
    },

    # ─────────── HLA-B*58:01 × 别嘌醇（SCAR）───────────
    {
        "gene": "HLA-B",
        "phenotype_keywords": _HLA_B5801,
        "phenotype_label": "HLA-B*58:01 阳性携带(汉族高发)",
        "drug_keywords": ["别嘌醇", "别嘌呤醇", "allopurinol"],
        "severity": "CRITICAL",
        "action": "立即联系处方医生评估改用非布司他等替代降尿酸药——HLA-B*58:01 阳性者别嘌醇有致命的重症皮肤不良反应（SCAR/SJS/TEN）风险，CPIC 强烈建议避免；出现皮疹/发热请急诊。",
        "message_template": "{gene} 报告 {phenotype}。别嘌醇在 HLA-B*58:01 阳性者中诱发重症皮肤不良反应（SCAR，含 SJS/TEN，可致命）的风险显著升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-allopurinol-and-hla-b/",
    },

    # ─────────── CYP2C19 × 伏立康唑（PM→过量；RM/UM→不足）───────────
    {
        "gene": "CYP2C19",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2C19 慢/中间代谢",
        "drug_keywords": ["伏立康唑", "voriconazole"],
        "severity": "HIGH",
        "action": "与处方医生/感染科讨论伏立康唑剂量并做血药浓度监测（TDM）——慢代谢者血药浓度易过高、肝毒性与神经毒性风险升高；不要自行调整。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。伏立康唑主要经 CYP2C19 清除，慢/中间代谢者血药浓度易超标，肝毒性/视觉与神经不良反应风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-voriconazole-and-cyp2c19/",
    },

    # ─────────── CYP2C19 × SSRI（西酞普兰/艾司西酞普兰/舍曲林）───────────
    {
        "gene": "CYP2C19",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2C19 慢/中间代谢",
        "drug_keywords": [
            "西酞普兰", "citalopram", "艾司西酞普兰", "escitalopram",
            "舍曲林", "sertraline",
        ],
        "severity": "MEDIUM",
        "action": "与处方精神科医生讨论是否减量或换用不依赖 CYP2C19 的 SSRI——慢代谢者血药浓度升高，西酞普兰/艾司西酞普兰存在剂量相关 QT 延长风险；切勿自行停药。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。西酞普兰/艾司西酞普兰/舍曲林部分经 CYP2C19 代谢，慢代谢者暴露升高（西酞普兰类还有 QT 延长顾虑）。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-selective-serotonin-reuptake-inhibitors-and-cyp2d6-and-cyp2c19/",
    },

    # ─────────── CYP2C19 × 三环类抗抑郁（阿米替林等）───────────
    {
        "gene": "CYP2C19",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2C19 慢/中间代谢",
        "drug_keywords": [
            "阿米替林", "amitriptyline", "氯米帕明", "clomipramine",
            "丙咪嗪", "imipramine", "多塞平", "doxepin", "三环",
        ],
        "severity": "MEDIUM",
        "action": "与处方医生讨论 TCA 减量或换药并考虑血药浓度监测——慢代谢者三环类血药浓度升高，抗胆碱与心脏（QT）不良反应风险增加；不要自行加减量。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。三环类抗抑郁药经 CYP2C19/CYP2D6 代谢，慢代谢者母体药物蓄积、不良反应风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-tricyclic-antidepressants-and-cyp2d6-and-cyp2c19/",
    },

    # ─────────── CYP2C19 × PPI（弱代谢→疗效更强/剂量可下调）───────────
    {
        "gene": "CYP2C19",
        "phenotype_keywords": _UM_RM,
        "phenotype_label": "CYP2C19 快/超快代谢",
        "drug_keywords": [
            "奥美拉唑", "omeprazole", "兰索拉唑", "lansoprazole",
            "泮托拉唑", "pantoprazole", "右兰索拉唑", "dexlansoprazole",
        ],
        "severity": "LOW",
        "action": "若 PPI 疗效不佳（反流/溃疡愈合慢），与处方医生讨论按 CPIC 上调剂量或换用——快/超快代谢者标准剂量 PPI 血药浓度偏低、抑酸不足；不要自行加量。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。PPI 主要经 CYP2C19 代谢，快/超快代谢者标准剂量血药浓度偏低，可能抑酸不足、疗效打折。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-proton-pump-inhibitors-and-cyp2c19/",
    },

    # ─────────── CYP2D6 × 他莫昔芬（PM→活性代谢物不足）───────────
    {
        "gene": "CYP2D6",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2D6 慢/中间代谢",
        "drug_keywords": ["他莫昔芬", "tamoxifen", "三苯氧胺"],
        "severity": "HIGH",
        "action": "与肿瘤科医生讨论——CYP2D6 慢代谢者他莫昔芬转化为活性代谢物 endoxifen 不足，可能影响疗效，CPIC 建议考虑芳香化酶抑制剂等替代；并避免合用强 CYP2D6 抑制剂。切勿自行停药。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。他莫昔芬需经 CYP2D6 转化为活性代谢物 endoxifen，慢代谢者活性代谢物偏低、可能影响内分泌治疗疗效。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-tamoxifen-based-on-cyp2d6-genotype/",
    },

    # ─────────── CYP2D6 × 阿托莫西汀（PM→暴露升高）───────────
    {
        "gene": "CYP2D6",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2D6 慢/中间代谢",
        "drug_keywords": ["阿托莫西汀", "托莫西汀", "atomoxetine"],
        "severity": "MEDIUM",
        "action": "与处方医生讨论按 CPIC 调整阿托莫西汀起始/滴定方案并监测不良反应——慢代谢者血药浓度可高数倍，心率血压升高等风险增加；不要自行加减量。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。阿托莫西汀主要经 CYP2D6 代谢，慢代谢者暴露显著升高，不良反应风险增加。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-atomoxetine-based-on-cyp2d6-genotype/",
    },

    # ─────────── CYP2D6 × 昂丹司琼/托烷司琼（UM→止吐失败）───────────
    {
        "gene": "CYP2D6",
        "phenotype_keywords": _UM_RM,
        "phenotype_label": "CYP2D6 超快/快代谢",
        "drug_keywords": ["昂丹司琼", "ondansetron", "托烷司琼", "tropisetron"],
        "severity": "MEDIUM",
        "action": "若止吐效果不佳，与处方医生讨论换用不经 CYP2D6 代谢的止吐药（如格拉司琼）——超快代谢者昂丹司琼/托烷司琼清除过快、止吐可能失败。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。昂丹司琼/托烷司琼经 CYP2D6 灭活，超快代谢者药物清除过快、止吐疗效下降。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-ondansetron-and-tropisetron-and-cyp2d6/",
    },

    # ─────────── CYP2D6 × SSRI（帕罗西汀/氟伏沙明等经 CYP2D6 者）───────────
    {
        "gene": "CYP2D6",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2D6 慢/中间代谢",
        "drug_keywords": ["帕罗西汀", "paroxetine", "氟伏沙明", "fluvoxamine"],
        "severity": "MEDIUM",
        "action": "与处方精神科医生讨论是否减量或换用不依赖 CYP2D6 的 SSRI——慢代谢者帕罗西汀/氟伏沙明血药浓度升高、不良反应风险增加；切勿自行停药。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。帕罗西汀/氟伏沙明经 CYP2D6 代谢，慢代谢者暴露升高、不良反应风险增加。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-selective-serotonin-reuptake-inhibitors-and-cyp2d6-and-cyp2c19/",
    },

    # ─────────── CYP2D6 × 三环类（阿米替林等，CYP2D6 侧）───────────
    {
        "gene": "CYP2D6",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2D6 慢/中间代谢",
        "drug_keywords": [
            "阿米替林", "amitriptyline", "去甲替林", "nortriptyline",
            "氯米帕明", "clomipramine", "丙咪嗪", "imipramine", "三环",
        ],
        "severity": "MEDIUM",
        "action": "与处方医生讨论 TCA 减量或换药并考虑血药浓度监测——CYP2D6 慢代谢者三环类血药浓度升高，抗胆碱与心脏不良反应风险增加；不要自行加减量。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。三环类抗抑郁药经 CYP2D6 代谢，慢代谢者母体药物蓄积、不良反应风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-tricyclic-antidepressants-and-cyp2d6-and-cyp2c19/",
    },

    # ─────────── CYP2C9 × 苯妥英（连同 HLA-B*15:02 另有规则）───────────
    {
        "gene": "CYP2C9",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2C9 慢/中间代谢",
        "drug_keywords": ["苯妥英", "phenytoin", "磷苯妥英", "fosphenytoin"],
        "severity": "HIGH",
        "action": "与处方神经科医生讨论按 CPIC 降低苯妥英维持剂量并做血药浓度监测——慢代谢者清除下降、易蓄积出现共济失调/眼震/中枢抑制等中毒表现；不要自行调整。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。苯妥英主要经 CYP2C9 代谢，慢/中间代谢者血药浓度易超治疗窗，中毒风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-phenytoin-and-cyp2c9-and-hla-b/",
    },

    # ─────────── CYP2C9 × NSAID（塞来昔布/布洛芬等高 t½ NSAID）───────────
    {
        "gene": "CYP2C9",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2C9 慢/中间代谢",
        "drug_keywords": [
            "塞来昔布", "celecoxib", "氟比洛芬", "flurbiprofen",
            "布洛芬", "ibuprofen", "美洛昔康", "meloxicam",
            "吡罗昔康", "piroxicam", "双氯芬酸", "diclofenac",
        ],
        "severity": "MEDIUM",
        "action": "与处方医生/药师讨论按 CPIC 从最低剂量起用、缩短疗程或换用非 CYP2C9 代谢的镇痛药——慢代谢者 NSAID 暴露升高，胃肠道/肾脏不良反应风险增加；不要自行加量。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。多种 NSAID 经 CYP2C9 代谢，慢/中间代谢者血药浓度升高、胃肠与肾脏不良反应风险增加。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-nsaids-based-on-cyp2c9-genotype/",
    },

    # ─────────── CYP3A5 × 他克莫司（表达者→剂量需上调）───────────
    {
        "gene": "CYP3A5",
        "phenotype_keywords": [
            "expresser", "intermediate expresser", "normal metabolizer",
            "高代谢", "*1/*1", "*1/*3", "*1/*6", "*1/*7",
        ],
        "phenotype_exclude_keywords": [
            "non-express", "nonexpress", "非表达", "*3/*3",
            "poor", "慢代谢", "低代谢",
        ],
        "phenotype_label": "CYP3A5 表达者（如 *1 携带，他克莫司清除更快）",
        "drug_keywords": ["他克莫司", "tacrolimus", "fk506", "fk-506"],
        "severity": "HIGH",
        "action": "与移植/肾科医生讨论按 CPIC 提高他克莫司起始剂量并加强谷浓度监测——CYP3A5 表达者标准剂量常达不到目标浓度、有排斥风险；剂量调整必须由医生基于血药浓度做。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。他克莫司经 CYP3A5 代谢，表达者清除更快、标准剂量谷浓度常偏低，移植排斥风险升高。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/guideline-for-tacrolimus-and-cyp3a5/",
    },

    # ─────────── CYP2B6 × 依非韦伦（PM→中枢毒性）───────────
    {
        "gene": "CYP2B6",
        "phenotype_keywords": _PM_IM,
        "phenotype_label": "CYP2B6 慢/中间代谢",
        "drug_keywords": ["依非韦伦", "efavirenz", "efv"],
        "severity": "MEDIUM",
        "action": "与 HIV 科医生讨论按 CPIC 考虑依非韦伦减量或换药——慢代谢者血药浓度升高，中枢神经系统不良反应（眩晕、异梦、抑郁）风险增加；切勿自行停抗病毒药。",
        "message_template": "{gene} 基因型 ({genotype}) 提示 {phenotype}。依非韦伦主要经 CYP2B6 代谢，慢/中间代谢者暴露升高、中枢神经系统毒性风险增加。你当前在用：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-efavirenz-based-on-cyp2b6-genotype/",
    },

    # ─────────── RYR1 / CACNA1S × 挥发性麻醉剂 + 琥珀胆碱（MH）───────────
    {
        "gene": "RYR1",
        "phenotype_keywords": [
            "malignant hyperthermia", "mh", "恶性高热", "susceptib", "易感",
            "pathogenic", "致病",
        ],
        "phenotype_exclude_keywords": [
            "no ", "low ", "阴性", "not susceptible", "无易感", "negative",
            "未检出", "未见", "未发现", "无致病", "无恶性高热", "无 mh",
            "wild", "野生", "正常", "benign", "良性", "likely benign",
        ],
        "phenotype_label": "RYR1 恶性高热易感变异",
        "drug_keywords": [
            "氟烷", "halothane", "异氟烷", "isoflurane", "七氟烷", "sevoflurane",
            "地氟烷", "desflurane", "恩氟烷", "enflurane", "琥珀胆碱",
            "succinylcholine", "suxamethonium", "挥发性麻醉",
        ],
        "severity": "CRITICAL",
        "action": "务必在任何手术/麻醉前主动告知麻醉医生你携带 RYR1 恶性高热易感变异——必须避免所有挥发性吸入麻醉剂和琥珀胆碱，改用非触发麻醉方案；这是 CPIC 列出的可致命急症基因。",
        "message_template": "{gene} 报告 {phenotype}。挥发性吸入麻醉剂与琥珀胆碱在恶性高热易感者中可触发致命的代谢危象。涉及药物：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-ryr1-and-cacna1s/",
    },
    {
        "gene": "CACNA1S",
        "phenotype_keywords": [
            "malignant hyperthermia", "mh", "恶性高热", "susceptib", "易感",
            "pathogenic", "致病",
        ],
        "phenotype_exclude_keywords": [
            "no ", "low ", "阴性", "not susceptible", "无易感", "negative",
            "未检出", "未见", "未发现", "无致病", "无恶性高热", "无 mh",
            "wild", "野生", "正常", "benign", "良性", "likely benign",
        ],
        "phenotype_label": "CACNA1S 恶性高热易感变异",
        "drug_keywords": [
            "氟烷", "halothane", "异氟烷", "isoflurane", "七氟烷", "sevoflurane",
            "地氟烷", "desflurane", "恩氟烷", "enflurane", "琥珀胆碱",
            "succinylcholine", "suxamethonium", "挥发性麻醉",
        ],
        "severity": "CRITICAL",
        "action": "务必在任何手术/麻醉前主动告知麻醉医生你携带 CACNA1S 恶性高热易感变异——必须避免所有挥发性吸入麻醉剂和琥珀胆碱，改用非触发麻醉方案。",
        "message_template": "{gene} 报告 {phenotype}。挥发性吸入麻醉剂与琥珀胆碱在恶性高热易感者中可触发致命的代谢危象。涉及药物：{drugs}。",
        "cpic_url": "https://cpicpgx.org/guidelines/cpic-guideline-for-ryr1-and-cacna1s/",
    },
]
