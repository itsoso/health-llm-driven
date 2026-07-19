#!/usr/bin/env ruby
# frozen_string_literal: true

require "optparse"
require "pathname"
require "xcodeproj"

module LocalDietDeviceHost
  TARGET_NAME = "LocalDietBenchmarkHost"
  BUNDLE_IDENTIFIER = "life.executor.health.local-diet-benchmark"

  module_function

  def generate(module_root:, output:, team_id: nil)
    project = Xcodeproj::Project.new(output)
    target = project.new_target(:application, TARGET_NAME, :ios, "16.0")
    source_group = project.main_group.new_group("Sources")
    source_paths = [
      module_root.join("DeviceHost/LocalDietBenchmarkHostApp.swift"),
      module_root.join("ios/LocalDietInferenceBenchmark.swift"),
      module_root.join("ios/LocalHealthCapabilityProbe.swift"),
    ]

    source_references = source_paths.map do |path|
      raise "missing source: #{path}" unless path.exist?

      source_group.new_file(path.to_s)
    end
    target.add_file_references(source_references)

    target.build_configurations.each do |configuration|
      settings = configuration.build_settings
      settings["CODE_SIGN_STYLE"] = "Automatic"
      settings["DEVELOPMENT_TEAM"] = team_id if team_id && !team_id.empty?
      settings["GENERATE_INFOPLIST_FILE"] = "YES"
      settings["INFOPLIST_KEY_CFBundleDisplayName"] = "Local Diet Benchmark"
      settings["INFOPLIST_KEY_UILaunchScreen_Generation"] = "YES"
      settings["INFOPLIST_KEY_UIApplicationSceneManifest_Generation"] = "YES"
      settings["IPHONEOS_DEPLOYMENT_TARGET"] = "16.0"
      settings["PRODUCT_BUNDLE_IDENTIFIER"] = BUNDLE_IDENTIFIER
      settings["PRODUCT_NAME"] = "$(TARGET_NAME)"
      settings["SWIFT_VERSION"] = "6.0"
      settings["TARGETED_DEVICE_FAMILY"] = "1"
    end

    project.save
    output
  end
end

if $PROGRAM_NAME == __FILE__
  options = {}
  OptionParser.new do |parser|
    parser.on("--output PATH") { |value| options[:output] = Pathname(value).expand_path }
    parser.on("--team-id TEAM_ID") { |value| options[:team_id] = value }
  end.parse!

  abort "--output is required" unless options[:output]

  module_root = Pathname(__dir__).join("..").expand_path
  LocalDietDeviceHost.generate(
    module_root: module_root,
    output: options.fetch(:output),
    team_id: options[:team_id]
  )
  puts options.fetch(:output)
end
