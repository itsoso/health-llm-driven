"""补剂管理模型"""
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Boolean, Time
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class SupplementDefinition(Base):
    """补剂定义 - 用户的补剂列表"""
    __tablename__ = "supplement_definitions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    name = Column(String, nullable=False)  # 补剂名称
    dosage = Column(String)  # 剂量（如：100mg, 5000IU）
    timing = Column(String)  # 服用时间（morning/noon/evening/bedtime）
    category = Column(String)  # 分类（维生素/矿物质/抗氧化/中药等）
    
    description = Column(Text)  # 描述/备注
    is_active = Column(Boolean, default=True)  # 是否启用
    sort_order = Column(Integer, default=0)  # 排序顺序
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="supplement_definitions")
    records = relationship("SupplementRecord", back_populates="supplement", cascade="all, delete-orphan")


class SupplementRecord(Base):
    """补剂打卡记录"""
    __tablename__ = "supplement_records"
    
    id = Column(Integer, primary_key=True, index=True)
    supplement_id = Column(Integer, ForeignKey("supplement_definitions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    taken = Column(Boolean, default=False)  # 是否已服用
    taken_time = Column(Time)  # 实际服用时间
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    supplement = relationship("SupplementDefinition", back_populates="records")
    user = relationship("User", backref="supplement_records")

