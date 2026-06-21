# CXR-S runs inside the Rokid glasses process and may use binder/reflection
# entry points that R8 cannot infer from the app source.
-keep class com.rokid.** { *; }
-dontwarn com.rokid.**

# MediaPipe Tasks owns the pose model/native bridge. Keep it conservative so the
# pushup recognition path keeps the same runtime behavior after shrinking.
-keep class com.google.mediapipe.** { *; }
-dontwarn com.google.mediapipe.**

# CameraX/OkHttp ship consumer rules; these suppress optional-platform warnings
# without changing runtime behavior.
-dontwarn androidx.camera.**
-dontwarn androidx.window.**
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
