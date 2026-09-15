import Foundation

/// Shopping payloads stay separate from health messages and health context serialization.
/// Decimal preserves numeric identifiers and currency values without Double rounding.
public enum ShoppingJSONValue: Codable, Sendable, Equatable {
    case object([String: ShoppingJSONValue])
    case array([ShoppingJSONValue])
    case string(String)
    case number(Decimal)
    case bool(Bool)
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode(Decimal.self) { self = .number(value) }
        else if let value = try? container.decode([ShoppingJSONValue].self) { self = .array(value) }
        else { self = .object(try container.decode([String: ShoppingJSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    public subscript(_ key: String) -> ShoppingJSONValue? { objectValue?[key] }
    public var objectValue: [String: ShoppingJSONValue]? {
        if case .object(let value) = self { return value }; return nil
    }
    public var arrayValue: [ShoppingJSONValue]? {
        if case .array(let value) = self { return value }; return nil
    }
    public var stringValue: String? {
        if case .string(let value) = self { return value }; return nil
    }
    public var scalarString: String? {
        switch self {
        case .string(let value): return value
        case .number(let value): return NSDecimalNumber(decimal: value).stringValue
        default: return nil
        }
    }
    public init(data: Data) throws {
        guard data.count <= ShoppingFrameDecoder.maximumFrameBytes else { throw ShoppingProtocolError.frameTooLarge }
        do { self = try JSONDecoder().decode(Self.self, from: data) }
        catch { throw ShoppingProtocolError.malformedPayload }
    }
}

public enum ShoppingProtocolError: Error, LocalizedError, Sendable, Equatable {
    case malformedPayload, unsupportedEnvelope, frameTooLarge, invalidMessage, commandNestingLimit
    case serviceRejected

    public var errorDescription: String? {
        switch self {
        case .malformedPayload: return "购物服务返回的数据无法解析。"
        case .unsupportedEnvelope: return "购物服务返回了尚未适配的消息格式。"
        case .frameTooLarge: return "购物服务返回的单条消息超过大小限制。"
        case .invalidMessage: return "购物消息缺少有效的消息标识或内容。"
        case .commandNestingLimit: return "购物消息中的嵌套指令超过限制。"
        case .serviceRejected: return "购物服务未接受此次请求，请检查登录状态和服务配置。"
        }
    }
}

public struct ShoppingProtocolNotice: Sendable, Equatable {
    public let code: String
    public let message: String
    public init(code: String, message: String) { self.code = code; self.message = message }
}

public struct ShoppingCommand: Codable, Sendable, Equatable {
    public let commandType: String
    public let commandData: ShoppingJSONValue
    public init(commandType: String, commandData: ShoppingJSONValue) {
        self.commandType = commandType; self.commandData = commandData
    }
}

public struct ShoppingMessage: Codable, Sendable, Equatable, Identifiable {
    public var messageId: String
    public var sessionId: String?
    public var sender: String
    public var blocks: [ShoppingBlock]
    public var id: String { messageId }
    public var text: String { blocks.compactMap(\.text).joined(separator: "\n") }

    public init(messageId: String, sessionId: String? = nil, sender: String = "ai", blocks: [ShoppingBlock]) {
        self.messageId = messageId; self.sessionId = sessionId; self.sender = sender; self.blocks = blocks
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        messageId = try container.decode(String.self, forKey: .messageId)
        guard !messageId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ShoppingProtocolError.invalidMessage
        }
        sessionId = try container.decodeIfPresent(String.self, forKey: .sessionId)
        // update_block may carry a partial msgItem without sender; the reducer retains the old sender.
        sender = try container.decodeIfPresent(String.self, forKey: .sender) ?? "ai"
        blocks = try container.decode([ShoppingBlock].self, forKey: .blocks)
        guard ["ai", "user"].contains(sender), !blocks.isEmpty, blocks.count <= 256 else {
            throw ShoppingProtocolError.invalidMessage
        }
    }
}

public struct ShoppingProduct: Sendable, Equatable, Identifiable {
    public let id: String
    public let name: String
    public let priceText: String?
    /// An untrusted candidate only. The UI must apply its desktop URL policy before opening it.
    public let detailURL: String?
    public let imageURL: String?
    public init(id: String, name: String, priceText: String? = nil, detailURL: String? = nil, imageURL: String? = nil) {
        self.id = id; self.name = name; self.priceText = priceText
        self.detailURL = detailURL; self.imageURL = imageURL
    }
}

public struct ShoppingBlock: Codable, Sendable, Equatable {
    public var moduleId: String?
    public var type: String
    public var content: ShoppingJSONValue
    public init(moduleId: String? = nil, type: String, content: ShoppingJSONValue) {
        self.moduleId = moduleId; self.type = type; self.content = content
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        moduleId = try container.decodeIfPresent(String.self, forKey: .moduleId)
        type = try container.decode(String.self, forKey: .type)
        content = try container.decode(ShoppingJSONValue.self, forKey: .content)
        guard !type.isEmpty else { throw ShoppingProtocolError.invalidMessage }
        if type == "text", content["text"]?.stringValue == nil { throw ShoppingProtocolError.invalidMessage }
    }

    public var text: String? {
        switch type {
        case "text", "text_btn", "button_vertical", "button_vertical_sug", "button_horizontal_sug", "error_retry":
            return content["text"]?.stringValue
        case "thinking_step":
            return content["thinkingInfo"]?["stateText"]?.stringValue
        case "stop_reply": return "已停止接收"
        default: return nil
        }
    }

    public var suggestedQuestions: [String] {
        let values: [String]
        switch type {
        case "question_card": values = content["tagList"]?.arrayValue?.compactMap { $0["title"]?.stringValue } ?? []
        case "recommend_word_list": values = content["recommendWords"]?.arrayValue?.compactMap { $0["message"]?.stringValue } ?? []
        case "button_horizontal": values = content["buttonHorizontalCards"]?.arrayValue?.compactMap { $0["message"]?.stringValue } ?? []
        case "button_vertical", "button_vertical_sug", "button_horizontal_sug": values = [text].compactMap { $0 }
        default: values = []
        }
        // Suggestions are text drafts only; embedded commandList is never executed automatically.
        return values.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    public var isSupported: Bool {
        ["text", "text_btn", "loading", "stop_reply", "error_retry", "thinking_step", "divider", "feedback",
         "question_card", "recommend_word_list", "button_horizontal", "button_vertical", "button_vertical_sug",
         "button_horizontal_sug", "product_single_small", "product_single_big", "product_multi_horizontal_stye1",
         "product_multi_horizontal_stye2", "product_multi_horizontal_stye3", "product_multi_vertical", "restock_good_list_card"].contains(type)
    }

    public var products: [ShoppingProduct] {
        let cards: [ShoppingJSONValue]
        let isCents: Bool
        switch type {
        case "product_single_small": cards = [content["productSingleSmallCard"]].compactMap { $0 }; isCents = false
        case "product_single_big": cards = [content["productSingleBigCard"]].compactMap { $0 }; isCents = false
        case "product_multi_horizontal_stye1", "product_multi_horizontal_stye2", "product_multi_horizontal_stye3":
            cards = content["productMultiHorizontalCards"]?.arrayValue ?? []; isCents = true
        case "product_multi_vertical", "restock_good_list_card":
            cards = content["productMultiVerticalCards"]?.arrayValue ?? []; isCents = true
        default: return []
        }
        return cards.enumerated().compactMap { index, card in
            guard let object = card.objectValue else { return nil }
            let name = object["itemTitle"]?.stringValue ?? "商品详情"
            let commandURL = object["productDetailButton"]?["commandList"]?.arrayValue?.first {
                $0["commandType"]?.stringValue == "jump_to"
            }?["commandData"]?["jumpUrl"]?.stringValue
            let price = object["price"]?.scalarString.flatMap { string -> Decimal? in
                guard string.range(of: #"^[0-9]+(?:\.[0-9]+)?$"#, options: .regularExpression) != nil else { return nil }
                return Decimal(string: string, locale: Locale(identifier: "en_US_POSIX"))
            }
            let priceText = price.map { value in
                var yuan = isCents ? value / 100 : value
                var rounded = Decimal()
                NSDecimalRound(&rounded, &yuan, 2, .plain)
                return "¥" + NSDecimalNumber(decimal: rounded).stringValue
            }
            return ShoppingProduct(
                id: object["itemId"]?.scalarString ?? "\(moduleId ?? type)-\(index)", name: name,
                priceText: priceText, detailURL: object["productDetailJumpUrl"]?.stringValue ?? commandURL,
                imageURL: object["headPic"]?.stringValue
            )
        }
    }
}

public struct ShoppingResponse: Sendable, Equatable {
    public var messages: [ShoppingMessage]
    public var suggestedQuestions: [String]
    public var sessionId: String?
    public var globalParams: [String: ShoppingJSONValue]
    public var pcursor: String?
    public var notices: [ShoppingProtocolNotice]
    public init(messages: [ShoppingMessage] = [], suggestedQuestions: [String] = [], sessionId: String? = nil,
                globalParams: [String: ShoppingJSONValue] = [:], pcursor: String? = nil, notices: [ShoppingProtocolNotice] = []) {
        self.messages = messages; self.suggestedQuestions = suggestedQuestions; self.sessionId = sessionId
        self.globalParams = globalParams; self.pcursor = pcursor; self.notices = notices
    }
}

/// Decodes one complete JSON frame, not arbitrary HTTP bytes. The transport owns framing.
/// Source: ChatService.ts reads JSON.parse(response).data.data; RequestHarmonyApi.ts additionally
/// accepts successful wrappers containing command strings. No completion marker is assumed here.
public enum ShoppingFrameDecoder {
    public static let maximumFrameBytes = 1_048_576

    public static func decode(_ data: Data) throws -> [ShoppingCommand] {
        let root = try ShoppingJSONValue(data: data)
        guard let object = root.objectValue else { throw ShoppingProtocolError.unsupportedEnvelope }
        try requireSuccess(object)
        guard let payload = object["data"], payload != .null else { return [] }
        return try decodePayload(payload)
    }

    public static func decodeCommand(_ data: Data) throws -> ShoppingCommand {
        try command(from: ShoppingJSONValue(data: data))
    }

    public static func decodeResponse(_ data: Data) throws -> ShoppingResponse {
        let root = try ShoppingJSONValue(data: data)
        guard let wrapper = root.objectValue else { throw ShoppingProtocolError.unsupportedEnvelope }
        try requireSuccess(wrapper)
        guard let value = wrapper["data"], value != .null else { return ShoppingResponse() }
        guard let payload = value.objectValue else { throw ShoppingProtocolError.unsupportedEnvelope }
        let knownKeys: Set<String> = ["sessionId", "haveSessionHistory", "title", "navbar", "welcomeInfo", "questionsFirstCards",
                                     "quickActions", "global", "loadPageStatus", "queryQuestionsInfo", "sugSendMsg", "pcursor",
                                     "historyList", "greetInfo", "sendModule", "questions", "greetingInfo", "userSugs", "useResponse", "tostDesc"]
        guard payload.isEmpty || !knownKeys.isDisjoint(with: payload.keys) else { throw ShoppingProtocolError.unsupportedEnvelope }
        var messages: [ShoppingMessage] = []
        if let history = payload["historyList"], history != .null {
            guard let list = history.arrayValue else { throw ShoppingProtocolError.malformedPayload }
            messages = try list.map(message(from:))
        }
        var questions: [String] = []
        for list in [payload["questions"], payload["userSugs"], payload["greetingInfo"]?["sugButtons"], payload["greetingInfo"]?["userSugs"]] {
            guard let list, list != .null else { continue }
            guard let items = list.arrayValue else { throw ShoppingProtocolError.malformedPayload }
            questions += items.compactMap { $0["message"]?.stringValue }
        }
        var globals: [String: ShoppingJSONValue] = [:]
        if let value = payload["global"], value != .null {
            guard let object = value.objectValue else { throw ShoppingProtocolError.malformedPayload }
            globals = object
        }
        var notices: [ShoppingProtocolNotice] = []
        if payload["sugSendMsg"] != nil {
            notices.append(.init(code: "automatic_send_ignored", message: "服务端建议的自动发送动作需要由你在购物页确认。"))
        }
        return ShoppingResponse(messages: messages, suggestedQuestions: questions.filter { !$0.isEmpty },
                                sessionId: payload["sessionId"]?.stringValue, globalParams: globals,
                                pcursor: payload["pcursor"]?.scalarString, notices: notices)
    }

    private static func requireSuccess(_ object: [String: ShoppingJSONValue]) throws {
        guard let result = object["result"] else { throw ShoppingProtocolError.unsupportedEnvelope }
        guard result == .number(1) else { throw ShoppingProtocolError.serviceRejected }
    }

    private static func decodePayload(_ payload: ShoppingJSONValue) throws -> [ShoppingCommand] {
        if let text = payload.stringValue {
            let lines = text.split(whereSeparator: \.isNewline)
            guard !lines.isEmpty, lines.count <= 256 else { throw ShoppingProtocolError.unsupportedEnvelope }
            return try lines.map { try decodeCommand(Data($0.utf8)) }
        }
        guard let object = payload.objectValue else { throw ShoppingProtocolError.unsupportedEnvelope }
        if object["result"] != nil { try requireSuccess(object) }
        if object["commandType"] != nil { return [try command(from: payload)] }
        guard let inner = object["data"], inner != .null else {
            if object["result"] == .number(1) { return [] }
            throw ShoppingProtocolError.unsupportedEnvelope
        }
        if let text = inner.stringValue { return [try decodeCommand(Data(text.utf8))] }
        return [try command(from: inner)]
    }

    fileprivate static func command(from value: ShoppingJSONValue) throws -> ShoppingCommand {
        guard let type = value["commandType"]?.stringValue, !type.isEmpty,
              let data = value["commandData"], data.objectValue != nil else { throw ShoppingProtocolError.malformedPayload }
        return ShoppingCommand(commandType: type, commandData: data)
    }

    fileprivate static func message(from value: ShoppingJSONValue) throws -> ShoppingMessage {
        do { return try JSONDecoder().decode(ShoppingMessage.self, from: JSONEncoder().encode(value)) }
        catch { throw ShoppingProtocolError.invalidMessage }
    }
}

/// Models frontend display behavior only. It cannot send messages, navigate, purchase, or reset an upstream session.
public struct ShoppingTranscript: Sendable, Equatable {
    public var messages: [ShoppingMessage]
    public var thinkingMessage: ShoppingMessage?
    public var globalParams: [String: ShoppingJSONValue]
    public var sessionId: String?

    public init(messages: [ShoppingMessage] = [], thinkingMessage: ShoppingMessage? = nil,
                globalParams: [String: ShoppingJSONValue] = [:], sessionId: String? = nil) {
        self.messages = messages; self.thinkingMessage = thinkingMessage
        self.globalParams = globalParams; self.sessionId = sessionId
    }

    @discardableResult public mutating func apply(_ command: ShoppingCommand) throws -> [ShoppingProtocolNotice] {
        var staged = self
        let notices = try staged.reduce(command, depth: 0)
        self = staged
        return notices
    }

    private mutating func reduce(_ command: ShoppingCommand, depth: Int) throws -> [ShoppingProtocolNotice] {
        guard depth < 8 else { throw ShoppingProtocolError.commandNestingLimit }
        switch command.commandType {
        case "show_msg", "set_msg", "append_local_msg", "update_block", "thinking_process_msg":
            guard let item = command.commandData["msgItem"] else { throw ShoppingProtocolError.invalidMessage }
            let incoming = try ShoppingFrameDecoder.message(from: item)
            if command.commandType == "thinking_process_msg" {
                thinkingMessage = incoming
                return []
            }
            if command.commandType == "update_block" {
                guard let index = messages.firstIndex(where: { $0.messageId == incoming.messageId }) else {
                    return [.init(code: "update_target_missing", message: "一条更新消息未找到对应的原消息。")]
                }
                var replacements: [String: ShoppingBlock] = [:]
                for block in incoming.blocks {
                    if let module = block.moduleId, !module.isEmpty { replacements[module] = block }
                }
                var replaced = false
                messages[index].blocks = messages[index].blocks.map { old in
                    guard let module = old.moduleId, let new = replacements[module] else { return old }
                    replaced = true
                    return new
                }
                return replaced ? unsupportedNotices(incoming) : [.init(code: "update_module_missing", message: "一条更新消息未找到对应的内容块。")]
            }
            thinkingMessage = nil
            if let id = incoming.sessionId { sessionId = id }
            if let index = messages.firstIndex(where: { $0.messageId == incoming.messageId }) {
                for block in incoming.blocks {
                    if let module = block.moduleId, !module.isEmpty,
                       let blockIndex = messages[index].blocks.firstIndex(where: { $0.moduleId == module }) {
                        let old = messages[index].blocks[blockIndex]
                        if old.type == "text", block.type == "text" {
                            guard var content = old.content.objectValue,
                                  let newContent = block.content.objectValue,
                                  let oldText = old.content["text"]?.stringValue,
                                  let newText = block.content["text"]?.stringValue else { throw ShoppingProtocolError.invalidMessage }
                            content.merge(newContent) { _, new in new }
                            content["text"] = .string(oldText + newText)
                            var merged = block
                            merged.content = .object(content)
                            messages[index].blocks[blockIndex] = merged
                        } else {
                            messages[index].blocks[blockIndex] = block
                        }
                    } else { messages[index].blocks.append(block) }
                }
            } else { messages.append(incoming) }
            return unsupportedNotices(incoming)
        case "set_global_param":
            guard let value = command.commandData["globalParams"]?.objectValue else { throw ShoppingProtocolError.malformedPayload }
            globalParams = value
            return []
        case "cmd_to_ai_page":
            guard let list = command.commandData["cmd_list"]?.arrayValue, list.count <= 256 else { throw ShoppingProtocolError.malformedPayload }
            var notices: [ShoppingProtocolNotice] = []
            for item in list { notices += try reduce(ShoppingFrameDecoder.command(from: item), depth: depth + 1) }
            return notices
        default:
            // create_session has an enum declaration but no verified payload contract in current source.
            return [.init(code: "unsupported_command", message: "收到一项当前 Mac 暂不支持的操作，请在快手 App 中继续。")]
        }
    }

    private func unsupportedNotices(_ message: ShoppingMessage) -> [ShoppingProtocolNotice] {
        message.blocks.contains(where: { !$0.isSupported })
            ? [.init(code: "unsupported_card", message: "部分卡片暂不支持在 Mac 展示，请在快手 App 中查看。")]
            : []
    }
}
