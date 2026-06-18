package life.executor.health.rokid.pushup

import kotlin.math.acos
import kotlin.math.pow
import kotlin.math.sqrt

data class PosePoint(
    val x: Float,
    val y: Float,
    val z: Float = 0f,
    val visibility: Float = 0f,
)

object PoseGeometry {
    const val LEFT_SHOULDER = 11
    const val RIGHT_SHOULDER = 12
    const val LEFT_ELBOW = 13
    const val RIGHT_ELBOW = 14
    const val LEFT_WRIST = 15
    const val RIGHT_WRIST = 16
    const val LEFT_HIP = 23
    const val RIGHT_HIP = 24
    const val LEFT_ANKLE = 27
    const val RIGHT_ANKLE = 28

    fun toPushupSample(timestampMs: Long, landmarks: List<PosePoint>): PushupPoseSample? {
        if (landmarks.size <= RIGHT_ANKLE) return null

        val left = sideSample(
            landmarks = landmarks,
            shoulderIndex = LEFT_SHOULDER,
            elbowIndex = LEFT_ELBOW,
            wristIndex = LEFT_WRIST,
            hipIndex = LEFT_HIP,
            ankleIndex = LEFT_ANKLE,
        )
        val right = sideSample(
            landmarks = landmarks,
            shoulderIndex = RIGHT_SHOULDER,
            elbowIndex = RIGHT_ELBOW,
            wristIndex = RIGHT_WRIST,
            hipIndex = RIGHT_HIP,
            ankleIndex = RIGHT_ANKLE,
        )
        val side = listOfNotNull(left, right).maxByOrNull { it.visibility } ?: return null

        return PushupPoseSample(
            timestampMs = timestampMs,
            elbowAngleDeg = side.elbowAngleDeg,
            shoulderHipAnkleAngleDeg = side.bodyAngleDeg,
            visibility = side.visibility,
        )
    }

    private fun sideSample(
        landmarks: List<PosePoint>,
        shoulderIndex: Int,
        elbowIndex: Int,
        wristIndex: Int,
        hipIndex: Int,
        ankleIndex: Int,
    ): SideSample {
        val shoulder = landmarks[shoulderIndex]
        val elbow = landmarks[elbowIndex]
        val wrist = landmarks[wristIndex]
        val hip = landmarks[hipIndex]
        val ankle = landmarks[ankleIndex]
        val visibility = listOf(shoulder, elbow, wrist, hip, ankle).map { it.visibility }.average()

        return SideSample(
            elbowAngleDeg = angleDeg(shoulder, elbow, wrist),
            bodyAngleDeg = angleDeg(shoulder, hip, ankle),
            visibility = visibility,
        )
    }

    private fun angleDeg(a: PosePoint, b: PosePoint, c: PosePoint): Double {
        val abX = (a.x - b.x).toDouble()
        val abY = (a.y - b.y).toDouble()
        val cbX = (c.x - b.x).toDouble()
        val cbY = (c.y - b.y).toDouble()
        val dot = abX * cbX + abY * cbY
        val abMagnitude = sqrt(abX.pow(2) + abY.pow(2))
        val cbMagnitude = sqrt(cbX.pow(2) + cbY.pow(2))
        val denominator = abMagnitude * cbMagnitude
        if (denominator == 0.0) return 0.0

        val cosine = (dot / denominator).coerceIn(-1.0, 1.0)
        return Math.toDegrees(acos(cosine))
    }

    private data class SideSample(
        val elbowAngleDeg: Double,
        val bodyAngleDeg: Double,
        val visibility: Double,
    )
}
