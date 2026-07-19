import Foundation
import SQLite3

public enum LocalHealthCollection: String, Codable, CaseIterable, Sendable {
    case dietRecords = "diet_records"
    case executionEvents = "execution_events"
}

public struct LocalHealthMutationWrite: Equatable, Sendable {
    public let collection: LocalHealthCollection
    public let id: String
    public let version: Int
    public let equalityIndexes: [String: String]
    public let payload: String

    public init(
        collection: LocalHealthCollection,
        id: String,
        version: Int,
        equalityIndexes: [String: String],
        payload: String
    ) {
        self.collection = collection
        self.id = id
        self.version = version
        self.equalityIndexes = equalityIndexes
        self.payload = payload
    }
}

public struct LocalHealthMutationDelete: Equatable, Sendable {
    public let collection: LocalHealthCollection
    public let id: String

    public init(collection: LocalHealthCollection, id: String) {
        self.collection = collection
        self.id = id
    }
}

public protocol LocalHealthFileProtectionApplying: Sendable {
    func applyCompleteProtection(to url: URL) throws
}

public struct SystemLocalHealthFileProtection: LocalHealthFileProtectionApplying {
    public init() {}

    public func applyCompleteProtection(to url: URL) throws {
        #if os(iOS)
        try FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.complete],
            ofItemAtPath: url.path
        )
        #endif
    }
}

struct LocalHealthStoredPayload: Codable, Equatable, Sendable {
    let payload: String
    let equalityIndexes: [String: String]
}

struct LocalHealthBackupRecord: Codable, Equatable, Sendable {
    let collection: LocalHealthCollection
    let id: String
    let version: Int
    let equalityIndexes: [String: String]
    let payload: String
}

public struct LocalHealthExportReceipt: Equatable, Sendable {
    public let url: URL
    public let recoveryKey: String

    public init(url: URL, recoveryKey: String) {
        self.url = url
        self.recoveryKey = recoveryKey
    }
}

public final class LocalHealthStore: @unchecked Sendable {
    let databaseURL: URL
    let exportDirectory: URL
    let crypto: LocalHealthCrypto
    let fileProtection: any LocalHealthFileProtectionApplying
    let protectedDataAvailable: @Sendable () -> Bool
    let randomBytes: @Sendable (Int) throws -> Data
    private let lock = NSRecursiveLock()

    public init(
        databaseURL: URL,
        rootKey: Data,
        exportDirectory: URL,
        fileProtection: any LocalHealthFileProtectionApplying =
            SystemLocalHealthFileProtection(),
        protectedDataAvailable: @escaping @Sendable () -> Bool = { true },
        randomBytes: @escaping @Sendable (Int) throws -> Data =
            LocalHealthStore.systemRandomBytes
    ) throws {
        self.databaseURL = databaseURL
        self.exportDirectory = exportDirectory
        crypto = try LocalHealthCrypto(rootKey: rootKey)
        self.fileProtection = fileProtection
        self.protectedDataAvailable = protectedDataAvailable
        self.randomBytes = randomBytes
    }

    public func putEncrypted(
        collection: LocalHealthCollection,
        id: String,
        version: Int,
        equalityIndexes: [String: String],
        payload: String
    ) throws {
        try locked {
            let backup = LocalHealthBackupRecord(
                collection: collection,
                id: id,
                version: version,
                equalityIndexes: equalityIndexes,
                payload: payload
            )
            try validate(backup)
            try withDatabase { database in
                try database.transaction {
                    try write(backup, to: database)
                }
            }
        }
    }

    public func getDecrypted(
        collection: LocalHealthCollection,
        id: String
    ) throws -> String? {
        try locked {
            try withDatabase { database in
                guard let envelope = try readEnvelope(
                    collection: collection,
                    id: id,
                    from: database
                ) else {
                    return nil
                }
                return try decrypt(envelope).payload
            }
        }
    }

    public func listDecrypted(
        collection: LocalHealthCollection,
        index: String,
        value: String
    ) throws -> [String] {
        try locked {
            guard !index.isEmpty, !value.isEmpty else {
                throw LocalHealthKernelError.invalidEnvelope
            }
            let blindValue = try crypto.blindIndex(
                domain: indexDomain(collection: collection, name: index),
                value: value
            )
            return try withDatabase { database in
                let statement = try database.prepare(
                    """
                    SELECT r.schema_version, r.object_id, r.object_version,
                           r.nonce, r.ciphertext, r.tag
                    FROM encrypted_records r
                    JOIN blind_indexes i
                      ON i.collection = r.collection
                     AND i.object_id = r.object_id
                    WHERE i.collection = ? AND i.index_name = ?
                      AND i.index_value = ?
                    ORDER BY r.object_id
                    """
                )
                defer { sqlite3_finalize(statement) }
                try localHealthBindText(collection.rawValue, at: 1, to: statement)
                try localHealthBindText(index, at: 2, to: statement)
                try localHealthBindText(blindValue, at: 3, to: statement)
                var payloads: [String] = []
                while sqlite3_step(statement) == SQLITE_ROW {
                    let envelope = try envelopeFromRow(
                        statement,
                        collection: collection,
                        columnOffset: 0
                    )
                    payloads.append(try decrypt(envelope).payload)
                }
                return payloads
            }
        }
    }

    public func delete(
        collection: LocalHealthCollection,
        id: String
    ) throws {
        try locked {
            try withDatabase { database in
                try delete(collection: collection, id: id, from: database)
            }
        }
    }

    public func applyMutation(
        writes: [LocalHealthMutationWrite],
        deletes: [LocalHealthMutationDelete]
    ) throws {
        try locked {
            guard !writes.isEmpty || !deletes.isEmpty,
                  writes.count + deletes.count <= 1_000 else {
                throw LocalHealthKernelError.invalidEnvelope
            }
            let records = writes.map {
                LocalHealthBackupRecord(
                    collection: $0.collection,
                    id: $0.id,
                    version: $0.version,
                    equalityIndexes: $0.equalityIndexes,
                    payload: $0.payload
                )
            }
            for record in records {
                try validate(record)
            }
            guard deletes.allSatisfy({ !$0.id.isEmpty }) else {
                throw LocalHealthKernelError.invalidEnvelope
            }
            try withDatabase { database in
                try database.transaction {
                    for record in records {
                        try write(record, to: database)
                    }
                    for deletion in deletes {
                        try delete(
                            collection: deletion.collection,
                            id: deletion.id,
                            from: database
                        )
                    }
                }
            }
        }
    }

    func allBackupRecords() throws -> [LocalHealthBackupRecord] {
        try locked {
            try withDatabase { database in
                let statement = try database.prepare(
                    """
                    SELECT schema_version, collection, object_id, object_version,
                           nonce, ciphertext, tag
                    FROM encrypted_records
                    ORDER BY collection, object_id
                    """
                )
                defer { sqlite3_finalize(statement) }
                var records: [LocalHealthBackupRecord] = []
                while sqlite3_step(statement) == SQLITE_ROW {
                    let collectionValue = try localHealthText(from: statement, at: 1)
                    guard let collection = LocalHealthCollection(rawValue: collectionValue) else {
                        throw LocalHealthKernelError.invalidEnvelope
                    }
                    let envelope = LocalHealthEncryptedEnvelope(
                        schemaVersion: Int(sqlite3_column_int(statement, 0)),
                        collection: collectionValue,
                        objectID: try localHealthText(from: statement, at: 2),
                        objectVersion: Int(sqlite3_column_int(statement, 3)),
                        nonce: localHealthBlob(from: statement, at: 4),
                        ciphertext: localHealthBlob(from: statement, at: 5),
                        tag: localHealthBlob(from: statement, at: 6)
                    )
                    let stored = try decrypt(envelope)
                    records.append(
                        LocalHealthBackupRecord(
                            collection: collection,
                            id: envelope.objectID,
                            version: envelope.objectVersion,
                            equalityIndexes: stored.equalityIndexes,
                            payload: stored.payload
                        )
                    )
                }
                return records
            }
        }
    }

    func restoreValidatedRecords(_ records: [LocalHealthBackupRecord]) throws {
        try locked {
            try withDatabase { database in
                guard try recordCount(in: database) == 0 else {
                    throw LocalHealthKernelError.vaultNotEmpty
                }
                try database.transaction {
                    for record in records {
                        try write(record, to: database)
                    }
                }
            }
        }
    }

    func isEmpty() throws -> Bool {
        try locked {
            try withDatabase { try recordCount(in: $0) == 0 }
        }
    }

    func validate(_ record: LocalHealthBackupRecord) throws {
        guard !record.id.isEmpty, record.version > 0 else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        for (name, value) in record.equalityIndexes {
            guard !name.isEmpty, !value.isEmpty else {
                throw LocalHealthKernelError.invalidEnvelope
            }
        }
    }

    private func write(
        _ record: LocalHealthBackupRecord,
        to database: LocalHealthSQLiteDatabase
    ) throws {
        let stored = LocalHealthStoredPayload(
            payload: record.payload,
            equalityIndexes: record.equalityIndexes
        )
        let plaintext = try JSONEncoder().encode(stored)
        let envelope = try crypto.seal(
            plaintext,
            collection: record.collection.rawValue,
            objectID: record.id,
            objectVersion: record.version
        )
        let statement = try database.prepare(
            """
            INSERT INTO encrypted_records(
                collection, object_id, object_version, schema_version,
                nonce, ciphertext, tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(collection, object_id) DO UPDATE SET
                object_version = excluded.object_version,
                schema_version = excluded.schema_version,
                nonce = excluded.nonce,
                ciphertext = excluded.ciphertext,
                tag = excluded.tag
            """
        )
        defer { sqlite3_finalize(statement) }
        try localHealthBindText(record.collection.rawValue, at: 1, to: statement)
        try localHealthBindText(record.id, at: 2, to: statement)
        sqlite3_bind_int(statement, 3, Int32(record.version))
        sqlite3_bind_int(statement, 4, Int32(envelope.schemaVersion))
        try localHealthBindBlob(envelope.nonce, at: 5, to: statement)
        try localHealthBindBlob(envelope.ciphertext, at: 6, to: statement)
        try localHealthBindBlob(envelope.tag, at: 7, to: statement)
        guard sqlite3_step(statement) == SQLITE_DONE else {
            throw LocalHealthKernelError.storageFailure
        }

        let deleteIndexes = try database.prepare(
            "DELETE FROM blind_indexes WHERE collection = ? AND object_id = ?"
        )
        try localHealthBindText(record.collection.rawValue, at: 1, to: deleteIndexes)
        try localHealthBindText(record.id, at: 2, to: deleteIndexes)
        let deleteResult = sqlite3_step(deleteIndexes)
        sqlite3_finalize(deleteIndexes)
        guard deleteResult == SQLITE_DONE else {
            throw LocalHealthKernelError.storageFailure
        }

        for (name, value) in record.equalityIndexes.sorted(by: { $0.key < $1.key }) {
            let indexStatement = try database.prepare(
                """
                INSERT INTO blind_indexes(
                    collection, object_id, index_name, index_value
                ) VALUES (?, ?, ?, ?)
                """
            )
            do {
                try localHealthBindText(record.collection.rawValue, at: 1, to: indexStatement)
                try localHealthBindText(record.id, at: 2, to: indexStatement)
                try localHealthBindText(name, at: 3, to: indexStatement)
                try localHealthBindText(
                    crypto.blindIndex(
                        domain: indexDomain(collection: record.collection, name: name),
                        value: value
                    ),
                    at: 4,
                    to: indexStatement
                )
                guard sqlite3_step(indexStatement) == SQLITE_DONE else {
                    throw LocalHealthKernelError.storageFailure
                }
                sqlite3_finalize(indexStatement)
            } catch {
                sqlite3_finalize(indexStatement)
                throw error
            }
        }
    }

    private func readEnvelope(
        collection: LocalHealthCollection,
        id: String,
        from database: LocalHealthSQLiteDatabase
    ) throws -> LocalHealthEncryptedEnvelope? {
        let statement = try database.prepare(
            """
            SELECT schema_version, object_id, object_version,
                   nonce, ciphertext, tag
            FROM encrypted_records
            WHERE collection = ? AND object_id = ?
            """
        )
        defer { sqlite3_finalize(statement) }
        try localHealthBindText(collection.rawValue, at: 1, to: statement)
        try localHealthBindText(id, at: 2, to: statement)
        let result = sqlite3_step(statement)
        if result == SQLITE_DONE {
            return nil
        }
        guard result == SQLITE_ROW else {
            throw LocalHealthKernelError.storageFailure
        }
        return try envelopeFromRow(
            statement,
            collection: collection,
            columnOffset: 0
        )
    }

    private func delete(
        collection: LocalHealthCollection,
        id: String,
        from database: LocalHealthSQLiteDatabase
    ) throws {
        guard !id.isEmpty else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        let statement = try database.prepare(
            "DELETE FROM encrypted_records WHERE collection = ? AND object_id = ?"
        )
        defer { sqlite3_finalize(statement) }
        try localHealthBindText(collection.rawValue, at: 1, to: statement)
        try localHealthBindText(id, at: 2, to: statement)
        guard sqlite3_step(statement) == SQLITE_DONE else {
            throw LocalHealthKernelError.storageFailure
        }
    }

    private func envelopeFromRow(
        _ statement: OpaquePointer,
        collection: LocalHealthCollection,
        columnOffset: Int32
    ) throws -> LocalHealthEncryptedEnvelope {
        LocalHealthEncryptedEnvelope(
            schemaVersion: Int(sqlite3_column_int(statement, columnOffset)),
            collection: collection.rawValue,
            objectID: try localHealthText(from: statement, at: columnOffset + 1),
            objectVersion: Int(sqlite3_column_int(statement, columnOffset + 2)),
            nonce: localHealthBlob(from: statement, at: columnOffset + 3),
            ciphertext: localHealthBlob(from: statement, at: columnOffset + 4),
            tag: localHealthBlob(from: statement, at: columnOffset + 5)
        )
    }

    private func decrypt(
        _ envelope: LocalHealthEncryptedEnvelope
    ) throws -> LocalHealthStoredPayload {
        let plaintext = try crypto.open(envelope)
        do {
            return try JSONDecoder().decode(LocalHealthStoredPayload.self, from: plaintext)
        } catch {
            throw LocalHealthKernelError.invalidEnvelope
        }
    }

    private func recordCount(in database: LocalHealthSQLiteDatabase) throws -> Int {
        let statement = try database.prepare("SELECT COUNT(*) FROM encrypted_records")
        defer { sqlite3_finalize(statement) }
        guard sqlite3_step(statement) == SQLITE_ROW else {
            throw LocalHealthKernelError.storageFailure
        }
        return Int(sqlite3_column_int(statement, 0))
    }

    private func indexDomain(
        collection: LocalHealthCollection,
        name: String
    ) -> String {
        "\(collection.rawValue).\(name).v1"
    }

    private func withDatabase<T>(
        _ body: (LocalHealthSQLiteDatabase) throws -> T
    ) throws -> T {
        guard protectedDataAvailable() else {
            throw LocalHealthKernelError.protectedDataUnavailable
        }
        let existed = FileManager.default.fileExists(atPath: databaseURL.path)
        do {
            try FileManager.default.createDirectory(
                at: databaseURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let database = try LocalHealthSQLiteDatabase(url: databaseURL)
            if !existed {
                try fileProtection.applyCompleteProtection(to: databaseURL)
            }
            return try body(database)
        } catch let error as LocalHealthKernelError {
            throw error
        } catch {
            throw LocalHealthKernelError.storageFailure
        }
    }

    private func locked<T>(_ body: () throws -> T) throws -> T {
        lock.lock()
        defer { lock.unlock() }
        return try body()
    }

    public static func systemRandomBytes(count: Int) throws -> Data {
        guard count > 0 else {
            throw LocalHealthKernelError.storageFailure
        }
        var generator = SystemRandomNumberGenerator()
        return Data((0..<count).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
    }
}
