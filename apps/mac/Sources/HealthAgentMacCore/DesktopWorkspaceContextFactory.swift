import Foundation

public enum DesktopWorkspaceContextFactory {
    public static func contextItem(for row: DesktopWorkspaceGuidanceRow, workspace: DesktopWorkspaceSummary) -> AgentContextItem {
        AgentContextItem(
            sourceID: "workspace_guidance:\(workspace.kind.rawValue):\(row.id)",
            sourceKind: "workspace_guidance",
            title: row.title,
            summary: row.detail,
            payload: [
                "workspace": workspace.kind.rawValue,
                "action": row.action.rawValue,
                "title": row.title,
                "detail": row.detail,
                "metrics": workspace.metrics.map { "\($0.title)=\($0.value)" }.joined(separator: "; "),
                "focus_domains": workspace.focusDomains.joined(separator: ", "),
                "active_jobs": workspace.jobs.map { "#\($0.id) \($0.jobType) \($0.status) \($0.progress)%" }.joined(separator: "; "),
                "source_root": workspace.knowledgeSummary?.localSourceSummary?.sourceRoot ?? ""
            ]
        )
    }

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

    public static func contextItem(for trend: DesktopHealthTrendContext) -> AgentContextItem {
        AgentContextItem(
            sourceID: "health_trend:\(trend.kind.rawValue):\(trend.rangeDays)d",
            sourceKind: "health_trend",
            title: "\(trend.title) · \(trend.rangeDays)天",
            summary: [
                trend.total.map { "total \(DesktopHealthTrendContext.format($0)) \(trend.unit)" },
                trend.average.map { "avg \(DesktopHealthTrendContext.format($0)) \(trend.unit)/day" },
                trend.recordCount.map { "\($0) records" }
            ].compactMap { $0 }.joined(separator: " · "),
            payload: [
                "kind": trend.kind.rawValue,
                "title": trend.title,
                "range_days": "\(trend.rangeDays)",
                "unit": trend.unit,
                "total": trend.total.map(DesktopHealthTrendContext.format) ?? "",
                "average": trend.average.map(DesktopHealthTrendContext.format) ?? "",
                "record_count": trend.recordCount.map(String.init) ?? "",
                "points": trend.pointSeriesText,
                "latest_record": trend.latestRecordText ?? ""
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

    public static func prompt(for trend: DesktopHealthTrendContext) -> String {
        [
            "请基于这段\(trend.rangeDays) 天\(trend.title)做趋势分析。",
            "趋势点：\(trend.pointSeriesText)。",
            trend.total.map { "合计：\(DesktopHealthTrendContext.format($0)) \(trend.unit)。" },
            trend.average.map { "日均：\(DesktopHealthTrendContext.format($0)) \(trend.unit)。" },
            trend.latestRecordText.map { "最近记录：\($0)。" },
            "请结合我的最近记录、穿戴数据、基因风险、补剂和知识库证据，判断趋势是否需要调整饮食、运动、补剂或复查计划；列出不确定性边界，不要当作诊断。"
        ].compactMap { $0 }.joined()
    }

    public static func prompt(for row: DesktopWorkspaceGuidanceRow, workspace: DesktopWorkspaceSummary) -> String {
        switch row.action {
        case .reviewWeeklyIntake:
            return "请基于当前数据工作台的 7 天饮食、饮水、补剂、体重、血压和步数概览，判断今天是否需要调整饮食、饮水、补剂或运动，并列出不确定性边界。"
        case .reviewClinicalBoundary:
            return "请基于当前基因工作台概览，说明哪些基因发现只能用于风险分层，哪些需要临床检测确认；不要把基因风险当成诊断或用药决定。"
        case .auditSourceCoverage:
            return "请基于当前知识库工作台上下文，审查得到、本地 llms-wiki、PubMed 和系统证据的覆盖是否足够；指出缺口、优先补充来源和下一步任务。"
        case .rebuildSystemKnowledgeBase:
            return "请基于当前知识库工作台上下文，规划一次系统知识库重建：包括 down-dedao/llms-wiki 来源、claim 编译、证据引用、来源覆盖和验收标准。"
        case .importDedaoFolder:
            return "请基于当前知识库工作台上下文，检查本地 down-dedao 健康课程和电子书如何导入到系统知识库，并说明导入后如何验证来源覆盖。"
        case .refreshRecentHealthData:
            return "请基于当前数据工作台上下文，判断刷新近期健康数据后应该优先检查哪些指标和异常趋势。"
        case .createMedicalImport:
            return "请基于当前数据工作台上下文，说明医疗文件导入任务应该如何命名、审计、提取指标并纳入 Agent 上下文。"
        case .importGenomeFile:
            return "请基于当前基因工作台上下文，说明导入 WeGene/23andMe 原始基因文件后的重分析流程、风险边界和验收标准。"
        case .runRiskReanalysis:
            return "请基于当前基因工作台上下文，规划一次基因风险重分析：包括源文件哈希、位点匹配、置信度、重复去重和临床边界。"
        }
    }
}
