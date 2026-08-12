"""主API路由"""
from fastapi import APIRouter
from app.api import (
    auth,
    admin,
    admin_system_map,
    admin_registration_invitations,
    admin_observability,
    admin_llm,
    admin_open_loop,
    admin_wscla,
    admin_slo,
    admin_longevity,
    movement_plan,
    diet_plan,
    daily_plan,
    dynamic_views,
    trajectory,
    users,
    basic_health,
    epigenetic_reports,
    medical_exams,
    prescriptions,
    chronic_health,
    medication_course,
    diseases,
    daily_health,
    health_checkin,
    goals,
    data_collection,
    data_connections,
    health_runtime_governance,
    health_analysis,
    garmin_analysis,
    garmin_timeseries,
    fitness_snapshot,
    sleep_spo2_analysis,
    daily_recommendation,
    supplements,
    supplement_inventory,
    supplement_products,
    supplement_audits,
    health_consultations,
    weight,
    waist,
    blood_pressure,
    diet,
    water,
    heart_rate,
    workout,
    wechat,
    devices,
    user_merge,
    upload,
    invitation,
    monitoring,
    user_profile,
    checkin,
    knowledge,
    system_knowledge,
    environment,
    disease_tracking,
    ai_scheduler,
    digital_twin,
    notification,
    smart_reminder,
    review,
    diet_recommendation,
    performance,
    user_api_key,
    user_llm_preference,
    weekly_briefing,
    speech,
    ai_insights,
    mood,
    symptoms,
    live_run,
    episodes,
    health_report,
    body_composition,
    health_score,
    medication,
    health_protocol,
    health_problem,
    agenda,
    daily_artifact,
    watch,
    write_intents,
    reorder_intents,
    schedule,
    fitness,
    calendar,
    health_program,
    program_templates,
    womens_health,
    vision,
    siri,
    illness,
    excretion,
    sleep_record,
    activity_status,
    smart_plan,
    health_event,
    bedroom_environment,
    home_assistant,
    withings,
    onboarding,
    data_export,
    health_trend,
    shared_conversation,
    skills,
    feedback,
    nfc,
    family,
    family_health,
    anomaly_alert,
    health_context,
    garmin_import,
    quick_questions,
    genetic_data,
    quick_record,
    data_health,
    sleep_analysis,
    exercise_recovery,
    movement,
    chronic_risk,
    multi_source_integration,
    personal_models,
    agent,
    twin,
    safety,
    orchestrator,
    cgm,
    personal_outcome,
    biomarkers,
    intervention_cycles,
    crossover_experiments,
    monthly_report,
    doctor_report,
    action_card,
    exercise_coaching,
    rhinitis_trend,
    spo2,
    tts,
    briefing,
    clarification,
    timeline,
    llm_usage,
    specialist_hit_rate,
    open_loop,
    clinical_journal,
    user_directive,
    telegram_webhook,
    memory_facts,
    conversation_memory,
    health_kg,
    hybrid_search,
    reasoning_trace,
    insights,
    judgment_feedback,
    client_events,
    app_release_policy,
    desktop,
    ambient,
    rokid,
    device_observation,
    aigc_media,
    community,
)

api_router = APIRouter()

# ── Auth & Access Control ──────────────────────────────────────────
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(wechat.router, prefix="/wechat", tags=["wechat"])
api_router.include_router(user_merge.router, prefix="/user-merge", tags=["user-merge"])
api_router.include_router(invitation.router, tags=["invitation"])
api_router.include_router(onboarding.router, tags=["onboarding"])

# ── Admin & System ─────────────────────────────────────────────────
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(
    admin_system_map.router,
    prefix="/admin/system-map",
    tags=["admin-system-map"],
)
api_router.include_router(admin_registration_invitations.router)
api_router.include_router(admin_observability.router, prefix="/admin/observability", tags=["admin-observability"])
api_router.include_router(admin_llm.router)
api_router.include_router(admin_open_loop.router, prefix="/admin/open-loop", tags=["admin-open-loop"])
api_router.include_router(admin_wscla.router, prefix="/admin/wscla", tags=["admin-wscla"])
api_router.include_router(admin_slo.router, prefix="/admin/slo", tags=["admin-slo"])
api_router.include_router(admin_longevity.router, prefix="/admin/longevity", tags=["admin-longevity"])
api_router.include_router(movement_plan.router)
api_router.include_router(diet_plan.router)
api_router.include_router(daily_plan.router)
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
api_router.include_router(performance.router)
api_router.include_router(data_health.router, prefix="/data-health", tags=["data-health"])
api_router.include_router(data_export.router)

# ── User & Profile ─────────────────────────────────────────────────
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(user_profile.router, tags=["user-profile"])
api_router.include_router(user_api_key.router, tags=["user-api-key"])
api_router.include_router(user_llm_preference.router)
api_router.include_router(weekly_briefing.router, tags=["weekly-briefing"])

# ── Health Data (Vitals & Records) ─────────────────────────────────
api_router.include_router(basic_health.router, prefix="/basic-health", tags=["basic-health"])
api_router.include_router(medical_exams.router, prefix="/medical-exams", tags=["medical-exams"])
api_router.include_router(prescriptions.router, prefix="/prescriptions", tags=["prescriptions"])
api_router.include_router(chronic_health.router, prefix="/chronic", tags=["chronic-health"])
api_router.include_router(medication_course.router, prefix="/medication-course", tags=["medication-course"])
api_router.include_router(epigenetic_reports.router, prefix="/epigenetic-reports", tags=["epigenetic-reports"])
api_router.include_router(diseases.router, prefix="/diseases", tags=["diseases"])
api_router.include_router(disease_tracking.router, tags=["disease-tracking"])
api_router.include_router(daily_health.router, prefix="/daily-health", tags=["daily-health"])
api_router.include_router(health_checkin.router, prefix="/checkin", tags=["checkin"])
api_router.include_router(checkin.router, tags=["checkin-v2"])
api_router.include_router(weight.router, prefix="/weight", tags=["weight"])
api_router.include_router(waist.router, prefix="/waist", tags=["waist"])
api_router.include_router(blood_pressure.router, prefix="/blood-pressure", tags=["blood-pressure"])
api_router.include_router(heart_rate.router, prefix="/heart-rate", tags=["heart-rate"])
api_router.include_router(spo2.router, prefix="/spo2", tags=["spo2"])
api_router.include_router(tts.router)
api_router.include_router(briefing.router)
api_router.include_router(clarification.router)
api_router.include_router(timeline.router)
api_router.include_router(sleep_record.router)
api_router.include_router(excretion.router)
api_router.include_router(mood.router)
api_router.include_router(symptoms.router, prefix="/symptoms", tags=["symptoms"])
api_router.include_router(live_run.router, prefix="/live-run", tags=["live-run"])
api_router.include_router(episodes.router, prefix="/episodes", tags=["episodes"])

# ── Diet & Supplements ─────────────────────────────────────────────
api_router.include_router(diet.router, prefix="/diet", tags=["diet"])
api_router.include_router(water.router, prefix="/water", tags=["water"])
api_router.include_router(diet_recommendation.router)
api_router.include_router(supplements.router, prefix="/supplements", tags=["supplements"])
api_router.include_router(supplement_inventory.router, prefix="/supplements", tags=["supplement-inventory"])
api_router.include_router(supplement_products.router, tags=["supplement-products"])
api_router.include_router(supplement_audits.router)
api_router.include_router(health_consultations.router)
api_router.include_router(medication.router)
api_router.include_router(health_protocol.router)
api_router.include_router(health_problem.router)
api_router.include_router(agenda.router)
api_router.include_router(daily_artifact.router)
api_router.include_router(watch.router)
api_router.include_router(write_intents.router)
api_router.include_router(reorder_intents.router)
api_router.include_router(schedule.router)
api_router.include_router(fitness.router)
api_router.include_router(calendar.router)
api_router.include_router(health_program.router)
api_router.include_router(program_templates.router)

# ── Exercise & Activity ────────────────────────────────────────────
api_router.include_router(workout.router, prefix="/workout", tags=["workout"])
api_router.include_router(activity_status.router)
api_router.include_router(exercise_coaching.router, tags=["exercise-coaching"])
api_router.include_router(exercise_recovery.router)
api_router.include_router(movement.router)

# ── Devices & Data Sync ───────────────────────────────────────────
api_router.include_router(bedroom_environment.router, tags=["bedroom-environment"])
api_router.include_router(home_assistant.router, tags=["home-assistant"])
api_router.include_router(withings.router)
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(data_collection.router, prefix="/data-collection", tags=["data-collection"])
api_router.include_router(data_connections.router)
api_router.include_router(health_runtime_governance.router)
api_router.include_router(garmin_analysis.router, prefix="/garmin-analysis", tags=["garmin-analysis"])
api_router.include_router(garmin_import.router)
api_router.include_router(garmin_timeseries.router, prefix="/garmin", tags=["garmin-timeseries"])
api_router.include_router(fitness_snapshot.router, prefix="/fitness-snapshot", tags=["fitness-snapshot"])
api_router.include_router(sleep_spo2_analysis.router, prefix="/sleep/spo2", tags=["sleep-spo2-analysis"])
api_router.include_router(nfc.router)
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(aigc_media.router)
api_router.include_router(community.router)

# ── AI & Agent System ──────────────────────────────────────────────
api_router.include_router(twin.router, tags=["twin"])
api_router.include_router(safety.router, tags=["safety"])
api_router.include_router(orchestrator.router, tags=["orchestrator"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(dynamic_views.router)
api_router.include_router(shared_conversation.router)
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(feedback.router)
api_router.include_router(speech.router)
api_router.include_router(action_card.router, tags=["action-cards"])
api_router.include_router(quick_record.router, tags=["quick-record"])

# ── Analytics & Insights ───────────────────────────────────────────
api_router.include_router(health_analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(daily_recommendation.router, prefix="/daily-recommendation", tags=["daily-recommendation"])
api_router.include_router(ai_insights.router, prefix="/ai-insights", tags=["ai-insights"])
api_router.include_router(health_report.router)
api_router.include_router(health_score.router)
api_router.include_router(health_trend.router)
api_router.include_router(trajectory.router)
api_router.include_router(health_event.router)
api_router.include_router(health_context.router)
api_router.include_router(anomaly_alert.router)
api_router.include_router(sleep_analysis.router)
api_router.include_router(chronic_risk.router)
api_router.include_router(multi_source_integration.router)
api_router.include_router(personal_models.router)
api_router.include_router(personal_outcome.router, tags=["personal-outcome"])
api_router.include_router(biomarkers.router)
api_router.include_router(intervention_cycles.router)
api_router.include_router(crossover_experiments.router)
api_router.include_router(monthly_report.router, tags=["monthly-report"])
api_router.include_router(doctor_report.router, tags=["doctor-report"])
api_router.include_router(rhinitis_trend.router, tags=["rhinitis-trend"])
api_router.include_router(cgm.router, tags=["cgm"])
api_router.include_router(body_composition.router)
api_router.include_router(system_knowledge.router, tags=["system-knowledge"])
api_router.include_router(system_knowledge.admin_router, tags=["admin-system-knowledge"])
api_router.include_router(knowledge.router, tags=["knowledge-base"])
api_router.include_router(llm_usage.router)
api_router.include_router(specialist_hit_rate.router)
api_router.include_router(open_loop.router)
api_router.include_router(clinical_journal.router)
api_router.include_router(user_directive.router)
api_router.include_router(telegram_webhook.router)
api_router.include_router(memory_facts.router)
api_router.include_router(conversation_memory.router)
api_router.include_router(health_kg.router)
api_router.include_router(hybrid_search.router)
api_router.include_router(reasoning_trace.router)
api_router.include_router(insights.router)
api_router.include_router(judgment_feedback.router)
api_router.include_router(client_events.router)
api_router.include_router(app_release_policy.router)
api_router.include_router(desktop.router)
api_router.include_router(ambient.router)
api_router.include_router(rokid.router)
api_router.include_router(device_observation.router)

# ── Environment & Context ──────────────────────────────────────────
api_router.include_router(environment.router, tags=["environment"])
api_router.include_router(digital_twin.router, prefix="/digital-twin", tags=["digital-twin"])

# ── Scheduling & Reminders ─────────────────────────────────────────
api_router.include_router(ai_scheduler.router, tags=["ai-scheduler"])
api_router.include_router(notification.router, tags=["notification"])
api_router.include_router(smart_reminder.router, tags=["reminders"])
api_router.include_router(smart_plan.router)
api_router.include_router(review.router, tags=["review"])
api_router.include_router(quick_questions.router)

# ── Genetics & Specialized Health ──────────────────────────────────
api_router.include_router(genetic_data.router, prefix="/genetic", tags=["genetic-data"])
api_router.include_router(womens_health.router)
api_router.include_router(illness.router)
api_router.include_router(vision.router)

# ── Family ─────────────────────────────────────────────────────────
api_router.include_router(family.router)
api_router.include_router(family_health.router, prefix="/family-health", tags=["family-health"])

# ── Lifestyle & Misc ──────────────────────────────────────────────
api_router.include_router(siri.router)
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
