import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ShoppingProtocolTests: XCTestCase {
    private func command(_ type: String, text: String, moduleID: String = "text", messageID: String = "reply") -> ShoppingCommand {
        ShoppingCommand(commandType: type, commandData: .object([
            "msgItem": .object([
                "messageId": .string(messageID), "sender": .string("ai"),
                "blocks": .array([.object([
                    "moduleId": .string(moduleID), "type": .string("text"),
                    "content": .object(["text": .string(text)])
                ])])
            ])
        ]))
    }

    func testShowAndSetAppendTextButUpdateBlockReplacesOnlyMatchingModule() throws {
        var transcript = ShoppingTranscript()
        try transcript.apply(command("show_msg", text: "你好"))
        try transcript.apply(command("set_msg", text: "，推荐"))
        XCTAssertEqual(transcript.messages.count, 1)
        XCTAssertEqual(transcript.messages[0].blocks[0].text, "你好，推荐")
        try transcript.apply(command("update_block", text: "新的完整内容"))
        XCTAssertEqual(transcript.messages[0].blocks[0].text, "新的完整内容")
        let notices = try transcript.apply(command("update_block", text: "不可追加", moduleID: "missing"))
        XCTAssertEqual(transcript.messages[0].blocks.count, 1)
        XCTAssertFalse(notices.isEmpty)
    }

    func testRepeatedProductModuleReplacesWithoutDuplicatingCard() throws {
        var transcript = ShoppingTranscript()
        let product: (String) -> ShoppingCommand = { name in
            ShoppingCommand(commandType: "show_msg", commandData: .object(["msgItem": .object([
                "messageId": .string("reply"), "sender": .string("ai"), "blocks": .array([
                    .object(["moduleId": .string("goods"), "type": .string("product_single_small"),
                             "content": .object(["productSingleSmallCard": .object([
                                "itemId": .string("p1"), "itemTitle": .string(name), "price": .string("99.90")
                             ])])])
                ])
            ])]))
        }
        try transcript.apply(product("旧标题"))
        try transcript.apply(product("新标题"))
        XCTAssertEqual(transcript.messages[0].blocks.count, 1)
        XCTAssertEqual(transcript.messages[0].blocks[0].products.first?.name, "新标题")
    }

    func testThinkingIsReplacedAndRemovedWhenAnswerArrives() throws {
        var transcript = ShoppingTranscript()
        try transcript.apply(command("thinking_process_msg", text: "正在查找", messageID: "think1"))
        try transcript.apply(command("thinking_process_msg", text: "正在比较", messageID: "think2"))
        XCTAssertEqual(transcript.thinkingMessage?.blocks.first?.text, "正在比较")
        XCTAssertEqual(transcript.messages.count, 0)
        try transcript.apply(command("show_msg", text: "找到了"))
        XCTAssertNil(transcript.thinkingMessage)
    }

    func testDecoderRequiresSuccessfulKnownWrapperAndPreservesErrors() throws {
        let encoded = try JSONEncoder().encode(command("show_msg", text: "你好"))
        let json = String(decoding: encoded, as: UTF8.self)
        let frame = Data("{\"result\":1,\"data\":{\"result\":1,\"data\":\(json)}}".utf8)
        XCTAssertEqual(try ShoppingFrameDecoder.decode(frame), [command("show_msg", text: "你好")])
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(Data("{\"result\":1,\"data\":{\"result\":-1,\"data\":\(json)}}".utf8)))
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(Data("{\"result\":-1,\"data\":\(json)}".utf8)))
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(Data("{\"unexpected\":\(json)}".utf8)))
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(Data("data: \(json)".utf8)))
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(Data("{broken".utf8)))
    }

    func testEmptySuccessIsNotInventedCompletionOrMessage() throws {
        XCTAssertEqual(try ShoppingFrameDecoder.decode(Data("{\"result\":1}".utf8)), [])
        XCTAssertEqual(try ShoppingFrameDecoder.decode(Data("{\"result\":1,\"data\":{\"result\":1}}".utf8)), [])
    }

    func testDocumentedHarmonyCommandStringAndDirectPayloadVariants() throws {
        let expected = command("show_msg", text: "中文内容")
        let commandData = try JSONEncoder().encode(expected)
        let commandJSON = try ShoppingJSONValue(data: commandData)
        let text = String(decoding: commandData, as: UTF8.self)
        let wrappers: [ShoppingJSONValue] = [
            .object(["result": .number(1), "data": commandJSON]),
            .object(["result": .number(1), "data": .string(text)]),
            .object(["result": .number(1), "data": .object(["result": .number(1), "data": .string(text)])])
        ]
        for wrapper in wrappers {
            XCTAssertEqual(try ShoppingFrameDecoder.decode(JSONEncoder().encode(wrapper)), [expected])
        }
        // A direct command is accepted only through the explicit command decoder, not as a successful service response.
        XCTAssertThrowsError(try ShoppingFrameDecoder.decode(commandData))
    }

    func testUnsupportedActionDoesNotSendOrNavigateOrResetSession() throws {
        var transcript = ShoppingTranscript()
        try transcript.apply(command("show_msg", text: "已有内容"))
        for kind in ["send_msg", "jump_to", "create_session", "new_unknown_command"] {
            let notices = try transcript.apply(ShoppingCommand(commandType: kind, commandData: .object([:])))
            XCTAssertEqual(notices.first?.code, "unsupported_command")
        }
        XCTAssertEqual(transcript.messages.count, 1)
    }

    func testMalformedMessageCannotMutateTranscript() throws {
        var transcript = ShoppingTranscript()
        try transcript.apply(command("show_msg", text: "已有内容"))
        let original = transcript
        XCTAssertThrowsError(try transcript.apply(ShoppingCommand(commandType: "show_msg", commandData: .object(["msgItem": .object(["blocks": .array([])])]))))
        XCTAssertEqual(transcript, original)
    }

    func testHistoryAndSuggestionsUseExplicitSourceFields() throws {
        let data = Data(#"{"result":1,"data":{"sessionId":"s1","global":{"entry":"shopping"},"pcursor":"no_more","historyList":[{"messageId":"m1","sender":"ai","blocks":[{"moduleId":"b1","type":"text","content":{"text":"历史内容"}}]}],"questions":[{"message":"找一个水杯","commandList":[{"commandType":"send_msg"}]}]}}"#.utf8)
        let response = try ShoppingFrameDecoder.decodeResponse(data)
        XCTAssertEqual(response.messages.first?.messageId, "m1")
        XCTAssertEqual(response.suggestedQuestions, ["找一个水杯"])
        XCTAssertEqual(response.pcursor, "no_more")
        XCTAssertEqual(response.sessionId, "s1")
        XCTAssertEqual(response.globalParams["entry"], .string("shopping"))
        XCTAssertThrowsError(try ShoppingFrameDecoder.decodeResponse(Data(#"{"result":1,"data":{"historyList":"not-array"}}"#.utf8)))
    }

    func testPricesRespectYuanVersusCentsAndDetailActionIsOnlyExtracted() {
        let single = ShoppingBlock(moduleId: "s", type: "product_single_small", content: .object([
            "productSingleSmallCard": .object(["itemId": .string("1"), "itemTitle": .string("杯子"), "price": .string("19.90"),
                                                "productDetailJumpUrl": .string("kwai://goods/1")])
        ]))
        let multi = ShoppingBlock(moduleId: "m", type: "product_multi_vertical", content: .object([
            "productMultiVerticalCards": .array([.object(["itemId": .number(2), "itemTitle": .string("碗"), "price": .number(1990)])])
        ]))
        XCTAssertEqual(single.products.first?.priceText, "¥19.9")
        XCTAssertEqual(multi.products.first?.priceText, "¥19.9")
        XCTAssertEqual(single.products.first?.detailURL, "kwai://goods/1") // UI must separately validate; reducer never navigates.
    }

    func testUnknownCardDoesNotExposeArbitraryPayloadAsText() {
        let block = ShoppingBlock(moduleId: "b", type: "future_payment", content: .object(["text": .string("secret opaque data")]))
        XCTAssertNil(block.text)
        XCTAssertTrue(block.products.isEmpty)
        XCTAssertFalse(block.isSupported)
    }

    func testNumericIDsRoundTripWithoutBinaryFloatPrecisionLoss() throws {
        let json = try ShoppingJSONValue(data: Data(#"{"itemId":9223372036854775807}"#.utf8))
        XCTAssertEqual(json["itemId"]?.scalarString, "9223372036854775807")
        let roundTrip = try ShoppingJSONValue(data: JSONEncoder().encode(json))
        XCTAssertEqual(roundTrip, json)
    }

    func testNestedCommandBatchIsAtomicOnMalformedLaterMessage() throws {
        var transcript = ShoppingTranscript()
        let good = try ShoppingJSONValue(data: JSONEncoder().encode(command("show_msg", text: "不应留下")))
        let invalid: ShoppingJSONValue = .object(["commandType": .string("show_msg"), "commandData": .object([:])])
        XCTAssertThrowsError(try transcript.apply(ShoppingCommand(commandType: "cmd_to_ai_page", commandData: .object(["cmd_list": .array([good, invalid])]))))
        XCTAssertTrue(transcript.messages.isEmpty)
    }

    func testGlobalParamsReplacePreviousObject() throws {
        var transcript = ShoppingTranscript(globalParams: ["old": .bool(true)])
        try transcript.apply(ShoppingCommand(commandType: "set_global_param", commandData: .object(["globalParams": .object(["new": .number(1)])])))
        XCTAssertEqual(transcript.globalParams, ["new": .number(1)])
    }

    func testMalformedTextDoesNotBecomeEmptySuccess() throws {
        var transcript = ShoppingTranscript()
        let json = Data(#"{"commandType":"show_msg","commandData":{"msgItem":{"messageId":"m1","blocks":[{"type":"text","content":{"unexpected":"text"}}]}}}"#.utf8)
        XCTAssertThrowsError(try transcript.apply(ShoppingFrameDecoder.decodeCommand(json)))
        XCTAssertTrue(transcript.messages.isEmpty)
    }
}
