package life.executor.health.rokid.pushup

data class PushupEventPayload(
    val eventType: String,
    val reps: Int?,
    val phase: PushupPhase?,
    val elbowAngleDeg: Double?,
    val shoulderHipAnkleAngleDeg: Double?,
    val visibility: Double?,
    val qualityScore: Double?,
    val feedback: String?,
    val suggestion: String?,
    val frameId: Long?,
    val sessionId: Int? = null,
    val state: String? = null,
    val message: String? = null,
    val detail: String? = null,
) {
    fun toJson(): String {
        val fields = mutableListOf<String>()
        fields += jsonField("event_type", eventType)
        reps?.let { fields += jsonField("reps", it) }
        phase?.let { fields += jsonField("phase", it.name.lowercase()) }
        elbowAngleDeg?.let { fields += jsonField("elbow_angle_deg", it) }
        shoulderHipAnkleAngleDeg?.let { fields += jsonField("shoulder_hip_ankle_angle_deg", it) }
        visibility?.let { fields += jsonField("visibility", it.coerceIn(0.0, 1.0)) }
        qualityScore?.let { fields += jsonField("quality_score", it.coerceIn(0.0, 100.0)) }

        val payloadFields = mutableListOf<String>()
        payloadFields += jsonField("source", "rokid_glasses_pushup")
        payloadFields += jsonField("model", "mediapipe_pose_landmarker_lite")
        feedback?.let { payloadFields += jsonField("feedback", it) }
        suggestion?.let { payloadFields += jsonField("suggestion", it) }
        frameId?.let { payloadFields += jsonField("frame_id", it) }
        sessionId?.let { payloadFields += jsonField("session_id", it) }
        state?.let { payloadFields += jsonField("state", it) }
        message?.let { payloadFields += jsonField("message", it) }
        detail?.let { payloadFields += jsonField("detail", it) }
        fields += "\"payload\":{${payloadFields.joinToString(",")}}"

        return "{${fields.joinToString(",")}}"
    }

    companion object {
        fun pose(event: PushupPoseEvent, frameId: Long): PushupEventPayload =
            PushupEventPayload(
                eventType = "pose",
                reps = event.reps,
                phase = event.phase,
                elbowAngleDeg = event.elbowAngleDeg,
                shoulderHipAnkleAngleDeg = event.shoulderHipAnkleAngleDeg,
                visibility = event.visibility,
                qualityScore = event.qualityScore,
                feedback = event.feedback,
                suggestion = event.suggestion,
                frameId = frameId,
            )

        fun rep(event: PushupRepEvent): PushupEventPayload =
            PushupEventPayload(
                eventType = "rep",
                reps = event.reps,
                phase = PushupPhase.UP,
                elbowAngleDeg = null,
                shoulderHipAnkleAngleDeg = null,
                visibility = null,
                qualityScore = event.qualityScore,
                feedback = event.feedback,
                suggestion = event.suggestion,
                frameId = null,
            )

        fun sessionState(
            state: String,
            message: String,
            detail: String? = null,
            sessionId: Int? = null,
        ): PushupEventPayload =
            PushupEventPayload(
                eventType = "session_state",
                reps = null,
                phase = null,
                elbowAngleDeg = null,
                shoulderHipAnkleAngleDeg = null,
                visibility = null,
                qualityScore = null,
                feedback = null,
                suggestion = null,
                frameId = null,
                sessionId = sessionId,
                state = state,
                message = message,
                detail = detail,
            )

        private fun jsonField(name: String, value: String): String =
            "\"${escape(name)}\":\"${escape(value)}\""

        private fun jsonField(name: String, value: Number): String =
            "\"${escape(name)}\":$value"

        private fun escape(value: String): String =
            value.asSequence().joinToString(separator = "") { char ->
                when (char) {
                    '\\' -> "\\\\"
                    '"' -> "\\\""
                    '\n' -> "\\n"
                    '\r' -> "\\r"
                    '\t' -> "\\t"
                    else -> char.toString()
                }
            }
    }
}
