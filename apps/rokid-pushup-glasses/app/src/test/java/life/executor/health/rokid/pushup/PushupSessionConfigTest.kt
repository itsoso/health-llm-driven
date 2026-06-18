package life.executor.health.rokid.pushup

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PushupSessionConfigTest {
    @Test
    fun parsesOpenUrlFromRevaIosBridge() {
        val config = PushupSessionConfig.parse(
            "reva://rokid/pushup?session_id=7&target_reps=20" +
                "&ingest_url=https%3A%2F%2Fhealth.executor.life%2Fapi%2Fv1%2Fdevices%2Frokid%2Fpushup-sessions%2F7%2Fevents" +
                "&ingest_token=secret-token",
        )

        assertEquals(7, config?.sessionId)
        assertEquals(20, config?.targetReps)
        assertEquals(
            "https://health.executor.life/api/v1/devices/rokid/pushup-sessions/7/events",
            config?.ingestUrl,
        )
        assertEquals("secret-token", config?.ingestToken)
    }

    @Test
    fun rejectsUrlWithoutIngestToken() {
        val config = PushupSessionConfig.parse(
            "reva://rokid/pushup?session_id=7&target_reps=20&ingest_url=https%3A%2F%2Fhealth.executor.life%2Fevents",
        )

        assertNull(config)
    }
}
