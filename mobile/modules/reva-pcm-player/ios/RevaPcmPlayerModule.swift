import AVFoundation
import ExpoModulesCore
import Foundation

public final class RevaPcmPlayerModule: Module {
  private let audioEngine = AVAudioEngine()
  private let playerNode = AVAudioPlayerNode()
  private let stateQueue = DispatchQueue(label: "life.executor.health.pcm-player")
  private var audioFormat: AVAudioFormat?
  private var configured = false
  private var running = false
  private var finishRequested = false
  private var pendingBuffers = 0
  private var generation = 0

  public func definition() -> ModuleDefinition {
    Name("RevaPcmPlayer")
    Events("onPlaybackDrained", "onPlaybackError")

    AsyncFunction("start") { (sampleRate: Double, promise: Promise) in
      self.stateQueue.async {
        do {
          try self.startPlayback(sampleRate: sampleRate)
          promise.resolve(nil)
        } catch {
          self.stopPlayback()
          promise.reject("PCM_PLAYBACK_START_FAILED", error.localizedDescription)
        }
      }
    }

    AsyncFunction("enqueue") { (audioBase64: String, promise: Promise) in
      self.stateQueue.async {
        do {
          try self.enqueue(audioBase64: audioBase64)
          promise.resolve(nil)
        } catch {
          self.sendEvent("onPlaybackError", ["message": error.localizedDescription])
          promise.reject("PCM_PLAYBACK_ENQUEUE_FAILED", error.localizedDescription)
        }
      }
    }

    AsyncFunction("finish") {
      self.stateQueue.async {
        self.finishRequested = true
        self.completeIfDrained()
      }
    }

    AsyncFunction("stop") {
      self.stateQueue.sync {
        self.stopPlayback()
      }
    }

    OnDestroy {
      self.stateQueue.sync {
        self.stopPlayback()
      }
    }
  }

  private func startPlayback(sampleRate: Double) throws {
    guard !running else { return }
    guard sampleRate == 24000,
          let format = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 24000,
            channels: 1,
            interleaved: false
          ) else {
      throw NSError(
        domain: "RevaPcmPlayer",
        code: 1,
        userInfo: [NSLocalizedDescriptionKey: "不支持的流式音频格式"]
      )
    }

    let session = AVAudioSession.sharedInstance()
    try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
    try session.setPreferredSampleRate(24000)
    try session.setPreferredIOBufferDuration(0.02)
    try session.setActive(true, options: [])

    if !configured {
      audioEngine.attach(playerNode)
      audioEngine.connect(playerNode, to: audioEngine.mainMixerNode, format: format)
      configured = true
    }
    audioFormat = format
    finishRequested = false
    pendingBuffers = 0
    generation += 1
    audioEngine.prepare()
    try audioEngine.start()
    playerNode.play()
    running = true
  }

  private func enqueue(audioBase64: String) throws {
    guard running, let format = audioFormat else {
      throw NSError(
        domain: "RevaPcmPlayer",
        code: 2,
        userInfo: [NSLocalizedDescriptionKey: "流式音频播放器尚未启动"]
      )
    }
    guard let data = Data(base64Encoded: audioBase64), !data.isEmpty, data.count % 2 == 0 else {
      throw NSError(
        domain: "RevaPcmPlayer",
        code: 3,
        userInfo: [NSLocalizedDescriptionKey: "流式音频分片无效"]
      )
    }

    let frameCount = AVAudioFrameCount(data.count / MemoryLayout<Int16>.size)
    guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount),
          let destination = buffer.int16ChannelData?[0] else {
      throw NSError(
        domain: "RevaPcmPlayer",
        code: 4,
        userInfo: [NSLocalizedDescriptionKey: "无法分配流式音频缓冲区"]
      )
    }
    buffer.frameLength = frameCount
    data.copyBytes(to: UnsafeMutableRawBufferPointer(
      start: destination,
      count: data.count
    ))

    let scheduledGeneration = generation
    pendingBuffers += 1
    playerNode.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
      guard let self else { return }
      self.stateQueue.async {
        guard self.running, self.generation == scheduledGeneration else { return }
        self.pendingBuffers = max(0, self.pendingBuffers - 1)
        self.completeIfDrained()
      }
    }
    if !playerNode.isPlaying {
      playerNode.play()
    }
  }

  private func completeIfDrained() {
    guard running, finishRequested, pendingBuffers == 0 else { return }
    sendEvent("onPlaybackDrained", [:])
    stopPlayback()
  }

  private func stopPlayback() {
    generation += 1
    finishRequested = false
    pendingBuffers = 0
    if configured {
      playerNode.stop()
      playerNode.reset()
    }
    if audioEngine.isRunning {
      audioEngine.stop()
    }
    running = false
    audioFormat = nil
    do {
      try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    } catch {
      // Playback is already stopped; the next audio-session owner can still activate normally.
    }
  }
}
