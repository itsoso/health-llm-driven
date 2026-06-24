package life.executor.health.rokid.pushup

import org.junit.Assert.assertTrue
import org.junit.Test

class MainViewModelSessionStateTest {
    @Test
    fun configureReportsSessionReadyStateToReva() {
        val reports = mutableListOf<PushupEventPayload>()
        val viewModel = MainViewModel(
            reporterFactory = { _, _ ->
                object : PushupEventReporter {
                    override fun report(payload: PushupEventPayload) {
                        reports += payload
                    }

                    override fun close() = Unit
                }
            },
            cxrBridgeFactory = { _, _ -> null },
        )

        viewModel.configure(
            "reva://rokid/pushup?session_id=7&target_reps=20" +
                "&ingest_url=https%3A%2F%2Fhealth.executor.life%2Fapi%2Fv1%2Fdevices%2Frokid%2Fpushup-sessions%2F7%2Fevents" +
                "&ingest_token=secret-token",
        )

        assertTrue(
            reports.any {
                it.toJson().contains("\"event_type\":\"session_state\"") &&
                    it.toJson().contains("\"state\":\"session_ready\"") &&
                    it.toJson().contains("\"session_id\":7")
            },
        )
    }

    @Test
    fun cameraAndAnalyzerStatusChangesAreReportedToReva() {
        val reports = mutableListOf<PushupEventPayload>()
        val viewModel = MainViewModel(
            reporterFactory = { _, _ ->
                object : PushupEventReporter {
                    override fun report(payload: PushupEventPayload) {
                        reports += payload
                    }

                    override fun close() = Unit
                }
            },
            cxrBridgeFactory = { _, _ -> null },
        )
        viewModel.configure(
            "reva://rokid/pushup?session_id=8&target_reps=20" +
                "&ingest_url=https%3A%2F%2Fhealth.executor.life%2Fapi%2Fv1%2Fdevices%2Frokid%2Fpushup-sessions%2F8%2Fevents" +
                "&ingest_token=secret-token",
        )
        reports.clear()

        viewModel.onCameraStatus("相机已启动")
        viewModel.onAnalyzerStatus("姿态模型已就绪")

        val json = reports.joinToString("\n") { it.toJson() }
        assertTrue(json.contains("\"state\":\"camera_status\""))
        assertTrue(json.contains("\"message\":\"相机已启动\""))
        assertTrue(json.contains("\"state\":\"analyzer_status\""))
        assertTrue(json.contains("\"message\":\"姿态模型已就绪\""))
    }

    @Test
    fun networkStatusChangesAreReportedToReva() {
        val reports = mutableListOf<PushupEventPayload>()
        val viewModel = MainViewModel(
            reporterFactory = { _, _ ->
                object : PushupEventReporter {
                    override fun report(payload: PushupEventPayload) {
                        reports += payload
                    }

                    override fun close() = Unit
                }
            },
            cxrBridgeFactory = { _, _ -> null },
        )
        viewModel.configure(
            "reva://rokid/pushup?session_id=9&target_reps=20" +
                "&ingest_url=https%3A%2F%2Fhealth.executor.life%2Fapi%2Fv1%2Fdevices%2Frokid%2Fpushup-sessions%2F9%2Fevents" +
                "&ingest_token=secret-token",
        )
        reports.clear()

        viewModel.onNetworkStatus(connected = false, detail = "no_validated_network")

        val json = reports.joinToString("\n") { it.toJson() }
        assertTrue(json.contains("\"state\":\"glasses_network_unavailable\""))
        assertTrue(json.contains("\"message\":\"眼镜网络不可用\""))
        assertTrue(json.contains("\"detail\":\"no_validated_network\""))
    }
}
