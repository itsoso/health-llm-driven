import Foundation
import XCTest
@testable import HealthAgentMacCore

final class MacP0FeatureTests: XCTestCase {
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
            .done(conversationID: 7, messageID: 9, completionStatus: "complete", model: nil, sourcesUsed: []),
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
          "action_cards": [{"id": 1, "title": "HbA1c 复查", "status": "active", "priority": 90}],
          "recent_memory": [{"id": 1, "object_value": "补剂依从率偏低"}],
          "recent_records_summary": {
            "date": "2026-05-23",
            "range_days": 30,
            "diet": {"today_count": 2, "today_calories": 1350.5, "last_30_count": 9, "last_30_calories": 8200},
            "water": {"today_count": 3, "today_total_ml": 900, "last_30_count": 12, "last_30_total_ml": 9600},
            "latest_weight": {"id": 12, "type": "weight", "title": "体重", "value": 70.2, "unit": "kg", "record_date": "2026-05-22"},
            "latest_blood_pressure": {"id": 13, "type": "blood_pressure", "title": "血压", "value": "118/76", "unit": "mmHg", "category": "正常", "record_date": "2026-05-21"},
            "latest_garmin": {"id": 14, "type": "garmin", "title": "Garmin", "record_date": "2026-05-23", "steps": 6840, "sleep_score": 82, "spo2_avg": 96.4, "resting_heart_rate": 52, "hrv": 46.5, "training_readiness_score": 73},
            "recent_records": [
              {"id": 13, "type": "blood_pressure", "title": "血压", "value": "118/76", "unit": "mmHg", "record_date": "2026-05-21"},
              {"id": 12, "type": "weight", "title": "体重", "value": 70.2, "unit": "kg", "record_date": "2026-05-22"}
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

        XCTAssertEqual(dataSummary.metrics.map(\.value), ["1350.5 kcal", "900 ml", "2"])
        XCTAssertEqual(dataSummary.jobs.map(\.id), [3])
        XCTAssertEqual(geneticsSummary.jobs.map(\.id), [1])
        XCTAssertEqual(knowledgeSummary.jobs.map(\.id), [2])
    }
}
