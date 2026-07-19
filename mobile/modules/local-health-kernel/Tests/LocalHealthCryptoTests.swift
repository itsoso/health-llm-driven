import CryptoKit
import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalHealthCryptoTests: XCTestCase {
    private let rootKey = Data((0..<32).map(UInt8.init))

    func testAESGCMRoundTripUsesUniqueNoncesAndAuthenticatesMetadata() throws {
        let crypto = try LocalHealthCrypto(rootKey: rootKey)
        let payload = Data(#"{"food_items":"米饭和鸡蛋"}"#.utf8)

        let first = try crypto.seal(
            payload,
            collection: "diet_records",
            objectID: "meal-1",
            objectVersion: 1
        )
        let second = try crypto.seal(
            payload,
            collection: "diet_records",
            objectID: "meal-1",
            objectVersion: 1
        )

        XCTAssertNotEqual(first.nonce, second.nonce)
        XCTAssertNotEqual(first.ciphertext, payload)
        XCTAssertEqual(try crypto.open(first), payload)

        let tampered = LocalHealthEncryptedEnvelope(
            schemaVersion: first.schemaVersion,
            collection: first.collection,
            objectID: first.objectID,
            objectVersion: 2,
            nonce: first.nonce,
            ciphertext: first.ciphertext,
            tag: first.tag
        )
        XCTAssertThrowsError(try crypto.open(tampered)) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .authenticationFailed)
        }
    }

    func testWrongSchemaAndWrongRootKeyFailClosed() throws {
        let crypto = try LocalHealthCrypto(rootKey: rootKey)
        let envelope = try crypto.seal(
            Data("private".utf8),
            collection: "execution_events",
            objectID: "event-1",
            objectVersion: 1
        )
        let unsupported = LocalHealthEncryptedEnvelope(
            schemaVersion: 99,
            collection: envelope.collection,
            objectID: envelope.objectID,
            objectVersion: envelope.objectVersion,
            nonce: envelope.nonce,
            ciphertext: envelope.ciphertext,
            tag: envelope.tag
        )

        XCTAssertThrowsError(try crypto.open(unsupported)) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .invalidEnvelope)
        }
        let wrongCrypto = try LocalHealthCrypto(rootKey: Data(repeating: 44, count: 32))
        XCTAssertThrowsError(try wrongCrypto.open(envelope)) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .authenticationFailed)
        }
    }

    func testDerivedKeysAreDomainSeparated() throws {
        let recordKey = try LocalHealthCrypto.deriveSubkey(
            rootKey: rootKey,
            purpose: .recordEncryption
        )
        let blindIndexKey = try LocalHealthCrypto.deriveSubkey(
            rootKey: rootKey,
            purpose: .blindIndex
        )

        XCTAssertNotEqual(keyData(recordKey), keyData(blindIndexKey))
    }

    func testBlindIndexIsStableDomainBoundAndDoesNotContainRawValue() throws {
        let crypto = try LocalHealthCrypto(rootKey: rootKey)

        let first = try crypto.blindIndex(domain: "day.v1", value: "2026-07-19")
        let same = try crypto.blindIndex(domain: "day.v1", value: "2026-07-19")
        let otherDomain = try crypto.blindIndex(
            domain: "meal-type.v1",
            value: "2026-07-19"
        )

        XCTAssertEqual(first, same)
        XCTAssertNotEqual(first, otherDomain)
        XCTAssertEqual(first.count, 64)
        XCTAssertFalse(first.contains("2026"))
    }

    func testRejectsNon256BitRootKeysAndEmptyBlindIndexInputs() throws {
        XCTAssertThrowsError(try LocalHealthCrypto(rootKey: Data(repeating: 1, count: 31)))

        let crypto = try LocalHealthCrypto(rootKey: rootKey)
        XCTAssertThrowsError(try crypto.blindIndex(domain: "", value: "secret"))
        XCTAssertThrowsError(try crypto.blindIndex(domain: "day.v1", value: ""))
    }

    private func keyData(_ key: SymmetricKey) -> Data {
        key.withUnsafeBytes { Data($0) }
    }
}
