import Foundation
import XCTest
@testable import HealthAgentMacCore

final class LabUploadClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testImportsPDFViaMedicalExamPDFEndpoint() async throws {
        let fileURL = try temporaryFile(name: "lab-report.pdf", contents: "PDFDATA")
        defer { try? FileManager.default.removeItem(at: fileURL) }

        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/medical-exams/import/pdf")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token")
            XCTAssertTrue(request.value(forHTTPHeaderField: "Content-Type")?.contains("multipart/form-data") ?? false)
            let body = try XCTUnwrap(request.bodyDataForTesting)
            let bodyText = try XCTUnwrap(String(data: body, encoding: .utf8))
            XCTAssertTrue(bodyText.contains(#"name="file"; filename="lab-report.pdf""#))
            XCTAssertTrue(bodyText.contains("Content-Type: application/pdf"))
            XCTAssertTrue(bodyText.contains("PDFDATA"))

            let data = """
            {
              "message": "PDF解析并导入成功",
              "exam_id": 42,
              "exam_date": "2026-06-18",
              "exam_type": "biochemistry",
              "hospital_name": "Test Lab",
              "items_count": 12,
              "conclusions_count": 1
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }

        let client = LabUploadClient(apiClient: APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        ))

        let result = try await client.importReport(fileURL: fileURL)

        XCTAssertEqual(result.examID, 42)
        XCTAssertEqual(result.itemsCount, 12)
        XCTAssertEqual(result.conclusionsCount, 1)
        XCTAssertNil(result.abnormalCount)
    }

    func testImportsImageViaMedicalExamImageEndpoint() async throws {
        let fileURL = try temporaryFile(name: "lab-photo.png", contents: "PNGDATA")
        defer { try? FileManager.default.removeItem(at: fileURL) }

        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/medical-exams/import/image")
            let body = try XCTUnwrap(request.bodyDataForTesting)
            let bodyText = try XCTUnwrap(String(data: body, encoding: .utf8))
            XCTAssertTrue(bodyText.contains(#"name="file"; filename="lab-photo.png""#))
            XCTAssertTrue(bodyText.contains("Content-Type: image/png"))

            let data = """
            {
              "message": "图片 OCR 导入成功",
              "exam_id": 77,
              "exam_date": "2026-06-18",
              "exam_type": "comprehensive",
              "items_count": 8,
              "abnormal_count": 2,
              "conclusion": "部分指标偏高"
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }

        let client = LabUploadClient(apiClient: APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token"),
            session: URLSession(configuration: .ephemeralWithStub)
        ))

        let result = try await client.importReport(fileURL: fileURL)

        XCTAssertEqual(result.examID, 77)
        XCTAssertEqual(result.itemsCount, 8)
        XCTAssertEqual(result.abnormalCount, 2)
        XCTAssertEqual(result.conclusion, "部分指标偏高")
    }

    func testMimeTypeMappingForLabReports() {
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "pdf"), "application/pdf")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "jpg"), "image/jpeg")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "jpeg"), "image/jpeg")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "png"), "image/png")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "heic"), "image/heic")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "webp"), "image/webp")
        XCTAssertEqual(LabReportUploadMime.mimeType(forExtension: "txt"), "application/octet-stream")
    }

    private func temporaryFile(name: String, contents: String) throws -> URL {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("LabUploadClientTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(name)
        try Data(contents.utf8).write(to: url)
        return url
    }
}
