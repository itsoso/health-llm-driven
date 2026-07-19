# frozen_string_literal: true

require "json"
require "digest"
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
  BLOCKED_CALIBRATION = MODULE_ROOT.join("model-manifests/chinese-clip-calibration-v2.json")
  STRATA = %w[
    single_item composite_dish mixed_plate packaged_food_drink confusable_pair
    non_food_adversarial degraded_adversarial
  ].freeze

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

        resources = target.resources_build_phase.files_references.map(&:display_name)
        assert_includes resources, "FakeChineseClip.mlpackage"
        assert_includes resources, "dataset-manifest.json"
        assert_includes resources, "fixture-001.png"
        assert_includes resources, "labels.bin"
        assert_equal 203, resources.length
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
      manifest["cases"][0]["licenseStatus"] = "unknown"
      manifest_path.write(JSON.generate(manifest))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "license"

      manifest["cases"][0]["licenseStatus"] = "synthetic"
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

  def test_generator_rejects_incomplete_dataset_and_free_delta_argument
    with_assets do |model, label_bank, fixtures|
      output = Pathname(Dir.mktmpdir("food-host-contract")).join("Host.xcodeproj")
      manifest_path = fixtures.join("dataset-manifest.json")
      manifest = JSON.parse(manifest_path.read)
      manifest["cases"] = manifest["cases"].first(299)
      manifest_path.write(JSON.generate(manifest))

      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "300"

      manifest_path.write(JSON.generate(dataset_manifest(fixtures)))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures,
        extra_args: ["--fp16-delta", "0.01"]
      )
      refute status.success?
      assert_includes stderr, "fp16-delta"
    ensure
      FileUtils.remove_entry(output.dirname) if output&.dirname&.exist?
    end
  end

  def test_generator_rejects_missing_strata_and_independent_splits
    with_assets do |model, label_bank, fixtures|
      output = Pathname(Dir.mktmpdir("food-host-structure")).join("Host.xcodeproj")
      manifest_path = fixtures.join("dataset-manifest.json")
      manifest = JSON.parse(manifest_path.read)
      manifest["cases"].each { |item| item["stratum"] = "single_item" }
      manifest_path.write(JSON.generate(manifest))

      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "missing strata"

      manifest = dataset_manifest(fixtures)
      manifest[:cases].each { |item| item[:split] = "test" }
      manifest_path.write(JSON.generate(manifest))
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures
      )
      refute status.success?
      assert_includes stderr, "calibration and test splits"
    ensure
      FileUtils.remove_entry(output.dirname) if output&.dirname&.exist?
    end
  end

  def test_evidence_host_rejects_blocked_calibration
    with_assets do |model, label_bank, fixtures|
      output = Pathname(Dir.mktmpdir("food-host-calibration")).join("Host.xcodeproj")
      _, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures,
        compile_only: false,
        extra_args: ["--calibration-manifest", BLOCKED_CALIBRATION.to_s]
      )

      refute status.success?
      assert_includes stderr, "pass status"
    ensure
      FileUtils.remove_entry(output.dirname) if output&.dirname&.exist?
    end
  end

  def test_evidence_host_embeds_only_frozen_calibration_thresholds
    with_assets do |model, label_bank, fixtures|
      output = Pathname(Dir.mktmpdir("food-host-calibrated")).join("Host.xcodeproj")
      manifest = JSON.parse(fixtures.join("dataset-manifest.json").read)
      calibration = fixtures.join("calibration.json")
      calibration.write(JSON.generate(passing_calibration(manifest)))

      stdout, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures,
        compile_only: false,
        extra_args: ["--calibration-manifest", calibration.to_s]
      )

      assert status.success?, "generator failed:\n#{stdout}\n#{stderr}"
      config = output.dirname.join("Generated/LocalFoodVisionBenchmarkConfig.swift").read
      assert_includes config, "static let evidenceCollectionEnabled = true"
      assert_includes config, "static let minimumScore = 0.5"
      assert_includes config, "static let minimumMargin = 0.03"
      calibration_sha256 = Digest::SHA256.file(calibration).hexdigest
      assert_includes config,
                      "static let calibrationManifestSHA256: String? = #{calibration_sha256.dump}"
    ensure
      FileUtils.remove_entry(output.dirname) if output&.dirname&.exist?
    end
  end

  def test_exploratory_host_accepts_a_small_non_private_dataset_without_calibration
    with_assets do |model, label_bank, fixtures|
      output = Pathname(Dir.mktmpdir("food-host-exploratory")).join("Host.xcodeproj")
      manifest_path = fixtures.join("dataset-manifest.json")
      manifest = JSON.parse(manifest_path.read)
      manifest["datasetVersion"] = "exploratory-food-v1"
      manifest["cases"] = [manifest.fetch("cases").fetch(0).merge("split" => "test")]
      manifest_path.write(JSON.generate(manifest))

      stdout, stderr, status = run_generator(
        output: output,
        model: model,
        label_bank: label_bank,
        fixtures: fixtures,
        compile_only: false,
        extra_args: ["--exploratory"]
      )

      assert status.success?, "generator failed:\n#{stdout}\n#{stderr}"
      config = output.dirname.join("Generated/LocalFoodVisionBenchmarkConfig.swift").read
      assert_includes config, 'static let runMode = "exploratory"'
      assert_includes config, "static let minimumScore = -1.0"
      assert_includes config, "static let minimumMargin = 0.0"
      assert_includes config, "static let calibrationManifestSHA256: String? = nil"
      assert_includes config, 'static let datasetName = "exploratory-chinese-food-eval"'
      project = Xcodeproj::Project.open(output)
      resources = project.targets.fetch(0).resources_build_phase.files_references.map(&:display_name)
      assert_includes resources, "fixture-000.png"
      assert_equal 4, resources.length
    ensure
      FileUtils.remove_entry(output.dirname) if output&.dirname&.exist?
    end
  end

  def test_host_has_explicit_switch_and_no_production_or_network_interfaces
    assert HOST_SOURCE.exist?, "missing host source: #{HOST_SOURCE}"
    source = HOST_SOURCE.read

    assert_includes source, "LOCAL_FOOD_VISION_BENCHMARK="
    assert_includes source, "LOCAL_FOOD_VISION_EXPLORATORY="
    assert_includes source, "let notForQualityGate = true"
    assert_includes source, "calibrationManifestSha256: calibrationManifestSHA256"
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
      300.times { |index| fixtures.join(format("fixture-%03d.png", index)).binwrite("png") }
      fixtures.join("dataset-manifest.json").write(JSON.generate(dataset_manifest(fixtures)))
      yield model, label_bank, fixtures
    end
  ensure
    FileUtils.remove_entry(asset_root) if asset_root&.exist?
  end

  def dataset_manifest(_fixtures)
    cases = 300.times.map do |index|
      stratum = STRATA[index % STRATA.length]
      non_food = stratum == "non_food_adversarial"
      expected = if non_food
                   []
                 elsif stratum == "mixed_plate"
                   %w[rice fish]
                 else
                   ["rice"]
                 end
      {
        caseId: format("case-%03d", index),
        fixtureId: format("fixture-%03d", index),
        file: format("fixture-%03d.png", index),
        split: index % 3 == 0 ? "calibration" : "test",
        stratum: stratum,
        licenseStatus: "synthetic",
        expectedFoodIdentities: expected,
        allowedAliases: {},
        nonFood: non_food,
      }
    end
    {
      schemaVersion: 2,
      datasetVersion: "authorized-food-eval-v2",
      containsPrivateUserData: false,
      cases: cases,
    }
  end

  def passing_calibration(manifest)
    calibration = manifest["cases"].select { |item| item["split"] == "calibration" }
    test = manifest["cases"].select { |item| item["split"] == "test" }
    {
      status: "pass",
      calibrationVersion: "cn-clip-calibration-v2",
      modelRevision: "717ba215769231e53b9b7c6b9d329b9cc5944418",
      labelSetVersion: "cn-food-labels-v2",
      selectedThresholds: {minimumScore: 0.5, minimumMargin: 0.03},
      rankingPolicyFloor: {
        minimumScore: 0.5,
        minimumMargin: 0.03,
        maximumCandidates: 3,
      },
      calibrationSplit: {
        caseCount: calibration.length,
        caseIdsSha256: case_ids_hash(calibration),
      },
      testSplit: {
        caseCount: test.length,
        caseIdsSha256: case_ids_hash(test),
      },
    }
  end

  def case_ids_hash(cases)
    value = cases.map { |item| item["caseId"] }.sort.map { |case_id| "#{case_id}\n" }.join
    Digest::SHA256.hexdigest(value)
  end

  def run_generator(output:, model:, label_bank:, fixtures:, compile_only: true, extra_args: [])
    mode_args = compile_only ? ["--compile-only"] : []
    Open3.capture3(
      RbConfig.ruby,
      GENERATOR.to_s,
      "--output", output.to_s,
      "--team-id", "TESTTEAM123",
      "--model", model.to_s,
      "--label-bank", label_bank.to_s,
      "--fixtures", fixtures.to_s,
      *mode_args,
      *extra_args
    )
  end
end
