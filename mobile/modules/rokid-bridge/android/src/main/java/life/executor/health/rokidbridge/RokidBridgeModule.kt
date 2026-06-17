package life.executor.health.rokidbridge

import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class RokidBridgeModule : Module() {
  private val supportedPackages = listOf(
    "com.rokid.sprite.global.aiapp",
    "com.rokid.sprite.aiapp",
  )

  private val context: Context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("RokidBridge")

    AsyncFunction("getIntegrationStatus") {
      val installedPackage = firstInstalledHiRokidPackage()
      mapOf(
        "platform" to "android",
        "bridgeAvailable" to true,
        "hiRokidInstalled" to (installedPackage != null),
        "canOpenHiRokid" to (launchIntentFor(installedPackage) != null),
        "mode" to "sdk_probe",
        "sdkLinked" to BuildConfig.ROKID_SDK_LINKED,
        "installedPackage" to installedPackage,
        "supportedPackages" to supportedPackages,
        "sdkClassProbe" to sdkClassProbe(),
      )
    }

    AsyncFunction("openHiRokid") {
      val installedPackage = firstInstalledHiRokidPackage() ?: return@AsyncFunction false
      val launchIntent = launchIntentFor(installedPackage) ?: return@AsyncFunction false
      launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      context.startActivity(launchIntent)
      true
    }
  }

  private fun firstInstalledHiRokidPackage(): String? =
    supportedPackages.firstOrNull { isPackageInstalled(it) }

  private fun isPackageInstalled(packageName: String): Boolean =
    try {
      packageManager.getPackageInfoCompat(packageName, 0)
      true
    } catch (_: PackageManager.NameNotFoundException) {
      false
    }

  private fun launchIntentFor(packageName: String?): Intent? =
    packageName?.let { packageManager.getLaunchIntentForPackage(it) }

  private fun sdkClassProbe(): Map<String, Boolean> =
    mapOf(
      "clientM.cxrApi" to classExists("com.rokid.cxr.client.extend.CxrApi"),
      "clientM.serviceBridge" to classExists("com.rokid.cxr.CXRServiceBridge"),
      "clientL.cxrLink" to classExists("com.rokid.cxr.link.CXRLink"),
      "clientL.authorization" to classExists("com.rokid.sprite.aiapp.externalapp.auth.AuthorizationHelper"),
      "clientL.mediaStreamService" to classExists("com.rokid.sprite.aiapp.externalapp.IMediaStreamService"),
    )

  private fun classExists(className: String): Boolean =
    try {
      Class.forName(className, false, javaClass.classLoader)
      true
    } catch (_: ClassNotFoundException) {
      false
    } catch (_: LinkageError) {
      false
    }

  private val packageManager: PackageManager
    get() = context.packageManager
}

private fun PackageManager.getPackageInfoCompat(packageName: String, flags: Int = 0): PackageInfo =
  if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
    getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(flags.toLong()))
  } else {
    @Suppress("DEPRECATION")
    getPackageInfo(packageName, flags)
  }
