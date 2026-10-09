"""Source-owned action occurrences; reads never mutate this index."""
import uuid
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, JSON, Text, Index
from app.database import Base

class HealthNavigationOccurrence(Base):
    __tablename__ = 'health_navigation_occurrences'
    __table_args__ = (UniqueConstraint('user_id','source','plan_date','action_key',name='uq_health_nav_occurrence'), Index('ix_health_nav_user_date','user_id','plan_date'))
    id = Column(String(32), primary_key=True, default=lambda:uuid.uuid4().hex)
    user_id = Column(Integer,ForeignKey('users.id'),nullable=False)
    plan_id = Column(Integer,ForeignKey('daily_operating_plans.id'),nullable=False)
    source = Column(String(40),nullable=False,default='daily_plan')
    plan_date = Column(Date,nullable=False)
    action_key = Column(String(160),nullable=False)
    title = Column(Text,nullable=False)
    completion_criterion = Column(Text,nullable=False,default='按 Health 中的行动说明执行后由本人确认')
    safety_state = Column(String(20),nullable=False,default='unknown')
    execution_status = Column(String(20),nullable=False,default='pending')
    revision = Column(Integer,nullable=False,default=1)
    content_hash = Column(String(64),nullable=False)
    source_as_of = Column(DateTime(timezone=True),nullable=False)
    last_event_id = Column(Integer,ForeignKey('intervention_events.id'),nullable=True)

class HealthNavigationDay(Base):
    __tablename__ = 'health_navigation_days'
    __table_args__ = (UniqueConstraint('user_id','plan_date',name='uq_health_nav_day'),)
    id = Column(Integer,primary_key=True)
    user_id = Column(Integer,ForeignKey('users.id'),nullable=False)
    plan_date = Column(Date,nullable=False)
    source_as_of = Column(DateTime(timezone=True),nullable=False)

class HealthNavigationOperation(Base):
    __tablename__ = 'health_navigation_operations'
    __table_args__ = (UniqueConstraint('user_id','operation_id',name='uq_health_nav_operation'),)
    id = Column(Integer,primary_key=True)
    user_id = Column(Integer,ForeignKey('users.id'),nullable=False)
    occurrence_id = Column(String(32),ForeignKey('health_navigation_occurrences.id'),nullable=False)
    operation_id = Column(String(36),nullable=False)
    payload_hash = Column(String(64),nullable=False)
    receipt = Column(JSON,nullable=False)
    created_at = Column(DateTime(timezone=True),nullable=False)
