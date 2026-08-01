import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ChatTranscriptHTMLTests: XCTestCase {

    // MARK: - escape (XSS 防线核心断言)

    func testEscapeNeutralizesScriptInjection() {
        let raw = "<script>alert('xss')</script>"
        let escaped = ChatTranscriptHTML.escape(raw)
        // 没有任何可执行的尖括号标签残留
        XCTAssertFalse(escaped.contains("<script"))
        XCTAssertFalse(escaped.contains("</script>"))
        XCTAssertFalse(escaped.contains("<"))
        XCTAssertFalse(escaped.contains(">"))
        XCTAssertEqual(escaped, "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;")
    }

    func testEscapeHandlesAmpersandFirst() {
        // & 必须最先转义,否则后插入的实体里的 & 会被二次转义成 &amp;amp;
        XCTAssertEqual(ChatTranscriptHTML.escape("a & b"), "a &amp; b")
        XCTAssertEqual(ChatTranscriptHTML.escape("<a> & </a>"), "&lt;a&gt; &amp; &lt;/a&gt;")
    }

    func testEscapeQuotesForAttributeSafety() {
        XCTAssertEqual(ChatTranscriptHTML.escape("\"hi\" 'there'"), "&quot;hi&quot; &#39;there&#39;")
    }

    func testEscapeLeavesPlainTextUnchanged() {
        XCTAssertEqual(ChatTranscriptHTML.escape("正常的中文文本 123"), "正常的中文文本 123")
    }

    func testEscapeIsIdempotentlySafeOnEmpty() {
        XCTAssertEqual(ChatTranscriptHTML.escape(""), "")
    }

    // MARK: - inline markdown after escape (受控白名单)

    func testInlineMarkdownBoldItalicCode() {
        let escaped = ChatTranscriptHTML.escape("**bold** *it* `c`")
        let html = ChatTranscriptHTML.inlineMarkdown(escaped)
        XCTAssertTrue(html.contains("<strong>bold</strong>"))
        XCTAssertTrue(html.contains("<em>it</em>"))
        XCTAssertTrue(html.contains("<code>c</code>"))
    }

    func testInlineMarkdownLeavesUnclosedMarkerLiteral() {
        let html = ChatTranscriptHTML.inlineMarkdown(ChatTranscriptHTML.escape("a **b"))
        XCTAssertEqual(html, "a **b")
    }

    func testInlineMarkdownDoesNotResurrectEscapedTags() {
        // 用户写的 <b> 已被 escape 成 &lt;b&gt;,inline markdown 不能把它变回真标签
        let escaped = ChatTranscriptHTML.escape("<b>not bold</b> **real**")
        let html = ChatTranscriptHTML.inlineMarkdown(escaped)
        XCTAssertFalse(html.contains("<b>"))
        XCTAssertTrue(html.contains("&lt;b&gt;"))
        XCTAssertTrue(html.contains("<strong>real</strong>"))
    }

    // MARK: - renderMessageBody (整条消息 → 安全 HTML)

    func testRenderMessageBodyEscapesInjectionInParagraph() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "Hello <img src=x onerror=alert(1)>")
        // 安全属性:尖括号被转义,注入不会成为真 DOM 元素/属性(文本里出现 "onerror"
        // 字样是无害的,因为它是被转义的纯文本,不是 HTML 属性)。
        XCTAssertFalse(html.contains("<img"))
        XCTAssertTrue(html.contains("&lt;img"))
        XCTAssertTrue(html.contains("&gt;"))
    }

    func testRenderMessageBodyProducesTableGrid() {
        let md = "| A | B |\n| 1 | 2 |"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("<table>"))
        XCTAssertTrue(html.contains("<th>A</th>"))
        XCTAssertTrue(html.contains("<td>1</td>"))
    }

    func testRenderMessageBodyBulletList() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "- one\n- two")
        XCTAssertTrue(html.contains("<ul>"))
        XCTAssertEqual(html.components(separatedBy: "<li>").count - 1, 2)
    }

    func testRenderMessageBodyHeading() {
        let html = ChatTranscriptHTML.renderMessageBody(markdown: "## Title")
        XCTAssertTrue(html.contains("<h2>Title</h2>"))
    }

    func testOrderedListContinuesAcrossNestedBullets() {
        // LLM 常把每个顶级条目都写成 "1.",插在条目间的子 bullet 会把 <ol> 冲断成单条列表 →
        // 修复前每个都显示 "1."。修复后应连续:后续 <ol> 带 start="2"/"3"。
        let md = "1. 蛋白质\n- 目标\n- 紧急\n1. 木糖醇\n- 行动\n1. 激素\n- 方案"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertTrue(html.contains("start=\"2\""), "第二个顶级条目应从 2 起: \(html)")
        XCTAssertTrue(html.contains("start=\"3\""), "第三个顶级条目应从 3 起: \(html)")
    }

    func testOrderedListResetsAfterHeading() {
        // 标题分界后是新的逻辑列表,应重新从 1 起(不带 start="2"/"3")。
        let md = "1. a\n1. b\n## 新段\n1. c"
        let html = ChatTranscriptHTML.renderMessageBody(markdown: md)
        XCTAssertFalse(html.contains("start=\"3\""), "标题后应重置计数,不应把 c 编成第 3 项: \(html)")
    }

    // MARK: - JS string injection safety

    func testRenderedMessageJSStringEscapesQuotesAndScriptClose() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "id-1",
            role: "assistant",
            bodyHTML: "<p>he said \"hi\" </script></p>\nline2",
            isStreaming: false,
            showCopy: true
        )
        let json = msg.jsonObject
        // 不能存在裸 " 破坏 JS 字符串(除字段分隔符外都应被转义)
        XCTAssertTrue(json.contains("\\\""))
        // </script> 的 < 被编码,避免提前闭合脚本块
        XCTAssertFalse(json.contains("</script>"))
        XCTAssertTrue(json.contains("\\u003c/script"))
        // 换行被编码,不破坏字符串字面量
        XCTAssertFalse(json.contains("\n"))
        XCTAssertTrue(json.contains("\\n"))
    }

    func testRenderedMessageJSONIncludesMessageTimeFields() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "id-1",
            role: "assistant",
            bodyHTML: "<p>hi</p>",
            isStreaming: false,
            showCopy: true,
            sentAtShort: "12:31",
            sentAtFull: "2026年7月14日 12:31",
            sentAtEpochMs: 1_720_960_260_000
        )

        let json = msg.jsonObject

        XCTAssertTrue(json.contains("\"sentAtShort\":\"12:31\""))
        XCTAssertTrue(json.contains("\"sentAtFull\":\"2026年7月14日 12:31\""))
        XCTAssertTrue(json.contains("\"sentAtEpochMs\":1720960260000"))
    }

    func testRenderedMessageKeepsCopyCapabilityForCompletedAssistantReply() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "assistant-copy",
            role: "assistant",
            bodyHTML: "<p>已完成</p>",
            isStreaming: false,
            showCopy: true
        )

        XCTAssertTrue(msg.jsonObject.contains("\"copy\":true"))
        XCTAssertFalse(msg.jsonObject.contains("\"streaming\":true"))
    }

    func testBundledTranscriptCopyActionUsesAccessibleIconOnlyStates() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let resourceURL = packageRoot
            .appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html")
        let source = try String(contentsOf: resourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("copy-btn-icon"))
        XCTAssertTrue(source.contains("aria-label"))
        XCTAssertFalse(source.contains("btn.textContent = \"Copy\""))
    }

    func testBundledTranscriptMessageTimeDoesNotReserveLayoutSpace() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let resourceURL = packageRoot
            .appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html")
        let source = try String(contentsOf: resourceURL, encoding: .utf8)
        let start = try XCTUnwrap(source.range(of: "  .message-time {"))
        let end = try XCTUnwrap(source.range(of: "  .row:hover", range: start.upperBound..<source.endIndex))
        let messageTimeCSS = String(source[start.lowerBound..<end.lowerBound])

        XCTAssertTrue(messageTimeCSS.contains("position: absolute;"))
        XCTAssertTrue(source.contains("row.appendChild(userTime);"))
        XCTAssertFalse(messageTimeCSS.contains("flex: 0 0 auto;"))
        XCTAssertFalse(messageTimeCSS.contains("margin-right: 8px;"))
    }

    func testBundledTranscriptRendersSparseTimeDividers() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let resourceURL = packageRoot
            .appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html")
        let source = try String(contentsOf: resourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("message-time-divider"))
        XCTAssertTrue(source.contains("shouldShowTimeDivider"))
        XCTAssertTrue(source.contains("makeTimeDivider"))
    }

    func testBundledTranscriptSchedulesSettledBottomScrolls() throws {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let resourceURL = packageRoot
            .appendingPathComponent("Sources/HealthAgentMac/Resources/chat-transcript.html")
        let source = try String(contentsOf: resourceURL, encoding: .utf8)

        XCTAssertTrue(source.contains("var scrollSettleDelays = [0, 80, 220, 480, 900];"))
        XCTAssertTrue(source.contains("function scheduleScrollToBottom(force)"))
        XCTAssertTrue(source.contains("scheduleScrollToBottom(true);"))
        XCTAssertTrue(source.contains("scheduleScrollToBottom(false);"))
        XCTAssertFalse(source.contains("scrollToBottomIfNeeded(true);"))
        XCTAssertFalse(source.contains("scrollToBottomIfNeeded(false);"))
    }

    // MARK: - meta footer (模型 · 轮数 · 耗时 / 数据源 / Skill)

    func testMetaFooterRendersModelRoundsElapsed() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "commercial/Claude-Opus-4.7",
            selectedModel: "commercial/Claude-Opus-4.7",
            answerModel: "commercial/Claude-Opus-4.7",
            toolModels: ["qwen3.7-max"],
            fallbackReasons: ["selected_model_tool_stream_failed"],
            elapsedMs: 3500,
            llmRounds: 3,
            sourcesUsed: [],
            toolsUsed: []
        )
        XCTAssertTrue(html.contains("meta-footer"))
        XCTAssertTrue(html.contains("3.5s"))
        XCTAssertTrue(html.contains("3 轮"))
        XCTAssertTrue(html.contains("回答 commercial/Claude-Opus-4.7"))
        XCTAssertTrue(html.contains("工具 qwen3.7-max"))
        XCTAssertTrue(html.contains("工具调用临时切到可靠模型"))
    }

    func testMetaFooterOmitsSingleRound() {
        // llm_rounds == 1 没有展示意义 → 不输出「N 轮」
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 1200, llmRounds: 1, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertTrue(html.contains("1.2s"))
        XCTAssertFalse(html.contains("轮"))
    }

    func testMetaFooterRendersSourcesAsCollapsibleDetails() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil,
            sourcesUsed: ["系统知识库", "Garmin 数据"], toolsUsed: []
        )
        XCTAssertTrue(html.contains("<details"))
        XCTAssertTrue(html.contains("引用 2 项数据"))
        XCTAssertTrue(html.contains("<li>系统知识库</li>"))
        XCTAssertTrue(html.contains("<li>Garmin 数据</li>"))
    }

    func testMetaFooterRendersToolChips() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil,
            sourcesUsed: [], toolsUsed: ["health_query", "health_record"]
        )
        XCTAssertTrue(html.contains("调用 Skill"))
        XCTAssertTrue(html.contains("meta-chip"))
        XCTAssertTrue(html.contains(">health_query<"))
        XCTAssertTrue(html.contains(">health_record<"))
    }

    func testMetaFooterLabelsToolsAsAttemptedWhenTurnFailed() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil,
            sourcesUsed: [], toolsUsed: ["health_record"],
            completionStatus: "error"
        )
        XCTAssertTrue(html.contains("尝试调用 Skill"))
        XCTAssertFalse(html.contains(">调用 Skill<"))
    }

    func testMetaFooterRendersTokenUsage() {
        let usage = LLMUsageProfile(
            calls: 2,
            promptTokens: 1800,
            completionTokens: 420,
            totalTokens: 2220,
            costUsd: 0.0004,
            costCny: 0.0029,
            costEstimated: true,
            tokenplanCreditsEstimate: 3.18,
            tokenplanCostCny: 0.0222,
            tokenplanPaygValueCny: 0.0029,
            tokenplanCostEstimated: true,
            latencyMs: 1200,
            models: ["qwen3.7-plus"],
            providers: ["tokenplan"],
            items: [
                LLMUsageCall(
                    provider: "tokenplan",
                    model: "qwen3.7-plus",
                    caller: "agent.answer",
                    promptTokens: 1000,
                    completionTokens: 300,
                    totalTokens: 1300,
                    costUsd: 0.0003,
                    costCny: 0.0022,
                    costEstimated: true,
                    latencyMs: 900,
                    success: true
                )
            ]
        )
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil,
            elapsedMs: nil,
            llmRounds: nil,
            sourcesUsed: [],
            toolsUsed: [],
            llmUsage: usage
        )
        XCTAssertTrue(html.contains("约¥0.02"))
        XCTAssertTrue(html.contains("套餐折算"))
        XCTAssertTrue(html.contains("Token 输入 1.8k"))
        XCTAssertTrue(html.contains("输出 420"))
        XCTAssertTrue(html.contains("按量价对照 约¥0.01以内"))
        XCTAssertTrue(html.contains("qwen3.7-plus"))
    }

    func testMetaFooterRendersFailedTokenUsageReason() {
        let usage = LLMUsageProfile(
            runID: "run_abc1234567890",
            calls: 1,
            promptTokens: 0,
            completionTokens: 0,
            totalTokens: 0,
            costUsd: 0,
            failedCalls: 1,
            models: ["qwen3.7-plus"],
            providers: ["tokenplan"],
            items: [
                LLMUsageCall(
                    runID: "run_abc1234567890",
                    provider: "tokenplan",
                    model: "qwen3.7-plus",
                    caller: "agent.answer",
                    promptTokens: 0,
                    completionTokens: 0,
                    totalTokens: 0,
                    costUsd: 0,
                    latencyMs: 1200,
                    success: false,
                    errorType: "insufficient_quota",
                    errorCode: "insufficient_quota",
                    errorMessage: "Your token-plan quota has been exhausted.",
                    recoveryAction: "fallback_attempted",
                    recoveryModel: "gpt-5.5"
                )
            ]
        )
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil,
            elapsedMs: nil,
            llmRounds: nil,
            sourcesUsed: [],
            toolsUsed: [],
            llmUsage: usage
        )
        XCTAssertTrue(html.contains("失败 1次"))
        XCTAssertTrue(html.contains("qwen3.7-plus"))
        XCTAssertTrue(html.contains("insufficient_quota"))
        XCTAssertTrue(html.contains("run run_abc1234567890"))
        XCTAssertTrue(html.contains("fallback_attempted"))
        XCTAssertTrue(html.contains("备用 gpt-5.5"))
    }

    func testMetaFooterEmptyWhenNoMeta() {
        // 所有字段为空 → 不输出任何 footer(空字符串,JS 端不渲染)
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: nil, elapsedMs: nil, llmRounds: nil, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertEqual(html, "")
    }

    func testImageGalleryRendersOnlySafeHTTPImages() {
        let html = ChatTranscriptHTML.imageGalleryHTML(urls: [
            "https://example.test/api/v1/upload/files/chat/dinner.jpg",
            "javascript:alert(1)",
            "file:///tmp/private.png",
            "ftp://example.test/private.png",
        ])

        XCTAssertTrue(html.contains("attachment-images"))
        XCTAssertTrue(html.contains("<img"))
        XCTAssertTrue(html.contains("src=\"https://example.test/api/v1/upload/files/chat/dinner.jpg\""))
        XCTAssertFalse(html.contains("javascript:"))
        XCTAssertFalse(html.contains("file:///"))
        XCTAssertFalse(html.contains("ftp://"))
    }

    func testDynamicCardRendersMedicalExamImportResultSafely() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "medical_exam_import_result",
            data: .object([
                "exam_id": .int(321),
                "exam_date": .string("2026-06-18"),
                "hospital_name": .string("Test <Lab>"),
                "items_count": .int(9),
                "abnormal_count": .int(2),
                "conclusions_count": .int(1),
                "conclusion": .string("LDL <script>alert(1)</script> 偏高"),
                "source": .string("image"),
                "review_required": .bool(true),
                "safety_note": .string("OCR/AI 解析结果需要复核后再用于判断。")
            ])
        ))

        XCTAssertTrue(html.contains("dynamic-card"))
        XCTAssertTrue(html.contains("体检报告已导入"))
        XCTAssertTrue(html.contains("图片 OCR"))
        XCTAssertTrue(html.contains("9 项指标"))
        XCTAssertTrue(html.contains("2 项异常"))
        XCTAssertTrue(html.contains("Test &lt;Lab&gt;"))
        XCTAssertFalse(html.contains("<script"))
        XCTAssertTrue(html.contains("&lt;script&gt;alert(1)&lt;/script&gt;"))
        XCTAssertTrue(html.contains("OCR/AI 解析结果需要复核后再用于判断。"))
    }

    func testDynamicCardRendersSafetyCardConservatively() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "safety",
            data: .object([
                "title": .string("今天不建议高强度训练"),
                "severity": .string("high"),
                "summary": .string("睡眠不足且 HRV 明显低于近期基线，建议把训练降级。"),
                "recommendations": .array([
                    .string("改为 20 分钟低强度步行或拉伸"),
                    .string("训练中如有胸闷、头晕、异常心悸，立即停止"),
                    .string("明早根据睡眠和静息心率重新评估"),
                    .string("第四条不应展示")
                ]),
                "boundary": .string("这不是诊断；如出现急性不适或持续症状，请及时就医。"),
                "requires_medical_attention": .bool(true),
                "rule_id": .string("acute_hrv_drop<script>alert(1)</script>")
            ])
        ))

        XCTAssertTrue(html.contains("safety-card"))
        XCTAssertTrue(html.contains("今天不建议高强度训练"))
        XCTAssertTrue(html.contains("高风险"))
        XCTAssertTrue(html.contains("睡眠不足且 HRV 明显低于近期基线，建议把训练降级。"))
        XCTAssertTrue(html.contains("改为 20 分钟低强度步行或拉伸"))
        XCTAssertTrue(html.contains("训练中如有胸闷、头晕、异常心悸，立即停止"))
        XCTAssertTrue(html.contains("明早根据睡眠和静息心率重新评估"))
        XCTAssertFalse(html.contains("第四条不应展示"))
        XCTAssertTrue(html.contains("需要关注"))
        XCTAssertTrue(html.contains("这不是诊断"))
        XCTAssertFalse(html.contains("<script"))
        XCTAssertTrue(html.contains("acute_hrv_drop&lt;script&gt;alert(1)&lt;/script&gt;"))
    }

    func testDynamicCardSafetyCardToleratesMalformedPayload() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "safety",
            data: .object([
                "title": .int(123),
                "severity": .string("unknown"),
                "summary": .object(["text": .string("bad payload")]),
                "recommendations": .string("改为低强度活动"),
                "boundary": .int(456),
                "requires_medical_attention": .string("yes")
            ])
        ))

        XCTAssertTrue(html.contains("安全提醒"))
        XCTAssertTrue(html.contains("安全提示"))
        XCTAssertTrue(html.contains("改为低强度活动"))
        XCTAssertTrue(html.contains("这不是诊断"))
    }

    func testDynamicCardRendersRecordQualityCard() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "record_quality",
            data: .object([
                "domain": .string("diet"),
                "title": .string("午餐已记录 <tag>"),
                "summary": .string("煎牛肉能量碗, 水煮蛋"),
                "metrics": .array([
                    .object(["label": .string("热量"), "value": .string("770kcal")]),
                    .object(["label": .string("蛋白"), "value": .string("30g")])
                ]),
                "progress": .object([
                    "protein_total_g": .int(37),
                    "protein_target_g": .int(112),
                    "remaining_protein_g": .int(75)
                ]),
                "primary_judgement": .string("本餐蛋白质到位；今日蛋白 37/112g。"),
                "personal_cautions": .array([
                    .string("胃溃疡记录在案，冷饮/酸性饮品可能刺激胃。")
                ]),
                "next_action": .string("下一餐补约 45g 蛋白，少油少刺激。"),
                "boundary": .string("健康管理建议，不替代医生诊断、处方或治疗。")
            ])
        ))

        XCTAssertTrue(html.contains("record-quality-card"))
        XCTAssertTrue(html.contains("午餐已记录 &lt;tag&gt;"))
        XCTAssertTrue(html.contains("记录后建议"))
        XCTAssertTrue(html.contains("770kcal"))
        XCTAssertTrue(html.contains("37/112g"))
        XCTAssertTrue(html.contains("还差75g"))
        XCTAssertTrue(html.contains("胃溃疡记录在案"))
        XCTAssertTrue(html.contains("健康管理建议"))
        XCTAssertFalse(html.contains("<tag>"))
    }

    func testDynamicCardRendersSafeRouteAndInlineActionsOnly() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "record_quality",
            data: .object([
                "domain": .string("diet"),
                "title": .string("午餐已记录"),
                "summary": .string("煎牛肉能量碗")
            ]),
            actions: [
                AgentDynamicCardActionDescriptor(
                    id: "show-next-meal",
                    label: "看下一餐建议",
                    action: "ui.inline.expand",
                    payload: .object([
                        "target": .string("next_meal"),
                        "patch": .object([
                            "expanded_sections": .array([.string("next_meal")]),
                            "next_meal_detail": .object([
                                "title": .string("下一餐建议"),
                                "summary": .string("下一餐补约 45g 蛋白，少油少刺激。"),
                                "options": .array([.string("鱼/豆腐 + 熟蔬菜")]),
                                "rationale": .array([.string("今日蛋白仍有缺口")]),
                                "continue_prompt": .string("可以继续在这里问阿衡：如果只能外卖，怎么选。")
                            ])
                        ])
                    ]),
                    style: "primary"
                ),
                AgentDynamicCardActionDescriptor(
                    id: "open-record",
                    label: "调整记录",
                    action: "route.open",
                    payload: .object([
                        "route": .string("/(tabs)/record")
                    ]),
                    style: "secondary"
                ),
                AgentDynamicCardActionDescriptor(
                    id: "unsafe-external",
                    label: "外部链接",
                    action: "route.open",
                    payload: .object([
                        "route": .string("https://example.test")
                    ]),
                    style: "secondary"
                ),
                AgentDynamicCardActionDescriptor(
                    id: "unsafe-action",
                    label: "直接写入",
                    action: "write.execute",
                    payload: .object([
                        "route": .string("/safe-looking")
                    ]),
                    style: "primary"
                )
            ]
        ))

        XCTAssertTrue(html.contains("dynamic-card-actions"))
        XCTAssertTrue(html.contains("看下一餐建议"))
        XCTAssertTrue(html.contains("dynamic-card-inline-action"))
        XCTAssertTrue(html.contains("下一餐补约 45g 蛋白"))
        XCTAssertTrue(html.contains("鱼/豆腐 + 熟蔬菜"))
        XCTAssertTrue(html.contains("/(tabs)/record"))
        XCTAssertFalse(html.contains("问阿衡下一餐"))
        XCTAssertFalse(html.contains("外部链接"))
        XCTAssertFalse(html.contains("直接写入"))
        XCTAssertFalse(html.contains("https://example.test"))
    }

    func testDynamicCardUnknownTypeFallsBackToSafeSummary() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "system_knowledge_evidence",
            data: .object([
                "entity": .object(["title": .string("MTHFR <tag>")]),
                "claims": .array([.object(["doc_id": .string("claim:c1")])])
            ])
        ))

        XCTAssertTrue(html.contains("知识证据卡"))
        XCTAssertTrue(html.contains("MTHFR &lt;tag&gt;"))
        XCTAssertFalse(html.contains("<tag>"))
    }

    func testDynamicCardGroupRendersEveryChildIncludingDietReceipt() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "cards_group",
            data: .object([
                "cards": .array([
                    .object([
                        "type": .string("aigc_media_job"),
                        "data": .object([
                            "kind": .string("text_to_image"),
                            "title": .string("早餐海报"),
                            "status": .string("queued"),
                            "progress": .int(0),
                        ]),
                    ]),
                    .object([
                        "type": .string("diet_draft"),
                        "data": .object([
                            "meal_type": .string("breakfast"),
                            "food_items": .string("鸡蛋和全麦面包"),
                            "recorded": .bool(true),
                        ]),
                    ]),
                ]),
            ])
        ))

        XCTAssertTrue(html.contains("早餐海报"))
        XCTAssertTrue(html.contains("鸡蛋和全麦面包"))
        XCTAssertTrue(html.contains("早餐 · 已记录"))
    }

    func testDynamicCardUnknownRenderAtomFallsBackToRegisteredTypeRenderer() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "system_knowledge_evidence",
            render: AgentDynamicCardRenderDescriptor(
                atom: "future_evidence_atom",
                reason: "experimental_renderer"
            ),
            data: .object([
                "entity": .object(["title": .string("MTHFR <tag>")]),
                "claims": .array([.object(["doc_id": .string("claim:c1")])])
            ])
        ))

        XCTAssertTrue(html.contains("知识证据卡"))
        XCTAssertTrue(html.contains("MTHFR &lt;tag&gt;"))
        XCTAssertFalse(html.contains("future_evidence_atom"))
        XCTAssertFalse(html.contains("动态卡片"))
        XCTAssertFalse(html.contains("<tag>"))
    }

    func testDynamicCardGenericAgentAtomEnvelopeUsesRenderAtomName() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "agent_atom",
            render: AgentDynamicCardRenderDescriptor(
                atom: "runtime_agenda",
                reason: "next_runtime_action"
            ),
            data: .object([
                "horizon_days": .int(7),
                "next_action": .object([
                    "title": .string("晚餐后步行 15 分钟")
                ])
            ])
        ))

        XCTAssertTrue(html.contains("动态卡片"))
        XCTAssertTrue(html.contains("runtime_agenda"))
        XCTAssertTrue(html.contains("晚餐后步行 15 分钟"))
        XCTAssertFalse(html.contains(">agent_atom<"))
    }

    func testAIGCMediaJobCardRendersOnlySignedPrivateResult() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "aigc_media_job",
            data: .object([
                "job_id": .string("aigc_1"),
                "kind": .string("text_to_video"),
                "status": .string("succeeded"),
                "progress": .int(100),
                "result": .object([
                    "media_type": .string("video/mp4"),
                    "url": .string("/api/v1/upload/files/aigc/7/output.mp4?expires=1&signature=test")
                ])
            ])
        ))

        XCTAssertTrue(html.contains("小巴创作"))
        XCTAssertTrue(html.contains("文生短视频"))
        XCTAssertTrue(html.contains("已完成"))
        XCTAssertTrue(html.contains("打开短视频"))
        XCTAssertTrue(html.contains("https://health.executor.life/api/v1/upload/files/aigc/7/output.mp4"))
        XCTAssertFalse(html.contains("aliyuncs.com"))
    }

    func testAIGCProjectionCardDataDoesNotPersistASignedResultURL() throws {
        let payload = """
        {"id":"aigc_1","kind":"text_to_video","status":"succeeded","progress":100,
         "result":{"media_type":"video/mp4","url":"/api/v1/upload/files/aigc/7/output.mp4?signature=secret"}}
        """.data(using: .utf8)!
        let projection = try JSONDecoder().decode(AIGCMediaJobProjection.self, from: payload)

        XCTAssertEqual(try XCTUnwrap(projection.persistedCardData()["result"]?["url"]), .null)
        XCTAssertEqual(projection.resultURL, "/api/v1/upload/files/aigc/7/output.mp4?signature=secret")
    }

    func testAIGCMediaConfirmationCardUsesOnlyOpaqueID() throws {
        let html = try XCTUnwrap(ChatTranscriptHTML.dynamicCardHTML(
            type: "aigc_media_confirmation",
            data: .object([
                "confirmation_id": .string("aigc_confirm_opaque_1"),
                "kind": .string("image_to_video"),
                "status": .string("pending"),
                "title": .string("小巴创作草稿"),
                "provider": .string("百炼 Wan"),
                "source_attached": .bool(true)
            ])
        ))

        XCTAssertTrue(html.contains("xiaoba-aigc-confirm://aigc_confirm_opaque_1"))
        XCTAssertTrue(html.contains("发送给百炼并生成"))
        XCTAssertFalse(html.contains("prompt"))
        XCTAssertFalse(html.contains("signature="))
    }

    func testMetaFooterOmitsEmptySourcesAndToolsBlocks() {
        // 有模型行,但 sources/tools 空 → 只出 meta-line,不出 details / meta-tools
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 1000, llmRounds: nil, sourcesUsed: [], toolsUsed: []
        )
        XCTAssertTrue(html.contains("meta-line"))
        XCTAssertFalse(html.contains("<details"))
        XCTAssertFalse(html.contains("meta-tools"))
    }

    func testMetaFooterEscapesXSSInModelSourcesTools() {
        let html = ChatTranscriptHTML.metaFooterHTML(
            model: "<img src=x onerror=alert(1)>",
            elapsedMs: 100,
            llmRounds: nil,
            sourcesUsed: ["<script>evil</script>"],
            toolsUsed: ["</span><b>x"]
        )
        // 任何注入内容都被转义,无真标签生成
        XCTAssertFalse(html.contains("<img"))
        XCTAssertFalse(html.contains("<script>evil"))
        XCTAssertTrue(html.contains("&lt;img"))
        XCTAssertTrue(html.contains("&lt;script&gt;evil"))
        XCTAssertTrue(html.contains("&lt;/span&gt;&lt;b&gt;x"))
    }

    func testRenderedMessageJSONIncludesFooterField() {
        let footer = ChatTranscriptHTML.metaFooterHTML(
            model: "m", elapsedMs: 2000, llmRounds: nil, sourcesUsed: ["kb"], toolsUsed: []
        )
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "x", role: "assistant", bodyHTML: "<p>hi</p>",
            isStreaming: false, showCopy: true, footerHTML: footer
        )
        let json = msg.jsonObject
        XCTAssertTrue(json.contains("\"footer\":"))
        // footer HTML 经 jsString 编码注入(< 被编码为 <)
        XCTAssertTrue(json.contains("\\u003cdetails") || json.contains("\\u003cdiv"))
        // 整条信封仍是合法 JSON
        let parsed = try? JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any]
        XCTAssertNotNil(parsed ?? nil)
        XCTAssertNotNil((parsed ?? [:])["footer"])
    }

    func testRenderedMessageFooterDefaultsEmpty() {
        let msg = ChatTranscriptHTML.RenderedMessage(
            id: "x", role: "user", bodyHTML: "<p>hi</p>", isStreaming: false, showCopy: false
        )
        XCTAssertEqual(msg.footerHTML, "")
        XCTAssertTrue(msg.jsonObject.contains("\"footer\":\"\""))
    }

    func testMessagesJSONArrayWellFormed() {
        let a = ChatTranscriptHTML.RenderedMessage(id: "a", role: "user", bodyHTML: "<p>hi</p>", isStreaming: false, showCopy: false)
        let b = ChatTranscriptHTML.RenderedMessage(id: "b", role: "assistant", bodyHTML: "<p>yo</p>", isStreaming: false, showCopy: true)
        let arr = ChatTranscriptHTML.messagesJSONArray([a, b])
        XCTAssertTrue(arr.hasPrefix("["))
        XCTAssertTrue(arr.hasSuffix("]"))
        let data = arr.data(using: .utf8)!
        let parsed = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        XCTAssertEqual((parsed ?? [])?.count, 2)
    }
}

// MARK: - mac 死键防线:不可执行的 route.open 不画按钮(2026-07-05)

extension ChatTranscriptHTMLTests {
    func testDietDraftCardRendersOwnerScopedPhotoAndManualConfirmationAction() {
        let action = AgentDynamicCardActionDescriptor(
            id: "confirm-contextual-diet:photo-draft-1",
            label: "确认记录",
            action: "diet_record.create",
            endpoint: "/diet/records",
            payload: .object([
                "record": .object([
                    "record_date": .string("2026-07-19"),
                    "meal_type": .string("lunch"),
                    "food_items": .string("鸡胸肉和杂粮饭"),
                    "photo_draft_token": .string("photo-draft-1"),
                ]),
            ]),
            style: "primary",
            requiresManualConfirm: true,
            capabilityID: "diet_draft.v1",
            requiredReceipt: true,
            autonomyTier: "manual_confirm"
        )
        let html = ChatTranscriptHTML.dynamicCardHTML(
            type: "diet_draft",
            data: .object([
                "meal_type": .string("lunch"),
                "food_items": .string("鸡胸肉和杂粮饭"),
                "calories": .int(560),
                "protein": .int(42),
                "photo_url": .string("/api/v1/upload/files/diet/1/lunch.jpg?expires=1&signature=signed"),
            ]),
            actions: [action]
        )

        XCTAssertTrue(html?.contains("午餐 · 待确认") == true)
        XCTAssertTrue(html?.contains("鸡胸肉和杂粮饭") == true)
        XCTAssertTrue(html?.contains("diet-draft-photo") == true)
        XCTAssertTrue(html?.contains("xiaoba-diet-confirm://confirm-contextual-diet:photo-draft-1") == true)
    }

    func testDynamicCardActionDecodesKernelPolicyMetadata() throws {
        let raw = Data("""
        {
          "id":"confirm-diet-draft",
          "label":"确认记录",
          "action":"diet_record.create",
          "capability_id":"diet_draft.v1",
          "required_receipt":true,
          "autonomy_tier":"manual_confirm",
          "policy_reason":"manual_confirm_write"
        }
        """.utf8)
        let action = try JSONDecoder().decode(AgentDynamicCardActionDescriptor.self, from: raw)

        XCTAssertEqual(action.capabilityID, "diet_draft.v1")
        XCTAssertEqual(action.requiredReceipt, true)
        XCTAssertEqual(action.autonomyTier, "manual_confirm")
        XCTAssertEqual(action.policyReason, "manual_confirm_write")
    }

    func testUnactionableRouteOpenButtonIsNotRendered() {
        let actions = [
            AgentDynamicCardActionDescriptor(
                id: "dead", label: "去神秘页", action: "route.open",
                payload: .object(["route": .string("/mystery-screen")]), style: "primary"
            ),
            AgentDynamicCardActionDescriptor(
                id: "ok", label: "去用药页记录", action: "route.open",
                payload: .object(["route": .string("/medications?draft=1")]), style: "primary"
            ),
        ]
        guard let html = ChatTranscriptHTML.dynamicCardHTML(type: "medication_draft", render: nil, data: .object([:]), actions: actions) else {
            return XCTFail("card html should render")
        }
        XCTAssertFalse(html.contains("去神秘页"), "mac 执行不了的路由不该渲染按钮(死键)")
        XCTAssertTrue(html.contains("去用药页记录"), "已映射路由的按钮应保留")
    }
}
