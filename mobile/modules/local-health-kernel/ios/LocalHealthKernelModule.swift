#if canImport(ExpoModulesCore)
import ExpoModulesCore
import Foundation
import UIKit

public final class LocalHealthKernelModule: Module {
    private struct BridgeMutation: Decodable {
        let writes: [BridgeWrite]
        let deletes: [BridgeDelete]
    }

    private struct BridgeWrite: Decodable {
        let collection: String
        let id: String
        let version: Int
        let equalityIndexes: [String: String]
        let payload: String
    }

    private struct BridgeDelete: Decodable {
        let collection: String
        let id: String
    }

    private struct VaultSession {
        let identityID: String
        let store: LocalHealthStore
    }

    private let lock = NSRecursiveLock()
    private var session: VaultSession?
    private var localVisionEngine: LocalChineseClipVisionEngine?

    public func definition() -> ModuleDefinition {
        Name("LocalHealthKernel")

        AsyncFunction("createVault") { (identityID: String) in
            try self.bridge {
                guard UIApplication.shared.isProtectedDataAvailable else {
                    throw LocalHealthKernelError.protectedDataUnavailable
                }
                let files = try SystemLocalHealthVaultFiles()
                let keyStore = self.makeKeyStore(files: files)
                let rootKey = try keyStore.createVaultKey(identityID: identityID)
                try files.prepareDirectories()
                self.session = VaultSession(
                    identityID: identityID,
                    store: try self.makeStore(rootKey: rootKey, files: files)
                )
            }
        }

        AsyncFunction("openVault") { (identityID: String) in
            try self.bridge {
                let files = try SystemLocalHealthVaultFiles()
                let keyStore = self.makeKeyStore(files: files)
                switch try keyStore.accessState(identityID: identityID) {
                case let .ready(rootKey):
                    try files.prepareDirectories()
                    self.session = VaultSession(
                        identityID: identityID,
                        store: try self.makeStore(rootKey: rootKey, files: files)
                    )
                case .recoveryOnly:
                    throw LocalHealthKernelError.vaultKeyMissing
                case .absent:
                    throw LocalHealthKernelError.vaultKeyMissing
                }
            }
        }

        AsyncFunction("putEncrypted") {
            (collection: String, id: String, version: Int,
             indexes: [String: String], payload: String) in
            try self.bridge {
                try self.requiredStore().putEncrypted(
                    collection: try self.collection(collection),
                    id: id,
                    version: version,
                    equalityIndexes: indexes,
                    payload: payload
                )
            }
        }

        AsyncFunction("commitMutation") { (mutationJSON: String) in
            try self.bridge {
                guard let data = mutationJSON.data(using: .utf8),
                      let mutation = try? JSONDecoder().decode(BridgeMutation.self, from: data)
                else {
                    throw LocalHealthKernelError.invalidEnvelope
                }
                let writes = try mutation.writes.map { write in
                    LocalHealthMutationWrite(
                        collection: try self.collection(write.collection),
                        id: write.id,
                        version: write.version,
                        equalityIndexes: write.equalityIndexes,
                        payload: write.payload
                    )
                }
                let deletes = try mutation.deletes.map { deletion in
                    LocalHealthMutationDelete(
                        collection: try self.collection(deletion.collection),
                        id: deletion.id
                    )
                }
                try self.requiredStore().applyMutation(
                    writes: writes,
                    deletes: deletes
                )
            }
        }

        AsyncFunction("getDecrypted") {
            (collection: String, id: String) -> String? in
            try self.bridge {
                try self.requiredStore().getDecrypted(
                    collection: try self.collection(collection),
                    id: id
                )
            }
        }

        AsyncFunction("listDecrypted") {
            (collection: String, index: String, value: String) -> [String] in
            try self.bridge {
                try self.requiredStore().listDecrypted(
                    collection: try self.collection(collection),
                    index: index,
                    value: value
                )
            }
        }

        AsyncFunction("delete") { (collection: String, id: String) in
            try self.bridge {
                try self.requiredStore().delete(
                    collection: try self.collection(collection),
                    id: id
                )
            }
        }

        AsyncFunction("exportEnvelope") { () -> [String: String] in
            try self.bridge {
                let receipt = try self.requiredStore().exportEnvelope()
                return [
                    "uri": receipt.url.absoluteString,
                    "recoveryKey": receipt.recoveryKey,
                ]
            }
        }

        AsyncFunction("restoreEnvelope") {
            (fileURI: String, recoveryKey: String) in
            try self.bridge {
                guard let url = URL(string: fileURI), url.isFileURL else {
                    throw LocalHealthKernelError.invalidEnvelope
                }
                try self.requiredStore().restoreEnvelope(
                    from: url,
                    recoveryKey: recoveryKey
                )
            }
        }

        AsyncFunction("deleteVault") { () in
            try self.bridge {
                let current = try self.requiredSession()
                let files = try SystemLocalHealthVaultFiles()
                let keyStore = self.makeKeyStore(files: files)
                try keyStore.deleteVault(identityID: current.identityID)
                self.session = nil
            }
        }

        AsyncFunction("recognizeFoodPhoto") { (fileURI: String) async throws -> String in
            var temporaryURL: URL?
            let loader = LocalFoodPhotoLoader()
            do {
                guard let url = URL(string: fileURI), url.isFileURL else {
                    throw LocalFoodVisionError.invalidFileURL
                }
                temporaryURL = url
                let image = try loader.load(fileURL: url)
                let result = try await self.requiredVisionEngine().infer(
                    request: LocalFoodVisionRequest(image: image)
                )
                let data = try JSONEncoder().encode(result)
                guard let json = String(data: data, encoding: .utf8) else {
                    throw LocalFoodVisionError.invalidModelOutput
                }
                try loader.deleteTemporaryCopyIfOwned(fileURL: url)
                return json
            } catch let error as LocalFoodVisionError {
                if let temporaryURL {
                    try loader.deleteTemporaryCopyIfOwned(fileURL: temporaryURL)
                }
                throw NSError(
                    domain: "LocalHealthKernel.Vision",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: String(describing: error)]
                )
            } catch {
                if let temporaryURL {
                    try loader.deleteTemporaryCopyIfOwned(fileURL: temporaryURL)
                }
                throw error
            }
        }

        OnDestroy {
            self.lock.lock()
            self.session = nil
            self.localVisionEngine = nil
            self.lock.unlock()
        }
    }

    private func makeKeyStore(
        files: SystemLocalHealthVaultFiles
    ) -> LocalHealthKeyStore {
        LocalHealthKeyStore(
            keychain: SystemLocalHealthKeychain(),
            files: files,
            randomBytes: { try LocalHealthStore.systemRandomBytes(count: 32) }
        )
    }

    private func makeStore(
        rootKey: Data,
        files: SystemLocalHealthVaultFiles
    ) throws -> LocalHealthStore {
        try LocalHealthStore(
            databaseURL: files.databaseURL,
            rootKey: rootKey,
            exportDirectory: files.exportDirectory,
            protectedDataAvailable: {
                UIApplication.shared.isProtectedDataAvailable
            }
        )
    }

    private func requiredSession() throws -> VaultSession {
        guard let session else {
            throw LocalHealthKernelError.vaultKeyMissing
        }
        return session
    }

    private func requiredStore() throws -> LocalHealthStore {
        try requiredSession().store
    }

    private func requiredVisionEngine() throws -> LocalChineseClipVisionEngine {
        lock.lock()
        defer { lock.unlock() }
        if let localVisionEngine { return localVisionEngine }
        let resources = try LocalFoodVisionResourceLocator.locate()
        let engine = LocalChineseClipVisionEngine(
            modelURL: resources.model,
            labelBankURL: resources.labelBank,
            provenance: LocalFoodVisionProvenance(
                modelArtifactSHA256: "a29b4f25bd993575db9a03bca0613a9074eb7ebb8312bd60748be43793e174a4",
                labelBankVersion: "cn-food-labels-v2",
                calibrationVersion: "exploratory-manual-confirmation-v1",
                precisionVariant: "int8"
            ),
            rankingPolicy: LocalFoodRankingPolicy(
                minimumScore: -1,
                minimumMargin: 0,
                maximumCandidates: 3
            ),
            proposer: LocalFoodVisionSaliencyProposer(),
            preprocessor: LocalFoodVisionPreprocessor(),
            modelLoader: LocalChineseClipCoreMLModelLoader(),
            labelLoader: LocalChineseClipLabelBankLoader(),
            runtimeGuard: LocalFoodProcessRuntimeGuard()
        )
        localVisionEngine = engine
        return engine
    }

    private func collection(_ rawValue: String) throws -> LocalHealthCollection {
        guard let collection = LocalHealthCollection(rawValue: rawValue) else {
            throw LocalHealthKernelError.invalidEnvelope
        }
        return collection
    }

    private func bridge<T>(_ operation: () throws -> T) throws -> T {
        lock.lock()
        defer { lock.unlock() }
        do {
            return try operation()
        } catch let error as LocalHealthKernelError {
            throw NSError(
                domain: "LocalHealthKernel",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: error.rawValue]
            )
        } catch {
            throw NSError(
                domain: "LocalHealthKernel",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: LocalHealthKernelError.storageFailure.rawValue]
            )
        }
    }
}
#endif
