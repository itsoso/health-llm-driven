import Foundation

/// 腕上打点(quick-record)的校验 + 请求构造。watchOS 各打点按钮调这里得到要发给后端的
/// (path, query, body),再经 WatchConnectivity 中继给 iPhone。校验在此可单测,防腕上发脏数据。
///
/// 安全/诚实边界:量参数有范围校验,越界→明确错误(不静默发,不让后端用默认值兜)。

public enum QuickRecordError: Error, Equatable, Sendable {
    case outOfRange(String)
    case missing(String)
}

public enum QuickRecordResultKind: String, Equatable, Sendable {
    case saved
    case draft
}

public struct QuickRecordRequest: Equatable, Sendable {
    public let path: String
    public let method: String
    public let query: [String: String]
    public let body: [String: String]   // 简化:字符串值(WC payload 友好);数字以字符串承载
    public let resultKind: QuickRecordResultKind
    public let successMessage: String

    public init(
        path: String,
        method: String,
        query: [String: String],
        body: [String: String],
        resultKind: QuickRecordResultKind = .saved,
        successMessage: String = "已记录"
    ) {
        self.path = path
        self.method = method
        self.query = query
        self.body = body
        self.resultKind = resultKind
        self.successMessage = successMessage
    }
}

public enum QuickRecord {
    /// 喝水:amount(ml)。对齐后端 /water/records/quick?amount=(必填,1–5000,无静默默认)。
    public static func water(amountML: Int) throws -> QuickRecordRequest {
        guard amountML > 0 && amountML <= 5000 else {
            throw QuickRecordError.outOfRange("饮水量需在 1–5000 ml")
        }
        return QuickRecordRequest(
            path: "/water/records/quick", method: "POST",
            query: ["amount": String(amountML)], body: [:]
        )
    }

    /// 运动打点(俯卧撑/跑步等):type + 可选 reps / duration_min。对齐 /daily-health/exercise。
    public static func exercise(
        type: String, reps: Int? = nil, durationMin: Double? = nil
    ) throws -> QuickRecordRequest {
        let t = type.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { throw QuickRecordError.missing("运动类型") }
        if let r = reps, r <= 0 { throw QuickRecordError.outOfRange("次数需为正") }
        if let d = durationMin, d <= 0 { throw QuickRecordError.outOfRange("时长需为正") }
        if reps == nil && durationMin == nil {
            throw QuickRecordError.missing("次数或时长至少给一个")
        }
        var body = ["exercise_type": t]
        if let r = reps { body["reps"] = String(r) }
        if let d = durationMin { body["duration_min"] = String(d) }
        return QuickRecordRequest(path: "/daily-health/exercise", method: "POST", query: [:], body: body)
    }

    /// 语音记一餐:转写文本 → 走解析草稿(/diet/voice/parse),确认后再写库(不在此直接入库)。
    public static func dietVoice(rawText: String) throws -> QuickRecordRequest {
        let t = rawText.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { throw QuickRecordError.missing("语音内容") }
        return QuickRecordRequest(
            path: "/diet/voice/parse", method: "POST", query: [:], body: ["raw_text": t],
            resultKind: .draft,
            successMessage: "待确认"
        )
    }
}
