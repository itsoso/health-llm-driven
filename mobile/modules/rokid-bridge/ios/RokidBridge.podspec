Pod::Spec.new do |s|
  rokid_ios_sdk_enabled = ['1', 'true', 'yes'].include?(
    (ENV['ROKID_IOS_SDK_ENABLED'] || ENV['ROKID_SDK_ENABLED']).to_s.downcase
  )

  s.name           = 'RokidBridge'
  s.version        = '0.1.0'
  s.summary        = 'Rokid CXR bridge for Reva ambient wearable inputs'
  s.description    = s.summary
  s.author         = ''
  s.homepage       = 'https://docs.expo.dev/modules/'
  s.platforms      = { :ios => '15.1' }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  if rokid_ios_sdk_enabled
    s.dependency 'RGCxrClient', '1.0.1'
  end

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule',
    'APPLICATION_EXTENSION_API_ONLY' => 'NO'
  }

  s.source_files = "**/*.{h,m,mm,swift}"
end
