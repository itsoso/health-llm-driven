import Foundation
import HealthAgentMacCore
import Observation
import WebKit

/// An in-memory browser dedicated to shopping. Discarding it also discards all
/// credentials. We deliberately read cookies on demand: WebKit's observer did
/// not reliably report the official login callback in the native probe.
@MainActor @Observable
final class ShoppingBrowserSession: NSObject, ShoppingCredentialSource, WKNavigationDelegate, WKUIDelegate {
    private(set) var webView: WKWebView?
    private(set) var pageError: String?
    private var generation = UUID()

    func open(loadLoginPage: Bool = true) {
        guard webView == nil else { return }
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        self.webView = webView
        pageError = nil
        if loadLoginPage { webView.load(URLRequest(url: ShoppingLoginPolicy.loginURL)) }
    }

    func cookies() async -> [HTTPCookie] {
        guard let store = webView?.configuration.websiteDataStore.httpCookieStore else { return [] }
        let token = generation
        let values = await store.allCookies()
        return token == generation ? values : []
    }

    func reset() {
        generation = UUID()
        let old = webView
        webView = nil
        pageError = nil
        old?.stopLoading()
        old?.navigationDelegate = nil
        old?.uiDelegate = nil
        old?.removeFromSuperview()
        // The store is nonpersistent. Erase the retired store too, but never
        // mutate the new store or publish results from this asynchronous cleanup.
        if let store = old?.configuration.websiteDataStore {
            Task { await store.removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast) }
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void) {
        guard webView === self.webView, let url = navigationAction.request.url,
              ShoppingLoginPolicy.allowsNavigation(url) || url.absoluteString == "about:blank" else {
            if webView === self.webView { pageError = "此登录窗口仅支持快手官方网页登录。" }
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard webView === self.webView, let url = navigationAction.request.url,
              ShoppingLoginPolicy.allowsNavigation(url) else { return nil }
        webView.load(navigationAction.request)
        return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard webView === self.webView, (error as NSError).code != NSURLErrorCancelled else { return }
        pageError = "登录页加载失败，请关闭后重试。"
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        guard webView === self.webView, (error as NSError).code != NSURLErrorCancelled else { return }
        pageError = "登录页连接中断，请关闭后重试。"
    }
}
