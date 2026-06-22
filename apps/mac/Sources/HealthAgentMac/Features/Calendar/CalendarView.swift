import SwiftUI
import HealthAgentMacCore

struct CalendarView: View {
    let client: CalendarClient
    @AppStorage(AppLanguage.defaultsKey) private var appLanguageRaw = AppLanguage.defaultLanguage.rawValue

    @State private var sources: [CalendarSource] = []
    @State private var events: [CalendarEvent] = []
    @State private var syncResult: CalendarSyncResult?
    @State private var isLoading = false
    @State private var isLoadingEvents = false
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
    @State private var selectedScope: CalendarSurfaceScope = .month
    @State private var anchorDate = Date()

    private var language: AppLanguage { AppLanguage(storedValue: appLanguageRaw) }

    private var uiCalendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        calendar.firstWeekday = 2
        return calendar
    }

    private var currentWindow: CalendarSurfaceLayout.Window {
        CalendarSurfaceLayout.window(scope: selectedScope, anchor: anchorDate, calendar: uiCalendar)
    }

    private var currentWindowDays: [Date] {
        CalendarSurfaceLayout.days(in: currentWindow, calendar: uiCalendar)
    }

    private var activeSources: Int {
        sources.filter(\.syncEnabled).count
    }

    private var sortedEvents: [CalendarEvent] {
        events.sorted { lhs, rhs in
            let lhsDate = Self.parseISODate(lhs.start) ?? .distantFuture
            let rhsDate = Self.parseISODate(rhs.start) ?? .distantFuture
            if lhsDate != rhsDate { return lhsDate < rhsDate }
            return (lhs.title ?? "") < (rhs.title ?? "")
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            calendarSidebar
                .frame(width: 286)
                .background(Color(nsColor: .controlBackgroundColor))

            Divider()

            VStack(spacing: 0) {
                toolbar
                    .padding(.horizontal, 20)
                    .padding(.vertical, 14)
                    .background(.background)

                Divider()

                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if let errorMessage {
                            Label(errorMessage, systemImage: "exclamationmark.triangle")
                                .font(.callout)
                                .foregroundStyle(.orange)
                                .padding(12)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
                        }

                        calendarCanvas

                        upcomingStrip
                    }
                    .padding(20)
                }
                .background(Color(nsColor: .textBackgroundColor).opacity(0.35))
            }
        }
        .task {
            if !didInitialLoad {
                didInitialLoad = true
                await refresh()
            }
        }
        .onChange(of: selectedScope) { _, _ in
            Task { await refreshEventsForVisibleRange() }
        }
        .onChange(of: anchorDate) { _, _ in
            Task { await refreshEventsForVisibleRange() }
        }
    }

    private var toolbar: some View {
        HStack(spacing: 10) {
            Button {
                moveWindow(-1)
            } label: {
                Image(systemName: "chevron.left")
            }
            .help(appText("Previous", appLanguageRaw))

            Button {
                anchorDate = Date()
            } label: {
                Text(appText("Today", appLanguageRaw))
            }
            .keyboardShortcut("t", modifiers: [.command])

            Button {
                moveWindow(1)
            } label: {
                Image(systemName: "chevron.right")
            }
            .help(appText("Next", appLanguageRaw))

            Text(windowTitle(currentWindow))
                .font(.title2.weight(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.85)
                .padding(.leading, 8)

            Spacer()

            Picker(appText("Calendar View", appLanguageRaw), selection: $selectedScope) {
                ForEach(CalendarSurfaceScope.allCases) { scope in
                    Text(scopeLabel(scope)).tag(scope)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 250)

            Button {
                Task { await refresh() }
            } label: {
                Image(systemName: isLoading || isLoadingEvents ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
            }
            .disabled(isLoading || isLoadingEvents || isSyncing)
            .help(appText("Refresh", appLanguageRaw))

            Button {
                Task { await syncNow() }
            } label: {
                Label(appText("Sync Now", appLanguageRaw), systemImage: isSyncing ? "arrow.triangle.2.circlepath" : "arrow.clockwise.icloud")
            }
            .buttonStyle(.borderedProminent)
            .disabled(isLoading || isLoadingEvents || isSyncing || sources.isEmpty)
        }
    }

    private var calendarSidebar: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(appText("Calendar", appLanguageRaw))
                        .font(.title2.weight(.bold))
                    Text(appText("Read-only calendar workbench for planning around real commitments.", appLanguageRaw))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                miniMonth

                sourceList

                syncStatus

                addSourceForm
            }
            .padding(16)
        }
    }

    private var miniMonth: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(monthTitle(anchorDate))
                    .font(.headline)
                Spacer()
                Button {
                    anchorDate = CalendarSurfaceLayout.moved(anchorDate, scope: .month, offset: -1, calendar: uiCalendar)
                } label: {
                    Image(systemName: "chevron.left")
                }
                .buttonStyle(.plain)
                Button {
                    anchorDate = CalendarSurfaceLayout.moved(anchorDate, scope: .month, offset: 1, calendar: uiCalendar)
                } label: {
                    Image(systemName: "chevron.right")
                }
                .buttonStyle(.plain)
            }

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 7), spacing: 6) {
                ForEach(weekdaySymbols, id: \.self) { symbol in
                    Text(symbol)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }

                ForEach(CalendarSurfaceLayout.monthGridDays(containing: anchorDate, calendar: uiCalendar), id: \.self) { date in
                    miniMonthDay(date)
                }
            }
        }
        .padding(12)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.10)))
    }

    private func miniMonthDay(_ date: Date) -> some View {
        let isSelected = uiCalendar.isDate(date, inSameDayAs: anchorDate)
        let isCurrentMonth = uiCalendar.component(.month, from: date) == uiCalendar.component(.month, from: anchorDate)
        let hasEvents = !events(on: date).isEmpty

        return Button {
            anchorDate = uiCalendar.startOfDay(for: date)
            if selectedScope == .year { selectedScope = .month }
        } label: {
            VStack(spacing: 2) {
                Text(dayNumber(date))
                    .font(.caption.weight(isSelected ? .bold : .regular))
                Circle()
                    .fill(hasEvents ? Color.accentColor : Color.clear)
                    .frame(width: 4, height: 4)
            }
            .foregroundStyle(isCurrentMonth ? Color.primary : Color.secondary.opacity(0.55))
            .frame(width: 28, height: 28)
            .background(isSelected ? Color.accentColor.opacity(0.16) : Color.clear, in: Circle())
        }
        .buttonStyle(.plain)
    }

    private var sourceList: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(appText("My Calendars", appLanguageRaw))
                    .font(.headline)
                Spacer()
                Text("\(activeSources)/\(sources.count)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if isLoading && sources.isEmpty {
                ProgressView()
                    .controlSize(.small)
            } else if sources.isEmpty {
                Text(appText("No calendar sources", appLanguageRaw))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(sources) { source in
                        sourceSidebarRow(source)
                    }
                }
            }
        }
    }

    private var syncStatus: some View {
        HStack(spacing: 10) {
            Image(systemName: "clock.arrow.circlepath")
                .foregroundStyle(.orange)
                .frame(width: 28, height: 28)
                .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 2) {
                Text(appText("Last Sync", appLanguageRaw))
                    .font(.subheadline.weight(.semibold))
                Text(lastSyncLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(10)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.10)))
    }

    private func sourceSidebarRow(_ source: CalendarSource) -> some View {
        HStack(spacing: 8) {
            Circle()
                .fill(color(from: source.color))
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(source.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text(sourceMeta(source))
                    .font(.caption2)
                    .foregroundStyle(source.lastError == nil ? Color.secondary : Color.orange)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            Toggle("", isOn: binding(for: source))
                .labelsHidden()
                .toggleStyle(.switch)
                .scaleEffect(0.72)
                .frame(width: 32)
                .disabled(updatingSourceIDs.contains(source.id) || deletingSourceID == source.id)
            Button(role: .destructive) {
                Task { await deleteSource(source) }
            } label: {
                Image(systemName: deletingSourceID == source.id ? "hourglass" : "trash")
            }
            .buttonStyle(.plain)
            .disabled(deletingSourceID != nil || updatingSourceIDs.contains(source.id))
        }
        .padding(8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var addSourceForm: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 9) {
                Picker(appText("Provider", appLanguageRaw), selection: $formProvider) {
                    ForEach(CalendarProviderOption.allCases) { option in
                        Text(option.title).tag(option)
                    }
                }
                .pickerStyle(.segmented)

                TextField(appText("Source Name", appLanguageRaw), text: $formName)
                    .textFieldStyle(.roundedBorder)
                TextField(formProvider == .ics ? appText("ICS URL", appLanguageRaw) : appText("CalDAV URL", appLanguageRaw), text: $formURL)
                    .textFieldStyle(.roundedBorder)
                HStack(spacing: 8) {
                    TextField(appText("Color", appLanguageRaw), text: $formColor)
                        .textFieldStyle(.roundedBorder)
                    Circle()
                        .fill(color(from: formColor))
                        .frame(width: 18, height: 18)
                }
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

                Text(appText("Only https calendar URLs are accepted. Reva imports events but never writes back to external calendars.", appLanguageRaw))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.top, 8)
        } label: {
            Label(appText("Add Source", appLanguageRaw), systemImage: "plus")
                .font(.headline)
        }
        .padding(12)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.10)))
    }

    private var canAddSource: Bool {
        !trimmed(formName).isEmpty && isHTTPSURL(formURL)
    }

    @ViewBuilder
    private var calendarCanvas: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(scopeSummaryTitle, systemImage: scopeIcon)
                    .font(.headline)
                Spacer()
                if isLoadingEvents {
                    ProgressView()
                        .controlSize(.small)
                }
                Text("\(sortedEvents.count) \(appText("Events", appLanguageRaw))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            switch selectedScope {
            case .day:
                dayView
            case .week:
                weekView
            case .month:
                monthView
            case .year:
                yearView
            }
        }
    }

    private var dayView: some View {
        VStack(alignment: .leading, spacing: 0) {
            dayHeader(anchorDate)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(.regularMaterial)

            Divider()

            let dayEvents = events(on: anchorDate)
            if dayEvents.isEmpty {
                ContentUnavailableView(
                    appText("No events on this day", appLanguageRaw),
                    systemImage: "calendar",
                    description: Text(appText("Use calendar sync to make Reva plan around real commitments.", appLanguageRaw))
                )
                .frame(minHeight: 360)
            } else {
                VStack(spacing: 0) {
                    ForEach(dayEvents) { event in
                        eventListRow(event)
                        Divider()
                    }
                }
            }
        }
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.12)))
    }

    private var weekView: some View {
        let days = currentWindowDays
        return VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(days, id: \.self) { date in
                    dayHeader(date)
                        .frame(maxWidth: .infinity)
                    if date != days.last {
                        Divider()
                    }
                }
            }
            .padding(.vertical, 8)
            .background(.regularMaterial)

            Divider()

            HStack(alignment: .top, spacing: 0) {
                ForEach(days, id: \.self) { date in
                    dayColumn(date, minHeight: 520)
                    if date != days.last {
                        Divider()
                    }
                }
            }
        }
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.12)))
    }

    private var monthView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(weekdaySymbols, id: \.self) { symbol in
                    Text(symbol)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.vertical, 10)
            .background(.regularMaterial)

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 0), count: 7), spacing: 0) {
                ForEach(CalendarSurfaceLayout.monthGridDays(containing: anchorDate, calendar: uiCalendar), id: \.self) { date in
                    monthCell(date)
                }
            }
        }
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.12)))
    }

    private var yearView: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 14), count: 3), spacing: 14) {
            ForEach(monthsInYear, id: \.self) { month in
                yearMonthCard(month)
            }
        }
    }

    private var upcomingStrip: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(appText("Upcoming Events", appLanguageRaw), systemImage: "list.bullet.rectangle")
                    .font(.headline)
                Spacer()
                Text(appText("Read-only", appLanguageRaw))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if sortedEvents.isEmpty {
                Text(appText("No upcoming events", appLanguageRaw))
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
            } else {
                VStack(spacing: 8) {
                    ForEach(sortedEvents.prefix(10)) { event in
                        eventListRow(event)
                    }
                }
            }
        }
    }

    private func dayHeader(_ date: Date) -> some View {
        VStack(spacing: 3) {
            Text(weekdayLabel(date))
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(dayNumber(date))
                .font(.title3.weight(uiCalendar.isDate(date, inSameDayAs: anchorDate) ? .bold : .semibold))
                .foregroundStyle(uiCalendar.isDateInToday(date) ? Color.accentColor : Color.primary)
        }
        .frame(maxWidth: .infinity)
    }

    private func dayColumn(_ date: Date, minHeight: CGFloat) -> some View {
        let dayEvents = events(on: date)
        return VStack(alignment: .leading, spacing: 6) {
            if dayEvents.isEmpty {
                Spacer(minLength: 0)
            } else {
                ForEach(dayEvents.prefix(8)) { event in
                    eventChip(event, compact: false)
                }
                if dayEvents.count > 8 {
                    Text(String(format: appText("%d more events", appLanguageRaw), dayEvents.count - 8))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, minHeight: minHeight, alignment: .topLeading)
        .contentShape(Rectangle())
        .onTapGesture {
            anchorDate = uiCalendar.startOfDay(for: date)
            selectedScope = .day
        }
    }

    private func monthCell(_ date: Date) -> some View {
        let dayEvents = events(on: date)
        let isCurrentMonth = uiCalendar.component(.month, from: date) == uiCalendar.component(.month, from: anchorDate)
        let isSelected = uiCalendar.isDate(date, inSameDayAs: anchorDate)
        return VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(dayNumber(date))
                    .font(.caption.weight(isSelected ? .bold : .semibold))
                    .foregroundStyle(uiCalendar.isDateInToday(date) ? Color.accentColor : (isCurrentMonth ? Color.primary : Color.secondary.opacity(0.55)))
                Spacer()
            }
            ForEach(dayEvents.prefix(4)) { event in
                eventChip(event, compact: true)
            }
            if dayEvents.count > 4 {
                Text(String(format: appText("%d more events", appLanguageRaw), dayEvents.count - 4))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .frame(minHeight: 136, alignment: .topLeading)
        .background(isSelected ? Color.accentColor.opacity(0.07) : Color.clear)
        .overlay(Rectangle().stroke(Color.secondary.opacity(0.10), lineWidth: 0.5))
        .contentShape(Rectangle())
        .onTapGesture {
            anchorDate = uiCalendar.startOfDay(for: date)
            selectedScope = .day
        }
    }

    private func yearMonthCard(_ month: Date) -> some View {
        let monthDays = CalendarSurfaceLayout.monthGridDays(containing: month, calendar: uiCalendar)
        let monthWindow = CalendarSurfaceLayout.window(scope: .month, anchor: month, calendar: uiCalendar)
        let monthEvents = events.filter { eventOverlaps(event: $0, start: monthWindow.start, end: monthWindow.end) }
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(monthTitle(month))
                    .font(.headline)
                Spacer()
                Text("\(monthEvents.count)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 3), count: 7), spacing: 4) {
                ForEach(monthDays.prefix(35), id: \.self) { date in
                    let hasEvent = !events(on: date).isEmpty
                    Text(dayNumber(date))
                        .font(.caption2)
                        .foregroundStyle(uiCalendar.component(.month, from: date) == uiCalendar.component(.month, from: month) ? Color.primary : Color.secondary.opacity(0.45))
                        .frame(height: 18)
                        .frame(maxWidth: .infinity)
                        .background(hasEvent ? Color.accentColor.opacity(0.12) : Color.clear, in: RoundedRectangle(cornerRadius: 4))
                }
            }
        }
        .padding(12)
        .frame(minHeight: 172, alignment: .top)
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.12)))
        .contentShape(Rectangle())
        .onTapGesture {
            anchorDate = month
            selectedScope = .month
        }
    }

    private func eventChip(_ event: CalendarEvent, compact: Bool) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(color(for: event))
                .frame(width: 5, height: 5)
            Text(compact ? compactEventLabel(event) : fullEventLabel(event))
                .font(compact ? .caption2.weight(.semibold) : .caption.weight(.semibold))
                .foregroundStyle(color(for: event))
                .lineLimit(compact ? 1 : 2)
                .truncationMode(.tail)
        }
        .padding(.horizontal, 5)
        .padding(.vertical, compact ? 2 : 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color(for: event).opacity(0.10), in: RoundedRectangle(cornerRadius: 5))
    }

    private func eventListRow(_ event: CalendarEvent) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: event.allDay ? "calendar" : "clock")
                .font(.headline)
                .foregroundStyle(color(for: event))
                .frame(width: 32, height: 32)
                .background(color(for: event).opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 5) {
                Text(eventTitle(event))
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

    private func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let window = currentWindow
            async let sourcesResult = client.listSources()
            async let eventsResult = client.fetchEvents(from: Self.ymd(window.start), to: Self.ymd(window.end))
            sources = try await sourcesResult
            events = try await eventsResult
        } catch {
            errorMessage = userFacingError(error, appLanguageRaw)
        }
    }

    private func refreshEventsForVisibleRange() async {
        if isLoading { return }
        isLoadingEvents = true
        errorMessage = nil
        defer { isLoadingEvents = false }
        do {
            let window = currentWindow
            events = try await client.fetchEvents(from: Self.ymd(window.start), to: Self.ymd(window.end))
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

    private func moveWindow(_ offset: Int) {
        anchorDate = CalendarSurfaceLayout.moved(anchorDate, scope: selectedScope, offset: offset, calendar: uiCalendar)
    }

    private var scopeSummaryTitle: String {
        switch selectedScope {
        case .day:
            return appText("Day Agenda", appLanguageRaw)
        case .week:
            return appText("Week Calendar", appLanguageRaw)
        case .month:
            return appText("Month Calendar", appLanguageRaw)
        case .year:
            return appText("Year Overview", appLanguageRaw)
        }
    }

    private var scopeIcon: String {
        switch selectedScope {
        case .day:
            return "calendar.day.timeline.left"
        case .week:
            return "calendar"
        case .month:
            return "calendar.grid"
        case .year:
            return "square.grid.3x3"
        }
    }

    private var weekdaySymbols: [String] {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        let symbols = formatter.shortStandaloneWeekdaySymbols ?? []
        guard symbols.count == 7 else { return [] }
        let start = max(0, uiCalendar.firstWeekday - 1)
        return (0..<7).map { symbols[(start + $0) % 7] }
    }

    private var monthsInYear: [Date] {
        let yearWindow = CalendarSurfaceLayout.window(scope: .year, anchor: anchorDate, calendar: uiCalendar)
        return (0..<12).compactMap { uiCalendar.date(byAdding: .month, value: $0, to: yearWindow.start) }
    }

    private func events(on date: Date) -> [CalendarEvent] {
        let start = uiCalendar.startOfDay(for: date)
        guard let end = uiCalendar.date(byAdding: .day, value: 1, to: start) else { return [] }
        return sortedEvents.filter { eventOverlaps(event: $0, start: start, end: end) }
    }

    private func eventOverlaps(event: CalendarEvent, start: Date, end: Date) -> Bool {
        guard let eventStart = Self.parseISODate(event.start) else { return false }
        let fallbackEnd = uiCalendar.date(byAdding: event.allDay ? .day : .minute, value: event.allDay ? 1 : 30, to: eventStart) ?? eventStart
        let eventEnd = Self.parseISODate(event.end) ?? fallbackEnd
        return eventStart < end && eventEnd > start
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

    private var lastSyncLabel: String {
        if let syncResult {
            return "\(syncResult.count) \(appText("Events", appLanguageRaw))"
        }
        let last = sources.compactMap(\.lastSyncAt).sorted().last
        return last.map(shortTimestamp) ?? appText("Never", appLanguageRaw)
    }

    private func eventTitle(_ event: CalendarEvent) -> String {
        (event.title?.isEmpty == false ? event.title : appText("Untitled Event", appLanguageRaw)) ?? appText("Untitled Event", appLanguageRaw)
    }

    private func compactEventLabel(_ event: CalendarEvent) -> String {
        if event.allDay {
            return eventTitle(event)
        }
        if let start = Self.parseISODate(event.start) {
            return "\(timeLabel(start)) \(eventTitle(event))"
        }
        return eventTitle(event)
    }

    private func fullEventLabel(_ event: CalendarEvent) -> String {
        "\(eventCompactTime(event)) \(eventTitle(event))"
    }

    private func eventCompactTime(_ event: CalendarEvent) -> String {
        if event.allDay { return appText("All-day", appLanguageRaw) }
        guard let start = Self.parseISODate(event.start) else { return "" }
        return timeLabel(start)
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

    private func windowTitle(_ window: CalendarSurfaceLayout.Window) -> String {
        switch window.scope {
        case .day:
            return dateTitle(window.anchor)
        case .week:
            return "\(shortDateTitle(window.start)) - \(shortDateTitle(window.end))"
        case .month:
            return monthTitle(window.anchor)
        case .year:
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
            formatter.dateFormat = language == .zh ? "yyyy年" : "yyyy"
            return formatter.string(from: window.anchor)
        }
    }

    private func scopeLabel(_ scope: CalendarSurfaceScope) -> String {
        switch scope {
        case .day:
            return appText("Day", appLanguageRaw)
        case .week:
            return appText("Week", appLanguageRaw)
        case .month:
            return appText("Month", appLanguageRaw)
        case .year:
            return appText("Year", appLanguageRaw)
        }
    }

    private func dateTitle(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = language == .zh ? "yyyy年M月d日" : "MMM d, yyyy"
        return formatter.string(from: date)
    }

    private func shortDateTitle(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = language == .zh ? "M月d日" : "MMM d"
        return formatter.string(from: date)
    }

    private func monthTitle(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = language == .zh ? "yyyy年MM月" : "MMMM yyyy"
        return formatter.string(from: date)
    }

    private func weekdayLabel(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = "EEE"
        return formatter.string(from: date)
    }

    private func dayNumber(_ date: Date) -> String {
        "\(uiCalendar.component(.day, from: date))"
    }

    private func timeLabel(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }

    private func shortTimestamp(_ value: String) -> String {
        if let date = Self.parseISODate(value) {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
            formatter.dateFormat = language == .zh ? "M月d日 HH:mm" : "MMM d HH:mm"
            return formatter.string(from: date)
        }
        return value.replacingOccurrences(of: "T", with: " ").prefix(16).description
    }

    private func formatDateTime(_ value: String?) -> String? {
        guard let value, let date = Self.parseISODate(value) else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .zh ? "zh_CN" : "en_US")
        formatter.dateFormat = language == .zh ? "M月d日 HH:mm" : "MMM d HH:mm"
        return formatter.string(from: date)
    }

    private func color(for event: CalendarEvent) -> Color {
        if let sourceID = event.sourceID,
           let source = sources.first(where: { $0.id == sourceID }) {
            return color(from: source.color)
        }
        return .teal
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

    private func clearForm() {
        formProvider = .ics
        formName = ""
        formURL = ""
        formUsername = ""
        formPassword = ""
        formColor = "#34C759"
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

    private static func ymd(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private static func parseISODate(_ value: String?) -> Date? {
        guard let value else { return nil }
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
