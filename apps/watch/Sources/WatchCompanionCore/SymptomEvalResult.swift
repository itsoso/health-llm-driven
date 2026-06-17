import Foundation

/// `/watch/symptoms` 的腕上响应模型 + **安全承重逻辑**。
///
/// 全场安全 stakes 最高(语音报急症),所有「这条响应安不安全 / 该多醒目 / 该不该震」的判定
/// 都放这里(纯 Foundation、可单测),**不下放给 View**。理由:View 容易把
/// `evaluation_failed` 或 critical 误渲成绿灯(under-alarm)——把判定钉死在可单测的 Core,
/// 用对抗用例锁住「即便 alerts 空、只要 evaluation_failed 就绝不 reassuring」。
///
/// 后端契约(对齐 backend/app/api/watch.py record_symptom):
///   { "symptom_id": Int,
///     "alerts": [ { "severity": {"value":Int,"label":String,"label_zh":String},
///                   "title":String, "action":String, "data_citation":{} } ],
///     "message": String?,
///     "evaluation_failed": Bool? }   // 仅失败分支出现;成功分支无此键 → decode 成 false
/// alerts 已由后端 severity 降序;evaluation_failed 时后端注入一条 HIGH advisory 进 alerts。

public struct SymptomSeverity: Codable, Equatable, Sendable {
    public let value: Int
    public let label: String       // "critical" / "high" / "medium" / ...(对齐 Severity.label)
    public let labelZh: String

    enum CodingKeys: String, CodingKey {
        case value, label
        case labelZh = "label_zh"
    }

    public init(value: Int, label: String, labelZh: String) {
        self.value = value
        self.label = label
        self.labelZh = labelZh
    }
}

public struct SymptomAlert: Codable, Equatable, Sendable {
    public let severity: SymptomSeverity
    public let title: String
    public let action: String?

    enum CodingKeys: String, CodingKey {
        case severity, title, action
        // data_citation 腕上不渲染,不解(避免对未知 JSON 结构强 decode)。
    }

    public init(severity: SymptomSeverity, title: String, action: String?) {
        self.severity = severity
        self.title = title
        self.action = action
    }
}

/// 腕上触觉强度(Core 枚举,View 再映射到 WKHapticType —— Core 不依赖 WatchKit)。
public enum SymptomHaptic: String, Equatable, Sendable {
    case strong   // critical → 强震(View 映 .failure)
    case notify   // high     → 提示(View 映 .notification)
    case click    // 其它/无告警 → 轻确认(View 映 .click)
}

/// 给 View 的横幅文案 + 视觉档位。**banner 的 tone 决定底色,View 不得自行判定绿灯。**
public struct SymptomBanner: Equatable, Sendable {
    public enum Tone: String, Equatable, Sendable {
        case critical   // 红底大字
        case high       // 橙
        case caution    // 橙/黄(评估未完成 = 不确定,绝不绿)
        case safe       // 绿(仅真·无告警 + 评估完成)
    }
    public let tone: Tone
    public let title: String
    public let action: String?

    public init(tone: Tone, title: String, action: String?) {
        self.tone = tone
        self.title = title
        self.action = action
    }
}

public struct SymptomEvalResult: Codable, Equatable, Sendable {
    public let symptomId: Int
    public let alerts: [SymptomAlert]
    public let message: String?
    public let evaluationFailed: Bool   // 成功分支后端不带此键 → decodeIfPresent 兜成 false

    enum CodingKeys: String, CodingKey {
        case symptomId = "symptom_id"
        case alerts, message
        case evaluationFailed = "evaluation_failed"
    }

    public init(symptomId: Int, alerts: [SymptomAlert], message: String?, evaluationFailed: Bool) {
        self.symptomId = symptomId
        self.alerts = alerts
        self.message = message
        self.evaluationFailed = evaluationFailed
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        symptomId = try c.decode(Int.self, forKey: .symptomId)
        // alerts 缺省/为 null 都兜成空(契约总会给数组,但防御性 decode)。
        alerts = (try? c.decode([SymptomAlert].self, forKey: .alerts)) ?? []
        message = try c.decodeIfPresent(String.self, forKey: .message)
        // ★ 成功分支无 evaluation_failed 键 → 默认 false;但失败分支显式 true 必须读到。
        evaluationFailed = (try? c.decodeIfPresent(Bool.self, forKey: .evaluationFailed)) ?? false
    }

    public static func decode(_ data: Data) throws -> SymptomEvalResult {
        try JSONDecoder().decode(SymptomEvalResult.self, from: data)
    }

    // MARK: - 安全承重计算属性(View 只读、不重算)

    /// 最高优先级告警(后端已 severity 降序 → 取 first)。
    public var topAlert: SymptomAlert? { alerts.first }

    /// 任一告警达 critical(label 或 value≥4 双判 —— 不光信 label 字符串,value 兜底)。
    public var isCritical: Bool {
        alerts.contains { $0.severity.label == "critical" || $0.severity.value >= 4 }
    }

    /// 触觉强度:critical→强震、high→提示、其它→轻确认。评估未完成时也至少给 notify(不轻描淡写)。
    public var hapticKind: SymptomHaptic {
        if isCritical { return .strong }
        if evaluationFailed { return .notify }   // 不确定 ≠ 无事:给提示级触觉,别只 click
        if let top = topAlert, top.severity.label == "high" || top.severity.value >= 3 {
            return .notify
        }
        return .click
    }

    /// **真·安全**才 true:无任何告警 **且** 评估完整跑完。
    /// evaluation_failed==true 时**永远 false**(即便 alerts 恰好为空也绝不 reassuring)——
    /// 这是 UI 不漏报的最后一道闸:View 只能据此点绿灯。
    public var isReassuringSafe: Bool {
        alerts.isEmpty && !evaluationFailed
    }

    /// 给 View 的横幅(标题/动作/档位)。失败态用 message + advisory,绝不退化成绿。
    public var displayBanner: SymptomBanner {
        if let top = topAlert {
            let tone: SymptomBanner.Tone
            if top.severity.label == "critical" || top.severity.value >= 4 {
                tone = .critical
            } else if evaluationFailed {
                // 有 alert 但本次评估不完整(多半就是注入的 HIGH advisory):醒目橙/红,不降成普通 high。
                tone = .caution
            } else if top.severity.label == "high" || top.severity.value >= 3 {
                tone = .high
            } else {
                tone = .high   // 任何被渲染出来的 alert 至少 high 档醒目,不弱化
            }
            return SymptomBanner(tone: tone, title: top.title, action: top.action)
        }

        // 无 alert 分支:
        if evaluationFailed {
            // 评估未完成且(异常地)无 alert 注入 → 仍必须醒目提示,绝不绿。
            return SymptomBanner(
                tone: .caution,
                title: "安全评估未完成",
                action: message ?? "本次未能完成自动安全筛查,请勿据此判断为安全;如有不适请及时就医,情况紧急请拨打 120。"
            )
        }

        // 真·无告警 = 安全。
        return SymptomBanner(
            tone: .safe,
            title: "未触发安全提醒",
            action: message ?? "已记录症状。若不适加重或持续,请及时就医。"
        )
    }
}
