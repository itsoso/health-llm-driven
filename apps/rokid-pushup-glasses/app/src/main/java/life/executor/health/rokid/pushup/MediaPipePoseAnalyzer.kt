package life.executor.health.rokid.pushup

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.util.Log
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.ImageProcessingOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarker
import com.google.mediapipe.tasks.vision.poselandmarker.PoseLandmarkerResult
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean

class MediaPipePoseAnalyzer(
    context: Context,
    private val onSample: (PushupPoseSample, Long) -> Unit,
    private val onStatus: (String) -> Unit,
) : ImageAnalysis.Analyzer, AutoCloseable {
    private val inFlight = AtomicBoolean(false)
    private val frameIds = ConcurrentHashMap<Long, Long>()
    private var frameId = 0L
    private var lastAnalyzedAtMs = 0L
    private var landmarker: PoseLandmarker? = null

    init {
        landmarker = runCatching { createLandmarker(context.applicationContext) }
            .onSuccess { onStatus("姿态模型已加载") }
            .onFailure { error ->
                Log.e(TAG, "Failed to initialize MediaPipe PoseLandmarker", error)
                onStatus("姿态模型加载失败: ${error.message ?: "missing asset"}")
            }
            .getOrNull()
    }

    override fun analyze(imageProxy: ImageProxy) {
        val poseLandmarker = landmarker
        val nowMs = System.currentTimeMillis()
        if (poseLandmarker == null || nowMs - lastAnalyzedAtMs < FRAME_INTERVAL_MS) {
            imageProxy.close()
            return
        }
        if (!inFlight.compareAndSet(false, true)) {
            imageProxy.close()
            return
        }

        lastAnalyzedAtMs = nowMs
        val currentFrameId = ++frameId
        frameIds[nowMs] = currentFrameId

        try {
            val bitmap = imageProxy.toRgbBitmap()
            val mpImage = BitmapImageBuilder(bitmap).build()
            val options = ImageProcessingOptions.builder()
                .setRotationDegrees(imageProxy.imageInfo.rotationDegrees)
                .build()
            poseLandmarker.detectAsync(mpImage, options, nowMs)
        } catch (error: Throwable) {
            Log.w(TAG, "Failed to analyze camera frame", error)
            frameIds.remove(nowMs)
            inFlight.set(false)
            onStatus("姿态分析失败: ${error.message ?: "frame"}")
        } finally {
            imageProxy.close()
        }
    }

    override fun close() {
        landmarker?.close()
        landmarker = null
        frameIds.clear()
    }

    private fun createLandmarker(context: Context): PoseLandmarker {
        val baseOptions = BaseOptions.builder()
            .setModelAssetPath(MODEL_ASSET)
            .build()
        val options = PoseLandmarker.PoseLandmarkerOptions.builder()
            .setBaseOptions(baseOptions)
            .setRunningMode(RunningMode.LIVE_STREAM)
            .setNumPoses(1)
            .setMinPoseDetectionConfidence(0.5f)
            .setMinPosePresenceConfidence(0.5f)
            .setMinTrackingConfidence(0.5f)
            .setResultListener { result, _ -> handleResult(result) }
            .setErrorListener { error ->
                Log.w(TAG, "MediaPipe PoseLandmarker callback error", error)
                inFlight.set(false)
                onStatus("姿态回调失败: ${error.message ?: "callback"}")
            }
            .build()
        return PoseLandmarker.createFromOptions(context, options)
    }

    private fun handleResult(result: PoseLandmarkerResult) {
        try {
            val landmarks = result.landmarks().firstOrNull()?.map { landmark ->
                PosePoint(
                    x = landmark.x(),
                    y = landmark.y(),
                    z = landmark.z(),
                    visibility = landmark.visibility().orElse(0f),
                )
            }
            if (landmarks.isNullOrEmpty()) {
                onStatus("未识别到人体")
                return
            }

            val sample = PoseGeometry.toPushupSample(
                timestampMs = result.timestampMs(),
                landmarks = landmarks,
            )
            if (sample == null) {
                onStatus("关键点不足")
                return
            }

            val id = frameIds.remove(result.timestampMs()) ?: frameId
            onSample(sample, id)
        } finally {
            inFlight.set(false)
        }
    }

    private fun ImageProxy.toRgbBitmap(): Bitmap {
        require(format == ImageFormat.YUV_420_888) {
            "Unsupported image format: $format"
        }
        val nv21 = toNv21()
        val image = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        val stream = ByteArrayOutputStream()
        image.compressToJpeg(Rect(0, 0, width, height), JPEG_QUALITY, stream)
        val bytes = stream.toByteArray()
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: error("Failed to decode camera frame")
    }

    private fun ImageProxy.toNv21(): ByteArray {
        val ySize = width * height
        val uvSize = width * height / 2
        val output = ByteArray(ySize + uvSize)

        copyPlane(
            buffer = planes[0].buffer,
            rowStride = planes[0].rowStride,
            pixelStride = planes[0].pixelStride,
            width = width,
            height = height,
            output = output,
            outputOffset = 0,
            outputPixelStride = 1,
        )
        copyPlane(
            buffer = planes[2].buffer,
            rowStride = planes[2].rowStride,
            pixelStride = planes[2].pixelStride,
            width = width / 2,
            height = height / 2,
            output = output,
            outputOffset = ySize,
            outputPixelStride = 2,
        )
        copyPlane(
            buffer = planes[1].buffer,
            rowStride = planes[1].rowStride,
            pixelStride = planes[1].pixelStride,
            width = width / 2,
            height = height / 2,
            output = output,
            outputOffset = ySize + 1,
            outputPixelStride = 2,
        )

        return output
    }

    private fun copyPlane(
        buffer: ByteBuffer,
        rowStride: Int,
        pixelStride: Int,
        width: Int,
        height: Int,
        output: ByteArray,
        outputOffset: Int,
        outputPixelStride: Int,
    ) {
        val source = buffer.duplicate()
        var outputIndex = outputOffset
        val row = ByteArray(rowStride)

        for (rowIndex in 0 until height) {
            val bytesToRead = minOf(rowStride, source.remaining())
            if (bytesToRead <= 0) break
            source.get(row, 0, bytesToRead)
            for (column in 0 until width) {
                val sourceIndex = column * pixelStride
                if (sourceIndex >= bytesToRead || outputIndex >= output.size) continue
                output[outputIndex] = row[sourceIndex]
                outputIndex += outputPixelStride
            }
            if (rowIndex == height - 1) break
        }
    }

    companion object {
        private const val TAG = "MediaPipePoseAnalyzer"
        private const val MODEL_ASSET = "pose_landmarker_lite.task"
        private const val FRAME_INTERVAL_MS = 150L
        private const val JPEG_QUALITY = 80
    }
}
