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
  PINNED_MODEL_REVISION = "717ba215769231e53b9b7c6b9d329b9cc5944418"

  module_function

  def generate(module_root:, output:, model:, label_bank:, fixtures:, fp16_delta:, team_id: nil)
    module_root = module_root.realpath
    output = absolute_path(output, "output")
    model = verified_build_asset(model, module_root, "model")
    label_bank = verified_build_asset(label_bank, module_root, "label bank")
    fixtures = verified_directory(fixtures, "fixtures")
    raise "model must be a .mlpackage or .mlmodelc" unless %w[.mlpackage .mlmodelc].include?(model.extname)
    raise "label bank must be a .bin file" unless label_bank.file? && label_bank.extname == ".bin"

    manifest_path = fixtures.join("dataset-manifest.json")
    manifest, fixture_paths = validate_manifest(manifest_path, fixtures)
    precision = model.to_s.include?("fp16") ? "fp16" : "int8-linear-per-channel-65536"
    if precision != "fp16" && (!fp16_delta&.finite? || fp16_delta < -1 || fp16_delta > 1)
      raise "--fp16-delta between -1 and 1 is required for a compressed model"
    end

    generated_source = write_config_source(
      output: output,
      model: model,
      label_bank: label_bank,
      precision: precision,
      fp16_delta: fp16_delta,
      manifest: manifest
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

  def validate_manifest(path, fixtures)
    raise "missing fixture manifest: #{path}" unless path.file?

    manifest = JSON.parse(path.read)
    raise "fixture manifest schemaVersion must equal 1" unless manifest["schemaVersion"] == 1
    raise "fixture manifest contains private user data" unless manifest["containsPrivateUserData"] == false
    raise "fixture manifest license is not authorized" unless ALLOWED_LICENSES.include?(manifest["licenseStatus"])
    raise "fixture manifest cases must be non-empty" unless manifest["cases"].is_a?(Array) && !manifest["cases"].empty?

    case_ids = []
    fixture_paths = manifest["cases"].map do |item|
      raise "fixture case must be an object" unless item.is_a?(Hash)
      case_id = item["caseId"]
      raise "fixture caseId must be unique and non-empty" unless case_id.is_a?(String) && !case_id.empty? && !case_ids.include?(case_id)
      case_ids << case_id
      relative = Pathname(item.fetch("file"))
      raise "fixture file must be a relative path inside fixtures" if relative.absolute?
      path = fixtures.join(relative).cleanpath
      raise "fixture file must remain inside fixtures" unless inside?(path, fixtures)
      raise "missing fixture file: #{relative}" unless path.file?
      real = path.realpath
      raise "fixture file must remain inside fixtures" unless inside?(real, fixtures)

      real
    rescue KeyError
      raise "fixture case file is required"
    end
    [manifest, fixture_paths]
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

  def write_config_source(output:, model:, label_bank:, precision:, fp16_delta:, manifest:)
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
          static let fp16ToCompressedIdentityPrecisionDelta: Double? = #{fp16_delta.nil? ? "nil" : fp16_delta}
          static let datasetName = #{manifest.fetch("name").to_s.dump}
          static let datasetVersion = #{manifest.fetch("version").to_s.dump}
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
    parser.on("--fp16-delta VALUE", Float) { |value| options[:fp16_delta] = value }
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
      fp16_delta: options[:fp16_delta],
      team_id: options[:team_id]
    )
    puts output
  rescue StandardError => error
    warn error.message
    exit 1
  end
end
