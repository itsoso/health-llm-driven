# Local podspec for the refreshed Rokid CXR-L iOS client.
#
# 为什么需要这个文件:
#   公开 CocoaPods 的 RGCxrClient 1.0.1 是旧 binary(569 行 interface, 无 callback
#   openCustomView / setNotifyEventListenCmds), 拿不到 CustomView 需要的 API。
#   仓库内 vendor/RGCxrClient.framework 是从官方 ios_cxr_l_sample 取的刷新框架
#   (659 行 interface, 带 callback + setNotifyEventListenCmds)。
#
#   之前用 RokidBridge.podspec 的 s.vendored_frameworks 接它 —— 但在 Expo
#   static_framework 模块里, vendored_frameworks 不把框架传播进 RokidBridge 的
#   -F framework 搜索路径(EAS build f0878b7b / Xcode 26.4 实测: RokidBridge 的
#   swiftc -F 只有 RGCoreKit, 没有 RGCxrClient → canImport(RGCxrClient)=false →
#   整个 SDK 编成 noop, build 绿却没 SDK)。
#
#   官方 sample 用一等 pod `pod 'RGCxrClient'` 才全对(module / 搜索路径 / 链接)。
#   这里把刷新框架做成一等本地 pod, 由 withRokidIosPods.js 用 :path 注入 Podfile,
#   RokidBridge 改成 s.dependency 'RGCxrClient' 来消费 —— 对齐 sample 的成功姿势。
Pod::Spec.new do |s|
  rokid_ios_client_version = ENV['ROKID_IOS_CLIENT_VERSION'].to_s.strip
  rokid_ios_client_version = '1.0.1' if rokid_ios_client_version.empty?

  s.name             = 'RGCxrClient'
  s.version          = rokid_ios_client_version
  s.summary          = 'Rokid CXR-L iOS client (refreshed vendored binary)'
  s.description      = 'Refreshed RGCxrClient.framework with CustomView callback APIs, vendored from the official CXR-L iOS sample.'
  s.homepage         = 'https://ar.rokid.com'
  s.author           = 'Rokid'
  s.license          = { :type => 'Commercial', :text => 'Rokid CXR-L SDK (vendored binary).' }
  s.platform         = :ios, '16.0'
  s.source           = { :git => '' }
  s.vendored_frameworks = 'RGCxrClient.framework'
  s.dependency 'RGCoreKit', '0.0.2'
end
