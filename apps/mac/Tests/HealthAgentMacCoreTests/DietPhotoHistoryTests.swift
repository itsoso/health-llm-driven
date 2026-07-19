import Foundation
import XCTest
@testable import HealthAgentMacCore

final class DietPhotoHistoryTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testRecentDietHistoryDecodesCanonicalPhotoAssetsAndResolvesPrivateURLs() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/diet/records/me?limit=12")
            let data = Data("""
            [{
              "id": 73,
              "user_id": 9,
              "record_date": "2026-07-19",
              "meal_type": "lunch",
              "food_items": "鸡胸肉 120g",
              "calories": 198,
              "protein": 37,
              "image_url": "/api/v1/upload/files/diet/9/cover.png?signature=cover",
              "image_urls": ["/api/v1/upload/files/diet/9/cover.png?signature=cover"],
              "photo_assets": [{
                "id": "asset-1",
                "url": "/api/v1/upload/files/diet/9/photo.png?signature=photo",
                "ordinal": 0,
                "media_type": "image/png",
                "origin": "chat"
              }]
            }]
            """.utf8)
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }

        let client = RecordClient(apiClient: APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        ))
        let records = try await client.fetchRecentDietRecords()

        XCTAssertEqual(records.count, 1)
        XCTAssertEqual(records[0].foodItems, "鸡胸肉 120g")
        XCTAssertEqual(records[0].photoAssets.map { $0.id }, ["asset-1"])
        XCTAssertEqual(records[0].displayPhotoURLs, [
            "https://example.test/api/v1/upload/files/diet/9/photo.png?signature=photo",
            "https://example.test/api/v1/upload/files/diet/9/cover.png?signature=cover",
        ])
    }
}
