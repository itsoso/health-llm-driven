# frozen_string_literal: true

require "minitest/autorun"
require "open3"
require "pathname"
require "tmpdir"
require "xcodeproj"

class GenerateDeviceHostTest < Minitest::Test
  MODULE_ROOT = Pathname(__dir__).join("../..").expand_path
  GENERATOR = MODULE_ROOT.join("scripts/generate_device_host.rb")
  HOST_SOURCE = MODULE_ROOT.join("DeviceHost/LocalDietBenchmarkHostApp.swift")

  def test_generator_creates_physical_ios_application_target
    assert GENERATOR.exist?, "missing generator: #{GENERATOR}"

    Dir.mktmpdir("local-diet-device-host") do |directory|
      output = Pathname(directory).join("LocalDietBenchmarkHost.xcodeproj")
      stdout, stderr, status = Open3.capture3(
        RbConfig.ruby,
        GENERATOR.to_s,
        "--output",
        output.to_s,
        "--team-id",
        "TESTTEAM123"
      )

      assert status.success?, "generator failed:\n#{stdout}\n#{stderr}"
      project = Xcodeproj::Project.open(output)
      target = project.targets.fetch(0)

      assert_equal "LocalDietBenchmarkHost", target.name
      assert_equal "com.apple.product-type.application", target.product_type
      assert_equal [
        "LocalDietBenchmarkHostApp.swift",
        "LocalDietInferenceBenchmark.swift",
        "LocalHealthCapabilityProbe.swift",
      ], target.source_build_phase.files_references.map(&:display_name).sort

      target.build_configurations.each do |configuration|
        settings = configuration.build_settings
        assert_equal "16.0", settings.fetch("IPHONEOS_DEPLOYMENT_TARGET")
        assert_equal "life.executor.health.local-diet-benchmark", settings.fetch("PRODUCT_BUNDLE_IDENTIFIER")
        assert_equal "TESTTEAM123", settings.fetch("DEVELOPMENT_TEAM")
        assert_equal "Automatic", settings.fetch("CODE_SIGN_STYLE")
      end
    end
  end

  def test_host_is_explicitly_synthetic_and_emits_machine_readable_report
    assert HOST_SOURCE.exist?, "missing host source: #{HOST_SOURCE}"
    source = HOST_SOURCE.read

    assert_includes source, "LocalDietLiveBenchmark.enableEnvironmentKey: \"1\""
    assert_includes source, "LOCAL_DIET_INFERENCE_BENCHMARK="
    refute_match(/HealthKit|PHPhotoLibrary|URLSession/, source)
  end
end
