import AppKit
import Observation
import ScreenCaptureKit
import Vision

enum ShoppingWindowMirrorError: LocalizedError {
    case windowUnavailable, notShoppingPage, captureFailed
    var errorDescription: String? {
        switch self {
        case .windowUnavailable: "未找到唯一可见的快手主窗口。请打开购物助手，保持窗口未最小化，再重新显示。"
        case .notShoppingPage: "快手窗口已离开购物助手或标题无法识别，已停止显示。请回到购物页后重新连接。"
        case .captureFailed: "快手画面读取失败，已停止显示。请检查屏幕录制权限和快手窗口后重试。"
        }
    }
}

/// Transient, read-only window preview. Never imports pixels into the shopping
/// transcript, saves them to disk, uploads them, or labels them as a new answer.
@MainActor @Observable final class ShoppingWindowMirror {
    private(set) var image: CGImage?
    private(set) var isActive = false
    private(set) var notice: String?
    private var generation = UUID()
    private var task: Task<Void, Never>?
    private let permission: () -> Bool
    private let capture: () async throws -> CGImage

    init(permission: @escaping () -> Bool = {
        CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess()
    }, capture: (() async throws -> CGImage)? = nil) {
        self.permission = permission
        if let capture { self.capture = capture }
        else { self.capture = { try await ShoppingWindowCapture.capture() } }
    }

    func start(isCurrent: @escaping () -> Bool = { true }) {
        stop()
        guard isCurrent() else { return }
        guard permission() else {
            notice = "需要在系统设置 → 隐私与安全性 → 屏幕与系统音频录制中允许小巴。授权后重新打开小巴，再点击显示。"
            return
        }
        isActive = true
        notice = "正在读取快手购物窗口…"
        let current = generation
        task = Task { [weak self] in
            // Bounded preview: no unattended background monitoring.
            for _ in 0..<120 {
                guard let self, self.generation == current, !Task.isCancelled else { return }
                guard isCurrent() else { self.stop(); return }
                do {
                    let frame = try await self.capture()
                    guard self.generation == current, !Task.isCancelled else { return }
                    guard isCurrent() else { self.stop(); return }
                    self.image = frame
                    self.notice = nil
                    try await Task.sleep(for: .seconds(1.5))
                } catch {
                    guard self.generation == current, !Task.isCancelled else { return }
                    self.stop()
                    self.notice = (error as? ShoppingWindowMirrorError)?.localizedDescription
                        ?? ShoppingWindowMirrorError.captureFailed.localizedDescription
                    return
                }
            }
            guard let self, self.generation == current else { return }
            self.stop()
            self.notice = "本次窗口显示已结束。需要继续查看时可重新连接。"
        }
    }

    func stop() {
        generation = UUID()
        task?.cancel()
        task = nil
        isActive = false
        image = nil
        notice = nil
    }
}

enum ShoppingWindowCapture {
    static func isShoppingHeading(_ text: String, confidence: Float) -> Bool {
        // Vision reports 0.5 for the verified mixed Latin/Chinese heading on
        // this app. Exact text and the physically cropped header remain required.
        confidence >= 0.5 && text.filter { !$0.isWhitespace }.uppercased() == "AI购物助手"
    }

    static func eligible(bundleID: String?, layer: Int, onScreen: Bool, width: Double, height: Double) -> Bool {
        bundleID == "com.jiangjia.gif" && layer == 0 && onScreen && width > 200 && height > 300
    }

    @MainActor static func capture() async throws -> CGImage {
        guard CGPreflightScreenCaptureAccess() else { throw ShoppingWindowMirrorError.captureFailed }
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        let windows = content.windows.filter {
            eligible(bundleID: $0.owningApplication?.bundleIdentifier, layer: $0.windowLayer,
                     onScreen: $0.isOnScreen, width: $0.frame.width, height: $0.frame.height)
        }
        guard windows.count == 1, let window = windows.first else { throw ShoppingWindowMirrorError.windowUnavailable }
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        let size = filter.contentRect.size
        let scale = min(Double(filter.pointPixelScale), 2160 / max(size.width, size.height))
        configuration.width = max(1, Int(size.width * scale))
        configuration.height = max(1, Int(size.height * scale))
        configuration.scalesToFit = true
        configuration.ignoreShadowsSingleWindow = true
        configuration.showsCursor = false
        configuration.capturesAudio = false
        let frame = try await SCScreenshotManager.captureImage(
            contentFilter: filter, configuration: configuration)
        // OCR only the fixed page heading, never the reply or account information.
        // A changed app page must not be silently mirrored into the shopping pane.
        let shoppingPage = try await Task.detached(priority: .utility) {
            // Physically crop before Vision: recognition must never receive the
            // chat body. ROI alone does not reliably exclude outside results.
            guard let headingImage = frame.cropping(to: CGRect(
                x: Double(frame.width) * 0.25, y: Double(frame.height) * 0.03,
                width: Double(frame.width) * 0.5, height: Double(frame.height) * 0.075)) else { return false }
            let request = VNRecognizeTextRequest()
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.recognitionLevel = .accurate
            request.customWords = ["AI购物助手"]
            try VNImageRequestHandler(cgImage: headingImage).perform([request])
            return (request.results ?? []).contains { observation in
                guard let heading = observation.topCandidates(1).first else { return false }
                return isShoppingHeading(heading.string, confidence: heading.confidence)
            }
        }.value
        guard shoppingPage else { throw ShoppingWindowMirrorError.notShoppingPage }
        return frame
    }
}
