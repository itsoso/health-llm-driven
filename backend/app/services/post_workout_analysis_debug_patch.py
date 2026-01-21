# 运动后分析 Debug 模式补丁
# 这个文件展示需要在 post_workout_analysis.py 中添加的 debug 逻辑

# 在各个步骤中添加 debug 信息的示例：

"""
步骤1：获取运动记录
"""
if debug_info:
    debug_info["steps"].append("1. 获取运动记录详情")

workout = db.query(WorkoutRecord).filter_by(
    id=workout_id,
    user_id=user_id
).first()

if not workout:
    return {"success": False, "error": "运动记录不存在"}

if debug_info:
    debug_info["data_sources"]["workout"] = {
        "workout_type": workout.workout_type,
        "workout_date": str(workout.workout_date),
        "duration_seconds": workout.duration_seconds,
        "distance_meters": workout.distance_meters,
        "avg_heart_rate": workout.avg_heart_rate,
        "max_heart_rate": workout.max_heart_rate,
        "avg_pace_seconds_per_km": workout.avg_pace_seconds_per_km,
        "calories": workout.calories,
        "training_effect_aerobic": workout.training_effect_aerobic,
        "training_effect_anaerobic": workout.training_effect_anaerobic
    }
    
    duration_min = workout.duration_seconds // 60 if workout.duration_seconds else 0
    distance_km = round(workout.distance_meters / 1000, 1) if workout.distance_meters else 0
    debug_info["reasoning"].append(
        f"✅ 运动记录：{workout.workout_type}，{distance_km}公里，用时{duration_min}分钟"
    )

"""
步骤2：获取用户信息
"""
if debug_info:
    debug_info["steps"].append("2. 获取用户基本信息")

profile = db.query(UserProfile).filter_by(user_id=user_id).first()

if debug_info and profile:
    debug_info["data_sources"]["user_profile"] = {
        "age": profile.age,
        "weight": profile.weight,
        "fitness_level": profile.fitness_level
    }
    debug_info["reasoning"].append(
        f"✅ 用户资料：{profile.age}岁，体重{profile.weight}kg，{profile.fitness_level}健身水平"
    )

"""
步骤3：计算心率区间
"""
if debug_info:
    debug_info["steps"].append("3. 计算心率区间基准")

hr_zones = None
if profile and profile.age:
    digital_twin = DigitalTwinService(db, user_id)
    hr_zones = digital_twin.calculate_target_heart_rate_zones()
    
    if debug_info and hr_zones:
        debug_info["data_sources"]["heart_rate_zones"] = hr_zones
        debug_info["reasoning"].append(
            f"💓 计算心率区间基准：最大心率{hr_zones.get('max_heart_rate')}bpm"
        )

"""
步骤4：分析心率分布
"""
if debug_info:
    debug_info["steps"].append("4. 分析心率区间分布")

hr_analysis = self._analyze_heart_rate_distribution(workout, hr_zones)

if debug_info and hr_analysis.get("has_hr_data"):
    # 添加心率区间分布数据
    if workout.hr_zone_1_seconds or workout.hr_zone_2_seconds:
        debug_info["data_sources"]["hr_zone_distribution"] = {
            "zone1_seconds": workout.hr_zone_1_seconds,
            "zone2_seconds": workout.hr_zone_2_seconds,
            "zone3_seconds": workout.hr_zone_3_seconds,
            "zone4_seconds": workout.hr_zone_4_seconds,
            "zone5_seconds": workout.hr_zone_5_seconds
        }
        
        total_time = workout.duration_seconds or 1
        debug_info["reasoning"].append("📊 心率分布分析：")
        
        zones = [
            ("Zone 1 (恢复)", workout.hr_zone_1_seconds),
            ("Zone 2 (燃脂)", workout.hr_zone_2_seconds),
            ("Zone 3 (有氧)", workout.hr_zone_3_seconds),
            ("Zone 4 (乳酸阈)", workout.hr_zone_4_seconds),
            ("Zone 5 (最大)", workout.hr_zone_5_seconds)
        ]
        
        for zone_name, zone_seconds in zones:
            if zone_seconds:
                percentage = (zone_seconds / total_time) * 100
                debug_info["reasoning"].append(
                    f"   - {zone_name}: {percentage:.1f}% ({zone_seconds}秒)"
                )

"""
步骤5：评估训练强度
"""
if debug_info:
    debug_info["steps"].append("5. 评估训练强度")

intensity_assessment = self._assess_training_intensity(workout, hr_zones)

if debug_info:
    debug_info["reasoning"].append(
        f"💪 训练强度评估：{intensity_assessment.get('intensity_level', '未知')}"
    )
    if workout.avg_heart_rate:
        debug_info["reasoning"].append(f"   - 平均心率{workout.avg_heart_rate}bpm")
    if workout.training_effect_aerobic:
        debug_info["reasoning"].append(
            f"   - 有氧训练效果{workout.training_effect_aerobic}"
        )
    if workout.training_effect_anaerobic:
        debug_info["reasoning"].append(
            f"   - 无氧训练效果{workout.training_effect_anaerobic}"
        )

"""
步骤6：检索知识库
"""
if debug_info:
    debug_info["steps"].append("6. 从知识库检索恢复建议")

knowledge = self._retrieve_post_workout_knowledge(
    workout=workout,
    hr_analysis=hr_analysis,
    intensity_assessment=intensity_assessment,
    debug_info=debug_info  # 传递 debug_info
)

"""
步骤7：生成建议
"""
if debug_info:
    debug_info["steps"].append("7. 生成个性化恢复和改进建议")

recovery_tips = self._generate_recovery_tips(
    workout=workout,
    intensity_assessment=intensity_assessment,
    knowledge=knowledge
)

improvement_tips = self._generate_improvement_tips(
    workout=workout,
    hr_analysis=hr_analysis,
    knowledge=knowledge
)

if debug_info:
    debug_info["reasoning"].append("✅ 生成完成：")
    debug_info["reasoning"].append(f"   - 恢复建议：{len(recovery_tips)}条")
    debug_info["reasoning"].append(f"   - 改进建议：{len(improvement_tips)}条")

"""
步骤8：对比目标
"""
if debug_info:
    debug_info["steps"].append("8. 对比目标进度")

goal_progress = self._calculate_goal_progress(db, user_id, workout)

if debug_info and goal_progress.get("has_goal"):
    debug_info["reasoning"].append(
        f"🎯 目标进度：{goal_progress.get('progress_description', '无')}"
    )

"""
最终返回时添加 debug 信息
"""
analysis = {
    "success": True,
    "generated_at": get_china_now().isoformat(),
    "workout_summary": self._format_workout_summary(workout),
    "hr_analysis": hr_analysis,
    "intensity_assessment": intensity_assessment,
    "recovery_tips": recovery_tips,
    "improvement_tips": improvement_tips,
    "goal_progress": goal_progress,
    "knowledge_points": knowledge.get("key_points", []),
    "overall_rating": self._calculate_overall_rating(
        hr_analysis, intensity_assessment
    )
}

# 添加 debug 信息
if debug_info:
    analysis["debug"] = debug_info

return analysis
