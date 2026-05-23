import Foundation

public enum DesktopWorkspaceContextFactory {
    public static func contextItem(for record: DesktopRecordMetric) -> AgentContextItem {
        AgentContextItem(
            sourceID: "health_record:\(record.id)",
            sourceKind: "health_record",
            title: record.title,
            summary: [
                record.recordDate,
                record.type,
                record.displayValue
            ].compactMap { $0 }.joined(separator: " · "),
            payload: [
                "id": "\(record.id)",
                "type": record.type,
                "title": record.title,
                "display_value": record.displayValue,
                "unit": record.unit ?? "",
                "category": record.category ?? "",
                "record_date": record.recordDate ?? ""
            ]
        )
    }

    public static func contextItem(for document: KnowledgeDocumentSummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "knowledge_document:\(document.docID)",
            sourceKind: "knowledge_document",
            title: document.title?.isEmpty == false ? document.title! : document.docID,
            summary: document.summary ?? document.docID,
            payload: [
                "doc_id": document.docID,
                "doc_type": document.docType,
                "title": document.title ?? "",
                "summary": document.summary ?? "",
                "evidence_level": document.evidenceLevel ?? "",
                "confidence": document.confidence.map { "\($0)" } ?? "",
                "sources": document.sources.joined(separator: ", ")
            ]
        )
    }

    public static func contextItem(for job: DesktopJobSummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "desktop_job:\(job.id)",
            sourceKind: "desktop_job",
            title: job.sourceName?.isEmpty == false ? job.sourceName! : job.jobType,
            summary: "#\(job.id) \(job.jobType) · \(job.status) · \(job.progress)%",
            payload: [
                "id": "\(job.id)",
                "job_type": job.jobType,
                "status": job.status,
                "progress": "\(job.progress)",
                "source_kind": job.sourceKind ?? "",
                "source_name": job.sourceName ?? "",
                "source_hash": job.sourceHash ?? "",
                "error_message": job.errorMessage ?? ""
            ]
        )
    }

    public static func prompt(for record: DesktopRecordMetric) -> String {
        "请基于这条健康记录分析其意义，并结合我最近 7 天/30 天趋势、基因风险、补剂和知识库证据，给出可执行建议。记录：\(record.title)，\(record.displayValue)，日期：\(record.recordDate ?? "unknown")。"
    }

    public static func prompt(for document: KnowledgeDocumentSummary) -> String {
        "请基于这条知识库证据，结合我的真实健康数据和当前上下文，判断它对我是否可行动，并列出证据强度、不确定性边界和下一步。证据：\(document.title ?? document.docID)。"
    }

    public static func prompt(for job: DesktopJobSummary) -> String {
        "请基于这个桌面任务的状态和结果上下文，判断下一步该怎么处理；如果失败，请分析可能原因和重试/修复方案。任务：#\(job.id) \(job.jobType)，状态：\(job.status)，进度：\(job.progress)%。"
    }
}
