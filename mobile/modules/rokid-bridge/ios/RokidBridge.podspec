Pod::Spec.new do |s|
  rokid_ios_sdk_enabled = ['1', 'true', 'yes'].include?(
    (ENV['ROKID_IOS_SDK_ENABLED'] || ENV['ROKID_SDK_ENABLED']).to_s.downcase
  )
  rokid_ios_simulator = ['1', 'true', 'yes'].include?(
    ENV['ROKID_IOS_SIMULATOR'].to_s.downcase
  )
  rokid_ios_client_version = ENV['ROKID_IOS_CLIENT_VERSION'].to_s.strip
  rokid_ios_client_version = '1.0.1' if rokid_ios_client_version.empty?
  rokid_ios_client_framework_path = ENV['ROKID_IOS_CLIENT_FRAMEWORK_PATH'].to_s.strip
  rokid_ios_client_has_callback_api = ['1', 'true', 'yes'].include?(
    ENV['ROKID_IOS_CLIENT_HAS_CALLBACK_API'].to_s.downcase
  )
  swift_flags = ['$(inherited)']

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

  if rokid_ios_sdk_enabled && !rokid_ios_simulator
    if !rokid_ios_client_framework_path.empty?
      s.vendored_frameworks = rokid_ios_client_framework_path
      s.dependency 'RGCoreKit', '0.0.2'
    else
      s.dependency 'RGCxrClient', rokid_ios_client_version
    end
    swift_flags << '-D' << 'ROKID_IOS_SDK_REQUESTED'
    if rokid_ios_client_has_callback_api
      swift_flags << '-D' << 'ROKID_CXRL_CALLBACK_API'
    end
  elsif rokid_ios_sdk_enabled && rokid_ios_simulator
    swift_flags << '-D' << 'ROKID_IOS_SIMULATOR_EXCLUDED'
  end

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule',
    'APPLICATION_EXTENSION_API_ONLY' => 'NO',
    'OTHER_SWIFT_FLAGS' => swift_flags.join(' ')
  }

  s.source_files = "**/*.{h,m,mm,swift}"
end
