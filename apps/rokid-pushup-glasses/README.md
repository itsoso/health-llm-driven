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

### Option A: Reva iOS CXR-L install

Use this when USB / ADB cannot see the glasses through the charging case.

1. Build the glasses APK:

```bash
cd apps/rokid-pushup-glasses
ANDROID_HOME="$HOME/Library/Android/sdk" ./scripts/download-pose-model.sh
ANDROID_HOME="$HOME/Library/Android/sdk" ./gradlew assembleDebug
```

2. Make the APK available to Reva iOS in one of two ways:

- Bundled native build: set `REVA_ROKID_PUSHUP_APK_PATH` to the APK path before
  running Expo prebuild / EAS local build. The iOS config plugin copies it as
  `rokid-pushup-glasses.apk`.
- Files fallback: AirDrop or save `app-debug.apk` to iPhone Files, then use
  Reva > Rokid 俯卧撑计数 > 安装/更新眼镜端 App and select the APK.

3. In Reva iOS:

- install a native build with `ROKID_IOS_SDK_ENABLED=1`;
- complete Rokid CXR-L authorization;
- open Rokid 俯卧撑计数;
- tap 安装/更新眼镜端 App;
- tap 启动眼镜识别.

### Option B: ADB install

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
