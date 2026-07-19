#!/usr/bin/env ruby
# frozen_string_literal: true

require "digest"
require "json"
require "optparse"
require "pathname"
require "xcodeproj"

module LocalFoodVisionDeviceHost
  TARGET_NAME = "LocalFoodVisionBenchmarkHost"
  BUNDLE_IDENTIFIER = "life.executor.health.local-food-vision-benchmark"
  ALLOWED_LICENSES = %w[licensed_for_evaluation public_domain synthetic].freeze
  ALLOWED_SPLITS = %w[calibration test].freeze
  REQUIRED_STRATA = %w[
    single_item composite_dish mixed_plate packaged_food_drink confusable_pair
    non_food_adversarial degraded_adversarial
  ].freeze
  MINIMUM_CASES = 300
  OPAQUE_CASE_ID = /\Acase-[a-z0-9][a-z0-9_-]*\z/
  OPAQUE_FIXTURE_ID = /\Afixture-[a-z0-9][a-z0-9_-]*\z/
  PINNED_MODEL_REVISION = "717ba215769231e53b9b7c6b9d329b9cc5944418"

  module_function

  def generate(
    module_root:, output:, model:, label_bank:, fixtures:, compile_only:, exploratory:,
    calibration_manifest: nil, team_id: nil
  )
    module_root = module_root.realpath
    output = absolute_path(output, "output")
    model = verified_build_asset(model, module_root, "model")
    label_bank = verified_build_asset(label_bank, module_root, "label bank")
    fixtures = verified_directory(fixtures, "fixtures")
    raise "model must be a .mlpackage or .mlmodelc" unless %w[.mlpackage .mlmodelc].include?(model.extname)
    raise "label bank must be a .bin file" unless label_bank.file? && label_bank.extname == ".bin"

    manifest_path = fixtures.join("dataset-manifest.json")
    manifest, fixture_paths = validate_manifest(
      manifest_path,
      fixtures,
      exploratory: exploratory
    )
    calibration = validate_calibration(
      calibration_manifest,
      manifest,
      compile_only: compile_only,
      exploratory: exploratory
    )
    precision = model.to_s.include?("fp16") ? "fp16" : "int8-linear-per-channel-65536"

    generated_source = write_config_source(
      output: output,
      model: model,
      label_bank: label_bank,
      precision: precision,
      manifest: manifest,
      calibration: calibration
    )
    project = Xcodeproj::Project.new(output)
    target = project.new_target(:application, TARGET_NAME, :ios, "16.0")
    source_group = project.main_group.new_group("Sources")
    resource_group = project.main_group.new_group("Resources")
    source_paths = [
      module_root.join("DeviceHost/LocalFoodVisionBenchmarkHostApp.swift"),
      module_root.join("ios/LocalDietInferenceBenchmark.swift"),
      module_root.join("ios/LocalHealthCapabilityProbe.swift"),
      module_root.join("ios/LocalFoodVisionTypes.swift"),
      module_root.join("ios/LocalFoodCandidateRanker.swift"),
      module_root.join("ios/LocalFoodVisionPreprocessor.swift"),
      module_root.join("ios/LocalChineseClipVisionEngine.swift"),
      module_root.join("ios/LocalFoodVisionBenchmark.swift"),
      generated_source,
    ]
    source_references = source_paths.map do |path|
      raise "missing source: #{path}" unless path.exist?

      source_group.new_file(path.to_s)
    end
    target.add_file_references(source_references)

    resource_paths = [model, label_bank, manifest_path, *fixture_paths]
    resource_references = resource_paths.map { |path| resource_group.new_file(path.to_s) }
    target.add_resources(resource_references)

    target.build_configurations.each do |configuration|
      settings = configuration.build_settings
      settings["CODE_SIGN_STYLE"] = "Automatic"
      settings["DEVELOPMENT_TEAM"] = team_id if team_id && !team_id.empty?
      settings["GENERATE_INFOPLIST_FILE"] = "YES"
      settings["INFOPLIST_KEY_CFBundleDisplayName"] = "Local Food Vision Benchmark"
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

  def absolute_path(value, name)
    path = Pathname(value)
    raise "#{name} path must be absolute" unless path.absolute?

    path.expand_path
  end

  def verified_build_asset(value, module_root, name)
    path = absolute_path(value, name)
    raise "missing #{name}: #{path}" unless path.exist?

    real = path.realpath
    build_root = module_root.join(".build").realpath
    raise "#{name} must remain inside #{build_root}" unless inside?(real, build_root)

    real
  end

  def verified_directory(value, name)
    path = absolute_path(value, name)
    raise "missing #{name}: #{path}" unless path.directory?

    path.realpath
  end

  def validate_manifest(path, fixtures, exploratory: false)
    raise "missing fixture manifest: #{path}" unless path.file?

    manifest = JSON.parse(path.read)
    expected_top_keys = %w[schemaVersion datasetVersion containsPrivateUserData cases]
    raise "fixture manifest keys are invalid" unless manifest.keys.sort == expected_top_keys.sort
    raise "fixture manifest schemaVersion must equal 2" unless manifest["schemaVersion"] == 2
    unless manifest["datasetVersion"].is_a?(String) && !manifest["datasetVersion"].empty?
      raise "fixture manifest datasetVersion must be non-empty"
    end
    raise "fixture manifest contains private user data" unless manifest["containsPrivateUserData"] == false
    minimum_cases = exploratory ? 1 : MINIMUM_CASES
    unless manifest["cases"].is_a?(Array) && manifest["cases"].length >= minimum_cases
      raise "fixture manifest requires at least #{minimum_cases} cases"
    end

    case_ids = []
    fixture_ids = []
    strata = []
    splits = []
    fixture_paths = manifest["cases"].map do |item|
      raise "fixture case must be an object" unless item.is_a?(Hash)
      expected_case_keys = %w[
        caseId fixtureId file split stratum licenseStatus expectedFoodIdentities
        allowedAliases nonFood
      ]
      raise "fixture case keys are invalid" unless item.keys.sort == expected_case_keys.sort
      case_id = item["caseId"]
      fixture_id = item["fixtureId"]
      unless case_id.is_a?(String) && OPAQUE_CASE_ID.match?(case_id) && !case_ids.include?(case_id)
        raise "fixture caseId must be unique and opaque"
      end
      unless fixture_id.is_a?(String) && OPAQUE_FIXTURE_ID.match?(fixture_id) && !fixture_ids.include?(fixture_id)
        raise "fixture fixtureId must be unique and opaque"
      end
      case_ids << case_id
      fixture_ids << fixture_id
      split = item["split"]
      stratum = item["stratum"]
      raise "fixture split is invalid" unless ALLOWED_SPLITS.include?(split)
      raise "fixture stratum is invalid" unless REQUIRED_STRATA.include?(stratum)
      raise "fixture case license is not authorized" unless ALLOWED_LICENSES.include?(item["licenseStatus"])
      splits << split
      strata << stratum
      expected = item["expectedFoodIdentities"]
      unless expected.is_a?(Array) && expected.uniq.length == expected.length &&
             expected.all? { |value| value.is_a?(String) && !value.empty? }
        raise "fixture expectedFoodIdentities is invalid"
      end
      raise "fixture allowedAliases must be an object" unless item["allowedAliases"].is_a?(Hash)
      raise "fixture nonFood must be boolean" unless [true, false].include?(item["nonFood"])
      raise "non-food fixture cannot expect food identities" if item["nonFood"] && !expected.empty?
      if stratum == "mixed_plate" && expected.length < 2
        raise "mixed_plate fixture requires at least two identities"
      end
      relative = Pathname(item.fetch("file"))
      raise "fixture file must be a relative path inside fixtures" if relative.absolute?
      path = fixtures.join(relative).cleanpath
      raise "fixture file must remain inside fixtures" unless inside?(path, fixtures)
      raise "missing fixture file: #{relative}" unless path.file?
      real = path.realpath
      raise "fixture file must remain inside fixtures" unless inside?(real, fixtures)

      split == "test" ? real : nil
    rescue KeyError
      raise "fixture case file is required"
    end
    if exploratory
      raise "exploratory fixtures must use only the test split" unless splits.uniq == ["test"]
    else
      missing_strata = REQUIRED_STRATA - strata.uniq
      raise "fixture manifest is missing strata: #{missing_strata.sort}" unless missing_strata.empty?
      raise "fixture manifest requires calibration and test splits" unless splits.uniq.sort == ALLOWED_SPLITS.sort
    end
    [manifest, fixture_paths.compact]
  rescue JSON::ParserError => error
    raise "invalid fixture manifest: #{error.message}"
  end

  def inside?(path, root)
    path == root || path.to_s.start_with?("#{root}#{File::SEPARATOR}")
  end

  def artifact_hash(path)
    digest = Digest::SHA256.new
    if path.file?
      File.open(path, "rb") { |file| IO.copy_stream(file, digest) }
    else
      path.glob("**/*").select(&:file?).sort.each do |item|
        digest.update(item.relative_path_from(path).to_s)
        digest.update("\0")
        File.open(item, "rb") { |file| digest.update(file.read(1_048_576)) until file.eof? }
      end
    end
    digest.hexdigest
  end

  def byte_count(path)
    return path.size if path.file?

    path.glob("**/*").select(&:file?).sum(&:size)
  end

  def aggregate_license(manifest)
    licenses = manifest.fetch("cases").map { |item| item.fetch("licenseStatus") }.uniq
    return licenses.first if licenses.length == 1
    return "licensed_for_evaluation" if licenses.include?("licensed_for_evaluation")
    return "public_domain" if licenses.include?("public_domain")

    "synthetic"
  end

  def split_hash(manifest, split)
    ids = manifest.fetch("cases")
      .select { |item| item.fetch("split") == split }
      .map { |item| item.fetch("caseId") }
      .sort
    Digest::SHA256.hexdigest(ids.map { |case_id| "#{case_id}\n" }.join)
  end

  def validate_calibration(value, manifest, compile_only:, exploratory: false)
    if exploratory
      raise "--exploratory cannot be combined with --compile-only" if compile_only
      raise "--exploratory cannot be combined with --calibration-manifest" if value

      return {
        "calibrationVersion" => "exploratory-uncalibrated-v1",
        "selectedThresholds" => {"minimumScore" => -1.0, "minimumMargin" => 0.0},
        "maximumCandidates" => 3,
        "evidenceCollectionEnabled" => false,
        "runMode" => "exploratory",
        "sha256" => nil,
      }
    end
    if compile_only
      raise "--compile-only cannot be combined with --calibration-manifest" if value

      return {
        "calibrationVersion" => "cn-clip-calibration-v2",
        "selectedThresholds" => {"minimumScore" => 0.5, "minimumMargin" => 0.03},
        "maximumCandidates" => 3,
        "evidenceCollectionEnabled" => false,
        "runMode" => "compile_only",
        "sha256" => nil,
      }
    end
    raise "--calibration-manifest is required unless --compile-only is set" unless value

    path = absolute_path(value, "calibration manifest")
    raise "missing calibration manifest: #{path}" unless path.file?
    calibration = JSON.parse(path.read)
    raise "calibration manifest must have pass status" unless calibration["status"] == "pass"
    unless calibration["calibrationVersion"] == "cn-clip-calibration-v2" &&
           calibration["modelRevision"] == PINNED_MODEL_REVISION &&
           calibration["labelSetVersion"] == "cn-food-labels-v2"
      raise "calibration provenance does not match the host"
    end
    thresholds = calibration["selectedThresholds"]
    floor = calibration["rankingPolicyFloor"]
    unless thresholds.is_a?(Hash) && floor == {
      "minimumScore" => 0.5,
      "minimumMargin" => 0.03,
      "maximumCandidates" => 3,
    }
      raise "calibration thresholds are invalid"
    end
    score = thresholds["minimumScore"]
    margin = thresholds["minimumMargin"]
    unless score.is_a?(Numeric) && score.finite? && score >= 0.5 &&
           margin.is_a?(Numeric) && margin.finite? && margin >= 0.03
      raise "calibration thresholds are below the frozen floor"
    end
    expected_splits = {
      "calibrationSplit" => {
        "caseCount" => manifest["cases"].count { |item| item["split"] == "calibration" },
        "caseIdsSha256" => split_hash(manifest, "calibration"),
      },
      "testSplit" => {
        "caseCount" => manifest["cases"].count { |item| item["split"] == "test" },
        "caseIdsSha256" => split_hash(manifest, "test"),
      },
    }
    expected_splits.each do |field, expected|
      raise "calibration #{field} does not match fixtures" unless calibration[field] == expected
    end
    {
      "calibrationVersion" => calibration["calibrationVersion"],
      "selectedThresholds" => thresholds,
      "maximumCandidates" => 3,
      "evidenceCollectionEnabled" => true,
      "runMode" => "evidence",
      "sha256" => Digest::SHA256.file(path).hexdigest,
    }
  rescue JSON::ParserError => error
    raise "invalid calibration manifest: #{error.message}"
  end

  def write_config_source(output:, model:, label_bank:, precision:, manifest:, calibration:)
    directory = output.dirname.join("Generated")
    directory.mkpath
    path = directory.join("LocalFoodVisionBenchmarkConfig.swift")
    source = <<~SWIFT
      import Foundation

      enum LocalFoodVisionBenchmarkConfig {
          static let modelBaseName = #{model.basename(model.extname).to_s.dump}
          static let modelArtifactSHA256 = #{artifact_hash(model).dump}
          static let modelRevision = #{PINNED_MODEL_REVISION.dump}
          static let sourceModelBytes = #{byte_count(model)}
          static let labelBankBaseName = #{label_bank.basename(label_bank.extname).to_s.dump}
          static let sourceLabelBankBytes = #{byte_count(label_bank)}
          static let precisionVariant = #{precision.dump}
          static let labelBankVersion = "cn-food-labels-v2"
          static let calibrationVersion = #{calibration.fetch("calibrationVersion").dump}
          static let calibrationManifestSHA256: String? = #{calibration["sha256"]&.dump || "nil"}
          static let minimumScore = #{calibration.fetch("selectedThresholds").fetch("minimumScore")}
          static let minimumMargin = #{calibration.fetch("selectedThresholds").fetch("minimumMargin")}
          static let maximumCandidates = #{calibration.fetch("maximumCandidates")}
          static let evidenceCollectionEnabled = #{calibration.fetch("evidenceCollectionEnabled")}
          static let runMode = #{calibration.fetch("runMode").dump}
          static let datasetName = #{(calibration.fetch("runMode") == "exploratory" ? "exploratory-chinese-food-eval" : "authorized-chinese-food-eval").dump}
          static let datasetVersion = #{manifest.fetch("datasetVersion").to_s.dump}
          static let datasetLicenseStatus = #{aggregate_license(manifest).dump}
      }
    SWIFT
    path.write(source)
    path
  end
end

if $PROGRAM_NAME == __FILE__
  options = {}
  OptionParser.new do |parser|
    parser.on("--output PATH") { |value| options[:output] = Pathname(value).expand_path }
    parser.on("--team-id TEAM_ID") { |value| options[:team_id] = value }
    parser.on("--model PATH") { |value| options[:model] = Pathname(value) }
    parser.on("--label-bank PATH") { |value| options[:label_bank] = Pathname(value) }
    parser.on("--fixtures PATH") { |value| options[:fixtures] = Pathname(value) }
    parser.on("--compile-only") { options[:compile_only] = true }
    parser.on("--exploratory") { options[:exploratory] = true }
    parser.on("--calibration-manifest PATH") do |value|
      options[:calibration_manifest] = Pathname(value)
    end
  end.parse!

  %i[output model label_bank fixtures].each do |name|
    abort "--#{name.to_s.tr("_", "-")} is required" unless options[name]
  end
  module_root = Pathname(__dir__).join("..").expand_path
  begin
    output = LocalFoodVisionDeviceHost.generate(
      module_root: module_root,
      output: options.fetch(:output),
      model: options.fetch(:model),
      label_bank: options.fetch(:label_bank),
      fixtures: options.fetch(:fixtures),
      compile_only: options.fetch(:compile_only, false),
      exploratory: options.fetch(:exploratory, false),
      calibration_manifest: options[:calibration_manifest],
      team_id: options[:team_id]
    )
    puts output
  rescue StandardError => error
    warn error.message
    exit 1
  end
end
