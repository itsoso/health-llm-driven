"""
chat_service 拆分重构的单元测试

测试拆分后的三个新模块：
- ChatActionHandler: Action 解析与执行
- ChatSkillsHandler: OpenClaw Skills 管理命令
- HealthContextBuilder: 健康上下文构建
以及重构后的 ChatService 本身
"""
import pytest
from datetime import date, datetime, timedelta

from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.daily_health import WaterIntake, GarminData
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.excretion import ExcretionRecord
from app.models.vocabulary import VocabularyWord
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.services.chat_action_handler import ChatActionHandler
from app.services.chat_skills_handler import ChatSkillsHandler
from app.services.health_context_builder import HealthContextBuilder
from app.services.chat_service import ChatService


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def test_user(db):
    user = User(name="重构测试用户", phone="13900000001")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_profile(db, test_user):
    profile = UserProfile(
        user_id=test_user.id,
        height_cm=175,
        birth_date=date(1990, 6, 15),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@pytest.fixture
def checkin_template(db, test_user):
    t = CheckinTemplate(
        user_id=test_user.id,
        name="俯卧撑",
        category="exercise",
        icon="💪",
        unit="个",
        default_target=50,
        is_active=True,
        is_archived=False,
        total_checkins=0,
        total_value=0,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def supplement_def(db, test_user):
    s = SupplementDefinition(
        user_id=test_user.id,
        name="维生素D",
        dosage="1粒",
        is_active=True,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture
def action_handler(db):
    return ChatActionHandler(db)


@pytest.fixture
def skills_handler():
    return ChatSkillsHandler()


@pytest.fixture
def context_builder(db):
    return HealthContextBuilder(db)


# ══════════════════════════════════════════════════════════
# ChatActionHandler 测试
# ══════════════════════════════════════════════════════════

class TestParseActions:
    """Action 解析"""

    def test_parse_valid_actions(self, action_handler):
        """解析合法的 <<<ACTIONS:[...]>>> 标记"""
        reply = '好的，已记录。<<<ACTIONS:[{"type":"water","amount":250}]>>>'
        clean, actions = action_handler.parse_actions(reply)
        assert clean == "好的，已记录。"
        assert len(actions) == 1
        assert actions[0]["type"] == "water"
        assert actions[0]["amount"] == 250

    def test_parse_no_actions(self, action_handler):
        """普通文本无 action 标记"""
        reply = "今天天气不错，适合跑步。"
        clean, actions = action_handler.parse_actions(reply)
        assert clean == reply
        assert actions == []

    def test_parse_invalid_json(self, action_handler):
        """JSON 格式错误时返回空列表"""
        reply = '已记录<<<ACTIONS:[{invalid json}]>>>'
        clean, actions = action_handler.parse_actions(reply)
        assert actions == []

    def test_parse_multiple_actions(self, action_handler):
        """解析多个 action"""
        reply = '好的<<<ACTIONS:[{"type":"water","amount":500},{"type":"checkin","template_id":1,"value":30}]>>>'
        clean, actions = action_handler.parse_actions(reply)
        assert clean == "好的"
        assert len(actions) == 2
        assert actions[0]["type"] == "water"
        assert actions[1]["type"] == "checkin"


class TestWaterAction:
    """喝水记录"""

    def test_handle_water_action(self, db, test_user, action_handler):
        """记录饮水"""
        today = date.today()
        now = datetime.now()
        result = action_handler._handle_water_action(
            test_user.id, {"amount": 300, "drink_type": "茶"}, today, now
        )
        assert result is not None
        assert result["type"] == "water"
        assert result["status"] == "saved"
        assert "300ml" in result["message"]

        record = db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).first()
        assert record is not None
        assert record.amount_ml == 300
        assert record.drink_type == "茶"

    def test_handle_water_default_amount(self, db, test_user, action_handler):
        """默认250ml饮水量"""
        today = date.today()
        now = datetime.now()
        result = action_handler._handle_water_action(
            test_user.id, {}, today, now
        )
        assert result is not None
        record = db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).first()
        assert record.amount_ml == 250


class TestCheckinAction:
    """打卡记录"""

    def test_handle_checkin_by_id(self, db, test_user, action_handler, checkin_template):
        """通过 template_id 打卡"""
        today = date.today()
        result = action_handler._handle_checkin_action(
            test_user.id,
            {"template_id": checkin_template.id, "value": 30},
            today,
        )
        assert result is not None
        assert result["type"] == "checkin"
        assert result["status"] == "saved"

        record = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.template_id == checkin_template.id,
        ).first()
        assert record is not None
        assert record.value == 30

    def test_handle_checkin_by_name(self, db, test_user, action_handler, checkin_template):
        """通过名称匹配打卡"""
        today = date.today()
        result = action_handler._handle_checkin_action(
            test_user.id,
            {"template_name": "俯卧撑", "value": 20},
            today,
        )
        assert result is not None
        assert result["status"] == "saved"

    def test_handle_checkin_accumulates(self, db, test_user, action_handler, checkin_template):
        """同一天重复打卡累加数值"""
        today = date.today()
        action_handler._handle_checkin_action(
            test_user.id, {"template_id": checkin_template.id, "value": 20}, today,
        )
        result = action_handler._handle_checkin_action(
            test_user.id, {"template_id": checkin_template.id, "value": 30}, today,
        )
        assert result["status"] == "updated"

        record = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.template_id == checkin_template.id,
        ).first()
        assert record.value == 50  # 20 + 30

    def test_handle_checkin_template_not_found(self, db, test_user, action_handler):
        """模板不存在返回 None"""
        today = date.today()
        result = action_handler._handle_checkin_action(
            test_user.id, {"template_id": 99999}, today,
        )
        assert result is None


class TestSupplementAction:
    """补剂记录"""

    def test_handle_supplement_by_id(self, db, test_user, action_handler, supplement_def):
        """通过 ID 记录补剂"""
        today = date.today()
        result = action_handler._handle_supplement_action(
            test_user.id, {"supplement_id": supplement_def.id}, today,
        )
        assert result is not None
        assert result["type"] == "supplement"
        assert result["status"] == "saved"
        assert "维生素D" in result["message"]

    def test_handle_supplement_by_name(self, db, test_user, action_handler, supplement_def):
        """通过名称匹配补剂"""
        today = date.today()
        result = action_handler._handle_supplement_action(
            test_user.id, {"supplement_name": "维生素"}, today,
        )
        assert result is not None
        assert result["status"] == "saved"

    def test_handle_supplement_not_found(self, db, test_user, action_handler):
        """补剂不存在返回 None"""
        today = date.today()
        result = action_handler._handle_supplement_action(
            test_user.id, {"supplement_name": "不存在的补剂"}, today,
        )
        assert result is None

    def test_handle_supplement_already_taken(self, db, test_user, action_handler, supplement_def):
        """重复记录更新为已服用"""
        today = date.today()
        action_handler._handle_supplement_action(
            test_user.id, {"supplement_id": supplement_def.id}, today,
        )
        result = action_handler._handle_supplement_action(
            test_user.id, {"supplement_id": supplement_def.id}, today,
        )
        assert result["status"] == "updated"


class TestExcretionAction:
    """排泄记录"""

    def test_handle_excretion_bowel(self, db, test_user, action_handler):
        """记录大便"""
        today = date.today()
        now = datetime.now()
        result = action_handler._handle_excretion_action(
            test_user.id,
            {"excretion_type": "bowel", "stool_type": 4, "color": "brown"},
            today, now,
        )
        assert result is not None
        assert result["status"] == "saved"
        assert "大便" in result["message"]

        record = db.query(ExcretionRecord).filter(ExcretionRecord.user_id == test_user.id).first()
        assert record.type == "bowel"
        assert record.stool_type == 4

    def test_handle_excretion_invalid_type_defaults_bowel(self, db, test_user, action_handler):
        """无效类型默认为 bowel"""
        today = date.today()
        now = datetime.now()
        result = action_handler._handle_excretion_action(
            test_user.id, {"excretion_type": "invalid"}, today, now,
        )
        record = db.query(ExcretionRecord).filter(ExcretionRecord.user_id == test_user.id).first()
        assert record.type == "bowel"


class TestVocabularyAction:
    """单词学习"""

    def test_handle_vocabulary_new_word(self, db, test_user, action_handler):
        """保存新单词"""
        result = action_handler._handle_vocabulary_action(
            test_user.id,
            {
                "word": "abandon",
                "phonetic_us": "/əˈbændən/",
                "meanings": '[{"pos":"v.","def":"放弃"}]',
            },
        )
        assert result is not None
        assert result["type"] == "vocabulary"
        assert result["status"] == "saved"

        vocab = db.query(VocabularyWord).filter(
            VocabularyWord.user_id == test_user.id,
            VocabularyWord.word == "abandon",
        ).first()
        assert vocab is not None
        assert vocab.phonetic_us == "/əˈbændən/"

    def test_handle_vocabulary_review_word(self, db, test_user, action_handler):
        """复习已存在的单词"""
        action_handler._handle_vocabulary_action(
            test_user.id, {"word": "hello", "meanings": "你好"},
        )
        result = action_handler._handle_vocabulary_action(
            test_user.id, {"word": "hello", "meanings": "你好，打招呼"},
        )
        assert result["status"] == "updated"

        vocab = db.query(VocabularyWord).filter(
            VocabularyWord.word == "hello",
        ).first()
        assert vocab.review_count == 2
        assert vocab.meanings == "你好，打招呼"  # 更新为最新的

    def test_handle_vocabulary_empty_word(self, db, test_user, action_handler):
        """空单词返回 None"""
        result = action_handler._handle_vocabulary_action(test_user.id, {"word": ""})
        assert result is None


class TestExecuteActions:
    """Action 执行调度"""

    def test_execute_unknown_type(self, db, test_user, action_handler):
        """未知 action 类型被跳过"""
        results = action_handler.execute_actions(
            test_user.id, [{"type": "unknown_type"}]
        )
        assert results == []

    def test_execute_multiple_actions(self, db, test_user, action_handler):
        """一次执行多个 action"""
        results = action_handler.execute_actions(
            test_user.id,
            [
                {"type": "water", "amount": 200},
                {"type": "water", "amount": 300},
            ]
        )
        assert len(results) == 2
        records = db.query(WaterIntake).filter(WaterIntake.user_id == test_user.id).all()
        assert len(records) == 2


# ══════════════════════════════════════════════════════════
# ChatSkillsHandler 测试
# ══════════════════════════════════════════════════════════

class TestChatSkillsHandler:
    """Skills 管理命令"""

    def test_non_admin_returns_none(self, skills_handler):
        """非管理员始终返回 None"""
        result = skills_handler.try_handle_skill_command("列出已安装技能", is_admin=False)
        assert result is None

    def test_unrecognized_command_returns_none(self, skills_handler):
        """无法识别的命令返回 None"""
        result = skills_handler.try_handle_skill_command("今天天气怎么样", is_admin=True)
        assert result is None

    def test_list_skills_matches(self, skills_handler):
        """匹配列出技能命令"""
        # 这会实际调用 openclaw_skills_service，可能因 SSH 不可用而报错
        # 但至少验证命令模式匹配不返回 None
        result = skills_handler.try_handle_skill_command("列出已安装技能", is_admin=True)
        assert result is not None  # 即使失败也会返回错误消息

    def test_gateway_status_matches(self, skills_handler):
        """匹配 gateway 状态命令"""
        result = skills_handler.try_handle_skill_command("gateway 状态", is_admin=True)
        assert result is not None

    def test_frontmatter_install_matches(self, skills_handler):
        """匹配 SKILL.md 内容安装"""
        content = "---\nname: test-skill\n---\nTest skill content"
        result = skills_handler.try_handle_skill_command(content, is_admin=True)
        assert result is not None


# ══════════════════════════════════════════════════════════
# HealthContextBuilder 测试
# ══════════════════════════════════════════════════════════

class TestExtractCity:
    """城市名提取"""

    def test_airport_location(self, context_builder):
        """从机场地点提取城市名"""
        assert context_builder._extract_city_from_location("成都双流T2") == "成都"
        assert context_builder._extract_city_from_location("杭州萧山T4") == "杭州"

    def test_station_location(self, context_builder):
        """从火车站地点提取城市名"""
        assert context_builder._extract_city_from_location("成都东站") == "成都"
        assert context_builder._extract_city_from_location("北京西站") == "北京"

    def test_plain_city(self, context_builder):
        """普通城市名不变"""
        assert context_builder._extract_city_from_location("江油") == "江油"
        assert context_builder._extract_city_from_location("上海") == "上海"

    def test_empty_location(self, context_builder):
        """空字符串返回原值"""
        assert context_builder._extract_city_from_location("") == ""


class TestTrimContextByRelevance:
    """上下文相关性裁剪"""

    def test_no_match_keeps_all(self, context_builder):
        """通用问题不裁剪"""
        parts = ["睡眠数据: 7.5小时", "运动统计: 8000步", "饮水: 1500ml"]
        result = context_builder._trim_context_by_relevance(parts, "我的健康状况怎么样")
        assert result == parts

    def test_sleep_question_keeps_sleep(self, context_builder):
        """睡眠相关问题保留睡眠数据全文"""
        parts = [
            "最近3天睡眠:\n  2026-01-01 分数80 总时长7h30min\n  2026-01-02 分数75",
            "最近7天运动统计(7天): 平均步数8000, 总计56000",
            "今日饮水: 1500ml/2000ml (75%)",
        ]
        result = context_builder._trim_context_by_relevance(parts, "我最近睡得怎么样")
        # 睡眠保留全文
        assert "\n" in result[0]
        # 运动被截断为首行
        assert "\n" not in result[1]

    def test_exercise_question_keeps_exercise(self, context_builder):
        """运动问题保留运动数据"""
        parts = [
            "最近3天睡眠:\n  多行数据",
            "最近7天运动统计(7天):\n  平均步数8000",
        ]
        result = context_builder._trim_context_by_relevance(parts, "我的步数怎么样")
        assert "\n" not in result[0]  # 睡眠被截断
        assert "\n" in result[1]  # 运动保留全文


class TestBuildActivityContext:
    """活动上下文构建"""

    def test_empty_user_returns_empty(self, db, test_user, context_builder):
        """无数据用户返回空字符串"""
        result = context_builder.build_activity_context(test_user.id)
        assert result == ""

    def test_with_checkin_templates(self, db, test_user, context_builder, checkin_template):
        """有打卡模板时返回模板列表"""
        result = context_builder.build_activity_context(test_user.id)
        assert "俯卧撑" in result
        assert "打卡模板" in result

    def test_with_supplements(self, db, test_user, context_builder, supplement_def):
        """有补剂时返回补剂列表"""
        result = context_builder.build_activity_context(test_user.id)
        assert "维生素D" in result
        assert "补剂列表" in result


# ══════════════════════════════════════════════════════════
# ChatService 重构后集成测试
# ══════════════════════════════════════════════════════════

class TestChatServiceInit:
    """ChatService 初始化"""

    def test_creates_sub_handlers(self, db):
        """初始化时创建三个子处理器"""
        service = ChatService(db)
        assert isinstance(service._context_builder, HealthContextBuilder)
        assert isinstance(service._action_handler, ChatActionHandler)
        assert isinstance(service._skills_handler, ChatSkillsHandler)


class TestFoodMessageDetection:
    """饮食消息检测"""

    def test_food_with_quantities(self, db):
        """多个量词模式检测为饮食"""
        service = ChatService(db)
        assert service._is_food_message("吃了三个鸡蛋两片面包") is True

    def test_food_action_keywords(self, db):
        """显式饮食关键词"""
        service = ChatService(db)
        assert service._is_food_message("帮我计算热量") is True
        assert service._is_food_message("记录饮食") is True

    def test_food_context_with_quantity(self, db):
        """饮食上下文 + 量词"""
        service = ChatService(db)
        assert service._is_food_message("早餐吃了2个包子") is True

    def test_not_food_message(self, db):
        """非饮食消息"""
        service = ChatService(db)
        assert service._is_food_message("今天天气怎么样") is False
        assert service._is_food_message("我的步数是多少") is False


class TestSearchDetection:
    """搜索检测"""

    def test_short_message_no_search(self, db):
        """短消息不搜索"""
        service = ChatService(db)
        assert service._should_search("嗯") is False
        assert service._should_search("好") is False

    def test_greeting_no_search(self, db):
        """打招呼不搜索"""
        service = ChatService(db)
        assert service._should_search("你好") is False
        assert service._should_search("谢谢") is False

    def test_food_message_no_search(self, db):
        """饮食记录不搜索"""
        service = ChatService(db)
        assert service._should_search("吃了三个鸡蛋两片面包") is False

    def test_normal_question_searches(self, db):
        """正常问题需要搜索"""
        service = ChatService(db)
        assert service._should_search("维生素D有什么作用") is True
        assert service._should_search("跑步前怎么热身") is True


class TestMealTypeByTime:
    """餐次推断"""

    def test_returns_string(self, db):
        """返回有效的餐次字符串"""
        service = ChatService(db)
        meal_type = service._get_meal_type_by_time()
        assert meal_type in ("breakfast", "lunch", "dinner", "snack")
