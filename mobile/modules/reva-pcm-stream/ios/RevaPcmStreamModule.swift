import AVFoundation
import ExpoModulesCore
import Foundation

public final class RevaPcmStreamModule: Module {
  private let audioEngine = AVAudioEngine()
  private let stateQueue = DispatchQueue(label: "life.executor.health.pcm-stream")
  private var converter: AVAudioConverter?
  private var running = false

  public func definition() -> ModuleDefinition {
    Name("RevaPcmStream")
    Events("onPcmChunk")

    AsyncFunction("start") { (promise: Promise) in
      self.requestMicrophonePermission { granted in
        guard granted else {
          promise.reject("MICROPHONE_PERMISSION_DENIED", "需要麦克风权限才能使用语音输入")
          return
        }
        self.stateQueue.async {
          do {
            try self.startCapture()
            promise.resolve(nil)
          } catch {
            self.stopCapture()
            promise.reject("PCM_CAPTURE_START_FAILED", error.localizedDescription)
          }
        }
      }
    }

    AsyncFunction("stop") {
      self.stateQueue.sync {
        self.stopCapture()
      }
    }

    AsyncFunction("cancel") {
      self.stateQueue.sync {
        self.stopCapture()
      }
    }

    OnDestroy {
      self.stateQueue.sync {
        self.stopCapture()
      }
    }
  }

  private func requestMicrophonePermission(completion: @escaping (Bool) -> Void) {
    if #available(iOS 17.0, *) {
      AVAudioApplication.requestRecordPermission(completionHandler: completion)
    } else {
      AVAudioSession.sharedInstance().requestRecordPermission(completion)
    }
  }

  private func startCapture() throws {
    guard !running else { return }

    let session = AVAudioSession.sharedInstance()
    try session.setCategory(.record, mode: .measurement, options: [])
    try session.setPreferredSampleRate(16000)
    try session.setPreferredIOBufferDuration(0.04)
    try session.setActive(true, options: [])

    let inputNode = audioEngine.inputNode
    let sourceFormat = inputNode.outputFormat(forBus: 0)
    guard sourceFormat.sampleRate > 0, sourceFormat.channelCount > 0 else {
      throw NSError(
        domain: "RevaPcmStream",
        code: 1,
        userInfo: [NSLocalizedDescriptionKey: "麦克风音频格式不可用"]
      )
    }
    guard let targetFormat = AVAudioFormat(
      commonFormat: .pcmFormatInt16,
      sampleRate: 16000,
      channels: 1,
      interleaved: true
    ), let converter = AVAudioConverter(from: sourceFormat, to: targetFormat) else {
      throw NSError(
        domain: "RevaPcmStream",
        code: 2,
        userInfo: [NSLocalizedDescriptionKey: "无法初始化语音音频转换器"]
      )
    }
    self.converter = converter

    inputNode.installTap(onBus: 0, bufferSize: 2048, format: sourceFormat) { [weak self] buffer, _ in
      self?.emitConvertedBuffer(buffer, targetFormat: targetFormat)
    }
    audioEngine.prepare()
    try audioEngine.start()
    running = true
  }

  private func emitConvertedBuffer(_ source: AVAudioPCMBuffer, targetFormat: AVAudioFormat) {
    guard let converter else { return }
    let ratio = targetFormat.sampleRate / source.format.sampleRate
    let capacity = AVAudioFrameCount(max(1, ceil(Double(source.frameLength) * ratio) + 8))
    guard let converted = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else {
      return
    }

    var suppliedInput = false
    var conversionError: NSError?
    let status = converter.convert(to: converted, error: &conversionError) { _, outputStatus in
      if suppliedInput {
        outputStatus.pointee = .noDataNow
        return nil
      }
      suppliedInput = true
      outputStatus.pointee = .haveData
      return source
    }
    guard conversionError == nil,
          status != .error,
          converted.frameLength > 0,
          let samples = converted.int16ChannelData?[0] else {
      return
    }

    let byteCount = Int(converted.frameLength) * MemoryLayout<Int16>.size
    let data = Data(bytes: samples, count: byteCount)
    let level = normalizedLevel(source)
    sendEvent("onPcmChunk", [
      "audioBase64": data.base64EncodedString(),
      "level": level,
    ])
  }

  private func normalizedLevel(_ buffer: AVAudioPCMBuffer) -> Double {
    guard let channels = buffer.floatChannelData, buffer.frameLength > 0 else { return 0 }
    let samples = channels[0]
    var sum: Float = 0
    for index in 0..<Int(buffer.frameLength) {
      let value = samples[index]
      sum += value * value
    }
    let rms = sqrt(sum / Float(buffer.frameLength))
    return Double(min(1, max(0, rms * 8)))
  }

  private func stopCapture() {
    if running {
      audioEngine.inputNode.removeTap(onBus: 0)
      audioEngine.stop()
    }
    running = false
    converter = nil
    do {
      try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    } catch {
      // The capture is already stopped; the next audio-session owner can still activate normally.
    }
  }
}
