import Foundation
import Observation

public enum ShoppingCredentialState: Equatable, Sendable {
    case notChecked, none, webOnly, serviceCandidate, serviceAccepted
}

public struct ShoppingQuestionSubmission {
    fileprivate let question: String
    fileprivate let generation: UUID
    fileprivate let ownerGeneration: UUID
}

@MainActor @Observable
public final class ShoppingChatViewModel {
    public let localBridge = ShoppingBridgeTransport()
    public var draft = ""
    public private(set) var transcript = ShoppingTranscript()
    public private(set) var suggestedQuestions: [String] = []
    public private(set) var notice: String?
    public private(set) var isBusy = false
    public private(set) var isDemo = false
    public private(set) var configuration: ShoppingConfiguration?
    public private(set) var credentialState: ShoppingCredentialState = .notChecked
    public private(set) var hasMoreHistory = true
    /// Shared by every Mac window. A logout invalidates pending identity lookups
    /// even if no lookup had completed yet.
    public private(set) var ownerGeneration = UUID()
    private var bridgeSessionSelected = false
    private var cursor = "0"
    private var owner: String?
    private var generation = UUID()
    /// Shared invalidation boundary for auxiliary views across all app windows.
    public var sessionGeneration: UUID { generation }
    private var credentialIdentity: [String]?
    private let credentials: any ShoppingCredentialSource
    private var service: (any ShoppingService)?
    private var operation: Task<Void, Never>?

    public init(credentials: any ShoppingCredentialSource, configuration: ShoppingConfiguration? = nil,
                service: (any ShoppingService)? = nil) {
        self.credentials = credentials
        self.configuration = configuration
        self.service = service ?? configuration.map { ShoppingClient(configuration: $0) }
        localBridge.onAccountChanged = { [weak self] in
            self?.invalidateOperation()
            self?.clearData()
            self?.notice = ShoppingBridgeError.authChanged.localizedDescription
        }
    }

    public var ownerIsBound: Bool { owner != nil }
    public var usesOfficialAppForSending: Bool {
        !isDemo && !localBridge.isReady && (bridgeSessionSelected || configuration == nil || service == nil ||
            (credentialState != .serviceCandidate && credentialState != .serviceAccepted))
    }

    public func prepareOfficialQuestion() -> ShoppingQuestionSubmission? {
        guard ownerIsBound, !isBusy, !localBridge.isActive, usesOfficialAppForSending,
              !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return ShoppingQuestionSubmission(question: draft, generation: generation, ownerGeneration: ownerGeneration)
    }

    public func validateOfficialQuestion(_ submission: ShoppingQuestionSubmission) -> String? {
        guard ownerIsBound, !isBusy, !localBridge.isActive, usesOfficialAppForSending,
              generation == submission.generation, ownerGeneration == submission.ownerGeneration,
              draft == submission.question else { return nil }
        return submission.question
    }
    public var canUseService: Bool {
        ownerIsBound && !isDemo && !bridgeSessionSelected && !localBridge.isActive && !isBusy && configuration != nil && service != nil
            && (credentialState == .serviceCandidate || credentialState == .serviceAccepted)
    }
    public var canSend: Bool {
        ownerIsBound && !isBusy && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (isDemo || localBridge.isReady || canUseService)
    }
    public var statusTitle: String {
        if isDemo { return "离线演示 · 示例内容" }
        if localBridge.isReady { return "本机快手已连接 · 回复显示在此" }
        if localBridge.isActive { return "等待快手桥接页确认" }
        if usesOfficialAppForSending { return "购物对话在快手客户端中进行" }
        switch credentialState {
        case .notChecked, .none: return "登录快手，开始购物对话"
        case .webOnly: return "已读取网页 Cookie，购物授权待确认"
        case .serviceCandidate: return "已发现购物凭据，等待服务验证"
        case .serviceAccepted: return "购物服务已连接"
        }
    }
    public var statusDetail: String {
        if isDemo { return "这里展示示例对话和商品，便于体验页面；不会发送请求或进行购买。" }
        if !ownerIsBound { return "正在确认小巴账号；确认后可使用独立购物会话。" }
        if localBridge.isActive { return localBridge.notice ?? "快手客户端需要保持运行；仅同步此次连接中主动发送的问题和回复。" }
        if usesOfficialAppForSending { return "在下方输入问题，点击“发送到快手”，由官方客户端提问并显示回复。小巴内嵌接口尚未接通。" }
        if configuration == nil { return "购物接入地址与授权方式正在确认。可以先登录官方网页，或查看离线演示。" }
        if credentialState == .webOnly { return "快手网页与购物服务使用的登录态不同。当前凭据不会被改写或跨域转发。" }
        return "购物仅使用此页面输入；登录与对话独立于健康数据，退出账号后清除本机内容。"
    }

    public func bindOwner(_ id: String?) {
        guard id == nil || owner != id else { return }
        ownerGeneration = UUID()
        logout()
        owner = id
    }

    @discardableResult public func resolveOwner(_ id: String?, generation: UUID) -> Bool {
        guard ownerGeneration == generation else { return false }
        bindOwner(id)
        return true
    }

    public func configure(_ configuration: ShoppingConfiguration) {
        guard ownerIsBound, self.configuration != configuration else { return }
        logout()
        self.configuration = configuration
        service = ShoppingClient(configuration: configuration)
        notice = "接入设置已应用，请重新登录快手并检查购物授权。"
    }

    public func logout() {
        bridgeSessionSelected = false
        localBridge.disconnect()
        invalidateOperation()
        clearData()
        isDemo = false
        credentialState = .notChecked
        credentialIdentity = nil
        credentials.reset()
    }

    public func prepareForLogin() {
        bridgeSessionSelected = false
        credentialIdentity = nil
        credentials.reset()
        localBridge.disconnect()
        invalidateOperation()
        clearData()
        credentialState = .notChecked
    }

    public func clearConversation() {
        invalidateOperation()
        clearData()
        notice = "本机对话已清空；服务端历史和会话仍保留。"
    }

    public func stop() {
        guard isBusy else { return }
        invalidateOperation()
        transcript.thinkingMessage = nil
        notice = "已停止接收；服务端任务是否取消尚未确认。"
    }

    public func setDemoMode(_ enabled: Bool) {
        guard ownerIsBound, isDemo != enabled else { return }
        localBridge.disconnect()
        invalidateOperation()
        clearData()
        isDemo = enabled
        if enabled {
            suggestedQuestions = ["找一个通勤用的保温杯", "比较一下这两款", "有什么适合送人的选择？"]
        }
    }

    public func refreshCredentials() async {
        guard ownerIsBound, !isBusy, !isDemo, !bridgeSessionSelected, !localBridge.isActive else { return }
        let token = generation
        let values = await credentials.cookies()
        guard token == generation, ownerIsBound, !isBusy, !isDemo, !bridgeSessionSelected, !localBridge.isActive else { return }
        acceptCredentialSnapshot(values)
    }

    public func send() async {
        guard canSend else { return }
        let content = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        if isDemo {
            draft = ""
            appendUser(content)
            appendDemoAnswer()
            return
        }
        if localBridge.isReady {
            await sendViaBridge(content)
            return
        }
        await run { cookies, service, token in
            self.draft = ""
            let messageID = self.appendUser(content)
            for try await frame in service.chat(content: content, messageID: messageID, globalParams: self.transcript.globalParams, cookies: cookies) {
                try self.check(token)
                let commands = try ShoppingFrameDecoder.decode(frame)
                for command in commands {
                    let notices = try self.transcript.apply(command)
                    if let first = notices.first { self.notice = first.message }
                }
                self.suggestedQuestions = Self.unique(self.transcript.messages.suffix(3).flatMap { $0.blocks.flatMap(\.suggestedQuestions) })
            }
            // Even a custom transport's clean EOF is not an upstream completion receipt.
            throw ShoppingClientError.completionUnconfirmed
        }
    }

    public func startLocalBridge() async throws -> ShoppingBridgePairing {
        guard ownerIsBound, !isDemo, !isBusy else { throw ShoppingBridgeError.unavailable }
        invalidateOperation()
        bridgeSessionSelected = true
        credentialState = .notChecked
        credentialIdentity = nil
        credentials.reset()
        // Never mix messages from two fast-changing Kuaishou identities.
        transcript = ShoppingTranscript()
        suggestedQuestions = []
        let token = generation
        let pairing = try await localBridge.start()
        do { try check(token) }
        catch {
            if localBridge.isCurrent(pairing) { localBridge.disconnect() }
            throw error
        }
        return pairing
    }

    public func disconnectLocalBridge() {
        invalidateOperation()
        localBridge.disconnect()
        transcript = ShoppingTranscript()
        suggestedQuestions = []
        notice = "本机连接已断开；停止接收不保证服务端任务取消。"
    }

    private func sendViaBridge(_ content: String) async {
        isBusy = true
        notice = nil
        let token = generation
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer {
                if token == self.generation {
                    self.isBusy = false
                    self.transcript.thinkingMessage = nil
                    self.operation = nil
                }
            }
            do {
                try self.check(token)
                let messageID = "mac-\(UUID().uuidString)"
                let stream = try self.localBridge.chat(content: content, messageID: messageID)
                self.draft = ""
                self.transcript.messages.append(.init(messageId: messageID, sender: "user", blocks: [
                    .init(moduleId: "text", type: "text", content: .object(["text": .string(content)]))
                ]))
                for try await frame in stream {
                    try self.check(token)
                    let command = try ShoppingFrameDecoder.decodeCommand(frame)
                    if let first = try self.transcript.apply(command).first { self.notice = first.message }
                    self.suggestedQuestions = Self.unique(self.transcript.messages.suffix(3).flatMap { $0.blocks.flatMap(\.suggestedQuestions) })
                }
                try self.check(token)
                self.notice = "已接收快手客户端本轮返回；服务端任务是否完整结束尚未确认。"
            } catch {
                guard token == self.generation, !Task.isCancelled else { return }
                self.localBridge.cancelRequest()
                self.notice = (error as? ShoppingBridgeError)?.localizedDescription
                    ?? (error as? ShoppingProtocolError)?.localizedDescription
                    ?? "购物回复未完成，请检查本机连接。"
            }
        }
        operation = task
        await task.value
    }

    public func load() async {
        await run { cookies, service, token in
            let data = try await service.load(cookies: cookies)
            try self.check(token)
            let response = try ShoppingFrameDecoder.decodeResponse(data)
            self.transcript = ShoppingTranscript(messages: Self.uniqueMessages(response.messages), globalParams: response.globalParams, sessionId: response.sessionId)
            self.suggestedQuestions = Self.unique(response.suggestedQuestions)
            self.updateCursor(response.pcursor)
            self.credentialState = .serviceAccepted
            self.notice = response.notices.first?.message
        }
    }

    public func loadHistory() async {
        guard hasMoreHistory else { return }
        let next = cursor
        await run { cookies, service, token in
            let data = try await service.history(pcursor: next, cookies: cookies)
            try self.check(token)
            let response = try ShoppingFrameDecoder.decodeResponse(data)
            let existing = Set(self.transcript.messages.map(\.messageId))
            self.transcript.messages = Self.uniqueMessages(response.messages.filter { !existing.contains($0.messageId) }) + self.transcript.messages
            self.updateCursor(response.pcursor)
            self.notice = response.notices.first?.message ?? (response.messages.isEmpty ? "暂无更多历史。" : "已加载购物历史。")
        }
    }

    public func loadQuestions() async {
        await run { cookies, service, token in
            let data = try await service.questions(cookies: cookies)
            try self.check(token)
            let response = try ShoppingFrameDecoder.decodeResponse(data)
            self.suggestedQuestions = Self.unique(response.suggestedQuestions)
            self.notice = response.notices.first?.message
        }
    }

    public func feedback(message: ShoppingMessage, positive: Bool) async {
        guard transcript.messages.contains(where: { $0.messageId == message.messageId }), message.sender == "ai" else { return }
        await run { cookies, service, token in
            let data = try await service.feedback(messageID: message.messageId, sessionID: message.sessionId ?? self.transcript.sessionId,
                                                  type: positive ? 1 : 2, cookies: cookies)
            try self.check(token)
            _ = try ShoppingFrameDecoder.decodeResponse(data)
            self.notice = "反馈已提交。"
        }
    }

    private func run(_ work: @escaping @MainActor ([HTTPCookie], any ShoppingService, UUID) async throws -> Void) async {
        guard canUseService, let service else { return }
        isBusy = true
        notice = nil
        let token = generation
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer {
                if token == self.generation {
                    self.isBusy = false
                    self.transcript.thinkingMessage = nil
                    self.operation = nil
                }
            }
            do {
                let values = await self.credentials.cookies()
                try self.check(token)
                guard !self.acceptCredentialSnapshot(values) else {
                    self.notice = "快手登录态已变化，旧操作已停止，请重新输入或加载。"
                    return
                }
                guard let configuration = self.configuration,
                      ShoppingCookiePolicy.hasServiceCredential(values, for: configuration.chatURL) else {
                    throw ShoppingClientError.missingCredential
                }
                try await work(values, service, token)
            } catch {
                guard token == self.generation, !Task.isCancelled else { return }
                if error as? ShoppingClientError == .authenticationRequired {
                    self.logout()
                    self.notice = ShoppingClientError.authenticationRequired.localizedDescription
                } else if let error = error as? ShoppingClientError {
                    self.notice = error.localizedDescription
                } else if let error = error as? ShoppingProtocolError {
                    self.notice = error.localizedDescription
                } else {
                    self.notice = "购物请求未完成，请稍后重试。"
                }
            }
        }
        operation = task
        await task.value
    }

    @discardableResult private func acceptCredentialSnapshot(_ values: [HTTPCookie]) -> Bool {
        let current = values.filter { ["token", "kuaishou.api_st", "userId", "ud", "kuaishou.server.webday7_st"].contains($0.name) }
            .map { "\($0.domain)\n\($0.path)\n\($0.name)\n\($0.value)" }.sorted()
        let changed = credentialIdentity != nil && credentialIdentity != current
        if changed { clearData() }
        credentialIdentity = current
        if let configuration, ShoppingCookiePolicy.hasServiceCredential(values, for: configuration.chatURL) {
            if changed || credentialState != .serviceAccepted { credentialState = .serviceCandidate }
        } else {
            let hasWeb = values.contains {
                $0.name == "kuaishou.server.webday7_st" && !$0.value.isEmpty
                    && ShoppingCookiePolicy.matches(cookie: $0, url: ShoppingLoginPolicy.loginURL)
            }
            credentialState = hasWeb ? .webOnly : .none
        }
        return changed
    }

    private func invalidateOperation() {
        localBridge.cancelRequest()
        generation = UUID()
        operation?.cancel()
        operation = nil
        isBusy = false
    }
    private func check(_ token: UUID) throws {
        try Task.checkCancellation()
        guard token == generation, ownerIsBound, !isDemo else { throw CancellationError() }
    }
    private func clearData() {
        transcript = ShoppingTranscript()
        draft = ""
        suggestedQuestions = []
        notice = nil
        cursor = "0"
        hasMoreHistory = true
    }
    private func updateCursor(_ value: String?) {
        guard let value, let number = Int32(value), number >= 0 else { hasMoreHistory = false; return }
        hasMoreHistory = value != cursor
        cursor = value
    }
    private static func unique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { !$0.isEmpty && seen.insert($0).inserted }.prefix(12).map { $0 }
    }
    private static func uniqueMessages(_ values: [ShoppingMessage]) -> [ShoppingMessage] {
        var seen = Set<String>()
        return values.filter { seen.insert($0.messageId).inserted }
    }
    @discardableResult private func appendUser(_ content: String) -> String {
        let messageID = "mac-\(UUID().uuidString)"
        transcript.messages.append(.init(messageId: messageID, sender: "user", blocks: [
            .init(moduleId: "text", type: "text", content: .object(["text": .string(content)]))
        ]))
        return messageID
    }
    private func appendDemoAnswer() {
        transcript.messages.append(.init(messageId: "demo-\(UUID().uuidString)", blocks: [
            .init(moduleId: "text", type: "text", content: .object(["text": .string("这是离线演示回复。以通勤保温杯为例，可以先比较容量、重量和清洗方式。以下商品与价格均为示例。") ])),
            .init(moduleId: "product", type: "product_multi_vertical", content: .object([
                "productMultiVerticalCards": .array([
                    .object(["itemId": .string("demo-1"), "itemTitle": .string("轻便通勤保温杯 · 示例"), "price": .number(12900)]),
                    .object(["itemId": .string("demo-2"), "itemTitle": .string("大容量旅行保温杯 · 示例"), "price": .number(18900)])
                ])
            ]))
        ]))
        notice = "示例回复已显示；真实商品推荐需连接购物服务。"
    }
}
