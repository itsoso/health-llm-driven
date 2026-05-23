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
}
