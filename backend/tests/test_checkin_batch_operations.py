"""打卡系统批量操作测试 - 测试优化后的批量查询"""
import pytest
from datetime import date, timedelta
from sqlalchemy import func
from app.models.user import User
from app.models.checkin import CheckinTemplate, CheckinRecord


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="checkinbatch",
        email="checkinbatch@example.com",
        hashed_password="hashed_password",
        name="打卡批量测试用户",
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_templates(db, test_user):
    """创建测试打卡模板"""
    templates = []
    categories = ["exercise", "health", "habit"]

    for i, category in enumerate(categories):
        for j in range(3):  # 每个分类3个模板
            template = CheckinTemplate(
                user_id=test_user.id,
                name=f"{category}模板{j+1}",
                category=category,
                icon="✅",
                default_target=1.0,
                unit="次",
                is_active=True,
                is_archived=False,
                sort_order=i * 3 + j
            )
            db.add(template)
            templates.append(template)

    db.commit()
    for t in templates:
        db.refresh(t)
    return templates


class TestCheckinBatchQueries:
    """测试打卡系统的批量查询优化"""

    def test_batch_load_today_records(self, db, test_user, test_templates):
        """测试批量加载今日记录"""
        today = date.today()

        # 为前5个模板创建今日记录
        for i in range(5):
            record = CheckinRecord(
                template_id=test_templates[i].id,
                user_id=test_user.id,
                checkin_date=today,
                value=1.0,
                target=1.0,
                completion_rate=100.0
            )
            db.add(record)
        db.commit()

        # 批量查询今日完成的模板ID
        template_ids = [t.id for t in test_templates]
        today_records = db.query(CheckinRecord.template_id).filter(
            CheckinRecord.template_id.in_(template_ids),
            CheckinRecord.checkin_date == today
        ).all()
        completed_template_ids = {r.template_id for r in today_records}

        # 验证结果
        assert len(completed_template_ids) == 5
        for i in range(5):
            assert test_templates[i].id in completed_template_ids
        for i in range(5, 9):
            assert test_templates[i].id not in completed_template_ids

    def test_batch_count_completed(self, db, test_user, test_templates):
        """测试批量统计完成数量"""
        today = date.today()

        # 创建一些完成记录
        for i in range(7):
            record = CheckinRecord(
                template_id=test_templates[i % len(test_templates)].id,
                user_id=test_user.id,
                checkin_date=today,
                value=1.0,
                target=1.0,
                completion_rate=100.0
            )
            db.add(record)
        db.commit()

        # 使用 count 进行批量统计
        completed_count = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.checkin_date == today
        ).count()

        assert completed_count == 7

    def test_batch_daily_trend(self, db, test_user, test_templates):
        """测试批量查询每日趋势"""
        today = date.today()

        # 创建过去7天的记录
        for i in range(7):
            day = today - timedelta(days=i)
            # 每天创建不同数量的记录
            for j in range(i + 1):
                if j < len(test_templates):
                    record = CheckinRecord(
                        template_id=test_templates[j].id,
                        user_id=test_user.id,
                        checkin_date=day,
                        value=1.0,
                        target=1.0,
                        completion_rate=100.0
                    )
                    db.add(record)
        db.commit()

        # 使用 GROUP BY 批量查询趋势
        week_ago = today - timedelta(days=6)
        trend_records = db.query(
            CheckinRecord.checkin_date,
            func.count(CheckinRecord.id).label('count')
        ).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.checkin_date >= week_ago,
            CheckinRecord.checkin_date <= today
        ).group_by(CheckinRecord.checkin_date).all()

        trend_map = {r.checkin_date: r.count for r in trend_records}

        # 验证趋势数据
        assert len(trend_map) == 7  # 7天都有记录
        assert trend_map[today] == 1  # 今天1条
        assert trend_map[today - timedelta(days=1)] == 2  # 昨天2条

    def test_batch_category_stats(self, db, test_user, test_templates):
        """测试批量统计分类数据"""
        # 统计每个分类的模板数量
        category_counts = {}
        for template in test_templates:
            cat = template.category
            if cat not in category_counts:
                category_counts[cat] = 0
            category_counts[cat] += 1

        # 验证每个分类3个模板
        assert category_counts["exercise"] == 3
        assert category_counts["health"] == 3
        assert category_counts["habit"] == 3

    def test_batch_records_with_template_info(self, db, test_user, test_templates):
        """测试批量加载记录及其模板信息"""
        today = date.today()

        # 创建多个记录
        for i, template in enumerate(test_templates[:5]):
            record = CheckinRecord(
                template_id=template.id,
                user_id=test_user.id,
                checkin_date=today - timedelta(days=i),
                value=1.0,
                target=1.0,
                completion_rate=100.0
            )
            db.add(record)
        db.commit()

        # 批量查询记录
        records = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == test_user.id
        ).order_by(CheckinRecord.checkin_date.desc()).all()

        # 批量加载模板信息
        template_ids = list(set(r.template_id for r in records))
        templates = {t.id: t for t in db.query(CheckinTemplate).filter(
            CheckinTemplate.id.in_(template_ids)
        ).all()}

        # 验证每条记录都能关联到模板
        assert len(records) == 5
        for record in records:
            template = templates.get(record.template_id)
            assert template is not None
            assert template.user_id == test_user.id

    def test_batch_date_range_filter(self, db, test_user, test_templates):
        """测试按日期范围批量过滤记录"""
        today = date.today()
        start = today - timedelta(days=5)
        end = today - timedelta(days=2)

        # 创建10天的记录
        for i in range(10):
            record = CheckinRecord(
                template_id=test_templates[0].id,
                user_id=test_user.id,
                checkin_date=today - timedelta(days=i),
                value=1.0,
                target=1.0,
                completion_rate=100.0
            )
            db.add(record)
        db.commit()

        # 使用日期范围过滤
        records = db.query(CheckinRecord).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.checkin_date >= start,
            CheckinRecord.checkin_date <= end
        ).all()

        # 应该有4条记录（第2、3、4、5天）
        assert len(records) == 4
        for record in records:
            assert start <= record.checkin_date <= end

    def test_batch_calendar_aggregation(self, db, test_user, test_templates):
        """测试日历聚合查询"""
        today = date.today()
        year, month = today.year, today.month
        start_date = date(year, month, 1)

        # 在本月创建记录
        days_with_records = []
        for day_offset in [0, 1, 2, 5, 10]:
            day = today - timedelta(days=day_offset)
            if day.month == month:
                days_with_records.append(day)
                for i in range(7):  # 每天7条记录
                    if i < len(test_templates):
                        record = CheckinRecord(
                            template_id=test_templates[i].id,
                            user_id=test_user.id,
                            checkin_date=day,
                            value=1.0,
                            target=1.0,
                            completion_rate=100.0
                        )
                        db.add(record)
        db.commit()

        # 使用 GROUP BY 聚合每日记录数
        from calendar import monthrange
        _, days_in_month = monthrange(year, month)
        end_date = date(year, month, days_in_month)

        records = db.query(
            CheckinRecord.checkin_date,
            func.count(CheckinRecord.id).label('count')
        ).filter(
            CheckinRecord.user_id == test_user.id,
            CheckinRecord.checkin_date >= start_date,
            CheckinRecord.checkin_date <= end_date
        ).group_by(CheckinRecord.checkin_date).all()

        # 验证聚合结果
        for r in records:
            assert r.count == 7  # 每天7条
