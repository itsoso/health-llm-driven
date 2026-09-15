import HealthAgentMacCore
import SwiftUI
import WebKit

struct ShoppingChatView: View {
    @Bindable var viewModel: ShoppingChatViewModel
    @Bindable var browser: ShoppingBrowserSession
    @Environment(\.openURL) private var openURL
    @State private var showsLogin = false
    @State private var showsConfiguration = false
    @State private var bridgeError: String?
    @State private var shoppingApp = ShoppingAppLauncher()
    @State private var windowMirror = ShoppingWindowMirror()
    @State private var isVisible = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 18) {
                        statusCard
                        if !viewModel.isDemo {
                            if viewModel.localBridge.isActive { localBridgeCard }
                            else { officialAppHandoff }
                            if let notice = viewModel.localBridge.notice ?? bridgeError {
                                Text(notice).font(.caption).foregroundStyle(WarmPalette.ink2)
                            }
                        }
                        if viewModel.transcript.messages.isEmpty && !windowMirror.isActive { welcome }
                        ForEach(viewModel.transcript.messages, id: \.messageId) { message in
                            messageView(message)
                        }
                        if let thinking = viewModel.transcript.thinkingMessage {
                            HStack {
                                ProgressView().controlSize(.small)
                                Text(thinking.blocks.compactMap(\.text).joined(separator: " "))
                                    .font(.callout).foregroundStyle(WarmPalette.ink2)
                            }
                        }
                        if !viewModel.suggestedQuestions.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("继续聊聊").font(.caption).foregroundStyle(WarmPalette.ink2)
                                ForEach(viewModel.suggestedQuestions, id: \.self) { question in
                                    Button { viewModel.draft = question } label: {
                                        HStack { Text(question).multilineTextAlignment(.leading); Spacer(); Image(systemName: "arrow.up.left") }
                                    }.buttonStyle(.bordered).disabled(viewModel.isBusy)
                                }
                            }
                        }
                        if let notice = viewModel.notice {
                            Text(notice).font(.callout).foregroundStyle(WarmPalette.ink2)
                                .accessibilityIdentifier("shopping-notice")
                        }
                        Color.clear.frame(height: 1).id("shopping-bottom")
                    }
                    .padding(24)
                    .frame(maxWidth: 820)
                    .frame(maxWidth: .infinity)
                }
                .onChange(of: viewModel.transcript) { _, _ in
                    proxy.scrollTo("shopping-bottom", anchor: .bottom)
                }
            }
            composer
        }
        .background(WarmPalette.paper)
        .tint(WarmPalette.clay)
        .navigationTitle("购物助手")
        .onAppear { isVisible = true }
        .onDisappear { isVisible = false; windowMirror.stop() }
        .onChange(of: viewModel.ownerGeneration) { _, _ in windowMirror.stop() }
        .onChange(of: viewModel.sessionGeneration) { _, _ in windowMirror.stop() }
        .onChange(of: viewModel.isDemo) { _, _ in windowMirror.stop() }
        .onChange(of: viewModel.localBridge.isActive) { _, _ in windowMirror.stop() }
        .sheet(isPresented: $showsLogin, onDismiss: {
            Task { await viewModel.refreshCredentials() }
        }) {
            ShoppingLoginSheet(browser: browser) { showsLogin = false }
        }
        .sheet(isPresented: $showsConfiguration) {
            ShoppingConfigurationSheet(viewModel: viewModel)
        }
        .onChange(of: viewModel.ownerIsBound) { _, bound in
            if !bound { showsLogin = false; showsConfiguration = false }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "bag").font(.title2).foregroundStyle(WarmPalette.clay)
            VStack(alignment: .leading, spacing: 3) {
                Text("购物助手").font(.title2.weight(.semibold))
                Text("快手电商 · 独立购物会话").font(.caption).foregroundStyle(WarmPalette.ink2)
            }
            Spacer()
            Menu {
                Button("连接本机快手（需桥接版购物页）") {
                    bridgeError = nil
                    Task {
                        do {
                            let pairing = try await viewModel.startLocalBridge()
                            guard viewModel.ownerIsBound, viewModel.localBridge.isCurrent(pairing) else { return }
                            let opened = await shoppingApp.openLocalBridge(pairing)
                            guard viewModel.ownerIsBound, viewModel.localBridge.isCurrent(pairing) else { return }
                            if !opened {
                                viewModel.disconnectLocalBridge()
                                bridgeError = shoppingApp.notice
                            }
                        } catch {
                            bridgeError = (error as? ShoppingBridgeError)?.localizedDescription ?? "本机连接已停止。"
                        }
                    }
                }.disabled(!viewModel.ownerIsBound || viewModel.isDemo || viewModel.isBusy || shoppingApp.isOpening || viewModel.localBridge.isActive)
                Divider()
                Button("网页登录（接入调试）") {
                    viewModel.prepareForLogin()
                    browser.open()
                    showsLogin = true
                }.disabled(!viewModel.ownerIsBound || viewModel.isDemo)
                Button("刷新登录状态") { Task { await viewModel.refreshCredentials() } }
                    .disabled(viewModel.isBusy || viewModel.isDemo)
                Button("连接购物服务") { Task { await viewModel.load() } }
                    .disabled(!viewModel.canUseService)
                Button("加载更多历史") { Task { await viewModel.loadHistory() } }
                    .disabled(!viewModel.canUseService || !viewModel.hasMoreHistory)
                Button("刷新推荐问题") { Task { await viewModel.loadQuestions() } }
                    .disabled(!viewModel.canUseService)
                Divider()
                Button("接入设置") { showsConfiguration = true }
                Button(viewModel.isDemo ? "退出离线演示" : "查看离线演示") { viewModel.setDemoMode(!viewModel.isDemo) }
                Divider()
                Button("清空本机对话") { windowMirror.stop(); viewModel.clearConversation() }
                Button("退出快手登录", role: .destructive) { windowMirror.stop(); viewModel.logout() }
            } label: { Image(systemName: "ellipsis.circle").font(.title3) }
            .menuStyle(.borderlessButton).fixedSize()
        }
        .padding(20)
    }

    private var statusCard: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: viewModel.isDemo ? "play.rectangle" : "person.crop.circle.badge.checkmark")
                .foregroundStyle(WarmPalette.clay)
            VStack(alignment: .leading, spacing: 5) {
                Text(viewModel.usesOfficialAppForSending ? "官方快手提问 · 小巴查看画面" : viewModel.statusTitle).font(.callout.weight(.semibold))
                Text(viewModel.usesOfficialAppForSending ? "在下方输入问题，点击“发送并查看”。登录和回答由快手处理，小巴内的直接服务接口仍未接通。" : viewModel.statusDetail).font(.caption).foregroundStyle(WarmPalette.ink2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(14).background(WarmPalette.card2, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityIdentifier("shopping-status")
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("想找点什么？").font(.largeTitle.weight(.semibold))
            Text("说说用途、预算和偏好，一起挑选合适的商品。")
                .foregroundStyle(WarmPalette.ink2)
            if !viewModel.isDemo {
                Button("先看看离线演示") { viewModel.setDemoMode(true) }.buttonStyle(.bordered)
            }
            Label("仅发送你在此输入的内容", systemImage: "lock.shield")
                .font(.caption).foregroundStyle(WarmPalette.ink3)
        }.padding(.vertical, 30)
    }

    private var localBridgeCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(viewModel.localBridge.isReady ? "新回复将在当前窗口显示" : "核对快手页面中的配对码").font(.headline)
            if let code = viewModel.localBridge.pairingCode {
                Text(code).font(.title.monospacedDigit())
            }
            Text("需要已分发桥接版本的购物页。快手客户端保持运行；仅同步本次主动提问及对应回复，不传递登录凭据。")
                .font(.caption).foregroundStyle(WarmPalette.ink2)
            Button("断开本机连接") { viewModel.disconnectLocalBridge() }.buttonStyle(.bordered)
            if !viewModel.localBridge.isReady, let notice = shoppingApp.notice {
                Text(notice).font(.caption).foregroundStyle(WarmPalette.ink2)
            }
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(WarmPalette.card, in: RoundedRectangle(cornerRadius: 12))
    }

    private var officialAppHandoff: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("在当前窗口查看快手回复").font(.headline)
            Text("提问交给已登录的官方快手，购物窗口画面在这里同步。首次使用需允许小巴录制屏幕；只读取快手购物窗口，不保存或上传画面。")
                .font(.caption).foregroundStyle(WarmPalette.ink2)
            HStack {
                Button(windowMirror.isActive ? "停止显示" : "显示快手购物窗口") {
                    if windowMirror.isActive { windowMirror.stop() }
                    else { startWindowMirror() }
                }.buttonStyle(.borderedProminent)
                    .disabled(!viewModel.ownerIsBound || shoppingApp.isOpening)
                    .accessibilityIdentifier("shopping-mirror-toggle")
                Button("在快手打开购物助手") {
                    Task { await shoppingApp.openShoppingAssistant() }
                }
                .buttonStyle(.bordered)
                .disabled(!viewModel.ownerIsBound || shoppingApp.isOpening)
                .accessibilityIdentifier("shopping-open-official-app")
                Link("安装官方快手", destination: ShoppingAppLauncher.appStoreURL)
                    .font(.caption)
            }
            if let notice = shoppingApp.notice {
                Text(notice).font(.caption).foregroundStyle(WarmPalette.ink2)
            }
            if let notice = windowMirror.notice {
                Text(notice).font(.callout).foregroundStyle(WarmPalette.ink2)
            }
            if let frame = windowMirror.image {
                Text("快手当前画面 · 可能包含手机历史，画面更新不代表本轮回答已完成")
                    .font(.caption).foregroundStyle(WarmPalette.ink2)
                Image(decorative: frame, scale: 1)
                    .resizable().scaledToFit().frame(maxWidth: 600)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("快手购物窗口实时画面")
                Text("长回复滚动、商品点击和购买请在快手窗口操作；保持快手窗口未最小化。每次显示约三分钟，可重新连接。")
                    .font(.caption).foregroundStyle(WarmPalette.ink2)
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(WarmPalette.card, in: RoundedRectangle(cornerRadius: 12))
    }

    private func messageView(_ message: ShoppingMessage) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(message.sender == "user" ? "你" : "购物助手")
                .font(.caption.weight(.semibold)).foregroundStyle(WarmPalette.ink2)
            ForEach(Array(message.blocks.enumerated()), id: \.offset) { _, block in
                if let text = block.text, !text.isEmpty {
                    // Plain text prevents server content from creating automatic links/actions.
                    Text(verbatim: text).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                }
                ForEach(Array(block.products.enumerated()), id: \.offset) { _, product in
                    productCard(product)
                }
                if !block.isSupported || (block.type.hasPrefix("product_") && block.products.isEmpty) {
                    Label("这类卡片暂不支持在 Mac 展示，可到快手 App 查看。", systemImage: "rectangle.on.rectangle.slash")
                        .font(.caption).foregroundStyle(WarmPalette.ink2)
                }
            }
            if message.sender != "user", !viewModel.isDemo {
                HStack {
                    Button { Task { await viewModel.feedback(message: message, positive: true) } } label: { Label("有帮助", systemImage: "hand.thumbsup") }
                    Button { Task { await viewModel.feedback(message: message, positive: false) } } label: { Label("没帮助", systemImage: "hand.thumbsdown") }
                }.font(.caption).buttonStyle(.borderless).disabled(!viewModel.canUseService)
            }
        }
        .padding(18)
        .background(message.sender == "user" ? WarmPalette.claySoft : WarmPalette.card, in: RoundedRectangle(cornerRadius: 16))
    }

    private func productCard(_ product: ShoppingProduct) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: "shippingbox").font(.title).foregroundStyle(WarmPalette.clay)
                .frame(width: 52, height: 60).background(WarmPalette.card2, in: RoundedRectangle(cornerRadius: 10))
            VStack(alignment: .leading, spacing: 8) {
                Text(product.name).font(.headline)
                if let price = product.priceText { Text(price).foregroundStyle(WarmPalette.clay).font(.title3.weight(.semibold)) }
                if !viewModel.isDemo, let value = product.detailURL, let url = URL(string: value), ShoppingLoginPolicy.allowsProductLink(url) {
                    Button("查看商品网页") { openURL(url) }.buttonStyle(.bordered)
                } else {
                    Text(viewModel.isDemo ? "演示商品 · 不可购买" : "当前链接需在快手 App 查看")
                        .font(.caption).foregroundStyle(WarmPalette.ink2)
                }
            }
            Spacer(minLength: 0)
        }.padding(14).background(WarmPalette.paper, in: RoundedRectangle(cornerRadius: 12))
    }

    private var composer: some View {
        VStack(spacing: 8) {
            HStack(alignment: .bottom, spacing: 12) {
                TextField("例如：找一个通勤用的保温杯，预算 200 元", text: $viewModel.draft, axis: .vertical)
                    .lineLimit(1...5).textFieldStyle(.plain)
                    .padding(14).background(WarmPalette.card, in: RoundedRectangle(cornerRadius: 12))
                    .onSubmit { submitShoppingQuestion() }
                    .disabled(!viewModel.ownerIsBound)
                    .accessibilityIdentifier("shopping-input")
                if viewModel.localBridge.isActive && !viewModel.localBridge.isReady {
                    Button("等待配对") {}.buttonStyle(.bordered).disabled(true)
                } else if viewModel.isBusy {
                    Button("停止接收") { viewModel.stop() }.buttonStyle(.bordered)
                } else if viewModel.usesOfficialAppForSending {
                    Button("发送并查看") { submitShoppingQuestion() }
                        .buttonStyle(.borderedProminent)
                        .disabled(!viewModel.ownerIsBound || shoppingApp.isOpening || viewModel.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .accessibilityIdentifier("shopping-send-to-official-app")
                } else {
                    Button { Task { await viewModel.send() } } label: { Image(systemName: "arrow.up").font(.headline).padding(6) }
                        .buttonStyle(.borderedProminent).disabled(!viewModel.canSend)
                        .accessibilityLabel("发送购物消息")
                }
            }
            Text(viewModel.isDemo ? "离线演示使用示例内容，不连接购物服务。" :
                    (viewModel.usesOfficialAppForSending ? "仅发送此处输入的问题，不附带健康资料；草稿保留，授权后可在上方查看快手画面。" : "购物历史可能与手机共享；停止接收不代表服务端任务已取消。"))
                .font(.caption2).foregroundStyle(WarmPalette.ink3)
        }.padding(20).background(WarmPalette.rail)
    }

    private func submitShoppingQuestion() {
        guard viewModel.ownerIsBound, !viewModel.isBusy, !shoppingApp.isOpening,
              !viewModel.localBridge.isActive || viewModel.localBridge.isReady else { return }
        if viewModel.usesOfficialAppForSending {
            guard let submission = viewModel.prepareOfficialQuestion() else { return }
            Task {
                guard let question = viewModel.validateOfficialQuestion(submission) else { return }
                windowMirror.stop()
                let opened = await shoppingApp.openShoppingAssistant(question: question)
                guard opened, isVisible, viewModel.validateOfficialQuestion(submission) != nil else { return }
                // Only return after the explicit handoff; never infer service success.
                NSApplication.shared.activate()
                startWindowMirror()
            }
        } else {
            Task { await viewModel.send() }
        }
    }

    private func startWindowMirror() {
        let session = viewModel.sessionGeneration
        let owner = viewModel.ownerGeneration
        windowMirror.start {
            isVisible && viewModel.ownerIsBound && viewModel.sessionGeneration == session
                && viewModel.ownerGeneration == owner && !viewModel.isDemo && !viewModel.localBridge.isActive
        }
    }
}

private struct ShoppingWebView: NSViewRepresentable {
    let webView: WKWebView
    func makeNSView(context: Context) -> WKWebView { webView }
    func updateNSView(_ nsView: WKWebView, context: Context) {}
}

private struct ShoppingLoginSheet: View {
    @Bindable var browser: ShoppingBrowserSession
    let close: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("快手官方网页登录").font(.title2.weight(.semibold))
                    Text("扫码完成后点击“完成并检查”。网页登录不等于购物服务已授权。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成并检查", action: close).buttonStyle(.borderedProminent)
            }
            if let error = browser.pageError { Text(error).foregroundStyle(.red).font(.callout) }
            if let webView = browser.webView { ShoppingWebView(webView: webView) }
            else { ContentUnavailableView("登录窗口已关闭", systemImage: "person.crop.circle") }
            Text("登录态仅保留在本次购物会话；退出快手或小巴会清除。")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(20).frame(width: 960, height: 680)
    }
}

private struct ShoppingConfigurationSheet: View {
    @Bindable var viewModel: ShoppingChatViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var gateway = ""
    @State private var entry = ""
    @State private var carrier = ""
    @State private var source = ""
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("购物接入设置").font(.title2.weight(.semibold))
            Text("填写服务方确认的接入地址和入口标识。设置仅保留在本次运行；更改后需要重新登录快手。")
                .font(.callout).foregroundStyle(.secondary)
            Form {
                TextField("HTTPS 网关", text: $gateway, prompt: Text("服务方提供的网关"))
                TextField("入口标识 entrySrc", text: $entry)
                TextField("载体 carrierType（可选）", text: $carrier)
                TextField("来源 sourceId（可选）", text: $source)
            }
            if let error { Text(error).foregroundStyle(.red).font(.callout) }
            HStack {
                Spacer()
                Button("取消") { dismiss() }
                Button("应用") {
                    do {
                        guard let url = URL(string: gateway.trimmingCharacters(in: .whitespacesAndNewlines)) else { throw ShoppingClientError.invalidConfiguration }
                        let config = try ShoppingConfiguration(gateway: url, entrySource: entry,
                                                               carrierType: carrier.isEmpty ? nil : carrier,
                                                               sourceID: source.isEmpty ? nil : source)
                        viewModel.configure(config)
                        dismiss()
                    } catch { self.error = ShoppingClientError.invalidConfiguration.localizedDescription }
                }.buttonStyle(.borderedProminent)
            }
        }.padding(24).frame(width: 520)
        .onAppear {
            gateway = viewModel.configuration?.gateway.absoluteString ?? ""
            entry = viewModel.configuration?.entrySource ?? ""
            carrier = viewModel.configuration?.carrierType ?? ""
            source = viewModel.configuration?.sourceID ?? ""
        }
    }
}
