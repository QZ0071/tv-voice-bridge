# 壁纸与屏保更换

仓库包含投影仪实际使用的 [11 张图片](../wallpapers/nintendo/README.md)：动森、马里奥、碧姬、罗莎塔、黛西、耀西、西施慧。已移除的动森博物馆图片不包含在内。

## 使用前提

电视已安装 [CleanYourTV 桌面](https://github.com/Gathin23/cleanyourtv)，并支持其 `config.json`、`wallpapers/` 和 `ClockDream` 屏保。本工具不会自动安装或替换桌面，也不适用于所有品牌的原生桌面。

语音桥和壁纸工具相互独立：更换壁纸不需要重新安装语音桥，也不修改语音服务。

## 一键应用

下载完整 Release ZIP，解压后 Windows 双击 **wallpapers.cmd**，输入电视地址。需要 Python 3.10+ 和已授权的 ADB；找不到 ADB 时可从 Google 官方站点下载。

或运行下面的命令，替换示例 IP：

```sh
python wallpaper_deploy.py --target 192.0.2.10:5555 --apply
```

默认行为：

- 桌面与时钟屏保使用同一组 11 张图片。
- 每 **5 分钟**按顺序轮换。
- 桌面暗化 30%，时钟屏保暗化 20%。
- 桌面空闲 5 分钟进入桌面时钟；Android 系统屏保也设为 ClockDream。系统何时自动进入屏保仍由设备自身休眠策略决定，不会修改全局息屏时间。
- 保留原有 dock、隐藏应用列表和其他桌面配置，只合并壁纸相关字段。

调整轮换间隔或只换桌面：

```sh
python wallpaper_deploy.py --target 192.0.2.10:5555 --apply --interval 10
python wallpaper_deploy.py --target 192.0.2.10:5555 --apply --wallpaper-only
```

不带 `--apply` 只列出本地图集和计划，不连接电视。

## 备份与恢复

应用前保存原桌面配置、屏保设置及恢复记录；旧图片文件夹在桌面专属目录中改名保留，新图全部上传后才切换。不会递归删除旧图片。

```sh
python wallpaper_deploy.py --target 192.0.2.10:5555 --restore backups/本次壁纸目录/state.json
```

保留电脑的 `backups/` 和电视端 `tvvb-old-wallpapers-*` 文件夹。恢复时，新图集也会改名保存，避免直接删除。应用和恢复会重新启动 CleanYourTV 桌面，不关闭 ADB，不改变默认 Home。

## 自定义图集

复制 `wallpapers/nintendo/`，替换 `images/` 中的图片，并同步 `manifest.json` 的文件列表与来源；配置只允许壁纸、轮换和时钟相关字段。

```sh
python wallpaper_deploy.py --target 192.0.2.10:5555 --apply --collection wallpapers/my-theme
```

## 图片权利

图片为第三方素材，版权归任天堂及对应作者，具体来源见图集 [manifest.json](../wallpapers/nintendo/manifest.json)。这些图片不属于本项目 MIT 授权的代码；请按来源条款使用，不将署名视为另行获得商用或再分发许可。
