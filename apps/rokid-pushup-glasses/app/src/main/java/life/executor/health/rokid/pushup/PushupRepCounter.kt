package life.executor.health.rokid.pushup

enum class PushupPhase {
    UNKNOWN,
    UP,
    DOWN,
    TRANSITION,
}

data class PushupPoseSample(
    val timestampMs: Long,
    val elbowAngleDeg: Double?,
    val shoulderHipAnkleAngleDeg: Double?,
    val visibility: Double?,
)

data class PushupCoachState(
    val reps: Int,
    val targetReps: Int,
    val phase: PushupPhase,
    val qualityScore: Double,
    val feedback: String,
    val suggestion: String,
)

data class PushupPoseEvent(
    val timestampMs: Long,
    val elbowAngleDeg: Double?,
    val shoulderHipAnkleAngleDeg: Double?,
    val visibility: Double?,
    val phase: PushupPhase,
    val reps: Int,
    val qualityScore: Double,
    val feedback: String,
    val suggestion: String,
)

data class PushupRepEvent(
    val timestampMs: Long,
    val reps: Int,
    val qualityScore: Double,
    val feedback: String,
    val suggestion: String,
)

data class PushupCounterUpdate(
    val state: PushupCoachState,
    val poseEvent: PushupPoseEvent,
    val repEvent: PushupRepEvent?,
)

class PushupRepCounter(
    private val targetReps: Int,
) {
    private var reps = 0
    private var phase = PushupPhase.UNKNOWN
    private var sawDown = false
    private var downStartedAtMs: Long? = null
    private var lastRepAtMs: Long? = null
    private var downMinElbowDeg: Double? = null
    private var downMinBodyAngleDeg: Double? = null
    private var qualityScore = 0.0
    private var feedback = "准备开始"
    private var suggestion = "把身体放进画面，保持侧身可见。"

    fun update(sample: PushupPoseSample): PushupCounterUpdate {
        val sampleVisibility = sample.visibility ?: 0.0
        val elbow = sample.elbowAngleDeg
        val body = sample.shoulderHipAnkleAngleDeg

        if (sampleVisibility < MIN_VISIBILITY || elbow == null) {
            feedback = "姿态不可见"
            suggestion = "向后一步，让肩、肘、髋、踝完整进入画面。"
            return updateFrom(sample, repEvent = null)
        }

        val observedPhase = phaseFromElbow(elbow)
        val repEvent = when (observedPhase) {
            PushupPhase.DOWN -> handleDown(sample)
            PushupPhase.UP -> handleUp(sample)
            PushupPhase.TRANSITION -> {
                phase = PushupPhase.TRANSITION
                feedback = "保持控制"
                suggestion = "下降和撑起都放慢一点，避免塌腰。"
                null
            }
            PushupPhase.UNKNOWN -> null
        }

        return updateFrom(sample, repEvent = repEvent)
    }

    private fun handleDown(sample: PushupPoseSample): PushupRepEvent? {
        if (!sawDown) {
            sawDown = true
            downStartedAtMs = sample.timestampMs
            downMinElbowDeg = sample.elbowAngleDeg
            downMinBodyAngleDeg = sample.shoulderHipAnkleAngleDeg
        } else {
            downMinElbowDeg = minNullable(downMinElbowDeg, sample.elbowAngleDeg)
            downMinBodyAngleDeg = minNullable(downMinBodyAngleDeg, sample.shoulderHipAnkleAngleDeg)
        }

        phase = PushupPhase.DOWN
        feedback = "到底部"
        suggestion = "胸口继续靠近地面，核心保持收紧。"
        return null
    }

    private fun handleUp(sample: PushupPoseSample): PushupRepEvent? {
        phase = PushupPhase.UP

        if (!sawDown) {
            feedback = "顶部准备"
            suggestion = "手掌压稳，下一次下降时保持身体一条线。"
            return null
        }

        val score = scoreRep(sample)
        val repSuggestion = suggestionFor(score)
        reps += 1
        sawDown = false
        downStartedAtMs = null
        downMinElbowDeg = null
        downMinBodyAngleDeg = null
        lastRepAtMs = sample.timestampMs
        qualityScore = score
        feedback = if (reps >= targetReps) "目标完成" else "第 ${reps} 个"
        suggestion = repSuggestion

        return PushupRepEvent(
            timestampMs = sample.timestampMs,
            reps = reps,
            qualityScore = score,
            feedback = feedback,
            suggestion = repSuggestion,
        )
    }

    private fun scoreRep(sample: PushupPoseSample): Double {
        var score = 96.0
        val minElbow = downMinElbowDeg ?: sample.elbowAngleDeg ?: 180.0
        val minBody = minNullable(downMinBodyAngleDeg, sample.shoulderHipAnkleAngleDeg) ?: 180.0
        val downStartedAt = downStartedAtMs

        if (minElbow > DEEP_ELBOW_DEG) {
            score -= 14.0
        }
        if (minBody < STRAIGHT_BODY_DEG) {
            score -= 24.0
        }
        if (downStartedAt != null && sample.timestampMs - downStartedAt < MIN_REP_DURATION_MS) {
            score -= 8.0
        }

        return score.coerceIn(0.0, 100.0)
    }

    private fun suggestionFor(score: Double): String {
        val minBody = downMinBodyAngleDeg ?: 180.0
        val minElbow = downMinElbowDeg ?: 180.0
        return when {
            minBody < STRAIGHT_BODY_DEG -> "收紧核心，肩、髋、踝保持一条线。"
            minElbow > DEEP_ELBOW_DEG -> "下一次再低一点，让肘角接近 90 度。"
            score >= 90.0 -> "节奏很好，继续保持。"
            else -> "动作有效，下一次放慢节奏。"
        }
    }

    private fun updateFrom(sample: PushupPoseSample, repEvent: PushupRepEvent?): PushupCounterUpdate {
        val state = PushupCoachState(
            reps = reps,
            targetReps = targetReps,
            phase = phase,
            qualityScore = qualityScore,
            feedback = feedback,
            suggestion = suggestion,
        )
        val poseEvent = PushupPoseEvent(
            timestampMs = sample.timestampMs,
            elbowAngleDeg = sample.elbowAngleDeg,
            shoulderHipAnkleAngleDeg = sample.shoulderHipAnkleAngleDeg,
            visibility = sample.visibility,
            phase = phase,
            reps = reps,
            qualityScore = qualityScore,
            feedback = feedback,
            suggestion = suggestion,
        )
        return PushupCounterUpdate(state = state, poseEvent = poseEvent, repEvent = repEvent)
    }

    private fun phaseFromElbow(elbowAngleDeg: Double): PushupPhase =
        when {
            elbowAngleDeg >= UP_ELBOW_DEG -> PushupPhase.UP
            elbowAngleDeg <= DOWN_ELBOW_DEG -> PushupPhase.DOWN
            else -> PushupPhase.TRANSITION
        }

    private fun minNullable(left: Double?, right: Double?): Double? =
        when {
            left == null -> right
            right == null -> left
            else -> minOf(left, right)
        }

    companion object {
        private const val MIN_VISIBILITY = 0.55
        private const val UP_ELBOW_DEG = 155.0
        private const val DOWN_ELBOW_DEG = 95.0
        private const val DEEP_ELBOW_DEG = 105.0
        private const val STRAIGHT_BODY_DEG = 160.0
        private const val MIN_REP_DURATION_MS = 450L
    }
}
