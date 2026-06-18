package life.executor.health.rokid.pushup

import android.util.Base64
import android.util.Log
import com.rokid.cxr.CXRServiceBridge
import com.rokid.cxr.Caps

class RokidCxrBridge(
    private val onStatus: (String) -> Unit,
    private val onMessage: (String) -> Unit,
) {
    private val cxrBridge = CXRServiceBridge()

    private val statusListener = object : CXRServiceBridge.StatusListener {
        override fun onConnected(p0: String?, p1: String?, p2: Int) {
            onStatus("CXR-S 已连接")
        }

        override fun onDisconnected() {
            onStatus("CXR-S 已断开")
        }

        override fun onConnecting(p0: String?, p1: String?, p2: Int) {
            onStatus("CXR-S 连接中")
        }

        override fun onARTCStatus(p0: Float, p1: Boolean) = Unit
        override fun onRokidAccountChanged(p0: String?) = Unit
        override fun onAudioNoise(p0: Float) = Unit
    }

    private val msgCallback = object : CXRServiceBridge.MsgCallback {
        override fun onReceive(name: String?, args: Caps?, bytes: ByteArray?) {
            onMessage("name=$name,args=${args?.let { parseCaps(it) } ?: "null"}")
        }
    }

    init {
        cxrBridge.setStatusListener(statusListener)
        cxrBridge.subscribe(CLIENT_KEY, msgCallback)
    }

    fun sendStatus(message: String) {
        runCatching {
            cxrBridge.sendMessage(CMD_KEY, Caps().apply {
                write("message")
                write(message)
            })
        }.onFailure { error ->
            Log.w(TAG, "Failed to send CXR status", error)
        }
    }

    fun close() = Unit

    private fun parseCaps(caps: Caps): String {
        val parts = mutableListOf<String>()
        for (index in 0 until caps.size()) {
            val value = caps.at(index)
            parts += when (value.type()) {
                Caps.Value.TYPE_STRING -> "string:${value.string}"
                Caps.Value.TYPE_INT32,
                Caps.Value.TYPE_UINT32 -> "int:${value.int}"
                Caps.Value.TYPE_INT64,
                Caps.Value.TYPE_UINT64 -> "long:${value.long}"
                Caps.Value.TYPE_FLOAT -> "float:${value.float}"
                Caps.Value.TYPE_DOUBLE -> "double:${value.double}"
                Caps.Value.TYPE_OBJECT -> "object:${parseCaps(value.`object`)}"
                Caps.Value.TYPE_BINARY -> value.binary?.let { binary ->
                    "binary:${Base64.encodeToString(binary.data, Base64.NO_WRAP)}"
                } ?: "binary:null"
                else -> "unknown"
            }
        }
        return parts.joinToString(prefix = "{", postfix = "}")
    }

    companion object {
        private const val TAG = "RokidCxrBridge"
        private const val CMD_KEY = "rk_custom_key"
        private const val CLIENT_KEY = "rk_custom_client"
    }
}
