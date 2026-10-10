# Mac 锁屏时运行 iOS 模拟器

本地入口：`scripts/mobile_sim_headless.py`。它使用 `simctl` 启动已安装的 App、捕获模拟器画面，并可通过 `xcodebuild test-without-building` 执行已经构建的 XCTest UI 测试，不依赖桌面窗口点击。

锁屏与系统休眠是不同状态。运行期间的 `caffeinate -i` 只阻止空闲系统休眠，不唤醒显示器、不关闭锁屏、不自动解锁；运行结束会释放。关机、主动休眠和合盖进入休眠不属于此路径的保证范围。

## 启动和截图

必须选择明确的模拟器 UUID，不接受多个模拟器启动时含糊的 `booted`：

```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun simctl list devices booted
python3 scripts/mobile_sim_headless.py \
  --device <模拟器UUID> \
  --require-locked --wait-for-lock 600 \
  --output /tmp/reva-sim-<本次唯一名称>
```

手动锁定 Mac 后，后台任务开始运行。`--require-locked` 要求开始和结束都读到明确的锁屏状态。状态来自 IORegistry 的 `IOConsoleLocked` 布尔值；字段缺失、类型异常或命令失败均阻断，不默认判定已解锁。`--wait-for-lock` 最多等待 600 秒，超时失败；每次使用新的输出目录，禁止覆盖原回执。

输出目录权限为 700，普通证据文件为 600。截图及 XCTest 结果可能含私密信息，只在本地保存，未经脱敏审核不要提交或上传。

## 滑动和点击验证

独立基础设施探针使用 iOS 系统设置页：启动、滑动、点击“通用”、核验导航栏并保存 XCTest 截图。它不修改系统设置，不使用健康数据，也不证明 LifeNav 的业务功能通过。

已安装 Xcode 和 CocoaPods 使用的 `xcodeproj` Ruby gem 时：

```bash
ruby scripts/simulator/build-ui-probe.rb /tmp/reva-ui-probe-<唯一名称>
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild build-for-testing \
  -project /tmp/reva-ui-probe-<唯一名称>/SimulatorProbe.xcodeproj \
  -scheme SimulatorProbe \
  -destination 'platform=iOS Simulator,id=<模拟器UUID>' \
  -derivedDataPath /tmp/reva-ui-probe-<唯一名称>/derived CODE_SIGNING_ALLOWED=NO
```

将生成的 `derived/Build/Products/*.xctestrun` 的实际路径传给上方 Python 命令的 `--xctestrun` 参数。该入口也接受候选 App 已构建的 UI 测试套件。XCTest 失败或超时会保存失败回执并返回非零；不能换成截图通过。

## 证据范围

回执记录实际模拟器 UUID、安装 App 内容哈希、截图哈希、可选测试套件哈希、开始/结束锁屏状态以及真实退出结果。测试后重新启动指定 App 再截图，避免把系统设置页冒充 App 页面。

安装内容哈希不能反推出源码 SHA，因此默认 `source_sha: null`，`functional_acceptance: unverified`。正式候选验收须另外提供可信构建与源码绑定、实际测试范围及运行结果，并遵守 `docs/governance/simulator-review-acceptance.md`。此工具不发布 OTA，也不绕过后端部署和可信发布闸门。
