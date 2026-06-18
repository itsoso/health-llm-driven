package life.executor.health.rokid.pushup

import androidx.lifecycle.ViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

data class RevaPushupUiState(
    val sessionId: Int? = null,
    val targetReps: Int = 20,
    val reps: Int = 0,
    val phase: PushupPhase = PushupPhase.UNKNOWN,
    val qualityScore: Double = 0.0,
    val feedback: String = "准备开始",
    val suggestion: String = "把身体放进画面，保持侧身可见。",
    val cameraStatus: String = "等待相机权限",
    val analyzerStatus: String = "等待姿态模型",
    val ingestStatus: String = "本地模式",
    val cxrStatus: String = "CXR-S 待连接",
)

class MainViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(RevaPushupUiState())
    val uiState: StateFlow<RevaPushupUiState> = _uiState

    private var counter = PushupRepCounter(targetReps = 20)
    private var eventReporter: PushupEventReporter = NoopPushupEventReporter
    private var lastPosePostedAtMs = 0L
    private var cxrBridge: RokidCxrBridge? = null

    init {
        cxrBridge = runCatching {
            RokidCxrBridge(
                onStatus = { status -> _uiState.update { it.copy(cxrStatus = status) } },
                onMessage = { message -> _uiState.update { it.copy(cxrStatus = "手机指令: $message") } },
            )
        }.getOrNull()
    }

    fun configure(rawUrl: String?) {
        val config = PushupSessionConfig.parse(rawUrl)
        eventReporter.close()

        if (config == null) {
            counter = PushupRepCounter(targetReps = 20)
            eventReporter = NoopPushupEventReporter
            _uiState.value = RevaPushupUiState(
                ingestStatus = "本地模式: 未收到 Reva session",
                cxrStatus = _uiState.value.cxrStatus,
            )
            cxrBridge?.sendStatus("pushup_local_mode")
            return
        }

        counter = PushupRepCounter(targetReps = config.targetReps)
        eventReporter = RevaPushupEventClient(config) { status ->
            _uiState.update { it.copy(ingestStatus = status) }
        }
        _uiState.value = RevaPushupUiState(
            sessionId = config.sessionId,
            targetReps = config.targetReps,
            ingestStatus = "Reva session #${config.sessionId}",
            cxrStatus = _uiState.value.cxrStatus,
        )
        cxrBridge?.sendStatus("pushup_session_ready:${config.sessionId}")
    }

    fun onCameraStatus(status: String) {
        _uiState.update { it.copy(cameraStatus = status) }
    }

    fun onAnalyzerStatus(status: String) {
        _uiState.update { it.copy(analyzerStatus = status) }
    }

    fun onPoseSample(sample: PushupPoseSample, frameId: Long) {
        val update = counter.update(sample)
        val visibilityPercent = (((sample.visibility ?: 0.0) * 100.0).coerceIn(0.0, 100.0)).toInt()
        _uiState.update {
            it.copy(
                reps = update.state.reps,
                targetReps = update.state.targetReps,
                phase = update.state.phase,
                qualityScore = update.state.qualityScore,
                feedback = update.state.feedback,
                suggestion = update.state.suggestion,
                analyzerStatus = "姿态可见 $visibilityPercent%",
            )
        }

        if (sample.timestampMs - lastPosePostedAtMs >= POSE_POST_INTERVAL_MS) {
            lastPosePostedAtMs = sample.timestampMs
            eventReporter.report(PushupEventPayload.pose(update.poseEvent, frameId = frameId))
        }
        update.repEvent?.let { rep ->
            eventReporter.report(PushupEventPayload.rep(rep))
            cxrBridge?.sendStatus("pushup_rep:${rep.reps}:score:${rep.qualityScore.toInt()}")
        }
    }

    override fun onCleared() {
        eventReporter.close()
        cxrBridge?.close()
        super.onCleared()
    }

    companion object {
        private const val POSE_POST_INTERVAL_MS = 500L
    }
}
