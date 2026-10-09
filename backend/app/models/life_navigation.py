"""Owner-scoped aggregate with bounded typed private planning history."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON
from app.database import Base

class LifeNavigationWorkspace(Base):
    __tablename__ = 'life_navigation_workspaces'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    revision = Column(Integer, nullable=False, default=0)
    data = Column(JSON, nullable=False)
    history = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), nullable=False)
