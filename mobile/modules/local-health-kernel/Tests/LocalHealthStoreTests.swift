import Foundation
import SQLite3
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalHealthStoreTests: XCTestCase {
    private let rootKey = Data((0..<32).map(UInt8.init))

    func testPutGetAndBlindIndexListPersistNoPlaintext() throws {
        try withStore { store, databaseURL, protection in
            let payload = #"{"food_items":"米饭和鸡蛋","record_date":"2026-07-19"}"#

            try store.putEncrypted(
                collection: .dietRecords,
                id: "meal-1",
                version: 1,
                equalityIndexes: ["day": "2026-07-19", "meal_type": "lunch"],
                payload: payload
            )

            XCTAssertEqual(
                try store.getDecrypted(collection: .dietRecords, id: "meal-1"),
                payload
            )
            XCTAssertEqual(
                try store.listDecrypted(
                    collection: .dietRecords,
                    index: "day",
                    value: "2026-07-19"
                ),
                [payload]
            )
            let databaseBytes = try Data(contentsOf: databaseURL)
            XCTAssertNil(databaseBytes.range(of: Data("米饭和鸡蛋".utf8)))
            XCTAssertNil(databaseBytes.range(of: Data("2026-07-19".utf8)))
            XCTAssertNil(databaseBytes.range(of: Data("lunch".utf8)))
            XCTAssertEqual(protection.protectedURLs, [databaseURL])
        }
    }

    func testTamperedCiphertextFailsWithoutPlaintextFallback() throws {
        try withStore { store, databaseURL, _ in
            try store.putEncrypted(
                collection: .dietRecords,
                id: "meal-1",
                version: 1,
                equalityIndexes: [:],
                payload: "private-meal"
            )
            try executeSQL(
                at: databaseURL,
                sql: "UPDATE encrypted_records SET tag = zeroblob(16)"
            )

            XCTAssertThrowsError(
                try store.getDecrypted(collection: .dietRecords, id: "meal-1")
            ) { error in
                XCTAssertEqual(error as? LocalHealthKernelError, .authenticationFailed)
            }
        }
    }

    func testFailedIndexWriteRollsBackTheRecord() throws {
        try withStore { store, databaseURL, _ in
            _ = try store.getDecrypted(collection: .dietRecords, id: "missing")
            try executeSQL(
                at: databaseURL,
                sql: """
                CREATE TRIGGER reject_test_index
                BEFORE INSERT ON blind_indexes
                WHEN NEW.index_name = 'force_failure'
                BEGIN SELECT RAISE(ABORT, 'forced failure'); END
                """
            )

            XCTAssertThrowsError(
                try store.putEncrypted(
                    collection: .dietRecords,
                    id: "meal-rollback",
                    version: 1,
                    equalityIndexes: ["force_failure": "secret"],
                    payload: "must-not-persist"
                )
            )
            XCTAssertNil(
                try store.getDecrypted(
                    collection: .dietRecords,
                    id: "meal-rollback"
                )
            )
        }
    }

    func testProtectedDataUnavailableFailsBeforeOpeningDatabase() throws {
        let directory = try temporaryDirectory()
        let databaseURL = directory.appendingPathComponent("vault.sqlite")
        let store = try LocalHealthStore(
            databaseURL: databaseURL,
            rootKey: rootKey,
            exportDirectory: directory,
            fileProtection: RecordingFileProtection(),
            protectedDataAvailable: { false }
        )

        XCTAssertThrowsError(
            try store.getDecrypted(collection: .dietRecords, id: "meal-1")
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .protectedDataUnavailable)
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: databaseURL.path))
    }

    func testCorruptDatabaseFailsClosedWithoutReplacingIt() throws {
        let directory = try temporaryDirectory()
        let databaseURL = directory.appendingPathComponent("vault.sqlite")
        let corruptBytes = Data("not-a-sqlite-database".utf8)
        try corruptBytes.write(to: databaseURL)
        let store = try LocalHealthStore(
            databaseURL: databaseURL,
            rootKey: rootKey,
            exportDirectory: directory,
            fileProtection: RecordingFileProtection()
        )

        XCTAssertThrowsError(
            try store.getDecrypted(collection: .dietRecords, id: "meal-1")
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .storageFailure)
        }
        XCTAssertEqual(try Data(contentsOf: databaseURL), corruptBytes)
    }

    func testDeleteRemovesOnlyTheRequestedEncryptedRecord() throws {
        try withStore { store, _, _ in
            for id in ["meal-1", "meal-2"] {
                try store.putEncrypted(
                    collection: .dietRecords,
                    id: id,
                    version: 1,
                    equalityIndexes: ["day": "2026-07-19"],
                    payload: id
                )
            }

            try store.delete(collection: .dietRecords, id: "meal-1")

            XCTAssertNil(try store.getDecrypted(collection: .dietRecords, id: "meal-1"))
            XCTAssertEqual(
                try store.listDecrypted(
                    collection: .dietRecords,
                    index: "day",
                    value: "2026-07-19"
                ),
                ["meal-2"]
            )
        }
    }

    func testExportUsesSeparateRecoveryKeyAndRestoresStableIDsIntoEmptyVault() throws {
        let sourceDirectory = try temporaryDirectory()
        let sourceDatabase = sourceDirectory.appendingPathComponent("source.sqlite")
        let source = try LocalHealthStore(
            databaseURL: sourceDatabase,
            rootKey: rootKey,
            exportDirectory: sourceDirectory,
            fileProtection: RecordingFileProtection(),
            randomBytes: DeterministicRandomBytes().bytes
        )
        try source.putEncrypted(
            collection: .dietRecords,
            id: "stable-meal-id",
            version: 3,
            equalityIndexes: ["day": "2026-07-19"],
            payload: "private-meal"
        )

        let receipt = try source.exportEnvelope()
        let exportData = try Data(contentsOf: receipt.url)
        XCTAssertFalse(String(decoding: exportData, as: UTF8.self).contains(receipt.recoveryKey))
        XCTAssertNil(exportData.range(of: Data("private-meal".utf8)))

        let destinationDirectory = try temporaryDirectory()
        let destinationDatabase = destinationDirectory.appendingPathComponent("restored.sqlite")
        let destination = try LocalHealthStore(
            databaseURL: destinationDatabase,
            rootKey: Data(repeating: 55, count: 32),
            exportDirectory: destinationDirectory,
            fileProtection: RecordingFileProtection()
        )
        try destination.restoreEnvelope(
            from: receipt.url,
            recoveryKey: receipt.recoveryKey
        )

        XCTAssertEqual(
            try destination.getDecrypted(
                collection: .dietRecords,
                id: "stable-meal-id"
            ),
            "private-meal"
        )
        XCTAssertEqual(
            try destination.listDecrypted(
                collection: .dietRecords,
                index: "day",
                value: "2026-07-19"
            ),
            ["private-meal"]
        )
        let restoredBytes = try Data(contentsOf: destinationDatabase)
        XCTAssertNil(restoredBytes.range(of: Data("private-meal".utf8)))
    }

    func testWrongRecoveryKeyAndNonEmptyRestoreLeaveDestinationUnchanged() throws {
        let sourceDirectory = try temporaryDirectory()
        let source = try LocalHealthStore(
            databaseURL: sourceDirectory.appendingPathComponent("source.sqlite"),
            rootKey: rootKey,
            exportDirectory: sourceDirectory,
            fileProtection: RecordingFileProtection()
        )
        try source.putEncrypted(
            collection: .dietRecords,
            id: "source-meal",
            version: 1,
            equalityIndexes: [:],
            payload: "source"
        )
        let receipt = try source.exportEnvelope()

        let destinationDirectory = try temporaryDirectory()
        let destination = try LocalHealthStore(
            databaseURL: destinationDirectory.appendingPathComponent("destination.sqlite"),
            rootKey: Data(repeating: 33, count: 32),
            exportDirectory: destinationDirectory,
            fileProtection: RecordingFileProtection()
        )
        XCTAssertThrowsError(
            try destination.restoreEnvelope(
                from: receipt.url,
                recoveryKey: Data(repeating: 4, count: 32).base64EncodedString()
            )
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .authenticationFailed)
        }
        XCTAssertNil(
            try destination.getDecrypted(collection: .dietRecords, id: "source-meal")
        )

        try destination.putEncrypted(
            collection: .dietRecords,
            id: "existing-meal",
            version: 1,
            equalityIndexes: [:],
            payload: "existing"
        )
        XCTAssertThrowsError(
            try destination.restoreEnvelope(
                from: receipt.url,
                recoveryKey: receipt.recoveryKey
            )
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .vaultNotEmpty)
        }
        XCTAssertEqual(
            try destination.getDecrypted(
                collection: .dietRecords,
                id: "existing-meal"
            ),
            "existing"
        )
    }

    func testMultiCollectionMutationCommitsRecordAndAuditEventAtomically() throws {
        try withStore { store, _, _ in
            let record = LocalHealthMutationWrite(
                collection: .dietRecords,
                id: "diet-1",
                version: 1,
                equalityIndexes: ["record_date": "2026-07-19"],
                payload: #"{"food_items":"米饭"}"#
            )
            let event = LocalHealthMutationWrite(
                collection: .executionEvents,
                id: "event-1",
                version: 1,
                equalityIndexes: ["record_id": "diet-1"],
                payload: #"{"kind":"diet_record_confirmed"}"#
            )

            try store.applyMutation(writes: [record, event], deletes: [])

            XCTAssertNotNil(
                try store.getDecrypted(collection: .dietRecords, id: "diet-1")
            )
            XCTAssertNotNil(
                try store.getDecrypted(collection: .executionEvents, id: "event-1")
            )
        }
    }

    func testInvalidWriteRollsTheEntireMutationBack() throws {
        try withStore { store, _, _ in
            let valid = LocalHealthMutationWrite(
                collection: .dietRecords,
                id: "diet-rollback",
                version: 1,
                equalityIndexes: ["record_date": "2026-07-19"],
                payload: #"{"food_items":"鸡蛋"}"#
            )
            let invalid = LocalHealthMutationWrite(
                collection: .executionEvents,
                id: "",
                version: 1,
                equalityIndexes: [:],
                payload: "{}"
            )

            XCTAssertThrowsError(
                try store.applyMutation(writes: [valid, invalid], deletes: [])
            ) { error in
                XCTAssertEqual(error as? LocalHealthKernelError, .invalidEnvelope)
            }
            XCTAssertNil(
                try store.getDecrypted(collection: .dietRecords, id: "diet-rollback")
            )
        }
    }

    private func withStore(
        _ body: (
            LocalHealthStore,
            URL,
            RecordingFileProtection
        ) throws -> Void
    ) throws {
        let directory = try temporaryDirectory()
        let databaseURL = directory.appendingPathComponent("vault.sqlite")
        let protection = RecordingFileProtection()
        let store = try LocalHealthStore(
            databaseURL: databaseURL,
            rootKey: rootKey,
            exportDirectory: directory,
            fileProtection: protection
        )
        try body(store, databaseURL, protection)
    }

    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(
            at: url,
            withIntermediateDirectories: true
        )
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    private func executeSQL(at url: URL, sql: String) throws {
        var database: OpaquePointer?
        guard sqlite3_open(url.path, &database) == SQLITE_OK, let database else {
            throw LocalHealthKernelError.storageFailure
        }
        defer { sqlite3_close(database) }
        guard sqlite3_exec(database, sql, nil, nil, nil) == SQLITE_OK else {
            throw LocalHealthKernelError.storageFailure
        }
    }
}

private final class RecordingFileProtection: LocalHealthFileProtectionApplying,
    @unchecked Sendable {
    var protectedURLs: [URL] = []

    func applyCompleteProtection(to url: URL) throws {
        protectedURLs.append(url)
    }
}

private final class DeterministicRandomBytes: @unchecked Sendable {
    private var nextByte: UInt8 = 1

    func bytes(count: Int) throws -> Data {
        defer { nextByte &+= 1 }
        return Data(repeating: nextByte, count: count)
    }
}
