package life.executor.health.rokid.pushup

import android.util.Log
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException

interface PushupEventReporter {
    fun report(payload: PushupEventPayload)
    fun close()
}

object NoopPushupEventReporter : PushupEventReporter {
    override fun report(payload: PushupEventPayload) = Unit
    override fun close() = Unit
}

class RevaPushupEventClient(
    private val config: PushupSessionConfig,
    private val client: OkHttpClient = OkHttpClient(),
    private val onStatus: (String) -> Unit = {},
) : PushupEventReporter {
    override fun report(payload: PushupEventPayload) {
        val request = Request.Builder()
            .url(config.ingestUrl)
            .header("X-Reva-Rokid-Session-Token", config.ingestToken)
            .post(payload.toJson().toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.w(TAG, "Failed to post pushup event", e)
                onStatus("上报失败: ${e.message ?: "network"}")
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!it.isSuccessful) {
                        onStatus("上报失败: HTTP ${it.code}")
                    }
                }
            }
        })
    }

    override fun close() {
        client.dispatcher.cancelAll()
    }

    companion object {
        private const val TAG = "RevaPushupEventClient"
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
