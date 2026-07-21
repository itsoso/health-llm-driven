import Foundation
import XCTest
@testable import HealthAgentMacCore

final class MacP0FeatureTests: XCTestCase {
    func testQuickRecordDisplayMessagePreservesSevereBloodPressureGuidance() {
        let guidance = BloodPressureSafetyGuidance(
            severity: "high",
            title: "血压严重升高，请复测",
            recheckInstruction: "请静坐至少 1 分钟后复测。",
            emergencyInstruction: "若同时出现胸痛，请立即拨打急救电话。",
            actionPath: "/blood-pressure"
        )
        let result = QuickRecordResult(
            type: "bp",
            message: "已记录血压 185/85 mmHg",
            success: true,
            safetyGuidance: guidance
        )

        XCTAssertEqual(
            result.displayMessage,
            "已记录血压 185/85 mmHg\n请静坐至少 1 分钟后复测。\n若同时出现胸痛，请立即拨打急救电话。"
        )
    }

    func testAgentStreamParserParsesTokenDoneAndErrorEvents() throws {
        let payload = """
        event: token
        data: {"content":"你好"}

        event: done
        data: {"conversation_id":7,"message_id":9,"completion_status":"complete"}

        event: error
        data: {"message":"timeout"}

        """

        let events = try AgentStreamParser.parse(payload)

        XCTAssertEqual(events, [
            .token("你好"),
            .done(conversationID: 7, messageID: 9, completionStatus: "complete", model: nil, sourcesUsed: [], toolsUsed: [], elapsedMs: nil, llmRounds: nil),
            .error("timeout")
        ])
    }

    @MainActor
    func testAgentViewModelKeepsModelPickerUsableWhileStreaming() {
        let model = AgentChatViewModel()
        model.isStreaming = true

        model.selectModel("claude-opus-4.7")

        XCTAssertEqual(model.selectedModelID, "claude-opus-4.7")
        XCTAssertTrue(model.isModelPickerEnabled)
    }

    /// The accumulating "thinking process" trace: consecutive `status` events
    /// build an ordered step list, the first `token` does NOT wipe it (adds a
    /// composing step instead), `done` settles every step, and a new `send()`
    /// clears the trace at the turn boundary.
    @MainActor
    func testThinkingStepsAccumulateSurviveFirstTokenAndResetOnNewTurn() async {
        let firstTurn: [AgentStreamEvent] = [
            .status(stage: "accepted", detail: nil, round: 1),
            .status(stage: "tool", detail: "查询健康数据", round: 1),
            .status(stage: "thinking", detail: nil, round: 2),
            .token("分"),
            .token("析"),
            .done(
                conversationID: 1, messageID: 1, completionStatus: "complete",
                model: "m", sourcesUsed: [], toolsUsed: [], elapsedMs: 10, llmRounds: 1
            ),
        ]
        let secondTurn: [AgentStreamEvent] = [
            .status(stage: "accepted", detail: nil, round: 1),
            .done(
                conversationID: 1, messageID: 2, completionStatus: "complete",
                model: "m", sourcesUsed: [], toolsUsed: [], elapsedMs: 5, llmRounds: 1
            ),
        ]
        // One script per stream() call (the ViewModel's streamService is a `let`,
        // so the same mock must serve both turns).
        let model = AgentChatViewModel(streamService: ScriptedStreamService(scripts: [firstTurn, secondTurn]))

        await model.send("分析好了吗")

        let labels = model.thinkingSteps.map { $0.labelKey }
        // Ordered accumulation: the three status stages, then the composing step
        // the first token appends — the trace was NOT cleared on first token.
        XCTAssertEqual(labels, [
            "Reva received your message…",
            "Working: %@…",
            // thinking stage with round≥2 → "organizing thoughts" per statusText.
            "Reva is organizing thoughts…",
            "Reva is composing a reply…",
        ])
        // The `tool` step carries the backend's Chinese label verbatim (spliced by
        // the View into the "Working: %@…" template).
        XCTAssertEqual(model.thinkingSteps[1].labelDetail, "查询健康数据")
        // After `done`, every step is settled (nothing left spinning).
        XCTAssertTrue(model.thinkingSteps.allSatisfy { $0.state == .done })

        // A new turn resets the trace at `send()` start (secondTurn script).
        await model.send("再问一次")
        // Only the new turn's single status step survives — old steps were cleared.
        XCTAssertEqual(model.thinkingSteps.map { $0.labelKey }, ["Reva received your message…"])
    }

    /// De-dup: a repeated identical `status` event must not append a duplicate row.
    @MainActor
    func testConsecutiveIdenticalStatusEventsDoNotDuplicateThinkingStep() async {
        let script: [AgentStreamEvent] = [
            .status(stage: "tool", detail: "查询健康数据", round: 1),
            .status(stage: "tool", detail: "查询健康数据", round: 1),
            .done(
                conversationID: 1, messageID: 1, completionStatus: "complete",
                model: "m", sourcesUsed: [], toolsUsed: [], elapsedMs: 5, llmRounds: 1
            ),
        ]
        let model = AgentChatViewModel(streamService: ScriptedStreamService(scripts: [script]))

        await model.send("查一下")

        XCTAssertEqual(model.thinkingSteps.count, 1)
        XCTAssertEqual(model.thinkingSteps.first?.labelDetail, "查询健康数据")
    }

    func testAgentModelCatalogIncludesAliyunTokenPlanModels() {
        let options = AgentModelCatalog.defaultOptions
        let optionIDs = Set(options.map(\.id))
        let shownManualModelIDs = [
            "claude-opus-4.7",
            "gemini-3.1-pro",
            "gpt-5.5",
            "qwen3.8-max-preview",
            "qwen3.7-plus",
            "qwen3.7-max",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "kimi-k2.7-code",
            "glm-5.2",
            "minimax-m2.5",
        ]
        let hiddenLowerModelIDs = [
            "commercial/GPT-5.4",
            "commercial/GPT-5.1",
            "commercial/DeepSeek-R1",
            "commercial/DeepSeek-V3.2",
            "commercial/Claude-Opus-4.7",
            "commercial/Gemini-3.1-Pro-Preview",
            "commercial/GPT-5.5",
            "qwen3.6-plus",
            "qwen3.6-flash",
            "deepseek-v3.2",
            "kimi-k2.6",
            "kimi-k2.5",
            "glm-5.1",
            "glm-5",
        ]

        for modelID in shownManualModelIDs {
            XCTAssertTrue(optionIDs.contains(modelID), "\(modelID) should be in Mac model picker")
        }
        for modelID in hiddenLowerModelIDs {
            XCTAssertFalse(optionIDs.contains(modelID), "\(modelID) should not be in Mac model picker")
        }
        // 图像生成模型不进对话 picker
        XCTAssertFalse(optionIDs.contains("qwen-image-2.0"))
        XCTAssertFalse(optionIDs.contains("qwen-image-2.0-pro"))
        XCTAssertFalse(optionIDs.contains("wan2.7-image"))
        XCTAssertFalse(optionIDs.contains("wan2.7-image-pro"))
        XCTAssertEqual(options.first(where: { $0.id == "qwen3.7-plus" })?.provider, "阿里 TokenPlan")
        XCTAssertEqual(optionIDs.count, options.count)
    }

    func testCommandPaletteBuildsCoreDesktopCommands() {
        let commands = DesktopCommandPalette.defaultCommands(language: .zh)

        XCTAssertTrue(commands.contains { $0.intent == .navigate(.agent) && $0.title == "问助手" })
        XCTAssertTrue(commands.contains { $0.intent == .navigate(.genetics) && $0.title == "打开基因" })
        let hasDataConnections = commands.contains { command in
            command.intent == .navigate(.dataConnections) && command.title == "打开数据连接与授权"
        }
        XCTAssertTrue(hasDataConnections)
        XCTAssertTrue(commands.contains { $0.intent == .quickPrompt && $0.title == "基于当前上下文问助手" })
    }

    func testSidebarIncludesDataConnectionsAsGovernedDataSurface() {
        XCTAssertTrue(SidebarDestination.sidebarVisible.contains(.dataConnections))
        XCTAssertEqual(SidebarDestination.dataConnections.title(language: .zh), "数据连接与授权")
        XCTAssertEqual(SidebarDestination.dataConnections.systemImage, "shield.lefthalf.filled")
    }

    func testCommandPaletteFiltersByTitleSubtitleAndKeywords() {
        let commands = DesktopCommandPalette.defaultCommands(language: .zh)

        let geneMatches = DesktopCommandPalette.filter(commands, query: "wegene")
        XCTAssertEqual(geneMatches.first?.intent, .navigate(.genetics))

        let recordMatches = DesktopCommandPalette.filter(commands, query: "饮食")
        XCTAssertTrue(recordMatches.contains { $0.intent == .navigate(.record) })

        let emptyMatches = DesktopCommandPalette.filter(commands, query: "   ")
        XCTAssertEqual(emptyMatches.map(\.id), commands.map(\.id))
    }

    func testWorkspaceContextFactoryBuildsHealthRecordContext() {
        let record = DesktopRecordMetric(
            id: 625,
            type: "diet",
            title: "晚餐",
            value: .int(650),
            unit: "kcal",
            category: "nutrition",
            recordDate: "2026-05-23"
        )

        let item = DesktopWorkspaceContextFactory.contextItem(for: record)

        XCTAssertEqual(item.sourceID, "health_record:625")
        XCTAssertEqual(item.sourceKind, "health_record")
        XCTAssertEqual(item.title, "晚餐")
        XCTAssertEqual(item.payload["type"], "diet")
        XCTAssertEqual(item.payload["display_value"], "650 kcal")
    }

    func testWorkspaceContextFactoryBuildsTrendContextForAgentHandoff() {
        let trend = DesktopHealthTrendContext(
            kind: .diet,
            rangeDays: 7,
            unit: "kcal",
            total: 4200,
            average: 600,
            recordCount: 5,
            points: [
                DesktopHealthTrendPoint(date: "2026-05-18", value: 500, count: 1),
                DesktopHealthTrendPoint(date: "2026-05-19", value: 700, count: 2)
            ],
            latestRecord: DesktopRecordMetric(
                id: 625,
                type: "diet",
                title: "晚餐",
                value: .int(650),
                unit: "kcal",
                category: "nutrition",
                recordDate: "2026-05-19"
            )
        )

        let item = DesktopWorkspaceContextFactory.contextItem(for: trend)
        let prompt = DesktopWorkspaceContextFactory.prompt(for: trend)

        XCTAssertEqual(item.sourceID, "health_trend:diet:7d")
        XCTAssertEqual(item.sourceKind, "health_trend")
        XCTAssertEqual(item.payload["range_days"], "7")
        XCTAssertEqual(item.payload["points"], "2026-05-18=500 kcal(count 1); 2026-05-19=700 kcal(count 2)")
        XCTAssertEqual(item.payload["latest_record"], "晚餐 · 650 kcal · 2026-05-19")
        XCTAssertTrue(prompt.contains("饮食趋势"))
        XCTAssertTrue(prompt.contains("7 天"))
        XCTAssertTrue(prompt.contains("2026-05-18=500 kcal"))
    }

    func testMarkdownRenderSupportPreservesHeadingsBoldAndNormalizesLists() {
        let markdown = """
        # 7天饮食趋势分析

        **趋势观察**
          - 5/19 偏高
          - 5/24 偏低

        | 维度 | 建议 |
        |---|---|
        | 饮食 | 暂不调整 |
        """

        let sanitized = MarkdownRenderSupport.sanitizedForSwiftUI(markdown)

        XCTAssertTrue(sanitized.contains("# 7天饮食趋势分析"))
        XCTAssertTrue(sanitized.contains("**趋势观察**"))
        XCTAssertTrue(sanitized.contains("- 5/19 偏高"))
        XCTAssertFalse(sanitized.contains("|---|---|"))
    }

    func testMarkdownRenderSupportReadableFallbackRemovesRawMarkdownMarkers() {
        let markdown = """
        ## 七天饮食趋势分析

        **趋势观察**

        | 维度 | 建议 |
        |---|---|
        | 饮食 | 暂不调整 |

        1. **先解决记录问题**
        """

        let fallback = MarkdownRenderSupport.readableFallback(markdown)

        XCTAssertTrue(fallback.contains("七天饮食趋势分析"))
        XCTAssertTrue(fallback.contains("趋势观察"))
        XCTAssertTrue(fallback.contains("饮食  暂不调整"))
        XCTAssertFalse(fallback.contains("##"))
        XCTAssertFalse(fallback.contains("**"))
        XCTAssertFalse(fallback.contains("|---"))
    }

    func testMarkdownRenderSupportBuildsReadableBlocks() {
        let markdown = """
        ## 七天饮食趋势分析

        **关键结论**：先补齐记录。

        - 今天饮水不足
        1. 晚饭后散步 20 分钟

        | 维度 | 建议 |
        |---|---|
        | 饮食 | 暂不调整 |
        """

        let blocks = MarkdownRenderSupport.blocks(from: markdown)

        XCTAssertEqual(blocks.first, .heading(level: 2, text: "七天饮食趋势分析"))
        XCTAssertTrue(blocks.contains(.paragraph("**关键结论**：先补齐记录。")))
        XCTAssertTrue(blocks.contains(.bullet("今天饮水不足")))
        XCTAssertTrue(blocks.contains(.numbered(index: "1", text: "晚饭后散步 20 分钟")))
        XCTAssertTrue(blocks.contains(.tableRow(["维度", "建议"])))
        XCTAssertTrue(blocks.contains(.tableRow(["饮食", "暂不调整"])))
    }

    func testMarkdownRenderSupportBlocksCacheReturnsConsistentResult() {
        // blocks() 现在带 NSCache(修聊天逐 token 重渲染卡顿)。缓存必须透明:
        // 同输入重复调用结果完全一致;不同输入互不串。
        let md1 = "## 标题\n\n- 第一条\n- 第二条"
        let md2 = "普通段落,没有标记。"
        let first = MarkdownRenderSupport.blocks(from: md1)
        let cached = MarkdownRenderSupport.blocks(from: md1) // 命中缓存
        XCTAssertEqual(first, cached)
        XCTAssertEqual(first.first, .heading(level: 2, text: "标题"))
        // 不同 key 不串
        XCTAssertEqual(MarkdownRenderSupport.blocks(from: md2), [.paragraph("普通段落,没有标记。")])
        // 再取一次 md1 仍一致(缓存未被 md2 污染)
        XCTAssertEqual(MarkdownRenderSupport.blocks(from: md1), first)
    }

    func testMarkdownRenderSupportBuildsCompactCardPreviewWithoutRawMarkers() {
        let markdown = """
        ## 🎯 核心目标

        **补剂**：5-MTHF（活性叶酸）400-800 μg/天。
        - 4 周复查 Hcy
        - 若 ALT/AST 异常先暂停
        """

        let preview = MarkdownRenderSupport.compactPreview(from: markdown, maxLines: 3)

        XCTAssertFalse(preview.contains("##"))
        XCTAssertFalse(preview.contains("**"))
        XCTAssertFalse(preview.contains("- "))
        XCTAssertTrue(preview.contains("核心目标"))
        XCTAssertTrue(preview.contains("补剂"))
        XCTAssertTrue(preview.contains("4 周复查 Hcy"))
    }

    func testWorkspaceContextFactoryBuildsKnowledgeDocumentAndJobContext() {
        let document = KnowledgeDocumentSummary(
            docID: "dedao:100-ecc79a079a92",
            docType: "claim",
            title: "LDL-C/ApoB 轨迹",
            summary: "血脂风险以 LDL-C/ApoB 轨迹为锚点",
            evidenceLevel: "B",
            confidence: 0.77,
            sources: ["dedao", "pubmed:30586774"]
        )
        let job = DesktopJobSummary(
            id: 91,
            jobType: "system_kb_rebuild",
            status: "running",
            progress: 40,
            sourceKind: "dedao_folder",
            sourceName: "down-dedao",
            sourceHash: "sha256:abc"
        )

        let documentItem = DesktopWorkspaceContextFactory.contextItem(for: document)
        let jobItem = DesktopWorkspaceContextFactory.contextItem(for: job)

        XCTAssertEqual(documentItem.sourceID, "knowledge_document:dedao:100-ecc79a079a92")
        XCTAssertEqual(documentItem.sourceKind, "knowledge_document")
        XCTAssertEqual(documentItem.payload["evidence_level"], "B")
        XCTAssertEqual(documentItem.payload["sources"], "dedao, pubmed:30586774")
        XCTAssertEqual(jobItem.sourceID, "desktop_job:91")
        XCTAssertEqual(jobItem.sourceKind, "desktop_job")
        XCTAssertEqual(jobItem.payload["progress"], "40")
    }

    func testKnowledgeWorkspacePresentationFiltersDocumentsByTypeAndQuery() {
        let documents = [
            KnowledgeDocumentSummary(
                docID: "claim:mthfr",
                docType: "claim",
                title: "MTHFR 叶酸边界",
                summary: "Hcy 和叶酸/B12 用于复查闭环。",
                evidenceLevel: "B",
                confidence: 0.82,
                sources: ["dedao:genetics"]
            ),
            KnowledgeDocumentSummary(
                docID: "article:lipids",
                docType: "article",
                title: "ApoB 与血脂轨迹",
                summary: "LDL-C/ApoB 用于长期风险观察。",
                evidenceLevel: "A",
                confidence: 0.91,
                sources: ["pubmed:30586774"]
            ),
            KnowledgeDocumentSummary(
                docID: "entity:gene:MTHFR",
                docType: "entity",
                title: "MTHFR",
                summary: "叶酸代谢相关基因实体。",
                evidenceLevel: nil,
                confidence: nil,
                sources: ["down-dedao-llm-wiki"]
            )
        ]

        XCTAssertEqual(
            KnowledgeWorkspacePresentation.filteredDocuments(
                documents,
                query: "叶酸",
                filter: .all
            ).map(\.docID),
            ["claim:mthfr", "entity:gene:MTHFR"]
        )
        XCTAssertEqual(
            KnowledgeWorkspacePresentation.filteredDocuments(
                documents,
                query: "",
                filter: .claims
            ).map(\.docID),
            ["claim:mthfr"]
        )
        XCTAssertEqual(
            KnowledgeWorkspacePresentation.filteredDocuments(
                documents,
                query: "apoB",
                filter: .articles
            ).map(\.docID),
            ["article:lipids"]
        )
    }

    func testFileIntakeClassifiesAndHashesGenomeAndDedaoSources() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("health-mac-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let genome = tempDir.appendingPathComponent("wegene.txt")
        try "rsid\tchromosome\tposition\tgenotype\nrs123\t1\t1\tAA\n".write(to: genome, atomically: true, encoding: .utf8)
        let dedao = tempDir.appendingPathComponent("down-dedao", isDirectory: true)
        try FileManager.default.createDirectory(at: dedao, withIntermediateDirectories: true)

        let genomeItem = try await FileIntakeService.inspect(url: genome)
        let dedaoItem = try await FileIntakeService.inspect(url: dedao)

        XCTAssertEqual(genomeItem.sourceKind, .genomeText)
        XCTAssertTrue(genomeItem.sha256.hasPrefix("sha256:"))
        XCTAssertEqual(dedaoItem.sourceKind, .dedaoFolder)
    }

    /// A plain photo (jpg/png/heic/webp) must NOT classify as `.medicalFile` — that
    /// force-routed every image to lab-report OCR and hard-failed 「记录午餐」+photo
    /// with a 422 「无法识别」. It must classify as `.image` so it flows to the agent's
    /// multimodal/vision path instead.
    func testFileIntakeClassifiesPhotoAsImageNotMedicalFile() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("health-mac-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        for ext in ["jpg", "jpeg", "png", "heic", "webp"] {
            let photo = tempDir.appendingPathComponent("lunch.\(ext)")
            try Data([0x01, 0x02, 0x03, 0x04]).write(to: photo)
            let item = try await FileIntakeService.inspect(url: photo)
            XCTAssertEqual(item.sourceKind, .image, "\(ext) should classify as .image")
            XCTAssertNotEqual(item.sourceKind, .medicalFile, "\(ext) must not force-route to lab OCR")
        }
    }

    /// A PDF here is almost always a lab report / medical document, so it must stay
    /// `.medicalFile` and remain eligible for the medical-exam import path.
    func testFileIntakeClassifiesPDFAsMedicalFile() async throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("health-mac-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let pdf = tempDir.appendingPathComponent("report.pdf")
        try Data("%PDF-1.4".utf8).write(to: pdf)
        let item = try await FileIntakeService.inspect(url: pdf)
        XCTAssertEqual(item.sourceKind, .medicalFile)
    }

    func testRecordClientPostsQuickRecordText() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/quick-record")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: String]
            XCTAssertEqual(body?["text"], "喝水500")
            let data = #"{"type":"water","message":"已记录饮水 500ml","success":true}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).quickRecord(text: "喝水500")

        XCTAssertEqual(result.type, "water")
        XCTAssertTrue(result.success)
    }

    func testRecordClientDecodesSevereBloodPressureQuickRecordGuidance() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/quick-record")
            let data = ##"{"type":"bp","message":"已记录血压 185/85 mmHg","success":true,"category":"血压严重升高","category_color":"#FF3B30","safety_guidance":{"severity":"high","title":"血压严重升高，请复测","recheck_instruction":"请静坐至少 1 分钟后复测。","emergency_instruction":"若同时出现胸痛，请立即拨打急救电话。","action_path":"/blood-pressure"}}"##.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).quickRecord(text: "血压185/85")

        XCTAssertEqual(result.category, "血压严重升高")
        XCTAssertEqual(result.safetyGuidance?.severity, "high")
        XCTAssertTrue(result.displayMessage.contains("复测"))
        XCTAssertTrue(result.displayMessage.contains("胸痛"))
    }

    func testRecordClientParsesVoiceDietDraft() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/diet/voice/parse")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: String]
            XCTAssertEqual(body?["raw_text"], "晚饭吃了鸡胸肉和米饭")
            XCTAssertEqual(body?["meal_type"], "dinner")
            let data = """
            {
              "raw_text": "晚饭吃了鸡胸肉和米饭",
              "meal_type": "dinner",
              "meal_type_label": "晚餐",
              "foods": [{"name": "鸡胸肉", "quantity": 120, "unit": "g", "calories": 198, "protein": 37}],
              "risk_tags": [],
              "confidence": 0.86,
              "needs_confirmation": false,
              "clarifying_question": null,
              "parser_version": "voice-1.0"
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let draft = try await RecordClient(apiClient: client).parseVoiceDietDraft(
            rawText: "晚饭吃了鸡胸肉和米饭",
            mealType: "dinner"
        )

        XCTAssertEqual(draft.mealType, "dinner")
        XCTAssertEqual(draft.mealTypeLabel, "晚餐")
        XCTAssertEqual(draft.foods.first?.name, "鸡胸肉")
        XCTAssertFalse(draft.needsConfirmation)
    }

    func testSupplementProductLibraryClientSearchesProductsForPickerAutofill() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/supplements/products?search=fish%20oil&limit=10")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token")
            let data = """
            {
              "total": 1,
              "items": [
                {
                  "id": 12,
                  "brand": "Nordic Naturals",
                  "name": "Ultimate Omega",
                  "category": "other",
                  "description": "High potency omega-3",
                  "serving_size": "2 softgels",
                  "price_cny": 268.5,
                  "rating": 4.8,
                  "health_tags": ["心血管", "炎症"],
                  "ingredients": [{"name": "EPA", "amount": "650mg"}],
                  "currency": "CNY",
                  "platform": "iherb",
                  "is_active": true
                }
              ]
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await SupplementProductLibraryClient(apiClient: client).searchProducts(query: "fish oil")

        XCTAssertEqual(result.total, 1)
        XCTAssertEqual(result.items.first?.id, 12)
        XCTAssertEqual(result.items.first?.displayName, "Nordic Naturals Ultimate Omega")
        XCTAssertEqual(result.items.first?.servingSize, "2 softgels")
        XCTAssertEqual(result.items.first?.priceCny, 268.5)
        XCTAssertEqual(result.items.first?.healthTags, ["心血管", "炎症"])
    }

    func testRecordClientPostsStructuredWeightToTypedEndpoint() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/weight/records")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertNotNil(body?["record_date"] as? String)
            XCTAssertEqual(body?["weight"] as? Double, 70.2)
            let data = #"{"id":12,"user_id":3,"record_date":"2026-05-23","weight":70.2}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordWeight(weightKg: 70.2)

        XCTAssertEqual(result.type, "weight")
        XCTAssertTrue(result.success)
        XCTAssertEqual(result.message, "已记录体重 70.2kg")
        XCTAssertEqual(result.recordID, 12)
        XCTAssertEqual(result.undoPath, "weight/records/12")
    }

    func testRecordClientDeletesSavedStructuredRecordUsingUndoPath() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/weight/records/12")
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data())
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        try await RecordClient(apiClient: client).undoSavedRecord(path: "weight/records/12")
    }

    func testRecordClientFetchesFrequentSupplementsForOneTapCheckin() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/supplements/me/frequent?limit=8&days=30")
            let data = """
            [
              {"supplement_id": 7, "name": "维生素D3", "dosage": "2000IU", "timing": "早餐后", "count": 21},
              {"supplement_id": 3, "name": "鱼油", "dosage": null, "timing": null, "count": 9}
            ]
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).fetchFrequentSupplements()

        XCTAssertEqual(result.count, 2)
        XCTAssertEqual(result.first?.supplementID, 7)
        XCTAssertEqual(result.first?.name, "维生素D3")
        XCTAssertEqual(result.first?.dosage, "2000IU")
        XCTAssertEqual(result.first?.count, 21)
        XCTAssertNil(result.last?.dosage)
    }

    func testRecordClientFetchesFrequentWaterForOneTapLogging() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/water/records/me/frequent?limit=6&days=30")
            let data = #"[{"amount_ml": 300, "drink_type": "水", "count": 40}, {"amount_ml": 200, "drink_type": "咖啡", "count": 5}]"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).fetchFrequentWater()

        XCTAssertEqual(result.count, 2)
        XCTAssertEqual(result.first?.amountMl, 300)
        XCTAssertEqual(result.first?.drinkType, "水")
        XCTAssertEqual(result.last?.drinkType, "咖啡")
    }

    func testRecordClientChecksInFrequentSupplementForToday() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/supplements/records/batch")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertNotNil(body?["record_date"] as? String)
            let checkins = body?["checkins"] as? [[String: Any]]
            XCTAssertEqual(checkins?.first?["supplement_id"] as? Int, 7)
            XCTAssertEqual(checkins?.first?["taken"] as? Bool, true)
            let data = #"{"message":"批量打卡成功","results":[{"supplement_id":7,"action":"created"}]}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).checkinSupplement(supplementID: 7, name: "维生素D3")

        XCTAssertEqual(result.type, "supplement")
        XCTAssertTrue(result.success)
        XCTAssertEqual(result.message, "已为今天补剂打卡：维生素D3")
        XCTAssertNil(result.undoPath)
    }

    func testRecordClientLogsFrequentWaterWithDrinkType() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/water/records")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["amount"] as? Int, 200)
            XCTAssertEqual(body?["drink_type"] as? String, "咖啡")
            let data = #"{"id":55}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordWater(amountMl: 200, drinkType: "咖啡")

        XCTAssertEqual(result.message, "已记录饮水 200ml 咖啡")
        XCTAssertEqual(result.undoPath, "water/records/55")
    }

    func testStructuredRecordDraftValidatesAndPreviewsSneezeCount() {
        XCTAssertFalse(StructuredRecordDraft(type: .sneeze, sneezeCount: "").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .sneeze, sneezeCount: "0").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .sneeze, sneezeCount: "abc").canSubmit)
        let draft = StructuredRecordDraft(type: .sneeze, sneezeCount: "7")
        XCTAssertTrue(draft.canSubmit)
        XCTAssertEqual(draft.previewText, "记录打喷嚏 7 次")
    }

    func testRecordClientPostsSneezeCountToCheckinEndpoint() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/checkin/")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertNotNil(body?["checkin_date"] as? String)
            XCTAssertEqual(body?["sneeze_count"] as? Int, 9)
            let data = #"{"id":31}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordSneeze(count: 9)

        XCTAssertEqual(result.type, "sneeze")
        XCTAssertTrue(result.success)
        XCTAssertEqual(result.message, "已记录今天打喷嚏 9 次")
        XCTAssertEqual(result.recordID, 31)
    }

    func testStructuredRecordDraftValidatesAndPreviewsExercise() {
        XCTAssertFalse(StructuredRecordDraft(type: .exercise, exerciseType: "", reps: "20").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .exercise, exerciseType: "俯卧撑").canSubmit) // no reps/duration
        let reps = StructuredRecordDraft(type: .exercise, exerciseType: "俯卧撑", reps: "20", sets: "3")
        XCTAssertTrue(reps.canSubmit)
        XCTAssertEqual(reps.previewText, "记录运动：俯卧撑 20个×3组")
        let single = StructuredRecordDraft(type: .exercise, exerciseType: "俯卧撑", reps: "15", sets: "1")
        XCTAssertEqual(single.previewText, "记录运动：俯卧撑 15个")
        let dur = StructuredRecordDraft(type: .exercise, exerciseType: "跑步", exerciseDuration: "30")
        XCTAssertTrue(dur.canSubmit)
        XCTAssertEqual(dur.previewText, "记录运动：跑步 30分钟")
    }

    func testStructuredRecordDraftConvertsAndPreviewsBloodGlucose() {
        // mmol/L → mg/dL conversion (×18.0182) for the backend.
        let mmol = StructuredRecordDraft(type: .bloodGlucose, glucoseValue: "5.5", glucoseUnit: "mmol")
        XCTAssertTrue(mmol.canSubmit)
        XCTAssertEqual(mmol.glucoseMgDl ?? 0, 99.1, accuracy: 0.1)
        XCTAssertEqual(mmol.previewText, "记录血糖 5.5 mmol/L")
        let mgdl = StructuredRecordDraft(type: .bloodGlucose, glucoseValue: "100", glucoseUnit: "mgdl")
        XCTAssertEqual(mgdl.glucoseMgDl ?? 0, 100, accuracy: 0.001)
        XCTAssertEqual(mgdl.previewText, "记录血糖 100 mg/dL")
        // Out of range rejected.
        XCTAssertNil(StructuredRecordDraft(type: .bloodGlucose, glucoseValue: "0.5", glucoseUnit: "mmol").glucoseMgDl)
        XCTAssertFalse(StructuredRecordDraft(type: .bloodGlucose, glucoseValue: "abc").canSubmit)
    }

    func testStructuredRecordDraftPreviewsExcretion() {
        let bowel = StructuredRecordDraft(type: .excretion, excretionType: "bowel", stoolType: "4")
        XCTAssertTrue(bowel.canSubmit)
        XCTAssertEqual(bowel.previewText, "记录排泄：大便（Bristol 4）")
        let urine = StructuredRecordDraft(type: .excretion, excretionType: "urine")
        XCTAssertEqual(urine.previewText, "记录排泄：小便")
    }

    func testRecordClientPostsBloodGlucoseReading() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/cgm/readings")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["glucose_mg_dl"] as? Double, 99.1)
            XCTAssertEqual(body?["source"] as? String, "manual")
            XCTAssertNotNil(body?["measured_at"] as? String)
            let data = #"{"id":12,"measured_at":"2026-06-02T09:00:00Z","glucose_mg_dl":99.1}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordBloodGlucose(mgDl: 99.1, displayText: "5.5 mmol/L")
        XCTAssertEqual(result.type, "blood_glucose")
        XCTAssertEqual(result.message, "已记录血糖 5.5 mmol/L")
    }

    func testRecordClientPostsExcretionRecord() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/excretion/records")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["type"] as? String, "bowel")
            XCTAssertEqual(body?["stool_type"] as? Int, 4)
            XCTAssertNotNil(body?["record_date"] as? String)
            let data = #"{"id":9,"record_date":"2026-06-02","type":"bowel"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordExcretion(type: "bowel", stoolType: 4, notes: nil)
        XCTAssertEqual(result.type, "excretion")
        XCTAssertEqual(result.undoPath, "excretion/records/9")
    }

    func testStructuredRecordDraftValidatesAndPreviewsMood() {
        XCTAssertFalse(StructuredRecordDraft(type: .mood, moodScore: "0").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .mood, moodScore: "11").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .mood, moodScore: "abc").canSubmit)
        let bare = StructuredRecordDraft(type: .mood, moodScore: "7")
        XCTAssertTrue(bare.canSubmit)
        XCTAssertEqual(bare.previewText, "记录心情 7/10")
        let noted = StructuredRecordDraft(type: .mood, moodScore: "8", moodNote: "睡得好")
        XCTAssertEqual(noted.previewText, "记录心情 8/10：睡得好")
    }

    func testMedicationDraftIsChipOnlyNotFormSubmittable() {
        XCTAssertFalse(StructuredRecordDraft(type: .medication).canSubmit)
        XCTAssertEqual(StructuredRecordDraft(type: .medication).previewText, "")
    }

    func testRecordClientFetchesMyMedications() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/medication/medications/me?active_only=true")
            let data = """
            [{"id": 4, "name": "莫米松", "dosage": "每侧2喷", "frequency": "每日一次", "is_active": true}]
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let meds = await RecordClient(apiClient: client).fetchMyMedications()
        XCTAssertEqual(meds.count, 1)
        XCTAssertEqual(meds.first?.id, 4)
        XCTAssertEqual(meds.first?.name, "莫米松")
        XCTAssertEqual(meds.first?.dosage, "每侧2喷")
    }

    func testRecordClientDecodesMedicationSafetyAlertsForMacSurface() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/medication/medications/me?active_only=true")
            let data = """
            [{
              "id": 9,
              "name": "卡马西平",
              "dosage": "100mg",
              "frequency": "每日一次",
              "safety_alerts": [{
                "rule_id": "pgx.cpic.hla-b_卡马西平",
                "category": "pgx",
                "severity": {"label": "critical", "label_zh": "紧急", "value": 4},
                "title": "HLA-B × 卡马西平",
                "message": "携带 HLA-B 风险等位基因时，卡马西平相关严重皮肤不良反应风险升高。",
                "action": "请先与医生或药师确认，不要自行调整用药。"
              }]
            }]
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let meds = await RecordClient(apiClient: client).fetchMyMedications()

        XCTAssertEqual(meds.first?.safetyAlerts.count, 1)
        XCTAssertEqual(meds.first?.safetyAlerts.first?.title, "HLA-B × 卡马西平")
        XCTAssertEqual(meds.first?.safetyAlerts.first?.severity.labelZH, "紧急")
        XCTAssertEqual(meds.first?.safetyAlertSummary, "紧急 · HLA-B × 卡马西平")
    }

    func testRecordClientLogsMedicationDose() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/medication/logs")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["medication_id"] as? Int, 4)
            XCTAssertEqual(body?["status"] as? String, "taken")
            XCTAssertEqual(body?["actual_dosage"] as? String, "每侧2喷")
            XCTAssertNotNil(body?["taken_time"] as? String)
            let data = #"{"id":88,"medication_id":4,"taken_date":"2026-06-02","taken_time":"09:00","status":"taken"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).logMedication(medicationID: 4, name: "莫米松", dosage: "每侧2喷")
        XCTAssertEqual(result.type, "medication")
        XCTAssertEqual(result.message, "已记录服药：莫米松 每侧2喷")
        XCTAssertEqual(result.undoPath, "medication/logs/88")
    }

    func testRecordClientPostsMoodRecord() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/mood/records")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["mood_score"] as? Int, 8)
            XCTAssertEqual(body?["journal"] as? String, "睡得好")
            XCTAssertNotNil(body?["record_date"] as? String)
            let data = #"{"id":21}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordMood(score: 8, note: "睡得好")
        XCTAssertEqual(result.type, "mood")
        XCTAssertEqual(result.message, "已记录心情 8/10")
    }

    func testStructuredRecordDraftValidatesAndPreviewsNasalWash() {
        XCTAssertFalse(StructuredRecordDraft(type: .nasalWash, nasalWashCount: "0").canSubmit)
        let draft = StructuredRecordDraft(type: .nasalWash, nasalWashCount: "2")
        XCTAssertTrue(draft.canSubmit)
        XCTAssertEqual(draft.previewText, "记录洗鼻 2 次")
    }

    func testRecordClientPostsExerciseWithAutoIntensity() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/daily-health/exercise")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["exercise_type"] as? String, "俯卧撑")
            XCTAssertEqual(body?["reps"] as? Int, 30)
            XCTAssertEqual(body?["sets"] as? Int, 2)
            XCTAssertEqual(body?["intensity"] as? String, "high") // reps>=30
            XCTAssertNotNil(body?["record_date"] as? String)
            let data = #"{"id":77,"user_id":3,"record_date":"2026-06-02","exercise_type":"俯卧撑"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordExercise(
            exerciseType: "俯卧撑", reps: 30, sets: 2, durationMinutes: nil
        )

        XCTAssertEqual(result.type, "exercise")
        XCTAssertTrue(result.success)
        XCTAssertEqual(result.message, "已记录运动：俯卧撑 30个×2组")
        XCTAssertEqual(result.recordID, 77)
        XCTAssertEqual(result.undoPath, "daily-health/exercise/77")
    }

    func testRecordClientPostsNasalWashToCheckin() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/checkin/")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: Any]
            XCTAssertEqual(body?["nasal_wash_count"] as? Int, 2)
            let data = #"{"id":40}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let result = try await RecordClient(apiClient: client).recordNasalWash(count: 2)

        XCTAssertEqual(result.type, "nasal_wash")
        XCTAssertEqual(result.message, "已记录今天洗鼻 2 次")
    }

    func testStructuredRecordDraftRequiresValidWeightBeforeSubmitting() {
        XCTAssertFalse(StructuredRecordDraft(type: .weight, weightKg: "").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .weight, weightKg: "abc").canSubmit)
        XCTAssertFalse(StructuredRecordDraft(type: .weight, weightKg: "0").canSubmit)
        XCTAssertTrue(StructuredRecordDraft(type: .weight, weightKg: "70.2").canSubmit)
        XCTAssertEqual(StructuredRecordDraft(type: .weight, weightKg: "70.2").previewText, "记录体重 70.2kg")
    }

    func testStructuredRecordDraftBuildsDietPreviewAndRequiresFoodName() {
        let emptyFood = StructuredRecordDraft(type: .diet, foodName: "", calories: "650", protein: "30")
        XCTAssertFalse(emptyFood.canSubmit)

        let draft = StructuredRecordDraft(type: .diet, foodName: "鸡胸肉沙拉", calories: "650", protein: "30")
        XCTAssertTrue(draft.canSubmit)
        XCTAssertEqual(draft.previewText, "记录饮食：鸡胸肉沙拉，650kcal，蛋白质30g")
    }

    func testDesktopJobClientCreatesListsDetailsAndRetriesJobs() async throws {
        var call = 0
        URLProtocolStub.handler = { request in
            call += 1
            if call == 1 {
                XCTAssertEqual(request.url?.path, "/api/v1/desktop/import-jobs")
                let data = #"{"id":1,"job_type":"gene_reanalysis","status":"queued","progress":0,"source_kind":"genome_txt","source_name":"wegene.txt","source_hash":"sha256:abc","request_payload":{"raw_upload_confirmed":true},"result_payload":{},"error_message":null}"#.data(using: .utf8)!
                return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
            }
            if call == 2 {
                XCTAssertEqual(request.url?.path, "/api/v1/desktop/jobs")
                let data = #"[{"id":1,"job_type":"gene_reanalysis","status":"queued","progress":0,"source_kind":"genome_txt","source_name":"wegene.txt","source_hash":"sha256:abc","request_payload":{},"result_payload":{},"error_message":null}]"#.data(using: .utf8)!
                return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
            }
            if call == 3 {
                XCTAssertEqual(request.url?.path, "/api/v1/desktop/jobs/1")
                let data = #"{"id":1,"job_type":"gene_reanalysis","status":"running","progress":35,"source_kind":"genome_txt","source_name":"wegene.txt","source_hash":"sha256:abc","request_payload":{},"result_payload":{"conversation_id":9},"error_message":null}"#.data(using: .utf8)!
                return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
            }
            XCTAssertEqual(request.url?.path, "/api/v1/desktop/jobs/1/retry")
            let data = #"{"id":2,"job_type":"gene_reanalysis","status":"queued","progress":0,"source_kind":"genome_txt","source_name":"wegene.txt","source_hash":"sha256:abc","request_payload":{},"result_payload":{},"error_message":null}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let api = APIClient(baseURL: URL(string: "https://example.test/api/v1")!, tokenProvider: StaticTokenProvider(token: nil), session: URLSession(configuration: .ephemeralWithStub))
        let client = DesktopJobClient(apiClient: api)

        let created = try await client.createJob(.init(
            jobType: "gene_reanalysis",
            sourceKind: "genome_txt",
            sourceName: "wegene.txt",
            sourceHash: "sha256:abc",
            requestPayload: ["raw_upload_confirmed": true]
        ))
        let listed = try await client.listJobs()
        let detail = try await client.getJob(id: 1)
        let retry = try await client.retryJob(id: 1)

        XCTAssertEqual(created.id, 1)
        XCTAssertEqual(listed.count, 1)
        XCTAssertEqual(detail.status, "running")
        XCTAssertEqual(detail.sourceName, "wegene.txt")
        XCTAssertEqual(detail.resultPayload?["conversation_id"]?.intValue, 9)
        XCTAssertEqual(retry.id, 2)
    }

    func testDesktopJobOutcomePresentationSummarizesCompletedFailedAndPendingJobs() {
        let completed = DesktopJobSummary(
            id: 10,
            jobType: "gene_reanalysis",
            status: "completed",
            progress: 100,
            sourceKind: "genome_txt",
            sourceName: "wegene.txt",
            sourceHash: "sha256:abc",
            resultPayload: [
                "conversation_id": 42,
                "action_cards_created": 3,
                "records_imported": 18191,
                "review_required": true
            ],
            completedAt: "2026-05-24T08:00:00"
        )
        let failed = DesktopJobSummary(
            id: 11,
            jobType: "dedao_compile",
            status: "failed",
            progress: 20,
            sourceKind: "dedao_folder",
            sourceName: "down-dedao",
            sourceHash: "sha256:def",
            errorMessage: "source folder missing"
        )
        let pending = DesktopJobSummary(
            id: 12,
            jobType: "medical_import",
            status: "running",
            progress: 45,
            sourceKind: "medical_file",
            sourceName: "lab.pdf"
        )

        let completedPresentation = DesktopJobOutcomePresentation(job: completed)
        let failedPresentation = DesktopJobOutcomePresentation(job: failed)
        let pendingPresentation = DesktopJobOutcomePresentation(job: pending)

        XCTAssertEqual(completedPresentation.state, .completed)
        XCTAssertEqual(completedPresentation.title, "Job completed")
        XCTAssertTrue(completedPresentation.summaryItems.contains(.init(title: "Action cards", value: "3")))
        XCTAssertTrue(completedPresentation.summaryItems.contains(.init(title: "Imported records", value: "18,191")))
        XCTAssertTrue(completedPresentation.nextActions.map(\.title).contains("Review generated results"))
        XCTAssertEqual(completedPresentation.conversationID, 42)

        XCTAssertEqual(failedPresentation.state, .failed)
        XCTAssertEqual(failedPresentation.title, "Job failed")
        XCTAssertTrue(failedPresentation.diagnostic.contains("source folder missing"))
        XCTAssertTrue(failedPresentation.nextActions.map(\.title).contains("Retry job"))

        XCTAssertEqual(pendingPresentation.state, .pending)
        XCTAssertEqual(pendingPresentation.title, "Job still running")
        XCTAssertTrue(pendingPresentation.nextActions.map(\.title).contains("Wait for completion"))
    }

    func testTraceClientDecodesConversationTrace() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/desktop/traces/7")
            let data = """
            {
              "conversation": {"id": 7, "title": "Trace"},
              "messages": [{"id": 1, "role": "user", "content": "hi"}],
              "assistant_message": {"id": 2, "model": "commercial/Claude-Opus-4.7", "elapsed_ms": 7100, "llm_ms": 5800, "llm_rounds": 2, "finish_reason": "stop", "completion_status": "complete"},
              "sources_used": ["系统知识库"],
              "tool_calls": [{"name": "knowledge_search"}],
              "evidence_cards": [{"title": "HbA1c"}],
              "raw_meta": {}
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let api = APIClient(baseURL: URL(string: "https://example.test/api/v1")!, tokenProvider: StaticTokenProvider(token: nil), session: URLSession(configuration: .ephemeralWithStub))

        let trace = try await TraceClient(apiClient: api).fetchTrace(conversationID: 7)

        XCTAssertEqual(trace.conversation.id, 7)
        XCTAssertEqual(trace.assistantMessage.model, "commercial/Claude-Opus-4.7")
        XCTAssertEqual(trace.assistantMessage.elapsedMs, 7100)
        XCTAssertEqual(trace.assistantMessage.llmMs, 5800)
        XCTAssertEqual(trace.assistantMessage.llmRounds, 2)
        XCTAssertEqual(trace.sourcesUsed, ["系统知识库"])
        XCTAssertEqual(trace.toolCalls.first?.name, "knowledge_search")
    }

    func testDesktopBootstrapBuildsWorkspaceSummaries() throws {
        let data = """
        {
          "user": {"id": 3, "name": "itsoso", "email": "i@example.com"},
          "model_preference": {"llm_model_id": "commercial/GPT-5.5"},
          "daily_plan": {"plan_date": "2026-05-23", "actions": [{"action_key": "walk", "title": "散步", "domain": "运动"}]},
          "trajectory": {"focus_domains": ["血脂", "血糖"]},
          "action_cards": [
            {"id": 1, "title": "HbA1c 复查", "status": "active", "priority": 90, "metric_key": "hba1c"},
            {"id": 2, "title": "MTHFR 基因补剂闭环", "status": "active", "priority": 80, "source_type": "genetic_analysis", "metric_key": "hcy"},
            {"id": 3, "title": "得到课程知识库重建", "status": "active", "priority": 70, "source_type": "dedao_kb"},
            {"id": 4, "title": "12 周补剂试验：5-MTHF", "content": "MTHFR C677T 携带者合成叶酸转化效率降低，建议用 Hcy 和叶酸复查闭环。", "status": "active", "priority": 60, "source_type": "orchestrator", "metric_key": "hcy"},
            {"id": 5, "title": "来源覆盖审计", "content": "检查得到、PubMed 和系统证据覆盖。", "status": "active", "priority": 50, "source_type": "source_audit"}
          ],
          "recent_memory": [
            {"id": 1, "object_value": "补剂依从率偏低"},
            {"id": 2, "object_value": "4"}
          ],
          "recent_records_summary": {
            "date": "2026-05-23",
            "range_days": 7,
            "available_ranges": [7, 30],
            "diet": {"today_count": 2, "today_calories": 1350.5, "last_7_count": 5, "last_7_calories": 4200, "last_7_avg_calories": 600, "last_30_count": 9, "last_30_calories": 8200},
            "water": {"today_count": 3, "today_total_ml": 900, "last_7_count": 10, "last_7_total_ml": 7600, "last_7_avg_ml": 1085.7, "last_30_count": 12, "last_30_total_ml": 9600},
            "supplements": {"active_count": 4, "today_count": 1, "last_7_count": 6, "last_7_avg_per_day": 0.9, "last_30_count": 22, "last_30_avg_per_day": 0.7, "adherence_7_pct": 21.4, "top_items": [{"name": "鱼油", "count": 4}]},
            "latest_weight": {"id": 12, "type": "weight", "title": "体重", "value": 70.2, "unit": "kg", "record_date": "2026-05-22"},
            "latest_blood_pressure": {"id": 13, "type": "blood_pressure", "title": "血压", "value": "118/76", "unit": "mmHg", "category": "正常", "record_date": "2026-05-21"},
            "latest_garmin": {"id": 14, "type": "garmin", "title": "Garmin", "record_date": "2026-05-23", "steps": 6840, "sleep_score": 82, "spo2_avg": 96.4, "resting_heart_rate": 52, "hrv": 46.5, "training_readiness_score": 73},
            "recent_records": [
              {"id": 13, "type": "blood_pressure", "title": "血压", "value": "118/76", "unit": "mmHg", "record_date": "2026-05-21"},
              {"id": 12, "type": "weight", "title": "体重", "value": 70.2, "unit": "kg", "record_date": "2026-05-22"}
            ]
          },
          "genomic_summary": {
            "profile_id": 7,
            "provider": "wegene",
            "test_date": "2026-05-15",
            "report_id": "wg-20260515",
            "profile_count": 2,
            "total_variant_count": 3,
            "record_count": 2,
            "high_risk_count": 1,
            "medium_risk_count": 1,
            "low_risk_count": 0,
            "info_count": 0,
            "actionable_count": 2,
            "category_count": 2,
            "top_categories": [
              {"category": "disease_risk", "count": 1, "high_risk_count": 0, "medium_risk_count": 1},
              {"category": "drug_sensitivity", "count": 1, "high_risk_count": 1, "medium_risk_count": 0}
            ],
            "top_findings": [
              {"id": 101, "rsid": "rs1061235", "category": "drug_sensitivity", "gene_name": "HLA-A*31:01", "variant_name": "卡马西平皮肤不良反应", "genotype": "AA", "result_label": "positive", "risk_level": "high", "evidence_level": "screening", "description": "提示用药前需要医生确认。", "variant_nature": "risk"}
            ],
            "profile_summaries": [
              {"profile_id": 7, "provider": "wegene", "test_date": "2026-05-15", "report_id": "wg-20260515", "record_count": 2, "is_active": true, "latest_import": {"status": "done", "raw_record_count": 18191, "known_total": 1200, "matched_count": 2, "duplicate_count": 3, "unknown_count": 11, "unmapped_count": 18176, "missing_count": 1198, "coverage_pct": 0.0, "finished_at": "2026-05-15T10:00:00"}},
              {"profile_id": 6, "provider": "wegene", "test_date": "2026-04-10", "report_id": "wg-20260410", "record_count": 1, "is_active": false, "latest_import": null}
            ],
            "latest_import": {"status": "done", "raw_record_count": 18191, "known_total": 1200, "matched_count": 2, "duplicate_count": 3, "unknown_count": 11, "unmapped_count": 18176, "missing_count": 1198, "coverage_pct": 0.0, "finished_at": "2026-05-15T10:00:00"}
          },
          "knowledge_summary": {
            "document_count": 3,
            "claim_count": 1,
            "entity_count": 1,
            "article_count": 1,
            "edge_count": 1,
            "source_total_count": 2,
            "doc_type_counts": [{"level": "article", "count": 1}, {"level": "claim", "count": 1}, {"level": "entity", "count": 1}],
            "entity_type_counts": [{"level": "gene", "count": 2}],
            "evidence_level_counts": [{"level": "B", "count": 1}],
            "source_counts": [{"source": "dedao:qiuzilong-genetics-07", "count": 3}],
            "local_source_summary": {
              "source_root": "/Users/liqiuhua/work/personal/down-dedao",
              "exists": true,
              "wiki_exists": true,
              "artifacts_exists": true,
              "wiki_markdown_count": 4,
              "artifact_json_count": 12,
              "raw_source_count": 46,
              "linked_document_count": 3,
              "origin_counts": [{"origin": "down-dedao-llm-wiki", "count": 3}],
              "bridge_manifest": {
                "pipeline": "down_dedao_llm_wiki_bridge_v1",
                "source_root": "/Users/liqiuhua/work/personal/down-dedao",
                "compiled_at": "2026-05-23T01:44:15Z"
              }
            },
            "recent_documents": [
              {"doc_id": "claim:c_mthfr_c677t_hcy_folate_boundary", "doc_type": "claim", "title": "MTHFR 叶酸边界", "summary": "Hcy 和叶酸/B12 用于复查闭环。", "evidence_level": "B", "confidence": 0.82, "sources": ["dedao:qiuzilong-genetics-07"]}
            ]
          },
          "active_jobs": [
            {"id": 1, "job_type": "gene_reanalysis", "status": "running", "progress": 40, "source_kind": "genome_txt", "source_name": "wegene.txt", "source_hash": "sha256:a", "request_payload": {}, "result_payload": {}, "error_message": null},
            {"id": 2, "job_type": "dedao_compile", "status": "queued", "progress": 0, "source_kind": "dedao_folder", "source_name": "down-dedao", "source_hash": "sha256:b", "request_payload": {}, "result_payload": {}, "error_message": null},
            {"id": 3, "job_type": "medical_import", "status": "queued", "progress": 0, "source_kind": "medical_file", "source_name": "lab.pdf", "source_hash": "sha256:c", "request_payload": {}, "result_payload": {}, "error_message": null}
          ]
        }
        """.data(using: .utf8)!

        let bootstrap = try JSONDecoder().decode(DesktopBootstrap.self, from: data)
        XCTAssertEqual(bootstrap.recentRecordsSummary.diet?.last30Count, 9)
        XCTAssertEqual(bootstrap.recentRecordsSummary.water?.last30TotalMl, 9600)
        XCTAssertEqual(bootstrap.recentRecordsSummary.latestWeight?.displayValue, "70.2 kg")
        XCTAssertEqual(bootstrap.recentRecordsSummary.latestBloodPressure?.displayValue, "118/76 mmHg")
        XCTAssertEqual(bootstrap.recentRecordsSummary.latestGarmin?.steps, 6840)
        XCTAssertEqual(bootstrap.recentRecordsSummary.recentRecords?.map(\.type), ["blood_pressure", "weight"])
        let dataSummary = bootstrap.workspaceSummary(for: .data)
        let geneticsSummary = bootstrap.workspaceSummary(for: .genetics)
        let knowledgeSummary = bootstrap.workspaceSummary(for: .knowledge)

        XCTAssertEqual(dataSummary.metrics.map(\.title), ["Diet 7d", "Water 7d", "Supplements 7d", "Latest Weight", "Latest BP", "Steps"])
        XCTAssertEqual(dataSummary.metrics.map(\.value), ["4,200 kcal", "7,600 ml", "6", "70.2 kg", "118/76 mmHg", "6,840"])
        XCTAssertEqual(dataSummary.recentRecords.map(\.title), ["血压", "体重"])
        XCTAssertEqual(dataSummary.actionCards.map(\.title), ["HbA1c 复查"])
        XCTAssertEqual(dataSummary.recentMemory.map(\.objectValue), ["补剂依从率偏低"])
        XCTAssertEqual(dataSummary.guidanceRows.map(\.title), ["Refresh recent health data", "Review weekly intake", "Create medical import"])
        XCTAssertEqual(dataSummary.jobs.map(\.id), [3])
        XCTAssertEqual(geneticsSummary.metrics.map(\.title), ["Active Variants", "All Variants", "Profiles", "High Risk", "Medium Risk", "Categories"])
        XCTAssertEqual(geneticsSummary.metrics.map(\.value), ["2", "3", "2", "1", "1", "2"])
        XCTAssertEqual(geneticsSummary.genomicSummary?.profileCount, 2)
        XCTAssertEqual(geneticsSummary.genomicSummary?.profileSummaries.first?.latestImport?.unmappedCount, 18176)
        XCTAssertEqual(geneticsSummary.genomicSummary?.topFindings.first?.geneName, "HLA-A*31:01")
        XCTAssertEqual(geneticsSummary.genomicSummary?.topCategories.map(\.category), ["disease_risk", "drug_sensitivity"])
        XCTAssertEqual(geneticsSummary.actionCards.map(\.title), ["MTHFR 基因补剂闭环", "12 周补剂试验：5-MTHF"])
        XCTAssertEqual(geneticsSummary.guidanceRows.map(\.title), ["Import genome file", "Run risk reanalysis", "Keep clinical boundary"])
        XCTAssertEqual(geneticsSummary.jobs.map(\.id), [1])
        XCTAssertEqual(knowledgeSummary.metrics.map(\.title), ["Documents", "Claims", "Sources", "Edges", "Entity Types"])
        XCTAssertEqual(knowledgeSummary.metrics.map(\.value), ["3", "1", "2", "1", "1"])
        XCTAssertEqual(knowledgeSummary.knowledgeSummary?.docTypeCounts.map(\.level), ["article", "claim", "entity"])
        XCTAssertEqual(knowledgeSummary.knowledgeSummary?.localSourceSummary?.linkedDocumentCount, 3)
        XCTAssertEqual(knowledgeSummary.knowledgeSummary?.localSourceSummary?.bridgeManifest?.pipeline, "down_dedao_llm_wiki_bridge_v1")
        XCTAssertEqual(knowledgeSummary.knowledgeSummary?.recentDocuments.first?.docID, "claim:c_mthfr_c677t_hcy_folate_boundary")
        XCTAssertEqual(knowledgeSummary.actionCards.map(\.title), ["得到课程知识库重建", "来源覆盖审计"])
        XCTAssertEqual(knowledgeSummary.guidanceRows.map(\.title), ["Import Dedao folder", "Rebuild system KB", "Audit source coverage"])
        XCTAssertEqual(knowledgeSummary.guidanceRows.map(\.action), [.importDedaoFolder, .rebuildSystemKnowledgeBase, .auditSourceCoverage])
        XCTAssertEqual(knowledgeSummary.jobs.map(\.id), [2])
    }
}
