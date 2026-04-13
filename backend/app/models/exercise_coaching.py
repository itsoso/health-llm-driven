"""
运动动作指导笔记 —— 记录 AI 对用户运动姿势的分析和纠正建议。

来源：
- 视频分析（用户上传运动视频，AI 提取帧分析）
- 文字描述（用户描述动作问题，AI 给出建议）
- 教练反馈（人工录入）

每条笔记绑定到具体的 exercise_type（俯卧撑/深蹲/跑步等），
可以在对应的 StrengthCard / WorkoutCard 里展示"上次纠正要点"。
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class ExerciseCoachingNote(Base):
    __tablename__ = "exercise_coaching_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 运动类型
    exercise_type = Column(String(50), nullable=False, index=True)  # 俯卧撑/深蹲/跑步/...

    # 分析内容
    title = Column(String(200))               # 简短标题
    good_points = Column(Text)                 # 做得好的（markdown）
    issues = Column(Text)                      # 需要改进的（markdown）
    checklist = Column(Text)                   # 训练 checklist（markdown）
    source_type = Column(String(30), default="ai_video")  # ai_video / ai_text / manual

    # 媒体
    video_url = Column(String(500))            # 原始视频 URL（如果有）
    frame_urls = Column(Text)                  # 关键帧 URLs（JSON 数组，如果有）

    # 状态
    is_active = Column(Boolean, default=True)  # 最新的一条为 active，旧的自动归档
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
