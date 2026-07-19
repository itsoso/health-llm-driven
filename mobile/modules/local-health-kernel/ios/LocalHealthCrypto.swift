import CryptoKit
import Foundation

public struct LocalHealthEncryptedEnvelope: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let collection: String
    public let objectID: String
    public let objectVersion: Int
    public let nonce: Data
    public let ciphertext: Data
    public let tag: Data

    public init(
        schemaVersion: Int,
        collection: String,
        objectID: String,
        objectVersion: Int,
        nonce: Data,
        ciphertext: Data,
        tag: Data
    ) {
        self.schemaVersion = schemaVersion
        self.collection = collection
        self.objectID = objectID
        self.objectVersion = objectVersion
        self.nonce = nonce
        self.ciphertext = ciphertext
        self.tag = tag
    }
}

enum LocalHealthKeyPurpose: String, Sendable {
    case recordEncryption = "record.v1"
    case blindIndex = "blind-index.v1"
}

public struct LocalHealthCrypto: Sendable {
    public static let schemaVersion = 1

    private let recordKey: SymmetricKey
    private let blindIndexKey: SymmetricKey

    public init(rootKey: Data) throws {
        recordKey = try Self.deriveSubkey(
            rootKey: rootKey,
            purpose: .recordEncryption
        )
        blindIndexKey = try Self.deriveSubkey(
            rootKey: rootKey,
            purpose: .blindIndex
        )
    }

    public func seal(
        _ plaintext: Data,
        collection: String,
        objectID: String,
        objectVersion: Int
    ) throws -> LocalHealthEncryptedEnvelope {
        guard !collection.isEmpty, !objectID.isEmpty, objectVersion > 0 else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        do {
            let authenticatedData = Self.authenticatedData(
                schemaVersion: Self.schemaVersion,
                collection: collection,
                objectID: objectID,
                objectVersion: objectVersion
            )
            let sealed = try AES.GCM.seal(
                plaintext,
                using: recordKey,
                authenticating: authenticatedData
            )
            return LocalHealthEncryptedEnvelope(
                schemaVersion: Self.schemaVersion,
                collection: collection,
                objectID: objectID,
                objectVersion: objectVersion,
                nonce: sealed.nonce.withUnsafeBytes { Data($0) },
                ciphertext: sealed.ciphertext,
                tag: sealed.tag
            )
        } catch let error as LocalHealthKernelError {
            throw error
        } catch {
            throw LocalHealthKernelError.storageFailure
        }
    }

    public func open(_ envelope: LocalHealthEncryptedEnvelope) throws -> Data {
        guard envelope.schemaVersion == Self.schemaVersion,
              !envelope.collection.isEmpty,
              !envelope.objectID.isEmpty,
              envelope.objectVersion > 0 else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        do {
            let nonce = try AES.GCM.Nonce(data: envelope.nonce)
            let box = try AES.GCM.SealedBox(
                nonce: nonce,
                ciphertext: envelope.ciphertext,
                tag: envelope.tag
            )
            return try AES.GCM.open(
                box,
                using: recordKey,
                authenticating: Self.authenticatedData(
                    schemaVersion: envelope.schemaVersion,
                    collection: envelope.collection,
                    objectID: envelope.objectID,
                    objectVersion: envelope.objectVersion
                )
            )
        } catch {
            throw LocalHealthKernelError.authenticationFailed
        }
    }

    public func blindIndex(domain: String, value: String) throws -> String {
        guard !domain.isEmpty, !value.isEmpty else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        let input = Data("\(domain)|\(value)".utf8)
        let digest = HMAC<SHA256>.authenticationCode(
            for: input,
            using: blindIndexKey
        )
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    static func deriveSubkey(
        rootKey: Data,
        purpose: LocalHealthKeyPurpose
    ) throws -> SymmetricKey {
        guard rootKey.count == 32 else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        return HKDF<SHA256>.deriveKey(
            inputKeyMaterial: SymmetricKey(data: rootKey),
            salt: Data("local-health-kernel.v1".utf8),
            info: Data(purpose.rawValue.utf8),
            outputByteCount: 32
        )
    }

    private static func authenticatedData(
        schemaVersion: Int,
        collection: String,
        objectID: String,
        objectVersion: Int
    ) -> Data {
        Data("\(schemaVersion)|\(collection)|\(objectID)|\(objectVersion)".utf8)
    }
}
