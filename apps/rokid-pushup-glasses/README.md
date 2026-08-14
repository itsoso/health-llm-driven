# Reva Rokid Push-up Glasses APK

Android app that runs on Rokid Glasses as `life.executor.health.rokid.pushup`.
It uses the glasses camera, MediaPipe Pose Landmarker, local push-up counting,
and posts pose/rep events back to Reva when launched with a Reva session URL.

## Release freeze

The tracked Gradle wrappers are frozen with exit 78. This project previously
used the debug keystore for a release APK, and the same repository flow could
install those bytes on physical glasses. Do not invoke Gradle, Android Studio,
ADB, or the iOS bridge as a workaround. Building, signing, and installing the
Rokid app require a separately authorized and audited manual external Gate.

## Install on Rokid Glasses

Historical CXR-L and ADB installation steps are intentionally not executable
instructions during the freeze. The future external Gate must own the exact
source, signing identity, artifact receipt, device target, and installation
evidence before either route is restored.

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
