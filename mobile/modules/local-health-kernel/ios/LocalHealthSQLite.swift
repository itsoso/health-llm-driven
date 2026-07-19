import Foundation
import SQLite3

let localHealthSQLiteTransient = unsafeBitCast(
    -1,
    to: sqlite3_destructor_type.self
)

final class LocalHealthSQLiteDatabase {
    let handle: OpaquePointer

    init(url: URL) throws {
        var database: OpaquePointer?
        let flags = SQLITE_OPEN_CREATE | SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX
        guard sqlite3_open_v2(url.path, &database, flags, nil) == SQLITE_OK,
              let database else {
            if let database {
                sqlite3_close(database)
            }
            throw LocalHealthKernelError.storageFailure
        }
        handle = database
        do {
            try execute("PRAGMA journal_mode = DELETE")
            try execute("PRAGMA synchronous = FULL")
            try execute("PRAGMA foreign_keys = ON")
            try execute(Self.schema)
        } catch {
            throw error
        }
    }

    deinit {
        sqlite3_close(handle)
    }

    func execute(_ sql: String) throws {
        guard sqlite3_exec(handle, sql, nil, nil, nil) == SQLITE_OK else {
            throw LocalHealthKernelError.storageFailure
        }
    }

    func prepare(_ sql: String) throws -> OpaquePointer {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK,
              let statement else {
            throw LocalHealthKernelError.storageFailure
        }
        return statement
    }

    func transaction<T>(_ body: () throws -> T) throws -> T {
        try execute("BEGIN IMMEDIATE")
        do {
            let result = try body()
            try execute("COMMIT")
            return result
        } catch {
            try? execute("ROLLBACK")
            throw error
        }
    }

    private static let schema = """
    CREATE TABLE IF NOT EXISTS encrypted_records (
        collection TEXT NOT NULL,
        object_id TEXT NOT NULL,
        object_version INTEGER NOT NULL,
        schema_version INTEGER NOT NULL,
        nonce BLOB NOT NULL,
        ciphertext BLOB NOT NULL,
        tag BLOB NOT NULL,
        PRIMARY KEY (collection, object_id)
    );
    CREATE TABLE IF NOT EXISTS blind_indexes (
        collection TEXT NOT NULL,
        object_id TEXT NOT NULL,
        index_name TEXT NOT NULL,
        index_value TEXT NOT NULL,
        PRIMARY KEY (collection, object_id, index_name),
        FOREIGN KEY (collection, object_id)
            REFERENCES encrypted_records(collection, object_id)
            ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_blind_lookup
        ON blind_indexes(collection, index_name, index_value);
    """
}

func localHealthBindText(
    _ value: String,
    at index: Int32,
    to statement: OpaquePointer
) throws {
    guard sqlite3_bind_text(
        statement,
        index,
        value,
        -1,
        localHealthSQLiteTransient
    ) == SQLITE_OK else {
        throw LocalHealthKernelError.storageFailure
    }
}

func localHealthBindBlob(
    _ value: Data,
    at index: Int32,
    to statement: OpaquePointer
) throws {
    let result = value.withUnsafeBytes { bytes in
        sqlite3_bind_blob(
            statement,
            index,
            bytes.baseAddress,
            Int32(bytes.count),
            localHealthSQLiteTransient
        )
    }
    guard result == SQLITE_OK else {
        throw LocalHealthKernelError.storageFailure
    }
}

func localHealthText(
    from statement: OpaquePointer,
    at index: Int32
) throws -> String {
    guard let value = sqlite3_column_text(statement, index) else {
        throw LocalHealthKernelError.storageFailure
    }
    return String(cString: value)
}

func localHealthBlob(
    from statement: OpaquePointer,
    at index: Int32
) -> Data {
    let count = Int(sqlite3_column_bytes(statement, index))
    guard count > 0, let bytes = sqlite3_column_blob(statement, index) else {
        return Data()
    }
    return Data(bytes: bytes, count: count)
}
