"""基于大模型的健康分析服务"""
import json
import logging
from datetime import date, timedelta, datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.daily_health import GarminData
from app.models.user import User
from app.models.basic_health import BasicHealthData
from app.models.user_profile import UserProfile
from app.config import settings
from app.utils.timezone import get_china_now, get_china_today

logger = logging.getLogger(__name__)

# 导入 LLM Provider
from app.services.llm import get_llm_provider


class LLMHealthAnalyzer:
    """
    基于大模型的健康分析器

    结合规则分析结果，使用大模型生成更智能、更个性化的健康建议
    """

    def __init__(self):
        self._provider = None
        try:
            self._provider = get_llm_provider()
            self.model = getattr(self._provider, 'model', 'gpt-4o-mini')
        except Exception as e:
            logger.warning(f"LLM Provider 初始化失败，将使用纯规则分析: {e}")
            self.model = "gpt-4o-mini"

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self._provider is not None

    async def analyze_with_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        使用自定义 prompt 进行 LLM 分析

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            LLM 响应内容字符串
        """
        if not self.is_available():
            raise Exception("LLM 服务不可用，请配置 LLM Provider")

        content = await self._provider.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = content.strip()

        # 处理可能的 markdown 代码块
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        return content

    def _build_user_context(
        self,
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """构建用户上下文信息（包含用户画像）"""
        user = db.query(User).filter(User.id == user_id).first()
        basic_health = db.query(BasicHealthData).filter(
            BasicHealthData.user_id == user_id
        ).order_by(BasicHealthData.record_date.desc()).first()

        # 获取用户画像
        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()

        context = {
            "name": user.name if user else "用户",
            "gender": user.gender if user else None,
            "age": None
        }

        if user and user.birth_date:
            today = date.today()
            context["age"] = today.year - user.birth_date.year

        if basic_health:
            context.update({
                "height": basic_health.height,
                "weight": basic_health.weight,
                "bmi": basic_health.bmi,
                "blood_pressure": f"{basic_health.systolic_bp}/{basic_health.diastolic_bp}" if basic_health.systolic_bp else None
            })

        # 从用户画像中补充信息
        if user_profile:
            # 基本信息（如果没有从User获取到）
            if not context.get("gender"):
                context["gender"] = user_profile.gender
            if not context.get("age") and user_profile.birth_date:
                today = date.today()
                context["age"] = today.year - user_profile.birth_date.year
            if not context.get("height"):
                context["height"] = user_profile.height_cm
            if not context.get("weight"):
                context["weight"] = user_profile.current_weight_kg

            # 健康目标
            context["health_goals"] = {
                "target_weight": user_profile.target_weight_kg,
                "target_sleep_hours": user_profile.target_sleep_hours,
                "target_steps": user_profile.target_steps,
                "target_water_ml": user_profile.target_water_ml,
                "target_exercise_minutes": user_profile.target_exercise_minutes
            }

            # 健康状况
            context["health_conditions"] = {
                "chronic_conditions": user_profile.chronic_conditions or [],
                "allergies": user_profile.allergies or [],
                "current_medications": user_profile.current_medications or []
            }

            # 生活习惯
            context["lifestyle"] = {
                "exercise_frequency": user_profile.exercise_frequency,
                "diet_preference": user_profile.diet_preference,
                "smoking_status": user_profile.smoking_status,
                "alcohol_consumption": user_profile.alcohol_consumption,
                "usual_sleep_time": user_profile.usual_sleep_time,
                "usual_wake_time": user_profile.usual_wake_time
            }

            # 工作环境
            context["work_environment"] = {
                "work_type": user_profile.work_type,
                "work_hours_per_day": user_profile.work_hours_per_day,
                "sitting_hours_per_day": user_profile.sitting_hours_per_day,
                "city": user_profile.city
            }

        return context

    def _build_gene_drug_constraints(self, db: Session, user_id: int) -> str:
        """
        从用户基因数据动态生成药物安全约束

        读取用户的 GeneticVariant 记录，匹配药物交互规则，
        生成可注入 AI prompt 的约束文本。
        多租户安全：每个用户独立生成，无基因数据则返回空字符串。
        """
        try:
            from app.models.genetic_data import GeneticVariant

            variants = db.query(GeneticVariant).filter(
                GeneticVariant.user_id == user_id
            ).all()

            if not variants:
                return ""

            # 基因-药物交互规则（Layer 2 通用规则）
            GENE_DRUG_RULES = {
                "CYP2D6": {
                    "high": {
                        "avoid": "可待因类止咳药（无法激活，无效且蓄积）、曲马多",
                        "substitute": "抗过敏药选西替利嗪（肾排泄）替代氯雷他定（CYP2D6代谢）",
                        "monitor": "如必须用氯雷他定，减量50%并监测嗜睡",
                    },
                    "medium": {
                        "monitor": "氯雷他定注意剂量，必要时改用西替利嗪",
                    },
                },
                "CYP2C19": {
                    "high": {
                        "substitute": "PPI选雷贝拉唑替代奥美拉唑；抗血小板选替格瑞洛替代氯吡格雷",
                    },
                    "medium": {
                        "monitor": "奥美拉唑减量50%或换用雷贝拉唑",
                    },
                },
                "ALDH2": {
                    "high": {
                        "avoid": "含酒精制剂、硝酸甘油（疗效显著降低）",
                        "lifestyle": "严格禁酒",
                    },
                    "medium": {
                        "avoid": "含酒精口服液/中成药（乙醛蓄积加重过敏）",
                        "lifestyle": "禁酒——乙醛是组胺释放触发因子",
                    },
                },
                "MTHFR": {
                    "high": {
                        "substitute": "叶酸必须用5-MTHF甲基叶酸(400-800μg/天)，禁止普通folic acid",
                        "supplement": "配合甲钴胺(活性B12)降低同型半胱氨酸",
                        "monitor": "每年检测同型半胱氨酸，目标<10μmol/L",
                    },
                    "medium": {
                        "monitor": "每1-2年检测同型半胱氨酸",
                    },
                },
                "9p21": {
                    "high": {
                        "avoid": "长期使用麻黄碱/伪麻黄碱（心血管风险）",
                        "monitor": "使用减充血剂期间每日监测血压",
                    },
                },
                "LCT": {
                    "high": {
                        "avoid": "含乳糖辅料药片（乳糖不耐受影响吸收）",
                        "lifestyle": "减少乳制品，改用无乳糖奶或植物奶",
                    },
                },
                "SLCO1B1": {
                    "high": {
                        "monitor": "他汀类药物肌病风险增加，需低剂量起始",
                    },
                    "medium": {
                        "monitor": "他汀类药物注意肌肉症状",
                    },
                },
            }

            constraints = []
            for variant in variants:
                gene = variant.gene_name
                risk = variant.risk_level  # "low", "medium", "high"

                if gene in GENE_DRUG_RULES and risk in GENE_DRUG_RULES[gene]:
                    rules = GENE_DRUG_RULES[gene][risk]
                    constraint_parts = [f"**{gene}** ({variant.result_label or risk}):"]

                    if "avoid" in rules:
                        constraint_parts.append(f"  - 避免: {rules['avoid']}")
                    if "substitute" in rules:
                        constraint_parts.append(f"  - 替代: {rules['substitute']}")
                    if "monitor" in rules:
                        constraint_parts.append(f"  - 监测: {rules['monitor']}")
                    if "supplement" in rules:
                        constraint_parts.append(f"  - 补充: {rules['supplement']}")
                    if "lifestyle" in rules:
                        constraint_parts.append(f"  - 生活方式: {rules['lifestyle']}")

                    constraints.append("\n".join(constraint_parts))

            if not constraints:
                return ""

            return (
                "\n\n## 此用户的药物基因组约束（硬性规则，AI建议不可违反）\n\n"
                + "\n\n".join(constraints)
                + "\n\n注意：以上约束基于用户基因检测结果，推荐用药时必须遵守。"
            )

        except Exception as e:
            logger.warning(f"构建基因药物约束失败: {e}")
            return ""

    def _build_genetic_profile_context(self, db: Session, user_id: int) -> str:
        """
        构建用户完整基因画像，用于个性化健康建议

        覆盖全部类别：营养代谢、运动基因、药物敏感性、疾病风险、睡眠基因
        """
        try:
            from app.models.genetic_data import GeneticVariant

            variants = db.query(GeneticVariant).filter(
                GeneticVariant.user_id == user_id
            ).order_by(
                GeneticVariant.risk_level.desc(),
                GeneticVariant.category
            ).all()

            if not variants:
                return ""

            cat_labels = {
                'nutrition': '营养代谢基因',
                'exercise': '运动基因',
                'drug_sensitivity': '药物敏感性',
                'disease_risk': '疾病风险基因',
                'sleep': '睡眠基因'
            }
            by_cat: dict = {}
            for v in variants:
                by_cat.setdefault(v.category or 'other', []).append(v)

            lines = ["\n\n## 用户基因检测画像（个性化建议必须参考）\n"]
            for cat, items in by_cat.items():
                lines.append(f"\n### {cat_labels.get(cat, cat)}")
                for v in items:
                    risk_tag = {'high': '⚠️高风险', 'medium': '⚡中风险', 'low': '✅低风险'}.get(v.risk_level, 'ℹ️')
                    line = f"- {risk_tag} **{v.gene_name}**"
                    if v.variant_name:
                        line += f" {v.variant_name}"
                    if v.genotype:
                        line += f" ({v.genotype})"
                    if v.result_label:
                        line += f": {v.result_label}"
                    if v.description:
                        line += f" — {v.description[:150]}"
                    lines.append(line)

            lines.append("\n**基于以上基因数据，你的健康建议应该：**")
            lines.append("- 营养基因异常 → 调整饮食建议（如MTHFR需活性叶酸、ALDH2需禁酒）")
            lines.append("- 运动基因特征 → 推荐匹配的运动类型（如ACTN3决定力量vs耐力倾向）")
            lines.append("- 睡眠基因 → 调整作息建议（如CLOCK/PER2影响昼夜节律）")
            lines.append("- 疾病风险 → 加强对应指标监测和预防建议")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"构建基因画像失败: {e}")
            return ""

    def _get_time_context(self) -> Dict[str, Any]:
        """获取当前时间上下文"""
        now = get_china_now()
        hour = now.hour

        if hour < 6:
            period = "凌晨"
            period_en = "early_morning"
            step_expectation = "very_low"  # 凌晨步数极低正常
        elif hour < 9:
            period = "早晨"
            period_en = "morning"
            step_expectation = "low"  # 早晨步数较低正常
        elif hour < 12:
            period = "上午"
            period_en = "late_morning"
            step_expectation = "moderate_low"  # 上午步数偏低正常
        elif hour < 14:
            period = "中午"
            period_en = "noon"
            step_expectation = "moderate"  # 中午应有一定步数
        elif hour < 18:
            period = "下午"
            period_en = "afternoon"
            step_expectation = "moderate_high"  # 下午应有较多步数
        elif hour < 21:
            period = "傍晚"
            period_en = "evening"
            step_expectation = "high"  # 傍晚应有较高步数
        else:
            period = "晚上"
            period_en = "night"
            step_expectation = "near_final"  # 晚上步数接近一天最终值

        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M"),
            "hour": hour,
            "period": period,
            "period_en": period_en,
            "step_expectation": step_expectation,
            "is_work_hours": 9 <= hour <= 18,
            "remaining_hours": 24 - hour,
            "exercise_window": "上午" if hour < 12 else ("下午" if hour < 18 else "晚间")
        }

    def _build_health_data_prompt(
        self,
        yesterday_data: GarminData,
        recent_data: List[GarminData],
        rule_analysis: Dict[str, Any],
        user_context: Dict[str, Any],
        environment_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建健康数据分析提示词"""

        # 获取当前时间上下文
        time_context = self._get_time_context()

        # 获取北京时间的今天和昨天日期
        china_today = get_china_now().date()
        china_yesterday = china_today - timedelta(days=1)

        # 构建时间上下文说明（明确北京时间）
        time_info = f"""
【重要：以下所有时间均为北京时间 (UTC+8)】
当前北京时间: {time_context['current_time']} ({time_context['period']})
今天日期(北京时间): {china_today}
昨天日期(北京时间): {china_yesterday}
今日剩余时间: 约{time_context['remaining_hours']}小时
当前时段: {time_context['period']}
适宜运动时段: {time_context['exercise_window']}
"""

        # 构建用户基本信息
        user_info = f"""
用户信息:
- 姓名: {user_context.get('name', '未知')}
- 年龄: {user_context.get('age', '未知')}岁
- 性别: {user_context.get('gender', '未知')}
- 身高: {user_context.get('height', '未知')}cm
- 体重: {user_context.get('weight', '未知')}kg
- BMI: {user_context.get('bmi', '未知')}
- 血压: {user_context.get('blood_pressure', '未知')}
"""

        # 添加健康目标（如果有）
        health_goals = user_context.get('health_goals', {})
        if health_goals and any(v for v in health_goals.values() if v is not None):
            user_info += f"""
健康目标:
- 目标体重: {health_goals.get('target_weight') or '未设置'}kg
- 目标睡眠: {health_goals.get('target_sleep_hours') or '未设置'}小时
- 目标步数: {health_goals.get('target_steps') or '未设置'}步
- 目标饮水: {health_goals.get('target_water_ml') or '未设置'}ml
- 目标运动时长: {health_goals.get('target_exercise_minutes') or '未设置'}分钟
"""

        # 添加健康状况（如果有）
        health_conditions = user_context.get('health_conditions', {})
        chronic_conditions = health_conditions.get('chronic_conditions', [])
        allergies = health_conditions.get('allergies', [])
        medications = health_conditions.get('current_medications', [])

        if chronic_conditions or allergies or medications:
            user_info += "\n健康状况:"
            if chronic_conditions:
                user_info += f"\n- 慢性病: {', '.join(str(c) for c in chronic_conditions)}"
            if allergies:
                user_info += f"\n- 过敏: {', '.join(str(a) for a in allergies)}"
            if medications:
                med_names = [m.get('name', str(m)) if isinstance(m, dict) else str(m) for m in medications]
                user_info += f"\n- 正在服用药物: {', '.join(med_names)}"

        # 添加生活习惯（如果有）
        lifestyle = user_context.get('lifestyle', {})
        if lifestyle and any(v for v in lifestyle.values() if v is not None):
            lifestyle_map = {
                'sedentary': '久坐不动',
                'light': '轻度活动',
                'moderate': '中度活动',
                'active': '活跃',
                'very_active': '非常活跃',
                'vegetarian': '素食',
                'vegan': '纯素食',
                'keto': '生酮饮食',
                'paleo': '原始饮食',
                'omnivore': '杂食',
                'never': '从不',
                'former': '曾经',
                'current': '目前',
                'social': '社交场合',
                'moderate': '适度',
                'heavy': '大量'
            }
            user_info += "\n生活习惯:"
            if lifestyle.get('exercise_frequency'):
                user_info += f"\n- 运动频率: {lifestyle_map.get(lifestyle['exercise_frequency'], lifestyle['exercise_frequency'])}"
            if lifestyle.get('diet_preference'):
                user_info += f"\n- 饮食偏好: {lifestyle_map.get(lifestyle['diet_preference'], lifestyle['diet_preference'])}"
            if lifestyle.get('smoking_status'):
                user_info += f"\n- 吸烟状态: {lifestyle_map.get(lifestyle['smoking_status'], lifestyle['smoking_status'])}"
            if lifestyle.get('alcohol_consumption'):
                user_info += f"\n- 饮酒习惯: {lifestyle_map.get(lifestyle['alcohol_consumption'], lifestyle['alcohol_consumption'])}"
            if lifestyle.get('usual_sleep_time'):
                user_info += f"\n- 通常入睡时间: {lifestyle['usual_sleep_time']}"
            if lifestyle.get('usual_wake_time'):
                user_info += f"\n- 通常起床时间: {lifestyle['usual_wake_time']}"

        # 添加工作环境（如果有）
        work_env = user_context.get('work_environment', {})
        if work_env and any(v for v in work_env.values() if v is not None):
            work_type_map = {
                'office': '办公室工作',
                'manual': '体力劳动',
                'hybrid': '混合工作'
            }
            user_info += "\n工作环境:"
            if work_env.get('work_type'):
                user_info += f"\n- 工作类型: {work_type_map.get(work_env['work_type'], work_env['work_type'])}"
            if work_env.get('work_hours_per_day'):
                user_info += f"\n- 每日工作时长: {work_env['work_hours_per_day']}小时"
            if work_env.get('sitting_hours_per_day'):
                user_info += f"\n- 每日久坐时长: {work_env['sitting_hours_per_day']}小时"
            if work_env.get('city'):
                user_info += f"\n- 所在城市: {work_env['city']}"

        # 构建分析数据部分
        # 注意：Garmin 的睡眠数据按醒来日期记录
        # 例如：1月18日的睡眠数据 = 1月17日晚上到1月18日早上的睡眠
        data_date = yesterday_data.record_date
        china_today = get_china_today()
        china_yesterday = china_today - timedelta(days=1)

        # 判断数据是今天还是昨天的
        is_today_data = (data_date == china_today)

        if is_today_data:
            # 如果是今天的数据，睡眠是昨晚的，运动数据不完整
            yesterday_info = f"""
健康数据 (数据日期: {data_date}，即今天 {china_today}):
【重要数据说明】
1. 睡眠数据：这是昨晚（{china_yesterday}晚上到{china_today}早上）的睡眠情况 ✅ 完整数据
2. 活动数据：今天才刚开始，步数和运动数据不完整，不要基于这些数据给建议！❌
3. 运动建议：应该基于昨天的运动情况（需要查看昨天的数据）和本周累计，给出今天的锻炼计划

【睡眠数据 - 昨晚 ({china_yesterday}晚 → {china_today}晨)】
- 睡眠分数: {yesterday_data.sleep_score or '无数据'}/100
- 总睡眠时长: {round(yesterday_data.total_sleep_duration / 60, 1) if yesterday_data.total_sleep_duration else '无数据'}小时
- 深度睡眠: {yesterday_data.deep_sleep_duration or '无数据'}分钟
- REM睡眠: {yesterday_data.rem_sleep_duration or '无数据'}分钟
- 浅睡眠: {yesterday_data.light_sleep_duration or '无数据'}分钟
- 清醒时间: {yesterday_data.awake_duration or '无数据'}分钟

【心率数据 - 今天（不完整）】
- 静息心率: {yesterday_data.resting_heart_rate or '无数据'} bpm
- 平均心率: {yesterday_data.avg_heart_rate or '无数据'} bpm
- 最高心率: {yesterday_data.max_heart_rate or '无数据'} bpm
- 最低心率: {yesterday_data.min_heart_rate or '无数据'} bpm
- 心率变异性(HRV): {yesterday_data.hrv or '无数据'} ms

【活动数据 - 今天（不完整，不要基于此给建议）】
- 步数: {yesterday_data.steps or '无数据'}步 ⚠️ 今天才刚开始
- 活动分钟: {yesterday_data.active_minutes or '无数据'}分钟 ⚠️ 今天才刚开始
- 消耗卡路里: {yesterday_data.calories_burned or '无数据'} kcal ⚠️ 今天才刚开始

【压力与恢复 - 今天（不完整）】
- 压力水平: {yesterday_data.stress_level or '无数据'}/100
- 身体电量最高值: {yesterday_data.body_battery_most_charged or '无数据'}
- 身体电量最低值: {yesterday_data.body_battery_lowest or '无数据'}
"""
        else:
            # 如果是昨天的数据，所有数据都是完整的
            yesterday_info = f"""
健康数据 (数据日期: {data_date}，即昨天 {china_yesterday}):
【重要数据说明】
1. 睡眠数据：这是前天晚上的睡眠情况（{data_date - timedelta(days=1)}晚 → {data_date}晨）
2. 活动数据：这是昨天全天的运动数据 ✅ 完整数据
3. 运动建议：应该基于这些完整的昨天数据和本周累计，给出今天的锻炼计划

【睡眠数据 - 前天晚上】
- 睡眠分数: {yesterday_data.sleep_score or '无数据'}/100
- 总睡眠时长: {round(yesterday_data.total_sleep_duration / 60, 1) if yesterday_data.total_sleep_duration else '无数据'}小时
- 深度睡眠: {yesterday_data.deep_sleep_duration or '无数据'}分钟
- REM睡眠: {yesterday_data.rem_sleep_duration or '无数据'}分钟
- 浅睡眠: {yesterday_data.light_sleep_duration or '无数据'}分钟
- 清醒时间: {yesterday_data.awake_duration or '无数据'}分钟

【心率数据 - 昨天】
- 静息心率: {yesterday_data.resting_heart_rate or '无数据'} bpm
- 平均心率: {yesterday_data.avg_heart_rate or '无数据'} bpm
- 最高心率: {yesterday_data.max_heart_rate or '无数据'} bpm
- 最低心率: {yesterday_data.min_heart_rate or '无数据'} bpm
- 心率变异性(HRV): {yesterday_data.hrv or '无数据'} ms

【活动数据 - 昨天全天 ✅】
- 步数: {yesterday_data.steps or '无数据'}步
- 活动分钟: {yesterday_data.active_minutes or '无数据'}分钟
- 消耗卡路里: {yesterday_data.calories_burned or '无数据'} kcal

【压力与恢复 - 昨天】
- 压力水平: {yesterday_data.stress_level or '无数据'}/100
- 身体电量最高值: {yesterday_data.body_battery_most_charged or '无数据'}
- 身体电量最低值: {yesterday_data.body_battery_lowest or '无数据'}
- 身体电量充电: {yesterday_data.body_battery_charged or '无数据'}
- 身体电量消耗: {yesterday_data.body_battery_drained or '无数据'}
"""

        # 构建趋势数据
        if recent_data and len(recent_data) > 1:
            sleep_scores = [d.sleep_score for d in recent_data if d.sleep_score]
            steps_list = [d.steps for d in recent_data if d.steps]
            rhr_list = [d.resting_heart_rate for d in recent_data if d.resting_heart_rate]
            active_minutes_list = [d.active_minutes for d in recent_data if d.active_minutes]

            # 计算本周实际运动时长（从 workout_records 表）
            # 获取本周的起止日期（北京时间）
            from app.models.daily_health import WorkoutRecord
            from sqlalchemy import func

            today = get_china_today()
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)

            # 查询本周的实际运动记录
            db = recent_data[0]._sa_instance_state.session if recent_data else None
            workout_minutes = 0
            if db:
                user_id = recent_data[0].user_id if recent_data else None
                if user_id:
                    total_seconds = db.query(func.sum(WorkoutRecord.duration_seconds)).filter(
                        WorkoutRecord.user_id == user_id,
                        WorkoutRecord.workout_date >= monday,
                        WorkoutRecord.workout_date <= today
                    ).scalar()
                    workout_minutes = round(total_seconds / 60, 1) if total_seconds else 0

            # 如果无法获取运动记录，回退到使用 active_minutes
            total_active_minutes = workout_minutes if workout_minutes > 0 else (sum(active_minutes_list) if active_minutes_list else 0)
            weekly_goal = 150  # WHO建议每周150分钟中等强度运动
            weekly_progress = round(total_active_minutes / weekly_goal * 100, 1) if total_active_minutes else 0

            trend_info = f"""
最近{len(recent_data)}天趋势（包括昨天）:
- 平均睡眠分数: {round(sum(sleep_scores)/len(sleep_scores), 1) if sleep_scores else '无数据'}
- 平均步数: {round(sum(steps_list)/len(steps_list)) if steps_list else '无数据'}步
- 平均静息心率: {round(sum(rhr_list)/len(rhr_list), 1) if rhr_list else '无数据'} bpm

本周运动情况（WHO建议每周150分钟中等强度有氧运动）:
- 本周累计运动时长: {total_active_minutes}分钟 (基于北京时间周一至今的实际运动记录)
- 目标完成度: {weekly_progress}% (目标: {weekly_goal}分钟/周)
- 还需运动: {max(0, weekly_goal - total_active_minutes)}分钟
【重要】给出运动建议时，应该考虑本周的累计运动量，督促用户完成每周150分钟的目标！
"""
        else:
            trend_info = ""

        # 规则分析结果摘要
        rule_summary = f"""
规则分析结果:
- 整体状态: {rule_analysis.get('overall_status', '未知')}
- 睡眠状态: {rule_analysis.get('sleep_analysis', {}).get('status', '未知')} - {rule_analysis.get('sleep_analysis', {}).get('quality_assessment', '')}
- 活动状态: {rule_analysis.get('activity_analysis', {}).get('status', '未知')}
- 心率状态: {rule_analysis.get('heart_rate_analysis', {}).get('status', '未知')}
- 恢复状态: {rule_analysis.get('stress_analysis', {}).get('recovery_status', '未知')}

规则分析发现的问题:
{chr(10).join(['- ' + issue for issue in rule_analysis.get('sleep_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('activity_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('heart_rate_analysis', {}).get('issues', [])])}
{chr(10).join(['- ' + issue for issue in rule_analysis.get('stress_analysis', {}).get('issues', [])])}
"""

        # 添加环境数据
        environment_info = ""
        if environment_data:
            weather = environment_data.get("weather", {})
            air_quality = environment_data.get("air_quality", {})
            exercise = environment_data.get("exercise", {})
            env_advices = environment_data.get("advices", [])
            env_warnings = environment_data.get("warnings", [])

            environment_info = f"""

【今日环境信息】
天气情况:
- 温度: {weather.get('temperature', '未知')}°C
- 体感温度: {weather.get('feels_like', '未知')}°C
- 湿度: {weather.get('humidity', '未知')}%
- 天气: {weather.get('weather', '未知')}
- 风速: {weather.get('wind_speed', '未知')} km/h

空气质量:
- AQI: {air_quality.get('aqi', '未知')}
- 空气质量等级: {air_quality.get('level', '未知')} - {air_quality.get('description', '')}
- PM2.5: {air_quality.get('pm25', '未知')} μg/m³
- 健康影响: {air_quality.get('health_implications', '未知')}

户外运动评估:
- 户外运动适宜: {'是' if exercise.get('outdoor_suitable', False) else '否'}
- 适宜度评分: {exercise.get('score', '未知')}/100
- 状态: {exercise.get('status', '未知')}
- 推荐活动: {', '.join(exercise.get('recommended_activities', [])) or '无'}

环境相关建议:
{chr(10).join(['- ' + advice for advice in env_advices]) if env_advices else '- 暂无'}

环境相关警告:
{chr(10).join(['- ' + warning for warning in env_warnings]) if env_warnings else '- 暂无'}
"""

        return time_info + user_info + yesterday_info + trend_info + rule_summary + environment_info

    async def analyze_daily_health(
        self,
        db: Session,
        user_id: int,
        yesterday_data: GarminData,
        recent_data: List[GarminData],
        rule_analysis: Dict[str, Any],
        environment_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        使用大模型分析每日健康数据

        Args:
            db: 数据库会话
            user_id: 用户ID
            yesterday_data: 昨日数据
            recent_data: 最近几天的数据
            rule_analysis: 规则分析结果
            environment_data: 环境数据（天气、空气质量）

        Returns:
            包含LLM分析结果的字典
        """
        if not self.is_available():
            return {
                "available": False,
                "message": "LLM服务不可用，请配置 LLM Provider"
            }

        try:
            user_context = self._build_user_context(db, user_id)
            health_prompt = self._build_health_data_prompt(
                yesterday_data, recent_data, rule_analysis, user_context, environment_data
            )

            # [Phase 0 dogfood] Digital Health Twin 统一状态快照
            # 作为额外结构化上下文注入 prompt —— 为 Phase 1 Safety Guardian 的
            # 统一 context 访问做铺垫。失败降级为空字符串不影响主流程。
            try:
                from app.twin.builder import build_twin
                from app.twin.formatter import twin_to_prompt_blob

                twin = build_twin(db, user_id)
                twin_blob = twin_to_prompt_blob(twin)
                if twin_blob:
                    health_prompt += f"\n\n[健康孪生快照]\n{twin_blob}\n"
                    logger.info(
                        f"[twin] injected into prompt: user={user_id}, "
                        f"sources={twin.meta.data_sources}, build_ms={twin.meta.build_ms}"
                    )
            except Exception as twin_err:
                logger.warning(f"[twin] prompt 注入失败（降级）: {twin_err}")

            # 基因画像（完整基因检测数据，用于个性化建议）
            genetic_profile = self._build_genetic_profile_context(db, user_id)
            if genetic_profile:
                health_prompt += genetic_profile

            # 基因-药物约束（硬性安全规则）
            gene_constraints = self._build_gene_drug_constraints(db, user_id)
            if gene_constraints:
                health_prompt += gene_constraints

            system_prompt = """你是一位专业的智能助理和运动生理学专家，同时具备营养基因组学知识。
你需要基于用户的可穿戴设备数据、个人画像、基因检测数据和当地环境信息，提供科学、高度个性化的健康建议。

⚠️ 【关键提醒】你收到的所有运动数据（步数、活动分钟、卡路里）都是昨天的数据，不是今天的！
今天才刚开始，所以你的运动建议应该：
1️⃣ 评价昨天的运动量（例如："昨天您走了8000步，活动了30分钟"）
2️⃣ 分析本周累计运动量是否达到WHO建议的150分钟/周
3️⃣ 给出今天的具体锻炼计划和督促（例如："今天建议您进行40分钟慢跑"）
❌ 绝对不要说"今天步数不足"或"今天运动量偏低"这类话，因为今天才刚开始！

分析原则:
1. 【个性化优先】深度结合用户画像信息（健康目标、慢性病、生活习惯、工作环境等），给出真正针对TA个人情况的建议
2. 【目标导向】如果用户设定了健康目标（如目标体重、步数等），建议应围绕帮助达成这些目标
3. 【慢性病关注】如果用户有慢性病（如鼻炎、咽炎等），建议应考虑这些疾病的管理和预防
4. 【工作适配】根据用户的工作类型和久坐时长，给出切实可行的运动建议
5. 【生活习惯】考虑用户的作息习惯、饮食偏好，让建议更容易被接受和执行
6. 【数据趋势】关注数据变化趋势，不仅看单日数据
7. 【具体可行】建议要具体、可执行，包含时间、数量等具体指标
8. 【积极鼓励】保持积极鼓励的语气，同时客观指出需要改进的地方
9. 【环境适应】根据当天的天气和空气质量，推荐合适的运动方式和时间
10.【运动推荐】给出具体的锻炼方式推荐，包括室内/室外选择、运动类型、时长、强度等
11.【时间感知】用户在中国（UTC+8），数据中的日期是北京时间日期
12.【数据时效】再次强调：活动数据（步数、活动分钟）是昨天的，睡眠数据是昨晚的，不是今天的！
13.【基因个性化】如果提供了基因检测数据，必须在建议中体现基因影响：
   - 营养代谢基因异常 → 明确指出该吃什么、避免什么（如MTHFR TT需甲基叶酸、ALDH2缺陷禁酒）
   - 运动基因 → 推荐匹配肌肉类型的训练（ACTN3 XX偏耐力、RR偏力量）
   - 睡眠基因 → 调整作息建议
   - 疾病风险基因 → 在warnings中提醒相关指标监测

🚨 【空气质量警告 - 必须严格执行】基于AQI指数（包含PM2.5）判断户外运动安全性：
- AQI ≤ 50（优）：空气清新，非常适合各类户外运动
- AQI 51-100（良）：空气质量可接受，可进行户外运动，敏感人群注意强度
- AQI 101-150（轻度污染）：⚠️ 敏感人群（有鼻炎、哮喘、心血管疾病等）应减少户外运动，建议室内运动
- AQI 151-200（中度污染）：⚠️ 所有人应减少户外运动时间和强度，优先选择室内运动
- AQI > 200（重度/严重污染）：🚫 强烈建议避免一切户外运动！必须选择室内运动（如瑜伽、室内健身、力量训练等）
当空气质量差时，exercise_recommendations中的location必须是"室内"，并在warnings中明确提醒空气污染风险！

请用JSON格式返回分析结果，包含以下字段:
{
    "health_summary": "一段话总结用户当前的健康状况，结合TA的健康目标进行评估（100字以内）",
    "key_insights": ["基于用户个人情况的关键洞察1", "关键洞察2", "关键洞察3"],
    "sleep_advice": "针对睡眠的具体建议，考虑用户的作息习惯和工作情况",
    "activity_advice": "针对运动活动的具体建议。格式：'昨天您...[评价昨天]，本周累计...[评价本周]，今天建议...[给出今天计划]'。不要评价今天的步数或运动量！",
    "heart_health_advice": "针对心率/心血管的建议",
    "recovery_advice": "针对恢复和压力管理的建议，考虑用户的工作强度",
    "environment_advice": "基于当天天气和空气质量的运动建议",
    "exercise_recommendations": [
        {
            "type": "运动类型（如跑步、瑜伽、力量训练等）",
            "location": "室内/室外",
            "duration": "建议时长（如30分钟）",
            "intensity": "强度（低/中/高）",
            "best_time": "最佳运动时间（如上午9-11点）",
            "reason": "推荐原因"
        }
    ],
    "today_focus": "今天最应该关注的一件事（与用户目标相关）",
    "today_actions": ["今天要做的具体行动1（包含时间和数量）", "行动2", "行动3"],
    "warnings": ["需要注意的健康风险，特别关注用户的慢性病情况和环境因素"],
    "encouragement": "一句针对用户当前状态的鼓励话语"
}

注意：只返回JSON，不要有其他文字。"""

            user_prompt = f"""请基于以下健康数据，为用户提供今日健康建议：

{health_prompt}

请分析这些数据并给出具体、可执行的建议，特别注意结合环境信息给出合适的运动推荐。"""

            content = await self._provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1500,
                timeout=60,
            )

            content = content.strip()

            # 尝试解析JSON
            # 处理可能的markdown代码块
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            llm_result = json.loads(content)
            llm_result["available"] = True

            logger.info(f"LLM分析完成，用户ID: {user_id}")
            return llm_result

        except json.JSONDecodeError as e:
            logger.error(f"LLM返回结果解析失败: {e}")
            return {
                "available": True,
                "error": "分析结果解析失败",
                "raw_response": content if 'content' in locals() else None
            }
        except Exception as e:
            logger.error(f"LLM分析失败: {e}")
            return {
                "available": False,
                "error": str(e)
            }

    async def generate_weekly_report(
        self,
        db: Session,
        user_id: int,
        week_data: List[GarminData]
    ) -> Dict[str, Any]:
        """生成周报分析"""
        if not self.is_available():
            return {"available": False, "message": "LLM服务不可用"}

        if not week_data:
            return {"available": False, "message": "无周数据"}

        try:
            user_context = self._build_user_context(db, user_id)

            # 构建周数据摘要
            week_summary = self._build_week_summary(week_data)

            system_prompt = """你是一位专业的智能助理。请基于用户一周的健康数据，生成一份周报分析。

请用JSON格式返回:
{
    "week_summary": "本周健康状况总结（150字以内）",
    "achievements": ["本周做得好的方面"],
    "improvements": ["需要改进的方面"],
    "trends": {
        "sleep": "睡眠趋势描述",
        "activity": "活动趋势描述",
        "heart_health": "心率趋势描述"
    },
    "next_week_goals": ["下周建议目标1", "下周建议目标2", "下周建议目标3"],
    "health_score": 85,  // 0-100的健康评分
    "key_recommendation": "最重要的一条建议"
}"""

            user_prompt = f"""用户信息:
{json.dumps(user_context, ensure_ascii=False, indent=2)}

本周健康数据摘要:
{week_summary}

请分析并生成周报。"""

            content = await self._provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=1000,
                timeout=60,
            )

            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)
            result["available"] = True
            return result

        except Exception as e:
            logger.error(f"周报生成失败: {e}")
            return {"available": False, "error": str(e)}

    def _build_week_summary(self, week_data: List[GarminData]) -> str:
        """构建周数据摘要"""
        if not week_data:
            return "无数据"

        sleep_scores = [d.sleep_score for d in week_data if d.sleep_score]
        sleep_durations = [d.total_sleep_duration for d in week_data if d.total_sleep_duration]
        steps_list = [d.steps for d in week_data if d.steps]
        rhr_list = [d.resting_heart_rate for d in week_data if d.resting_heart_rate]
        stress_list = [d.stress_level for d in week_data if d.stress_level]

        summary = f"""
数据天数: {len(week_data)}天
日期范围: {week_data[-1].record_date if week_data else ''} 至 {week_data[0].record_date if week_data else ''}

睡眠:
- 平均睡眠分数: {round(sum(sleep_scores)/len(sleep_scores), 1) if sleep_scores else '无数据'}
- 最高睡眠分数: {max(sleep_scores) if sleep_scores else '无数据'}
- 最低睡眠分数: {min(sleep_scores) if sleep_scores else '无数据'}
- 平均睡眠时长: {round(sum(sleep_durations)/len(sleep_durations)/60, 1) if sleep_durations else '无数据'}小时

活动:
- 平均步数: {round(sum(steps_list)/len(steps_list)) if steps_list else '无数据'}步
- 总步数: {sum(steps_list) if steps_list else '无数据'}步
- 达标天数(>10000步): {len([s for s in steps_list if s >= 10000]) if steps_list else 0}天

心率:
- 平均静息心率: {round(sum(rhr_list)/len(rhr_list), 1) if rhr_list else '无数据'} bpm
- 最低静息心率: {min(rhr_list) if rhr_list else '无数据'} bpm

压力:
- 平均压力水平: {round(sum(stress_list)/len(stress_list), 1) if stress_list else '无数据'}
"""
        return summary


# 单例实例
llm_analyzer = LLMHealthAnalyzer()
