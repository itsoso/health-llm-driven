import Foundation

/// GenUI reva-ui 组件的编译期能力开关。
///
/// rank1 「GenUI-first」把 ≤500字叙事 + `metric_table` 卡片作为深分析的默认呈现。渲染器
/// (chat-transcript.html 的 JS builder + CSS)**随包发布**,但能力协商 cap 与桌面指令
/// 的切换默认**暗着**——只有 prose eval gate 过后,才用一行提交把 `tableCapEnabled` 翻 true。
///
/// 为什么用编译期常量而非运行时开关:它决定的是「本端向后端声明能渲染什么」+「让后端切换
/// 到简洁指令」两件跨端契约动作。二者必须与后端服务端 gate 同步开合,不该被用户偶然触发;
/// 编译期常量让 header 与指令在 flag=false 时与历史**逐字节一致**(见 tests),零回归。
public enum RevaUIFeatureFlags {
    /// `revaUITableCapEnabled`(rank1):是否声明 `genui-table-v1` cap 并改用简洁桌面指令。
    /// 默认 **false** —— 渲染器已就绪,cap 仍暗。翻开只需把这一行改成 `true`。
    public static let tableCapEnabled = false
}
