#!/usr/bin/env ruby
# encoding: utf-8
# pbxproj 含中文显示名 → 强制 UTF-8,否则 Ruby 默认 US-ASCII 读 pbxproj 报 invalid byte。
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8
# 把 RevaWatch watchOS App target 注入 prebuilt 的 Expo iOS xcodeproj。
# 用法: ruby apps/watch/scripts/inject_watch_target.rb [path/to/app.xcodeproj]
#
# 这是 config-plugin 的可执行参考(纯 Ruby xcodeproj,比 JS xcode lib 更可靠地建 watch target)。
# 幂等: 已存在 RevaWatch target 则跳过创建,只刷新源文件引用。
require 'xcodeproj'
require 'fileutils'

default_proj = Dir[File.expand_path('../../../../mobile/ios/*.xcodeproj', __FILE__)].sort.first
proj_path = ARGV[0] || default_proj || File.expand_path('../../../../mobile/ios/HealthPilot.xcodeproj', __FILE__)
watch_name = 'RevaWatch'
watch_bundle = 'life.executor.health.watchkitapp'
ios_bundle = (ENV['REVA_IOS_BUNDLE_ID'] || 'life.executor.health').strip
src_dir = File.join(File.dirname(proj_path), watch_name)   # ios/RevaWatch

abort("✗ 工程不存在: #{proj_path}") unless File.exist?(proj_path)
abort("✗ 源目录不存在: #{src_dir}") unless Dir.exist?(src_dir)

project = Xcodeproj::Project.open(proj_path)

def ensure_plist_value(plist_path, key, value)
  abort("✗ plist 不存在: #{plist_path}") unless File.exist?(plist_path)
  cmd = '/usr/libexec/PlistBuddy'
  return if system(cmd, '-c', "Set :#{key} #{value}", plist_path, out: File::NULL, err: File::NULL)
  ok = system(cmd, '-c', "Add :#{key} string #{value}", plist_path, out: File::NULL, err: File::NULL)
  abort("✗ 写 plist 失败: #{plist_path} #{key}=#{value}") unless ok
end

# 版本号必须与主 app 一致(否则 watchOS 校验报版本不匹配)。
configured_main_target_name = ENV['REVA_MAIN_TARGET_NAME'].to_s.strip
main_t = nil
main_t = project.targets.find { |t| t.name == configured_main_target_name } unless configured_main_target_name.empty?
main_t ||= project.targets.find do |t|
  t.respond_to?(:product_type) &&
    t.product_type == 'com.apple.product-type.application' &&
    t.name != watch_name
end
abort("✗ 主 app target 不存在: #{configured_main_target_name.empty? ? '(auto)' : configured_main_target_name}") unless main_t

main_group_path = ENV['REVA_MAIN_GROUP_PATH'].to_s.strip
main_group_path = main_t.name if main_group_path.empty?
main_infoplist_file = ENV['REVA_IOS_INFOPLIST_FILE'].to_s.strip
main_infoplist_file = "#{main_group_path}/Info.plist" if main_infoplist_file.empty?
main_bs = main_t&.build_configurations&.find { |c| c.name == 'Release' }&.build_settings || {}
configured_mv = ENV['REVA_MARKETING_VERSION'].to_s.strip
mv = configured_mv.empty? ? (main_bs['MARKETING_VERSION'] || '1.0') : configured_mv
cv = main_bs['CURRENT_PROJECT_VERSION'] || '1'
puts "• 主 app target: #{main_t.name} INFOPLIST_FILE=#{main_infoplist_file}"
puts "• 主 app 版本: MARKETING_VERSION=#{mv} CURRENT_PROJECT_VERSION=#{cv}"

if main_t
  main_t.build_configurations.each do |c|
    bs = c.build_settings
    bs['PRODUCT_BUNDLE_IDENTIFIER'] = ios_bundle
    bs['GENERATE_INFOPLIST_FILE'] = 'NO'
    bs['INFOPLIST_FILE'] = main_infoplist_file
    bs['MARKETING_VERSION'] = mv
    bs['DEVELOPMENT_TEAM'] ||= ENV['APPLE_TEAM_ID'] || main_bs['DEVELOPMENT_TEAM'] || 'QA2U724DAN'
  end
end

# Apple Team ID:watch app + complication 必须有显式 DEVELOPMENT_TEAM,否则 EAS 构建时
# 这两个 target(EAS 只为主 app target 注入凭据,不认识 watch)会落到"无 team"自动签名,
# Xcode 14 默认对 resource bundle / 嵌入二进制要求每个 target 有 team → EAS #94:
# "resource bundles are signed by default, which requires setting the development team for each target"。
# 本地 xcodebuild 用命令行 DEVELOPMENT_TEAM 兜全 target 所以复现不出;EAS 复现得出 → 必须烤进工程。
# 取值优先级:env APPLE_TEAM_ID(EAS 可注)→ 主 app 已有的 DEVELOPMENT_TEAM → 已知团队 QA2U724DAN(baokun Pan)。
team_id = ENV['APPLE_TEAM_ID'] || main_bs['DEVELOPMENT_TEAM'] || 'QA2U724DAN'
puts "• watch 签名 team: DEVELOPMENT_TEAM=#{team_id} (CODE_SIGN_STYLE=Automatic)"

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
  bs['GENERATE_INFOPLIST_FILE'] = 'NO'
  bs['INFOPLIST_FILE'] = "#{watch_name}/Info.plist"
  bs.delete('INFOPLIST_KEY_WKApplication')
  bs.delete('INFOPLIST_KEY_WKCompanionAppBundleIdentifier')
  bs.delete('INFOPLIST_KEY_CFBundleIconName')
  # 注:显示名不写进 pbxproj(中文会让 CocoaPods 读 pbxproj 时 ASCII-8BIT 崩);
  # 腕上显示名走 watch target 的 Info.plist,本脚本在下方用 PlistBuddy 幂等写入。
  # 不再强制 CODE_SIGNING_ALLOWED=NO —— 发版时 EAS/xcodebuild 要给 watch target 签名,
  # 强制 NO 会让嵌入二进制未签名 → "not signed with the same certificate as the parent app"。
  bs['PRODUCT_NAME'] = watch_name
  bs['MARKETING_VERSION'] = mv                                # 与主 app 一致,过 watchOS 版本校验
  bs['CURRENT_PROJECT_VERSION'] = cv
  bs.delete('INFOPLIST_KEY_CFBundleDisplayName')              # 幂等清理:历史中文值会让 CocoaPods 崩
  bs['DEVELOPMENT_TEAM'] = team_id                            # EAS 不为 watch target 注 team → 必须烤进工程(见上)
  bs['CODE_SIGN_STYLE'] = 'Automatic'                         # 配 -allowProvisioningUpdates 自动建 watch profile
  bs['CODE_SIGN_ENTITLEMENTS'] = "#{watch_name}/RevaWatch.entitlements"
  bs.delete('CODE_SIGN_INJECT_BASE_ENTITLEMENTS')
end

watch_plist = File.join(src_dir, 'Info.plist')
ensure_plist_value(watch_plist, 'CFBundleDisplayName', '小巴健康')
ensure_plist_value(watch_plist, 'CFBundleName', '小巴健康')

# 源文件组 + 引用(幂等:先清掉本 target 已有的 RevaWatch 源 build files)
group = project.main_group.find_subpath(watch_name, true)
group.path = watch_name
group.set_source_tree('SOURCE_ROOT')
group.clear

existing = target.source_build_phase.files_references.map(&:real_path).map(&:to_s)
Dir.glob(File.join(src_dir, '*.swift')).sort.each do |f|
  ref = group.new_file(File.basename(f))
  next if existing.include?(File.expand_path(f))
  target.add_file_references([ref])
end
puts "✓ 已加 #{Dir.glob(File.join(src_dir, '*.swift')).size} 个 swift 源"

asset_catalog = File.join(src_dir, 'Assets.xcassets')
if Dir.exist?(asset_catalog)
  target.resources_build_phase.files.each do |build_file|
    ref = build_file.file_ref
    next unless ref&.path&.end_with?('Assets.xcassets') || ref&.path&.include?('AppIcon.appiconset/') || ref&.path&.include?('IconFiles/')
    build_file.remove_from_project
  end
  asset_ref = group.new_file('Assets.xcassets')
  target.resources_build_phase.add_file_reference(asset_ref)
  puts "✓ 已把 Assets.xcassets 加进 #{watch_name} resources"

  icon_pngs = Dir.glob(File.join(asset_catalog, 'AppIcon.appiconset', '*.png')).sort
  icon_pngs.each do |png|
    ref = group.new_file(File.join('Assets.xcassets', 'AppIcon.appiconset', File.basename(png)))
    target.resources_build_phase.add_file_reference(ref)
  end
  puts "✓ 已把 #{icon_pngs.size} 个 watch icon PNG 加进 #{watch_name} resources"
end

# ── complication widget extension(WidgetKit,嵌入 watch app)──────────────
comp_name = 'RevaComplication'
comp_dir = File.join(File.dirname(proj_path), comp_name)   # ios/RevaComplication
if Dir.exist?(comp_dir)
  comp = project.targets.find { |t| t.name == comp_name }
  if comp.nil?
    comp = project.new_target(:app_extension, comp_name, :watchos, '10.0')
    puts "✓ 新建 widget extension target: #{comp_name}"
  else
    puts "• widget target 已存在,刷新源引用: #{comp_name}"
  end

  comp.build_configurations.each do |c|
    bs = c.build_settings
    bs['PRODUCT_BUNDLE_IDENTIFIER'] = "#{watch_bundle}.watchkitextension"
    bs['SDKROOT'] = 'watchos'
    bs['TARGETED_DEVICE_FAMILY'] = '4'
    bs['WATCHOS_DEPLOYMENT_TARGET'] = '10.0'
    bs['SWIFT_VERSION'] = '5.0'
    bs['GENERATE_INFOPLIST_FILE'] = 'NO'
    bs['INFOPLIST_FILE'] = "#{comp_name}/Info.plist"
    bs['PRODUCT_NAME'] = comp_name
    bs['MARKETING_VERSION'] = mv                              # 与主 app 一致,过 watchOS 版本校验
    bs['CURRENT_PROJECT_VERSION'] = cv
    bs['DEVELOPMENT_TEAM'] = team_id                          # 同 watch app:EAS 不注 team → 烤进工程
    bs['CODE_SIGN_STYLE'] = 'Automatic'
    bs['CODE_SIGN_ENTITLEMENTS'] = "#{comp_name}/RevaComplication.entitlements"
    bs.delete('CODE_SIGN_INJECT_BASE_ENTITLEMENTS')
  end

  comp_plist = File.join(comp_dir, 'Info.plist')
  ensure_plist_value(comp_plist, 'CFBundleDisplayName', '小巴健康')
  ensure_plist_value(comp_plist, 'CFBundleName', '小巴健康')

  cgroup = project.main_group.find_subpath(comp_name, true)
  cgroup.path = comp_name
  cgroup.set_source_tree('SOURCE_ROOT')
  cgroup.clear
  cexisting = comp.source_build_phase.files_references.map(&:real_path).map(&:to_s)
  Dir.glob(File.join(comp_dir, '*.swift')).sort.each do |f|
    ref = cgroup.new_file(File.basename(f))
    next if cexisting.include?(File.expand_path(f))
    comp.add_file_references([ref])
  end
  puts "✓ 已加 #{Dir.glob(File.join(comp_dir, '*.swift')).size} 个 widget swift 源"

  # 嵌入 watch app(Embed App Extensions copy phase)+ 依赖
  unless target.dependencies.any? { |d| d.display_name == comp_name }
    target.add_dependency(comp)
  end
  embed = target.copy_files_build_phases.find { |p| p.name == 'Embed Watch Extensions' }
  if embed.nil?
    embed = target.new_copy_files_build_phase('Embed Watch Extensions')
    embed.symbol_dst_subfolder_spec = :plug_ins
  end
  already = embed.files_references.map { |r| r.path }.compact
  unless already.include?(comp.product_reference.path)
    bf = embed.add_file_reference(comp.product_reference)
    bf.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
  end
  puts "✓ 已把 #{comp_name} 嵌入 #{watch_name}"
end

# ── iPhone WC bridge(加进主 app target,持 token 转发后端)──────────────
ios_root = File.dirname(proj_path)
bridge_src = File.expand_path('../../../../mobile/native/watch/WatchPhoneBridge.swift', __FILE__)
if File.exist?(bridge_src)
  main_target = main_t
  if main_target
    bridge_dir = File.join(ios_root, main_group_path, 'WatchBridge')
    FileUtils.mkdir_p(bridge_dir)
    dest = File.join(bridge_dir, 'WatchPhoneBridge.swift')
    FileUtils.cp(bridge_src, dest)
    bgroup = project.main_group.find_subpath("#{main_group_path}/WatchBridge", true)
    bgroup.path = "#{main_group_path}/WatchBridge"
    bgroup.set_source_tree('SOURCE_ROOT')
    main_refs = main_target.source_build_phase.files_references.map(&:real_path).map(&:to_s)
    unless main_refs.include?(File.expand_path(dest))
      main_target.add_file_references([bgroup.new_file(File.basename(dest))])
    end
    puts "✓ WatchPhoneBridge.swift 已加进主 target #{main_target.name}"

    # 把 watch app 嵌进 iOS app(否则 EAS 打的 iOS 包不含手表 App)+ iOS 依赖 watch
    unless main_target.dependencies.any? { |d| d.display_name == watch_name }
      main_target.add_dependency(target)
    end
    embed_watch = main_target.copy_files_build_phases.find { |p| p.name == 'Embed Watch Content' }
    if embed_watch.nil?
      embed_watch = main_target.new_copy_files_build_phase('Embed Watch Content')
      embed_watch.symbol_dst_subfolder_spec = :products_directory
      embed_watch.dst_path = '$(CONTENTS_FOLDER_PATH)/Watch'
    end
    w_already = embed_watch.files_references.map { |r| r.path }.compact
    unless w_already.include?(target.product_reference.path)
      wbf = embed_watch.add_file_reference(target.product_reference)
      wbf.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
    end
    puts "✓ 已把 #{watch_name} 嵌进 iOS app #{main_target.name}"
  end
end

# ── 防御:主工程里任何 resource bundle 类型 target 都设 CODE_SIGNING_ALLOWED=NO ──────────
# Xcode 14 起 resource bundle 默认要签名 → 无 team 时报 EAS #94。Pods 的 bundle 由 Expo
# post_install 已设 NO,但主工程若(将来 watch 引入)出现 bundle target 不会被 Pods 那段覆盖。
# resource bundle 本就不该签名(只是资源容器),统一设 NO,fail-safe 掉这层校验。
project.targets.each do |t|
  next unless t.respond_to?(:product_type) && t.product_type == 'com.apple.product-type.bundle'
  t.build_configurations.each { |c| c.build_settings['CODE_SIGNING_ALLOWED'] = 'NO' }
  puts "✓ resource bundle #{t.name} → CODE_SIGNING_ALLOWED=NO"
end

attrs = project.root_object.attributes['TargetAttributes'] ||= {}
[main_t, target, project.targets.find { |t| t.name == comp_name }].compact.each do |t|
  target_attrs = attrs[t.uuid] ||= {}
  target_attrs['DevelopmentTeam'] = team_id
  target_attrs['ProvisioningStyle'] = 'Automatic'
  target_attrs.delete('SystemCapabilities') if [watch_name, comp_name].include?(t.name)
end

[main_t, target, project.targets.find { |t| t.name == comp_name }].compact.each do |t|
  t.build_configurations.each do |c|
    bs = c.build_settings
    puts "• #{t.name}/#{c.name}: bundle=#{bs['PRODUCT_BUNDLE_IDENTIFIER']} entitlements=#{bs['CODE_SIGN_ENTITLEMENTS'] || '(none)'} profile=#{bs['PROVISIONING_PROFILE_SPECIFIER'] || '(auto)'}"
  end
end

project.save
puts "✓ 保存: #{proj_path}"
