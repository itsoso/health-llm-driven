import Foundation

public enum AppLanguage: String, CaseIterable, Identifiable, Sendable {
    case zh
    case en

    public static let defaultsKey = "appLanguage"
    public static let defaultLanguage = AppLanguage.zh

    public var id: String { rawValue }

    public var nativeName: String {
        switch self {
        case .zh: "中文"
        case .en: "English"
        }
    }

    public init(storedValue: String) {
        self = AppLanguage(rawValue: storedValue) ?? .defaultLanguage
    }
}

public enum L10n {
    public static func text(_ key: String, language: AppLanguage) -> String {
        switch language {
        case .zh:
            zhCN[key] ?? key
        case .en:
            key
        }
    }

    private static let zhCN: [String: String] = [
        "Health Agent": "健康 Agent",
        "Today": "今日",
        "Agent": "助手",
        "Record": "记录",
        "Data": "数据",
        "Genetics": "基因",
        "Knowledge": "知识库",
        "Labs, records, trajectory, and active medical imports.": "化验、记录、轨迹和进行中的医疗导入。",
        "Genome reanalysis jobs, source hashes, and risk-boundary handoff.": "基因重分析任务、来源哈希和风险边界交接。",
        "Dedao compilation, system KB rebuilds, and source coverage.": "得到资料编译、系统知识库重建和来源覆盖。",
        "Jobs": "任务",
        "Trace": "追踪",
        "Settings": "设置",
        "Ask Agent": "问助手",
        "Import": "导入",
        "Import File": "导入文件",
        "Open Today": "打开今日",
        "Checking login...": "正在检查登录状态...",
        "Sign in with your executor.life account.": "使用 executor.life 账号登录。",
        "Username or email": "用户名或邮箱",
        "Password": "密码",
        "Sign In": "登录",
        "Signing in...": "正在登录...",
        "Daily operating plan, feedback, and active desktop jobs.": "每日执行计划、反馈和桌面任务。",
        "Refresh": "刷新",
        "Loading desktop context...": "正在加载桌面上下文...",
        "Top Actions": "优先行动",
        "No actions loaded yet.": "还没有加载行动。",
        "Done": "完成",
        "Adjust": "调整",
        "Active Jobs": "进行中的任务",
        "No active desktop jobs.": "没有进行中的桌面任务。",
        "Loading workspace...": "正在加载工作台...",
        "No workspace data loaded": "还没有工作台数据",
        "Focus Domains": "关注领域",
        "No focus domains loaded.": "还没有关注领域。",
        "Relevant Jobs": "相关任务",
        "No active jobs for this workspace.": "这个工作台没有进行中的任务。",
        "Recent Memory": "近期记忆",
        "No recent memory loaded.": "还没有近期记忆。",
        "No actions loaded": "还没有行动",
        "Analysis": "分析",
        "Title": "标题",
        "Attach": "添加附件",
        "Web Search": "联网搜索",
        "Ask about health data, labs, genes, records, or a specific execution plan.": "询问健康数据、化验、基因、记录或具体执行方案。",
        "Models": "模型",
        "Mode": "模式",
        "Auto Select": "自动选择",
        "Default 3": "默认 3 个",
        "Evidence": "证据",
        "Sources, attachments, and evidence refs will appear here.": "来源、附件和证据引用会显示在这里。",
        "Attachments": "附件",
        "Sources": "来源",
        "Ready for desktop chat, file context, and evidence inspection.": "已准备好桌面聊天、文件上下文和证据检查。",
        "Quick Record": "快捷记录",
        "Structured Form": "结构化表单",
        "Record food, water, supplement, weight, BP, or symptom": "记录饮食、饮水、补剂、体重、血压或症状",
        "Type": "类型",
        "Diet": "饮食",
        "Water": "饮水",
        "Weight": "体重",
        "BP": "血压",
        "Symptom": "症状",
        "Preview": "预览",
        "Save Structured": "保存结构化记录",
        "Saving...": "正在保存...",
        "Save": "保存",
        "Recent Local Records": "本地最近记录",
        "Recent saved commands in this Mac session will appear here.": "本次 Mac 会话保存过的记录命令会显示在这里。",
        "Saved": "已保存",
        "Undo": "撤销",
        "Undoing...": "正在撤销...",
        "Undo failed": "撤销失败",
        "Record undone.": "记录已撤销。",
        "Reuse": "复用",
        "Delete": "删除",
        "Food name or photo description": "食物名称或图片描述",
        "Calories kcal": "热量 kcal",
        "Protein g": "蛋白质 g",
        "Amount ml": "饮水量 ml",
        "Supplement": "补剂",
        "Dose and timing": "剂量和时间",
        "Weight kg": "体重 kg",
        "Systolic": "收缩压",
        "Diastolic": "舒张压",
        "Symptom, severity, and context": "症状、严重程度和背景",
        "Choose File or Folder": "选择文件或文件夹",
        "Create Job": "创建任务",
        "I confirm this raw local file may be registered as a desktop import job.": "我确认可以将这个本地原始文件登记为桌面导入任务。",
        "No file selected": "还没有选择文件",
        "Select a genome txt, medical file, Apple Health export, or Dedao folder.": "选择基因 txt、医疗文件、Apple Health 导出或得到文件夹。",
        "ID": "ID",
        "Progress": "进度",
        "Action": "操作",
        "Details": "详情",
        "Retry": "重试",
        "Job Detail": "任务详情",
        "Status": "状态",
        "Source": "来源",
        "Kind": "类型",
        "Open Trace": "打开追踪",
        "Result": "结果",
        "Select a job to inspect source, result, error, and trace handoff.": "选择一个任务以查看来源、结果、错误和追踪跳转。",
        "Conversation ID": "对话 ID",
        "Load": "加载",
        "Conversation": "对话",
        "Model": "模型",
        "Elapsed": "总耗时",
        "LLM": "LLM",
        "Finish": "结束原因",
        "No trace loaded": "还没有加载追踪",
        "Auth": "认证",
        "Bearer token": "Bearer token",
        "Save Token": "保存 Token",
        "Clear Token": "清除 Token",
        "Sign Out": "退出登录",
        "API": "API",
        "Base URL": "Base URL",
        "Changing the API base URL takes effect after restarting the Mac app.": "修改 API 地址后，重启 Mac App 生效。",
        "Voice": "语音",
        "Output voice": "输出音色",
        "Private Female": "私享女声",
        "System Default": "系统默认",
        "Privacy and Files": "隐私和文件",
        "Allow local file hashing before import": "导入前允许本地文件哈希",
        "Files stay local in this P0 client. Import jobs register source metadata and hashes unless a backend upload flow is added later.": "P0 客户端中文件保持在本地。除非后续增加后端上传流程，导入任务只登记来源元数据和哈希。",
        "Language": "语言",
        "Display language": "显示语言",
        "Chinese is the default. Language changes apply immediately in most views.": "默认使用中文。大多数界面会立即应用语言切换。"
    ]
}
