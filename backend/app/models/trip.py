"""
行程记录模型 - 记录旅行中的交通和活动
"""
from datetime import date, datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Trip(Base):
    """行程主表"""
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    trip_name = Column(String(200), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    destination = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="trips")
    items = relationship("TripItem", back_populates="trip", cascade="all, delete-orphan",
                         order_by="TripItem.item_date, TripItem.item_order")

    __table_args__ = (
        Index('idx_trip_user_start', 'user_id', 'start_date'),
    )


class TripItem(Base):
    """行程明细表"""
    __tablename__ = "trip_items"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    item_date = Column(Date, nullable=False)
    item_order = Column(Integer, default=0)
    item_type = Column(String(50), nullable=False)  # flight/train/bus/taxi/hotel/activity/other

    title = Column(String(200), nullable=False)

    # 交通相关
    origin = Column(String(100), nullable=True)
    destination = Column(String(100), nullable=True)
    departure_time = Column(String(10), nullable=True)
    arrival_time = Column(String(10), nullable=True)
    transport_number = Column(String(50), nullable=True)
    carrier = Column(String(100), nullable=True)
    departure_terminal = Column(String(20), nullable=True)
    arrival_terminal = Column(String(20), nullable=True)

    # 活动/酒店相关
    location = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    trip = relationship("Trip", back_populates="items")
    user = relationship("User")

    __table_args__ = (
        Index('idx_tripitem_trip_date', 'trip_id', 'item_date'),
    )
