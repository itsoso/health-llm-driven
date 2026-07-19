import CryptoKit
import Foundation

private struct LocalHealthExportEnvelope: Codable, Sendable {
    let schemaVersion: Int
    let salt: Data
    let nonce: Data
    let ciphertext: Data
    let tag: Data
}

private struct LocalHealthExportPayload: Codable, Sendable {
    let records: [LocalHealthBackupRecord]
}

extension LocalHealthStore {
    public func exportEnvelope() throws -> LocalHealthExportReceipt {
        let records = try allBackupRecords()
        let recoveryKey = try randomBytes(32)
        let salt = try randomBytes(16)
        guard recoveryKey.count == 32, salt.count == 16 else {
            throw LocalHealthKernelError.storageFailure
        }
        let exportKey = exportKey(recoveryKey: recoveryKey, salt: salt)
        let payload = try JSONEncoder().encode(LocalHealthExportPayload(records: records))
        let sealed: AES.GCM.SealedBox
        do {
            sealed = try AES.GCM.seal(
                payload,
                using: exportKey,
                authenticating: exportAuthenticatedData
            )
        } catch {
            throw LocalHealthKernelError.storageFailure
        }
        let envelope = LocalHealthExportEnvelope(
            schemaVersion: 1,
            salt: salt,
            nonce: sealed.nonce.withUnsafeBytes { Data($0) },
            ciphertext: sealed.ciphertext,
            tag: sealed.tag
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(envelope)
        try FileManager.default.createDirectory(
            at: exportDirectory,
            withIntermediateDirectories: true
        )
        let url = exportDirectory.appendingPathComponent(
            "reva-local-health-export-\(UUID().uuidString.lowercased()).json"
        )
        try data.write(to: url, options: .atomic)
        try fileProtection.applyCompleteProtection(to: url)
        return LocalHealthExportReceipt(
            url: url,
            recoveryKey: recoveryKey.base64EncodedString()
        )
    }

    public func restoreEnvelope(from url: URL, recoveryKey: String) throws {
        guard try isEmpty() else {
            throw LocalHealthKernelError.vaultNotEmpty
        }
        guard let keyData = Data(base64Encoded: recoveryKey), keyData.count == 32 else {
            throw LocalHealthKernelError.authenticationFailed
        }
        let envelope: LocalHealthExportEnvelope
        do {
            envelope = try JSONDecoder().decode(
                LocalHealthExportEnvelope.self,
                from: Data(contentsOf: url)
            )
        } catch {
            throw LocalHealthKernelError.invalidEnvelope
        }
        guard envelope.schemaVersion == 1, envelope.salt.count == 16 else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        let plaintext: Data
        do {
            let nonce = try AES.GCM.Nonce(data: envelope.nonce)
            let box = try AES.GCM.SealedBox(
                nonce: nonce,
                ciphertext: envelope.ciphertext,
                tag: envelope.tag
            )
            plaintext = try AES.GCM.open(
                box,
                using: exportKey(recoveryKey: keyData, salt: envelope.salt),
                authenticating: exportAuthenticatedData
            )
        } catch {
            throw LocalHealthKernelError.authenticationFailed
        }
        let payload: LocalHealthExportPayload
        do {
            payload = try JSONDecoder().decode(LocalHealthExportPayload.self, from: plaintext)
        } catch {
            throw LocalHealthKernelError.invalidEnvelope
        }
        var identifiers: Set<String> = []
        for record in payload.records {
            try validate(record)
            guard identifiers.insert("\(record.collection.rawValue)|\(record.id)").inserted else {
                throw LocalHealthKernelError.invalidEnvelope
            }
        }
        try restoreValidatedRecords(payload.records)
    }

    private var exportAuthenticatedData: Data {
        Data("1|local-health-export".utf8)
    }

    private func exportKey(recoveryKey: Data, salt: Data) -> SymmetricKey {
        HKDF<SHA256>.deriveKey(
            inputKeyMaterial: SymmetricKey(data: recoveryKey),
            salt: salt,
            info: Data("export.v1".utf8),
            outputByteCount: 32
        )
    }
}
