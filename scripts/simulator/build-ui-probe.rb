# Generates an isolated XCTest runner; never modifies the mobile native project.
require 'xcodeproj'
require 'fileutils'
root = File.expand_path(ARGV.fetch(0))
FileUtils.mkdir_p(root)
project = Xcodeproj::Project.new(File.join(root, 'SimulatorProbe.xcodeproj'))
target = project.new_target(:ui_test_bundle, 'SimulatorProbe', :ios, '16.0')
source = project.main_group.new_file(File.expand_path('LockedSimulatorTests.swift', __dir__))
target.source_build_phase.add_file_reference(source)
target.build_configurations.each do |config|
  config.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'life.executor.simulatorprobe'
  config.build_settings['GENERATE_INFOPLIST_FILE'] = 'YES'
  config.build_settings['SWIFT_VERSION'] = '5.0'
  config.build_settings['CODE_SIGNING_ALLOWED'] = 'NO'
end
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.add_test_target(target)
scheme.save_as(project.path, 'SimulatorProbe', true)
