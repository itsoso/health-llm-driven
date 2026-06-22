import SwiftUI
import HealthAgentMacCore

struct CalendarView: View {
    let client: CalendarClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var sources: [CalendarSource] = []
    @State private var events: [CalendarEvent] = []
    @State private var syncResult: CalendarSyncResult?
    @State private var isLoading = false
    @State private var isSyncing = false
    @State private var isAdding = false
    @State private var updatingSourceIDs: Set<Int> = []
    @State private var deletingSourceID: Int?
    @State private var errorMessage: String?
    @State private var formProvider: CalendarProviderOption = .ics
    @State private var formName = ""
    @State private var formURL = ""
    @State private var formUsername = ""
    @State private var formPassword = ""
    @State private var formColor = "#34C759"
    @State private var didInitialLoad = false

    private var activeSources: Int {
        sources.filter(\.syncEnabled).count
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                summaryGrid
                sourceManagement
                upcomingEvents
            }
            .padding(24)
            .frame(maxWidth: 1080, alignment: .leading)
        }
        .task {
            if !didInitialLoad {
                didInitialLoad = true
                await refresh()
            }
        }
    }

    private var header: some View {
        HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                Text(appText("Calendar", appLanguageRaw))
                    .font(.largeTitle.weight(.bold))
                Text(appText("Connect external calendars, sync them into Reva, and inspect upcoming events without writing back.", appLanguageRaw))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 10) {
                Button {
                    Task { await refresh() }
                } label: {
                    Label(appText("Refresh", appLanguageRaw), systemImage: isLoading ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
                }
                .disabled(isLoading || isSyncing)

                Button {
                    Task { await syncNow() }
                } label: {
                    Label(appText("Sync Now", appLanguageRaw), systemImage: isSyncing ? "arrow.triangle.2.circlepath" : "arrow.clockwise.icloud")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isLoading || isSyncing || sources.isEmpty)
            }
        }
    }

    private var summaryGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
            summaryTile(appText("Sources", appLanguageRaw), "\(sources.count)", "calendar.badge.clock", .blue)
            summaryTile(appText("Sync Enabled", appLanguageRaw), "\(activeSources)", "checkmark.icloud", .green)
            summaryTile(appText("Upcoming Events", appLanguageRaw), "\(events.count)", "list.bullet.rectangle", .purple)
            summaryTile(appText("Last Sync", appLanguageRaw), lastSyncLabel, "clock.arrow.circlepath", .orange)
        }
    }

    private var lastSyncLabel: String {
        if let syncResult {
            return "\(syncResult.count)"
        }
        let last = sources.compactMap(\.lastSyncAt).sorted().last
        return last.map(shortTimestamp) ?? appText("Never", appLanguageRaw)
    }

    private func summaryTile(_ title: String, _ value: String, _ icon: String, _ color: Color) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 34, height: 34)
                .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 3) {
                Text(value)
                    .font(.title3.weight(.bold))
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.12)))
    }

    private var sourceManagement: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader(
                appText("Calendar Sources", appLanguageRaw),
                appText("CalDAV and ICS are read-only imports; credentials never appear in this list.", appLanguageRaw),
                icon: "calendar.badge.plus"
            )

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
            }

            if isLoading && sources.isEmpty {
                ProgressView(appText("Loading calendar sources...", appLanguageRaw))
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if sources.isEmpty {
                ContentUnavailableView(
                    appText("No calendar sources", appLanguageRaw),
                    systemImage: "calendar.badge.plus",
                    description: Text(appText("Add an ICS subscription or CalDAV account to let Reva plan around real commitments.", appLanguageRaw))
                )
                .frame(minHeight: 150)
            } else {
                VStack(spacing: 10) {
                    ForEach(sources) { source in
                        sourceRow(source)
                    }
                }
            }

            addSourceForm
        }
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.12)))
    }

    private func sourceRow(_ source: CalendarSource) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Circle()
                .fill(color(from: source.color))
                .frame(width: 12, height: 12)
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Text(source.name)
                        .font(.headline)
                        .lineLimit(1)
                    Text(source.provider.uppercased())
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2)
                        .background(.regularMaterial, in: Capsule())
                    if !source.writable {
                        Text(appText("Read-only", appLanguageRaw))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                }
                Text(sourceMeta(source))
                    .font(.caption)
                    .foregroundStyle(source.lastError == nil ? Color.secondary : Color.orange)
                    .lineLimit(2)
            }
            Spacer()
            Toggle(appText("Sync Enabled", appLanguageRaw), isOn: binding(for: source))
                .labelsHidden()
                .disabled(updatingSourceIDs.contains(source.id) || deletingSourceID == source.id)
                .help(appText("Enable or pause sync for this source.", appLanguageRaw))
            Button(role: .destructive) {
                Task { await deleteSource(source) }
            } label: {
                if deletingSourceID == source.id {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Label(appText("Delete", appLanguageRaw), systemImage: "trash")
                }
            }
            .disabled(deletingSourceID != nil || updatingSourceIDs.contains(source.id))
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var addSourceForm: some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()
            Text(appText("Add Source", appLanguageRaw))
                .font(.headline)
            HStack(spacing: 10) {
                Picker(appText("Provider", appLanguageRaw), selection: $formProvider) {
                    ForEach(CalendarProviderOption.allCases) { option in
                        Text(option.title).tag(option)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 220)

                TextField(appText("Source Name", appLanguageRaw), text: $formName)
                    .textFieldStyle(.roundedBorder)
                TextField(formProvider == .ics ? appText("ICS URL", appLanguageRaw) : appText("CalDAV URL", appLanguageRaw), text: $formURL)
                    .textFieldStyle(.roundedBorder)
            }
            HStack(spacing: 10) {
                TextField(appText("Color", appLanguageRaw), text: $formColor)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 120)
                if formProvider == .caldav {
                    TextField(appText("Username", appLanguageRaw), text: $formUsername)
                        .textFieldStyle(.roundedBorder)
                    SecureField(appText("Password", appLanguageRaw), text: $formPassword)
                        .textFieldStyle(.roundedBorder)
                }
                Button {
                    Task { await addSource() }
                } label: {
                    if isAdding {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label(appText("Add Source", appLanguageRaw), systemImage: "plus")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canAddSource || isAdding)
            }
            Text(appText("Only https calendar URLs are accepted. Reva imports events but never writes back to external calendars.", appLanguageRaw))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var canAddSource: Bool {
        !trimmed(formName).isEmpty && isHTTPSURL(formURL)
    }

    private var upcomingEvents: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader(
                appText("Upcoming Events", appLanguageRaw),
                appText("Read-only event details from your own calendar sources. Agent paths must use the privacy seam.", appLanguageRaw),
                icon: "calendar.day.timeline.left"
            )
            if isLoading && events.isEmpty {
                ProgressView(appText("Loading events...", appLanguageRaw))
                    .frame(maxWidth: .infinity, minHeight: 140)
            } else if events.isEmpty {
                ContentUnavailableView(
                    appText("No upcoming events", appLanguageRaw),
                    systemImage: "calendar",
                    description: Text(appText("Sync a source to show the next seven days here and in Today Timeline.", appLanguageRaw))
                )
                .frame(minHeight: 160)
            } else {
                VStack(spacing: 8) {
                    ForEach(events.prefix(80)) { event in
                        eventRow(event)
                    }
                }
            }
        }
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.12)))
    }

    private func eventRow(_ event: CalendarEvent) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: event.allDay ? "calendar" : "clock")
                .font(.headline)
                .foregroundStyle(.teal)
                .frame(width: 32, height: 32)
                .background(.teal.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 5) {
                Text((event.title?.isEmpty == false ? event.title : appText("Untitled Event", appLanguageRaw)) ?? appText("Untitled Event", appLanguageRaw))
                    .font(.headline)
                    .lineLimit(2)
                Text(eventTimeLine(event))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let location = event.location, !location.isEmpty {
                    Text(location)
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if let source = sourceName(for: event.sourceID) {
                Text(source)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.regularMaterial, in: Capsule())
            }
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private func sectionHeader(_ title: String, _ subtitle: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(.teal)
                .frame(width: 28, height: 28)
                .background(.teal.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.title3.weight(.bold))
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    private func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let sourcesResult = client.listSources()
            async let eventsResult = client.fetchEvents(from: Self.ymd(Date()), to: Self.ymd(Self.weekAhead()))
            sources = try await sourcesResult
            events = try await eventsResult
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func syncNow() async {
        isSyncing = true
        errorMessage = nil
        defer { isSyncing = false }
        do {
            syncResult = try await client.sync()
            await refresh()
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func addSource() async {
        guard canAddSource else { return }
        isAdding = true
        errorMessage = nil
        defer { isAdding = false }
        do {
            let username = formProvider == .caldav ? nilIfEmpty(formUsername) : nil
            let password = formProvider == .caldav ? nilIfEmpty(formPassword) : nil
            let request = CalendarSourceCreateRequest(
                provider: formProvider.rawValue,
                name: trimmed(formName),
                url: trimmed(formURL),
                color: nilIfEmpty(formColor),
                username: username,
                password: password
            )
            _ = try await client.addSource(request)
            clearForm()
            await refresh()
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func updateSource(_ source: CalendarSource, syncEnabled: Bool) async {
        updatingSourceIDs.insert(source.id)
        errorMessage = nil
        defer { updatingSourceIDs.remove(source.id) }
        do {
            let updated = try await client.updateSource(id: source.id, patch: .init(syncEnabled: syncEnabled))
            if let index = sources.firstIndex(where: { $0.id == source.id }) {
                sources[index] = updated
            }
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func deleteSource(_ source: CalendarSource) async {
        deletingSourceID = source.id
        errorMessage = nil
        defer { deletingSourceID = nil }
        do {
            try await client.deleteSource(id: source.id)
            sources.removeAll { $0.id == source.id }
            events.removeAll { $0.sourceID == source.id }
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func binding(for source: CalendarSource) -> Binding<Bool> {
        Binding(
            get: { sources.first(where: { $0.id == source.id })?.syncEnabled ?? source.syncEnabled },
            set: { enabled in Task { await updateSource(source, syncEnabled: enabled) } }
        )
    }

    private func sourceMeta(_ source: CalendarSource) -> String {
        if let error = source.lastError, !error.isEmpty {
            return "\(appText("Last Error", appLanguageRaw)): \(error)"
        }
        if let lastSyncAt = source.lastSyncAt {
            return "\(appText("Last Sync", appLanguageRaw)): \(shortTimestamp(lastSyncAt))"
        }
        return appText("Never synced", appLanguageRaw)
    }

    private func sourceName(for sourceID: Int?) -> String? {
        guard let sourceID else { return nil }
        return sources.first { $0.id == sourceID }?.name
    }

    private func eventTimeLine(_ event: CalendarEvent) -> String {
        if event.allDay {
            return appText("All-day", appLanguageRaw)
        }
        let start = formatDateTime(event.start)
        let end = formatDateTime(event.end)
        switch (start, end) {
        case let (start?, end?):
            return "\(start) - \(end)"
        case let (start?, nil):
            return start
        default:
            return appText("Time not set", appLanguageRaw)
        }
    }

    private func shortTimestamp(_ value: String) -> String {
        if let date = Self.parseISODate(value) {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: AppLanguage(storedValue: appLanguageRaw) == .zh ? "zh_CN" : "en_US")
            formatter.dateFormat = AppLanguage(storedValue: appLanguageRaw) == .zh ? "M月d日 HH:mm" : "MMM d HH:mm"
            return formatter.string(from: date)
        }
        return value.replacingOccurrences(of: "T", with: " ").prefix(16).description
    }

    private func formatDateTime(_ value: String?) -> String? {
        guard let value, let date = Self.parseISODate(value) else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: AppLanguage(storedValue: appLanguageRaw) == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = AppLanguage(storedValue: appLanguageRaw) == .zh ? "M月d日 HH:mm" : "MMM d HH:mm"
        return formatter.string(from: date)
    }

    private func clearForm() {
        formProvider = .ics
        formName = ""
        formURL = ""
        formUsername = ""
        formPassword = ""
        formColor = "#34C759"
    }

    private func color(from hex: String?) -> Color {
        let raw = (hex ?? "#34C759").trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard raw.count == 6, let value = UInt64(raw, radix: 16) else { return .green }
        return Color(
            red: Double((value >> 16) & 0xFF) / 255.0,
            green: Double((value >> 8) & 0xFF) / 255.0,
            blue: Double(value & 0xFF) / 255.0
        )
    }

    private func nilIfEmpty(_ value: String) -> String? {
        let trimmed = trimmed(value)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func isHTTPSURL(_ value: String) -> Bool {
        guard let url = URL(string: trimmed(value)) else { return false }
        return url.scheme == "https" && url.host?.isEmpty == false
    }

    private static func weekAhead() -> Date {
        Foundation.Calendar.current.date(byAdding: .day, value: 7, to: Date()) ?? Date()
    }

    private static func ymd(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private static func parseISODate(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) {
            return date
        }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
}

private enum CalendarProviderOption: String, CaseIterable, Identifiable {
    case ics
    case caldav

    var id: String { rawValue }
    var title: String { rawValue.uppercased() }
}
