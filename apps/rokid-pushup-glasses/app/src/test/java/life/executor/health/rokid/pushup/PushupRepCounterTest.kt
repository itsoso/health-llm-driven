package life.executor.health.rokid.pushup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PushupRepCounterTest {
    @Test
    fun countsOneRepAfterUpDownUpSequence() {
        val counter = PushupRepCounter(targetReps = 20)

        assertEquals(null, counter.update(sample(0, elbow = 170.0, body = 176.0)).repEvent)
        assertEquals(null, counter.update(sample(700, elbow = 84.0, body = 174.0)).repEvent)
        val out = counter.update(sample(1_500, elbow = 166.0, body = 175.0))

        assertEquals(1, out.state.reps)
        assertEquals(PushupPhase.UP, out.state.phase)
        assertEquals(1, out.repEvent?.reps)
        assertTrue(out.repEvent?.qualityScore ?: 0.0 >= 85.0)
    }

    @Test
    fun doesNotCountWhenVisibilityIsLow() {
        val counter = PushupRepCounter(targetReps = 20)

        counter.update(sample(0, elbow = 170.0, body = 176.0, visibility = 0.95))
        counter.update(sample(500, elbow = 84.0, body = 174.0, visibility = 0.2))
        val out = counter.update(sample(1_200, elbow = 166.0, body = 175.0, visibility = 0.95))

        assertEquals(0, out.state.reps)
    }

    @Test
    fun lowersQualityForSoftBodyLine() {
        val counter = PushupRepCounter(targetReps = 20)

        counter.update(sample(0, elbow = 170.0, body = 176.0))
        counter.update(sample(700, elbow = 84.0, body = 142.0))
        val out = counter.update(sample(1_500, elbow = 166.0, body = 144.0))

        assertEquals(1, out.state.reps)
        assertTrue(out.state.qualityScore < 80.0)
        assertTrue(out.repEvent?.suggestion?.contains("收紧") == true)
    }

    private fun sample(
        timestampMs: Long,
        elbow: Double,
        body: Double,
        visibility: Double = 0.94,
    ) = PushupPoseSample(
        timestampMs = timestampMs,
        elbowAngleDeg = elbow,
        shoulderHipAnkleAngleDeg = body,
        visibility = visibility,
    )
}
