package life.executor.health.rokid.pushup

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var analyzer: MediaPipePoseAnalyzer? = null

    private val cameraPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                startCamera()
            } else {
                viewModel.onCameraStatus("相机权限未授权")
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        viewModel.configure(intent?.dataString)
        reportNetworkStatus()

        setContent {
            MaterialTheme {
                RevaPushupScreen(viewModel = viewModel)
            }
        }

        requestCameraOrStart()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        viewModel.configure(intent.dataString)
        reportNetworkStatus()
        requestCameraOrStart()
    }

    override fun onDestroy() {
        analyzer?.close()
        cameraExecutor.shutdown()
        super.onDestroy()
    }

    private fun requestCameraOrStart() {
        reportNetworkStatus()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun startCamera() {
        reportNetworkStatus()
        viewModel.onCameraStatus("相机启动中")
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener(
            {
                val provider = cameraProviderFuture.get()
                bindCamera(provider)
            },
            ContextCompat.getMainExecutor(this),
        )
    }

    private fun bindCamera(provider: ProcessCameraProvider) {
        analyzer?.close()
        analyzer = MediaPipePoseAnalyzer(
            context = this,
            onSample = { sample, frameId -> viewModel.onPoseSample(sample, frameId) },
            onStatus = { status -> viewModel.onAnalyzerStatus(status) },
        )

        val analysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
            .build()
            .also { it.setAnalyzer(cameraExecutor, analyzer!!) }

        provider.unbindAll()
        val selector = if (provider.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)) {
            CameraSelector.DEFAULT_BACK_CAMERA
        } else {
            CameraSelector.DEFAULT_FRONT_CAMERA
        }
        provider.bindToLifecycle(this, selector, analysis)
        viewModel.onCameraStatus("相机已启动")
    }

    private fun reportNetworkStatus() {
        val manager = getSystemService(ConnectivityManager::class.java)
        val network = manager?.activeNetwork
        val capabilities = network?.let { manager.getNetworkCapabilities(it) }
        val hasInternet = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
        val validated = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
        val transport = when {
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true -> "wifi"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true -> "cellular"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) == true -> "ethernet"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_BLUETOOTH) == true -> "bluetooth"
            capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_USB) == true -> "usb"
            else -> "unknown"
        }
        val connected = hasInternet && validated
        val detail = "transport=$transport; internet=$hasInternet; validated=$validated"
        viewModel.onNetworkStatus(connected = connected, detail = detail)
    }
}

@Composable
private fun RevaPushupScreen(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsState()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .padding(horizontal = 28.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.SpaceBetween,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Header(state)
        RepCounter(state)
        Guidance(state)
        Footer(state)
    }
}

@Composable
private fun Header(state: RevaPushupUiState) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = state.ingestStatus,
            color = Color(0xFF7DD3FC),
            fontSize = 14.sp,
            maxLines = 1,
        )
        Text(
            text = phaseText(state.phase),
            color = Color(0xFFE5E7EB),
            fontSize = 14.sp,
            maxLines = 1,
        )
    }
}

@Composable
private fun RepCounter(state: RevaPushupUiState) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = "${state.reps}",
            color = Color.White,
            fontSize = 76.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
            lineHeight = 82.sp,
        )
        Text(
            text = "/ ${state.targetReps}",
            color = Color(0xFFCBD5E1),
            fontSize = 26.sp,
            fontWeight = FontWeight.Medium,
        )
        Spacer(modifier = Modifier.height(10.dp))
        Text(
            text = "质量 ${state.qualityScore.toInt()}",
            color = qualityColor(state.qualityScore),
            fontSize = 22.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun Guidance(state: RevaPushupUiState) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = state.feedback,
            color = Color.White,
            fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            maxLines = 2,
        )
        Text(
            text = state.suggestion,
            color = Color(0xFFE5E7EB),
            fontSize = 18.sp,
            lineHeight = 23.sp,
            textAlign = TextAlign.Center,
            maxLines = 3,
        )
    }
}

@Composable
private fun Footer(state: RevaPushupUiState) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        StatusDot(text = state.cameraStatus, color = Color(0xFF34D399))
        StatusDot(text = state.analyzerStatus, color = Color(0xFFA78BFA))
        StatusDot(text = state.networkStatus, color = Color(0xFFFBBF24))
        StatusDot(text = state.cxrStatus, color = Color(0xFF38BDF8))
    }
}

@Composable
private fun StatusDot(text: String, color: Color) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        androidx.compose.foundation.Canvas(modifier = Modifier.size(7.dp)) {
            drawCircle(color = color)
        }
        Text(
            modifier = Modifier.padding(start = 8.dp),
            text = text,
            color = Color(0xFF94A3B8),
            fontSize = 12.sp,
            maxLines = 1,
        )
    }
}

private fun phaseText(phase: PushupPhase): String =
    when (phase) {
        PushupPhase.UNKNOWN -> "准备"
        PushupPhase.UP -> "顶部"
        PushupPhase.DOWN -> "底部"
        PushupPhase.TRANSITION -> "移动中"
    }

private fun qualityColor(score: Double): Color =
    when {
        score >= 85.0 -> Color(0xFF34D399)
        score >= 70.0 -> Color(0xFFFBBF24)
        score > 0.0 -> Color(0xFFFB7185)
        else -> Color(0xFF64748B)
    }
