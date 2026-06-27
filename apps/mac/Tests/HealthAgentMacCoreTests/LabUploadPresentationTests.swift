import XCTest
@testable import HealthAgentMacCore

final class LabUploadPresentationTests: XCTestCase {
    func testMedicalExamImportPresentationIncludesSummaryAndReviewWarning() {
        let result = LabUploadResult(
            message: "PDF解析并导入成功",
            examID: 42,
            examDate: "2026-06-18",
            examType: "biochemistry",
            hospitalName: "三甲医院",
            itemsCount: 28,
            abnormalCount: 3,
            conclusionsCount: 2,
            conclusion: "血脂偏高"
        )

        let presentation = LabUploadPresentation.make(result: result, fileName: "report.pdf")

        XCTAssertEqual(presentation.title, "report.pdf")
        XCTAssertEqual(presentation.statusText, "体检报告已导入。OCR/AI 解析值需要复核后再用于判断。")
        XCTAssertEqual(presentation.summary, "#42 · 2026-06-18 · biochemistry · 三甲医院 · 28 items · 3 abnormal · 2 conclusions · 血脂偏高")
        XCTAssertEqual(presentation.agentPrompt, "解释这份刚上传的体检报告：先列出异常/关键指标，再说明不确定性边界、需要复核的项目和下一步行动。")
    }
}
