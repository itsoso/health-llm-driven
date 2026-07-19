# frozen_string_literal: true

require "json"
require "fileutils"
require "minitest/autorun"
require "open3"
require "pathname"
require "tmpdir"
require "xcodeproj"

class GenerateFoodVisionDeviceHostTest < Minitest::Test
  MODULE_ROOT = Pathname(__dir__).join("../..").expand_path
  GENERATOR = MODULE_ROOT.join("scripts/generate_food_vision_device_host.rb")
  HOST_SOURCE = MODULE_ROOT.join("DeviceHost/LocalFoodVisionBenchmarkHostApp.swift")

  def test_generator_creates_isolated_ios16_host_with_only_authorized_resources
    with_assets do |model, label_bank, fixtures|
      Dir.mktmpdir("local-food-vision-host") do |directory|
        output = Pathname(directory).join("LocalFoodVisionBenchmarkHost.xcodeproj")
        stdout, stderr, status = run_generator(
          output: output,
          model: model,
          label_bank: label_bank,
          fixtures: fixtures
        )

        assert status.success?, "generator failed:\n#{stdout}\n#{stderr}"
        project = Xcodeproj::Project.open(output)
        target = project.targets.fetch(0)
        assert_equal "LocalFoodVisionBenchmarkHost", target.name
        assert_equal "com.apple.product-type.application", target.product_type
        assert_equal "16.0", target.build_configurations.fetch(0)
          .build_settings.fetch("IPHONEOS_DEPLOYMENT_TARGET")
        assert_equal "life.executor.health.local-food-vision-benchmark",
                     target.build_configurations.fetch(0)
                       .build_settings.fetch("PRODUCT_BUNDLE_IDENTIFIER")

        resources = target.resources_build_phase.files_references.map(&:display_name).sort
        assert_equal [
          "FakeChineseClip.mlpackage",
          "dataset-manifest.json",
          "fixture-001.png",
          "labels.bin",
        ], resources
        sources = target.source_build_phase.files_references.map(&:display_name)
        assert_includes sources, "LocalFoodVisionBenchmarkHostApp.swift"
        assert_includes sources, "LocalFoodVisionBenchmark.swift"
        assert_includes sources, "LocalChineseClipVisionEngine.swift"
      end
    end
  end

  def test_generator_rejects_relative_missing_private_unlicensed_and_traversing_assets
    output_root = Pathname(Dir.mktmpdir("food-host-invalid"))
    output = output_root.join("Host.xcodeproj")
    with_assets do |model, label_bank, fixtures|
      _, stderr, status = run_generator(
        output: output,
        model: Pathname("relative.mlpackage"),
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "absolute"

      manifest_path = fixtures.join("dataset-manifest.json")
      manifest = JSON.parse(manifest_path.read)
      manifest["containsPrivateUserData"] = true
      manifest_path.write(JSON.generate(manifest))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "private"

      manifest["containsPrivateUserData"] = false
      manifest["licenseStatus"] = "unknown"
      manifest_path.write(JSON.generate(manifest))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "license"

      manifest["licenseStatus"] = "licensed_for_evaluation"
      manifest["cases"][0]["file"] = "../outside.png"
      manifest_path.write(JSON.generate(manifest))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "inside"
    end
  ensure
    FileUtils.remove_entry(output_root) if output_root&.exist?
  end

  def test_host_has_explicit_switch_and_no_production_or_network_interfaces
    assert HOST_SOURCE.exist?, "missing host source: #{HOST_SOURCE}"
    source = HOST_SOURCE.read

    assert_includes source, "LOCAL_FOOD_VISION_BENCHMARK="
    refute_match(/HealthKit|URLSession|PHPhotoLibrary|DietRepository/, source)
  end

  private

  def with_assets
    asset_root = MODULE_ROOT.join(".build/generator-test-#{Process.pid}-#{rand(1_000_000)}")
    model = asset_root.join("FakeChineseClip.mlpackage")
    model.mkpath
    model.join("Manifest.json").write("{}")
    label_bank = asset_root.join("labels.bin")
    label_bank.write("labels")
    Dir.mktmpdir("authorized-food-fixtures") do |directory|
      fixtures = Pathname(directory)
      fixtures.join("fixture-001.png").binwrite("png")
      fixtures.join("dataset-manifest.json").write(
        JSON.generate(
          {
            schemaVersion: 1,
            name: "authorized-food-eval",
            version: "v1",
            licenseStatus: "licensed_for_evaluation",
            containsPrivateUserData: false,
            cases: [
              {
                caseId: "opaque-case-001",
                fixtureRef: "fixture-001",
                file: "fixture-001.png",
                expectedFoodIdentities: ["rice"],
                nonFood: false,
              },
            ],
          }
        )
      )
      yield model, label_bank, fixtures
    end
  ensure
    FileUtils.remove_entry(asset_root) if asset_root&.exist?
  end

  def run_generator(output:, model:, label_bank:, fixtures:)
    Open3.capture3(
      RbConfig.ruby,
      GENERATOR.to_s,
      "--output", output.to_s,
      "--team-id", "TESTTEAM123",
      "--model", model.to_s,
      "--label-bank", label_bank.to_s,
      "--fixtures", fixtures.to_s,
      "--fp16-delta", "0.01"
    )
  end
end
