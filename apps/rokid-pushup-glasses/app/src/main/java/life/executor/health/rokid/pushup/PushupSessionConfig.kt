package life.executor.health.rokid.pushup

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

data class PushupSessionConfig(
    val sessionId: Int,
    val targetReps: Int,
    val ingestUrl: String,
    val ingestToken: String,
) {
    companion object {
        fun parse(rawUrl: String?): PushupSessionConfig? {
            if (rawUrl.isNullOrBlank()) return null

            val uri = runCatching { URI(rawUrl) }.getOrNull() ?: return null
            if (uri.scheme != "reva" || uri.host != "rokid" || uri.path != "/pushup") {
                return null
            }

            val query = parseQuery(uri.rawQuery ?: return null)
            val sessionId = query["session_id"]?.toIntOrNull() ?: return null
            val targetReps = query["target_reps"]?.toIntOrNull()?.coerceAtLeast(1) ?: 20
            val ingestUrl = query["ingest_url"]?.takeIf { it.startsWith("https://") || it.startsWith("http://") }
                ?: return null
            val ingestToken = query["ingest_token"]?.takeIf { it.isNotBlank() } ?: return null

            return PushupSessionConfig(
                sessionId = sessionId,
                targetReps = targetReps,
                ingestUrl = ingestUrl,
                ingestToken = ingestToken,
            )
        }

        private fun parseQuery(rawQuery: String): Map<String, String> {
            if (rawQuery.isBlank()) return emptyMap()

            return rawQuery.split("&")
                .mapNotNull { pair ->
                    val index = pair.indexOf("=")
                    if (index <= 0) return@mapNotNull null

                    val key = decode(pair.substring(0, index))
                    val value = decode(pair.substring(index + 1))
                    key to value
                }
                .toMap()
        }

        private fun decode(value: String): String =
            URLDecoder.decode(value, StandardCharsets.UTF_8.name())
    }
}
