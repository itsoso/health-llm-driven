require "fileutils"
require "pathname"
require "xcodeproj"

output_dir = Pathname.new(ARGV.fetch(0)).expand_path
source_path = Pathname.new(__dir__).join("XiaobaAcceptanceUITests.swift")
project_path = output_dir.join("XiaobaAcceptance.xcodeproj")
test_source_dir = output_dir.join("XiaobaAcceptanceUITests")
test_source_path = test_source_dir.join("XiaobaAcceptanceUITests.swift")

FileUtils.mkdir_p(test_source_dir)
FileUtils.cp(source_path, test_source_path)

project = Xcodeproj::Project.new(project_path.to_s)
target = project.new_target(
  :ui_test_bundle,
  "XiaobaAcceptanceUITests",
  :ios,
  "16.0"
)

source_group = project.main_group.new_group("XiaobaAcceptanceUITests")
source_ref = source_group.new_file("XiaobaAcceptanceUITests/XiaobaAcceptanceUITests.swift")
target.add_file_references([source_ref])

target.build_configurations.each do |config|
  config.build_settings["PRODUCT_BUNDLE_IDENTIFIER"] =
    "life.executor.health.releaseacceptance.xctrunner"
  config.build_settings["DEVELOPMENT_TEAM"] = "QA2U724DAN"
  config.build_settings["CODE_SIGN_STYLE"] = "Automatic"
  config.build_settings["SWIFT_VERSION"] = "5.0"
  config.build_settings["IPHONEOS_DEPLOYMENT_TARGET"] = "16.0"
  config.build_settings["GENERATE_INFOPLIST_FILE"] = "YES"
end

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.add_test_target(target)
scheme.save_as(project_path.to_s, "XiaobaAcceptanceUITests", true)

project.save
