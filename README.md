# TV Voice Bridge · 电视语音桥

把同一颗遥控器麦克风键分成两种用途，复用电视已有的语音识别服务：

| 当前场景 | 说话后的行为 |
| --- | --- |
| 选中了普通文字输入框 | 将识别文字填入当前输入框，不自动提交搜索 |
| 桌面等没有选中输入框的页面，说“我想看熊出没” | 提取原生助手理解的影片名，打开影视仓搜索“熊出没” |
| 其他原生助手指令 | 保留原生处理路径 |

**这是一套可扩展的部署框架，不是全品牌电视通用破解包。** 当前已实测的技术基线是哈趣 K1 Pro 的 Android 9 / 当贝 Rocky-DDS 语音服务。其他品牌默认只检测、不修改；不能因为都是安卓电视，就直接套用音频路由和语音接口。

本项目不包含原厂 APK、反编译源码、语音服务密钥、影视仓安装包或影视源。请自行安装并配置合法可用的目标播放器。

## 一键部署

先在电视开启并授权 ADB。电脑需要 **Python 3.10+**，电视与电脑需要能互相连接。

1. 下载 [最新 Release](https://github.com/QZ0071/tv-voice-bridge/releases/latest) 的完整 ZIP 并解压。
2. Windows 双击 `deploy.cmd`，输入电视 IP；macOS / Linux 运行 `sh deploy.sh --target 电视IP:5555`。
3. 脚本先检测设备和原生语音协议，通过后备份、安装、配置并设置结果入口。找不到 ADB 时，会从 Google 官方站点下载 platform-tools。
4. 如电视系统仍要求选择打开方式，选择 **TV语音桥 → 始终**。
5. 用真实遥控器测试输入框听写、桌面影片搜索，以及一个原生助手指令。

默认目标包是 `com.huawei.himovceie`，对应已验证的影视仓版本。不同分支包名或搜索接口可能不同。

也可以先只检测。以下地址是示例，请替换为电视实际地址：

```sh
python deploy.py --target 192.0.2.10:5555 --check
python deploy.py --target 192.0.2.10:5555 --apply
```

源码克隆后需先编译；完整 Release ZIP 已包含插件 APK。运行 `python deploy.py --help` 查看参数。

## 兼容范围

| 适配档案 | 状态 | 安装行为 |
| --- | --- | --- |
| 哈趣 K1 Pro，Android 9，`marconi / HQK1Pro` | 原设备适配版 2.1 已经用真实遥控器验证听写与影片搜索 | 精确匹配型号、检查原生接口后可部署 |
| 其他当贝 Rocky / DDS 设备 | 协议候选，未经逐机验证 | 默认拒绝；显式 `--experimental-profile` 后仍需通过接口检查并实测 |
| 小米、小爱、Google Assistant、其他语音栈 | 尚无适配器 | 只检测，不安装 |
| Tizen、webOS、VIDAA、非安卓设备 | 不适用 | 不支持 |

公开安装器接受 Android 8–12L 范围；这不代表该范围的每台电视都兼容。新固件可能改变接口，仍要重新验证。Android 13+ 的前台服务与权限需要单独适配。

实验档案不会启用哈趣专用音频路由；“接口能连接”不等于遥控器麦克风一定能用。

## 部署会改什么

- 安装独立插件 `io.github.qz0071.tvvoicebridge`。
- 在原有无障碍服务列表后追加插件服务，保留其他服务。
- 保留原生语音助手界面，将本机 `db_voice://db_launcher/control` 的影片搜索请求分流到插件。
- 在已验证的 K1 Pro 上，登记固件已有的 BLE 遥控器输入路由；Binder 事务号从本机框架读取，不向其他电视硬套固定数字。
- 本地写入恢复记录，失败时自动回滚已经记录的系统配置。

不替换桌面、不改变默认输入法、不停用系统语音引擎、不卸载应用、不刷机、不 root、不进入工厂菜单，也不关闭 ADB。公开版不安装或修改影视内容源。

插件无麦克风权限，不运行自己的识别模型；它订阅本机原生识别结果。原生服务原来如何联网识别，仍由原生服务负责。

## 恢复与重复部署

每次部署会输出本机恢复记录路径：

```sh
python deploy.py --target 192.0.2.10:5555 --restore backups/本次目录/state.json
```

恢复会核对设备地址、型号，恢复无障碍列表、原助手浮窗权限、原处理入口和旧适配插件状态；此次新装插件保留为停用状态。**请保留 `backups/`，不要将其公开上传。**

v1.0 不会自动覆盖已经安装的公开版插件，也不会用卸载来解决签名冲突。旧版已装设备的升级、恢复后的重新启用，需要核对已有签名与配置后操作，参见 [部署细节](docs/deployment.md)。

从本次个人适配版 `com.local.voiceinput` 迁移，须显式增加 `--replace-legacy`；检测阶段不会停用它。

## 其他 TVBox 分支

搜索通过明确的 Home Activity 和导出广播接口完成。可调整：

```sh
python deploy.py --target 192.0.2.10:5555 --apply \
  --target-package your.player.package \
  --home-activity your.player.HomeActivity \
  --search-receiver your.player.SearchReceiver \
  --search-action your.player.SEARCH \
  --search-extra title --search-delay 5000
```

这仅配置目标应用，不会让未知电视自动获得原生语音适配。目标应用必须真实支持对应接口。

## 构建与测试

需要 JDK 17、Android SDK 34 / build-tools 34.0.0。设置 `ANDROID_HOME` 或本地 `local.properties`，然后：

```sh
./gradlew testReleaseUnitTest assembleRelease
python -m unittest discover -s tests -v
python scripts/package_release.py
```

Windows 使用 `gradlew.bat`。Release ZIP 由打包脚本生成，包含部署脚本、适配档案、APK、SHA256 和文档。CI 只构建测试，不自动将随机调试签名的 APK 当成正式升级包发布。

## 技术路线与贡献

- [技术路线与踩坑](docs/architecture.md)
- [部署、权限与回滚](docs/deployment.md)
- [新增设备适配](docs/adapters.md)
- [验证记录](docs/validation.md)

欢迎提交脱敏的设备型号、Android 版本、语音栈和接口检测结果。请勿提交 ADB 私钥、账号令牌、原厂 APK、完整系统日志或包含家庭网络信息的备份。

项目代码使用 MIT License；Gradle Wrapper 保持其 Apache-2.0 许可，见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。
