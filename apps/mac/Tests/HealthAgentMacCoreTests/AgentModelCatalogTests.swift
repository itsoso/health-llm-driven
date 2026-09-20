import Foundation
import XCTest
@testable import HealthAgentMacCore

@MainActor
final class AgentModelCatalogTests: XCTestCase {
    func testCatalogRefreshUsesAuthenticatedUserDirectoryAndReplacesFallback() async {
        URLProtocolStub.reset()
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/v1/me/llm-preference")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer catalog-test")
            let data = #"{"model_id":null,"options":[{"id":"new-model","label":"New Model","provider":"provider","model":"new-model","speed_tier":"fast"}]}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let api = APIClient(baseURL: URL(string: "https://example.test/api/v1")!,
                            tokenProvider: StaticTokenProvider(token: "catalog-test"),
                            session: URLSession(configuration: .ephemeralWithStub))
        let vm = AgentChatViewModel(selectedModelID: "qwen3.8-max", modelCatalogClient: AgentModelCatalogClient(apiClient: api))
        await vm.refreshModelCatalog()
        XCTAssertEqual(vm.modelOptions, [.init(id: "new-model", title: "New Model", provider: "provider", tier: "fast")])
        XCTAssertEqual(vm.selectedModelID, "qwen3.8-max", "Refresh must never silently select a different model")
        XCTAssertNil(vm.modelCatalogNotice)
        XCTAssertFalse(vm.isRefreshingModelCatalog)

        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!, Data())
        }
        await vm.refreshModelCatalog()
        XCTAssertEqual(vm.modelOptions.map(\.id), ["new-model"])
        XCTAssertNotNil(vm.modelCatalogNotice)
        XCTAssertFalse(vm.isRefreshingModelCatalog)

        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(#"{"options":[]}"#.utf8))
        }
        await vm.refreshModelCatalog()
        XCTAssertTrue(vm.modelOptions.isEmpty, "An empty server catalog must not resurrect retired models")
        XCTAssertNil(vm.modelCatalogNotice)
    }

    func testMalformedDirectoryIsNotAdvertisedAsFresh() async {
        URLProtocolStub.reset()
        for body in [
            #"{"options":[{"id":"same","label":"A","provider":"p","speed_tier":"fast"},{"id":"same","label":"B","provider":"p","speed_tier":"fast"}]}"#,
            #"{"options":[{"id":" ","label":"A","provider":"p","speed_tier":"fast"}]}"#,
            #"{"options":[{"id":"missing-fields"}]}"#
        ] {
            URLProtocolStub.handler = { request in
                (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(body.utf8))
            }
            let api = APIClient(baseURL: URL(string: "https://example.test/api/v1")!,
                                tokenProvider: StaticTokenProvider(token: "catalog-test"),
                                session: URLSession(configuration: .ephemeralWithStub))
            let vm = AgentChatViewModel(modelCatalogClient: AgentModelCatalogClient(apiClient: api))
            await vm.refreshModelCatalog()
            XCTAssertFalse(vm.hasLoadedModelCatalog)
            XCTAssertEqual(vm.modelOptions, AgentModelCatalog.defaultOptions)
            XCTAssertNotNil(vm.modelCatalogNotice)
        }
    }

    func testOverlappingRefreshesShareOneInFlightLoad() async {
        let loader = SuspendedCatalog()
        let vm = AgentChatViewModel(modelCatalogClient: loader)
        let first = Task { await vm.refreshModelCatalog() }
        await loader.waitForStart()
        await vm.refreshModelCatalog()
        let count = await loader.calls
        XCTAssertEqual(count, 1)
        XCTAssertTrue(vm.isRefreshingModelCatalog)
        await loader.finish()
        await first.value
        XCTAssertFalse(vm.isRefreshingModelCatalog)
        XCTAssertTrue(vm.hasLoadedModelCatalog)
    }
}

private actor SuspendedCatalog: AgentModelCatalogLoading {
    private(set) var calls = 0
    private var pending: CheckedContinuation<[AgentModelOption], Never>?
    private var started: CheckedContinuation<Void, Never>?

    func waitForStart() async {
        if calls > 0 { return }
        await withCheckedContinuation { started = $0 }
    }

    func loadModels() async throws -> [AgentModelOption] {
        calls += 1
        return await withCheckedContinuation {
            pending = $0
            started?.resume()
            started = nil
        }
    }

    func finish() {
        pending?.resume(returning: [])
        pending = nil
    }
}
