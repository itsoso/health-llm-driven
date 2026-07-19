Pod::Spec.new do |s|
  s.name           = 'LocalHealthKernel'
  s.version        = '1.0.0'
  s.summary        = 'Encrypted, device-local health data kernel'
  s.description    = s.summary
  s.author         = ''
  s.homepage       = 'https://executor.life'
  s.platforms      = { :ios => '16.0' }
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'
  s.frameworks = 'CoreGraphics', 'CoreML', 'CryptoKit', 'Foundation', 'ImageIO', 'Security', 'UIKit', 'Vision'
  s.libraries = 'sqlite3'
  s.resources = 'Resources/**/*'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule'
  }

  s.source_files = '**/*.{h,m,swift}'
end
