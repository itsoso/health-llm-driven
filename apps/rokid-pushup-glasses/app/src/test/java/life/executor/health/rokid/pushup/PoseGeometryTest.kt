package life.executor.health.rokid.pushup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PoseGeometryTest {
    @Test
    fun buildsSampleFromMostVisibleSide() {
        val landmarks = MutableList(33) { PosePoint(0f, 0f, visibility = 0.2f) }
        landmarks[PoseGeometry.LEFT_SHOULDER] = PosePoint(0f, 0f, visibility = 0.95f)
        landmarks[PoseGeometry.LEFT_ELBOW] = PosePoint(1f, 0f, visibility = 0.95f)
        landmarks[PoseGeometry.LEFT_WRIST] = PosePoint(2f, 0f, visibility = 0.95f)
        landmarks[PoseGeometry.LEFT_HIP] = PosePoint(0f, 1f, visibility = 0.95f)
        landmarks[PoseGeometry.LEFT_ANKLE] = PosePoint(0f, 2f, visibility = 0.95f)

        val sample = PoseGeometry.toPushupSample(timestampMs = 42, landmarks = landmarks)

        assertEquals(42L, sample?.timestampMs)
        assertEquals(180.0, sample?.elbowAngleDeg ?: 0.0, 0.1)
        assertEquals(180.0, sample?.shoulderHipAnkleAngleDeg ?: 0.0, 0.1)
        assertTrue((sample?.visibility ?: 0.0) > 0.9)
    }
}
