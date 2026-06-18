# Reva Rokid Push-up Glasses APK

Android app that runs on Rokid Glasses as `life.executor.health.rokid.pushup`.
It uses the glasses camera, MediaPipe Pose Landmarker, local push-up counting,
and posts pose/rep events back to Reva when launched with a Reva session URL.

## Build

```bash
cd apps/rokid-pushup-glasses
ANDROID_HOME="$HOME/Library/Android/sdk" ./scripts/download-pose-model.sh
ANDROID_HOME="$HOME/Library/Android/sdk" ./gradlew assembleDebug
```

Debug APK:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## Install on Rokid Glasses

```bash
adb devices
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The package and entry activity are:

```text
life.executor.health.rokid.pushup
life.executor.health.rokid.pushup.MainActivity
```

## Reva Session Launch

Reva iOS creates a session and opens the glasses app with:

```text
reva://rokid/pushup?session_id=7&target_reps=20&ingest_url=https%3A%2F%2F...%2Fevents&ingest_token=...
```

When the URL is present, the app posts:

```text
POST {ingest_url}
X-Reva-Rokid-Session-Token: {ingest_token}
Content-Type: application/json
```

Direct launch without the URL still runs local counting and the glasses UI, but
does not upload events.
