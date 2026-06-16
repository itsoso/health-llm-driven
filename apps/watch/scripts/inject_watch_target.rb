#!/usr/bin/env ruby
# 把 RevaWatch watchOS App target 注入 prebuilt 的 HealthPilot.xcodeproj。
# 用法: ruby apps/watch/scripts/inject_watch_target.rb [path/to/HealthPilot.xcodeproj]
#
# 这是 config-plugin 的可执行参考(纯 Ruby xcodeproj,比 JS xcode lib 更可靠地建 watch target)。
# 幂等: 已存在 RevaWatch target 则跳过创建,只刷新源文件引用。
require 'xcodeproj'

proj_path = ARGV[0] || File.expand_path('../../../../mobile/ios/HealthPilot.xcodeproj', __FILE__)
watch_name = 'RevaWatch'
watch_bundle = 'life.executor.health.watchkitapp'
ios_bundle = 'life.executor.health'
src_dir = File.join(File.dirname(proj_path), watch_name)   # ios/RevaWatch

abort("✗ 工程不存在: #{proj_path}") unless File.exist?(proj_path)
abort("✗ 源目录不存在: #{src_dir}") unless Dir.exist?(src_dir)

project = Xcodeproj::Project.open(proj_path)

target = project.targets.find { |t| t.name == watch_name }
if target.nil?
  target = project.new_target(:application, watch_name, :watchos, '10.0')
  puts "✓ 新建 watchOS app target: #{watch_name}"
else
  puts "• target 已存在,刷新源引用: #{watch_name}"
end

target.build_configurations.each do |c|
  bs = c.build_settings
  bs['PRODUCT_BUNDLE_IDENTIFIER'] = watch_bundle
  bs['SDKROOT'] = 'watchos'
  bs['TARGETED_DEVICE_FAMILY'] = '4'                          # Apple Watch
  bs['WATCHOS_DEPLOYMENT_TARGET'] = '10.0'
  bs['SWIFT_VERSION'] = '5.0'
  bs['GENERATE_INFOPLIST_FILE'] = 'YES'
  bs['INFOPLIST_KEY_WKApplication'] = 'YES'                   # 现代单 target watch app
  bs['INFOPLIST_KEY_WKCompanionAppBundleIdentifier'] = ios_bundle
  bs['INFOPLIST_KEY_CFBundleDisplayName'] = '健康助理'
  bs['CODE_SIGNING_ALLOWED'] = 'NO'                           # 仅编译验证;发版时由 EAS 处理签名
  bs['PRODUCT_NAME'] = watch_name
end

# 源文件组 + 引用(幂等:先清掉本 target 已有的 RevaWatch 源 build files)
group = project.main_group.find_subpath(watch_name, true)
group.set_source_tree('SOURCE_ROOT')
group.clear

existing = target.source_build_phase.files_references.map(&:real_path).map(&:to_s)
Dir.glob(File.join(src_dir, '*.swift')).sort.each do |f|
  ref = group.new_file(f)
  next if existing.include?(File.expand_path(f))
  target.add_file_references([ref])
end
puts "✓ 已加 #{Dir.glob(File.join(src_dir, '*.swift')).size} 个 swift 源"

project.save
puts "✓ 保存: #{proj_path}"
