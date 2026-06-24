package life.executor.health.rokid.pushup

import org.junit.Assert.assertTrue
import org.junit.Test

class PushupEventPayloadTest {
    @Test
    fun serializesPoseEventForRevaIngestSchema() {
        val event = PushupPoseEvent(
            timestampMs = 1_000,
            elbowAngleDeg = 84.5,
            shoulderHipAnkleAngleDeg = 174.0,
            visibility = 0.94,
            phase = PushupPhase.DOWN,
            reps = 3,
            qualityScore = 91.0,
            feedback = "到底部",
            suggestion = "保持核心收紧",
        )

        val json = PushupEventPayload.pose(event, frameId = 12).toJson()

        assertTrue(json.contains("\"event_type\":\"pose\""))
        assertTrue(json.contains("\"phase\":\"down\""))
        assertTrue(json.contains("\"shoulder_hip_ankle_angle_deg\":174.0"))
        assertTrue(json.contains("\"frame_id\":12"))
    }

    @Test
    fun serializesRepEventForRevaIngestSchema() {
        val event = PushupRepEvent(
            timestampMs = 1_500,
            reps = 4,
            qualityScore = 88.0,
            feedback = "第 4 个",
            suggestion = "继续保持",
        )

        val json = PushupEventPayload.rep(event).toJson()

        assertTrue(json.contains("\"event_type\":\"rep\""))
        assertTrue(json.contains("\"reps\":4"))
        assertTrue(json.contains("\"quality_score\":88.0"))
        assertTrue(json.contains("\"suggestion\":\"继续保持\""))
    }

    @Test
    fun serializesSessionStateForRevaIngestSchema() {
        val json = PushupEventPayload.sessionState(
            state = "ingest_failed",
            message = "HTTP 403",
            detail = "token_rejected",
        ).toJson()

        assertTrue(json.contains("\"event_type\":\"session_state\""))
        assertTrue(json.contains("\"state\":\"ingest_failed\""))
        assertTrue(json.contains("\"message\":\"HTTP 403\""))
        assertTrue(json.contains("\"detail\":\"token_rejected\""))
    }
}
