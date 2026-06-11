import XCTest
@testable import HealthAgentMacCore

final class OriginatorClientTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    // MARK: - recognize decoding

    func testDecodesRecognizeWithOriginatorAndWithout() throws {
        let json = """
        {
          "items": [
            {
              "raw_name": "拜阿司匹灵 100mg",
              "generic_name": "阿司匹林",
              "dosage": "100mg",
              "frequency": "qd",
              "originator": { "generic": "阿司匹林", "brand": "拜阿司匹灵", "manufacturer": "拜耳" },
              "has_originator": true
            },
            {
              "raw_name": "某仿制药",
              "generic_name": "二甲双胍",
              "dosage": null,
              "frequency": null,
              "originator": null,
              "has_originator": false
            }
          ],
          "matched_originators": 1,
          "note": "仅供参考，以药师/医生为准"
        }
        """
        let response = try decode(PrescriptionRecognizeResponse.self, json)

        XCTAssertEqual(response.items.count, 2)
        XCTAssertEqual(response.matchedOriginators, 1)
        XCTAssertEqual(response.note, "仅供参考，以药师/医生为准")

        let first = response.items[0]
        XCTAssertEqual(first.rawName, "拜阿司匹灵 100mg")
        XCTAssertEqual(first.genericName, "阿司匹林")
        XCTAssertTrue(first.hasOriginator)
        XCTAssertEqual(first.originator?.brand, "拜阿司匹灵")
        XCTAssertEqual(first.originator?.manufacturer, "拜耳")
        XCTAssertEqual(first.displayName, "拜阿司匹灵 100mg")

        let second = response.items[1]
        XCTAssertNil(second.originator)
        XCTAssertFalse(second.hasOriginator)
        XCTAssertNil(second.dosage)
        // displayName falls back to generic when raw is the literal but present;
        // here raw is present so it wins.
        XCTAssertEqual(second.displayName, "某仿制药")
    }

    func testRecognizeMissingFieldsDoNotFailDecoding() throws {
        // Empty/partial payload must decode to a safe empty response, never throw.
        let response = try decode(PrescriptionRecognizeResponse.self, "{}")
        XCTAssertTrue(response.items.isEmpty)
        XCTAssertEqual(response.matchedOriginators, 0)
        XCTAssertNil(response.note)
    }

    func testItemDisplayNameFallsBackToGenericWhenRawMissing() throws {
        let json = """
        { "generic_name": "辛伐他汀", "has_originator": false }
        """
        let item = try decode(PrescriptionItem.self, json)
        XCTAssertNil(item.rawName)
        XCTAssertEqual(item.displayName, "辛伐他汀")
    }

    func testItemIDsAreStableAcrossDecodes() throws {
        let json = """
        { "raw_name": "A药", "generic_name": "a", "dosage": "10mg", "has_originator": false }
        """
        let a = try decode(PrescriptionItem.self, json)
        let b = try decode(PrescriptionItem.self, json)
        XCTAssertEqual(a.id, b.id)
        XCTAssertEqual(a.id, "A药|a|10mg")
    }

    // MARK: - recommendations decoding

    func testDecodesRecommendations() throws {
        let json = """
        {
          "recommendations": [
            {
              "med_name": "我的阿托伐他汀",
              "generic_name": "阿托伐他汀",
              "generic_key": "atorvastatin",
              "brand": "立普妥",
              "manufacturer": "辉瑞"
            }
          ]
        }
        """
        let response = try decode(OriginatorRecommendationsResponse.self, json)
        XCTAssertEqual(response.recommendations.count, 1)
        let rec = response.recommendations[0]
        XCTAssertEqual(rec.medName, "我的阿托伐他汀")
        XCTAssertEqual(rec.brand, "立普妥")
        XCTAssertEqual(rec.id, "atorvastatin")
    }

    func testRecommendationIDFallsBackToGenericNameWhenKeyMissing() throws {
        let json = """
        { "med_name": "x", "generic_name": "二甲双胍", "generic_key": "", "brand": "格华止", "manufacturer": "默克" }
        """
        let rec = try decode(OriginatorRecommendation.self, json)
        XCTAssertEqual(rec.id, "二甲双胍")
    }

    func testEmptyRecommendationsDecode() throws {
        let response = try decode(OriginatorRecommendationsResponse.self, "{}")
        XCTAssertTrue(response.recommendations.isEmpty)
    }

    // MARK: - status request encoding

    func testStatusRequestEncodesSnakeCaseAndRawStatus() throws {
        let request = OriginatorStatusRequest(
            genericName: "阿托伐他汀",
            status: .adopted,
            brand: "立普妥",
            manufacturer: "辉瑞"
        )
        let data = try JSONEncoder().encode(request)
        let object = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(object["generic_name"] as? String, "阿托伐他汀")
        XCTAssertEqual(object["status"] as? String, "adopted")
        XCTAssertEqual(object["brand"] as? String, "立普妥")
        XCTAssertEqual(object["manufacturer"] as? String, "辉瑞")
    }

    func testStatusResponseDecodes() throws {
        let response = try decode(
            OriginatorStatusResponse.self,
            #"{ "generic_name": "二甲双胍", "status": "dismissed" }"#
        )
        XCTAssertEqual(response.genericName, "二甲双胍")
        XCTAssertEqual(response.status, "dismissed")
    }

    // MARK: - originator lookup decoding

    func testLookupDecodesNullOriginator() throws {
        let response = try decode(
            OriginatorLookupResponse.self,
            #"{ "query": "未知药", "originator": null, "has_originator": false }"#
        )
        XCTAssertEqual(response.query, "未知药")
        XCTAssertNil(response.originator)
        XCTAssertFalse(response.hasOriginator)
    }

    // MARK: - MIME mapping (pure)

    func testMimeTypeMapping() {
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "jpg"), "image/jpeg")
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "JPEG"), "image/jpeg")
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "png"), "image/png")
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "heic"), "image/heic")
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "webp"), "image/webp")
        // Unknown extension must not be guessed — server decides.
        XCTAssertEqual(PrescriptionImageMime.mimeType(forExtension: "pdf"), "application/octet-stream")
    }

    // MARK: - multipart body builder (pure)

    func testMultipartBodyContainsHeadersAndPayload() throws {
        let payload = Data("FAKEIMAGE".utf8)
        let body = APIClient.multipartBody(
            boundary: "B123",
            fieldName: "file",
            fileName: "rx.png",
            mimeType: "image/png",
            fileData: payload
        )
        let text = try XCTUnwrap(String(data: body, encoding: .utf8))
        XCTAssertTrue(text.contains("--B123\r\n"))
        XCTAssertTrue(text.contains("Content-Disposition: form-data; name=\"file\"; filename=\"rx.png\""))
        XCTAssertTrue(text.contains("Content-Type: image/png"))
        XCTAssertTrue(text.contains("FAKEIMAGE"))
        XCTAssertTrue(text.hasSuffix("--B123--\r\n"))
    }
}
