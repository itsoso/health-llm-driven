import Foundation

public struct LabUploadPresentation: Equatable, Sendable {
    public let title: String
    public let statusText: String
    public let summary: String
    public let agentPrompt: String

    public static func make(result: LabUploadResult, fileName: String?) -> LabUploadPresentation {
        var parts: [String] = ["#\(result.examID)"]
        if let examDate = result.examDate, !examDate.isEmpty {
            parts.append(examDate)
        }
        if let examType = result.examType, !examType.isEmpty {
            parts.append(examType)
        }
        if let hospitalName = result.hospitalName, !hospitalName.isEmpty {
            parts.append(hospitalName)
        }
        if let itemsCount = result.itemsCount {
            parts.append("\(itemsCount) items")
        }
        if let abnormalCount = result.abnormalCount {
            parts.append("\(abnormalCount) abnormal")
        }
        if let conclusionsCount = result.conclusionsCount {
            parts.append("\(conclusionsCount) conclusions")
        }
        if let conclusion = result.conclusion, !conclusion.isEmpty {
            parts.append(conclusion)
        }

        return LabUploadPresentation(
            title: fileName?.isEmpty == false ? fileName! : "体检报告",
            statusText: "体检报告已导入。OCR/AI 解析值需要复核后再用于判断。",
            summary: parts.joined(separator: " · "),
            agentPrompt: "解释这份刚上传的体检报告：先列出异常/关键指标，再说明不确定性边界、需要复核的项目和下一步行动。"
        )
    }
}
