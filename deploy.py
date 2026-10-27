#!/usr/bin/env python3
"""TV Voice Bridge: compatibility check, transactional ADB deployment, exact rollback.

Python standard library only. No root, factory menus, APK downloads from third parties,
ADB shutdown, removal of existing apps, or changes to the user's default input method.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGE = "io.github.qz0071.tvvoicebridge"
SERVICE = PACKAGE + "/.VoiceInputService"
RECEIVER = PACKAGE + "/.DeployReceiver"
LEGACY_SERVICE = "com.local.voiceinput/.VoiceInputService"
URI = "db_voice://db_launcher/control"
DEFAULT_TARGET = "com.huawei.himovceie"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


class DeployError(RuntimeError):
    pass


class Adb:
    def __init__(self, executable: str, serial: str):
        self.executable, self.serial = executable, serial

    def run(self, *args: str, timeout: int = 25, check: bool = True) -> str:
        completed = subprocess.run(
            [self.executable, "-s", self.serial, *map(str, args)],
            text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout,
        )
        output = (completed.stdout + completed.stderr).strip()
        failed = completed.returncode != 0 or any(
            marker in output for marker in (
                "Security exception:", "java.lang.SecurityException:",
                "Permission Denial:", "Failure [", "Error: ", "error: device",
            )
        )
        if check and failed:
            # Arguments may include user configuration, but never API credentials.
            raise DeployError(output or f"ADB command failed ({completed.returncode})")
        return output

    def shell(self, *args: str, **kwargs) -> str:
        # ADB joins shell argv on Android: quote every argument for the remote shell.
        return self.run("shell", " ".join(shlex.quote(str(arg)) for arg in args), **kwargs)

    def setting(self, key: str) -> str:
        return self.shell("settings", "get", "secure", key)

    def put_setting(self, key: str, value: str) -> None:
        if value == "null":
            self.shell("settings", "delete", "secure", key)
        else:
            self.shell("settings", "put", "secure", key, value)


def adb_path(explicit: str | None, download: bool = False) -> str:
    candidates = [explicit, shutil.which("adb"), os.environ.get("TV_ADB_BINARY")]
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk:
        candidates.append(str(Path(sdk) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")))
    if os.name == "nt":
        candidates.append(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe"))
    candidates.append(str(ROOT / ".tools/platform-tools" / ("adb.exe" if os.name == "nt" else "adb")))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    if not download:
        raise DeployError("找不到 adb。安装 Android platform-tools，或增加 --download-adb。")
    host = "windows" if os.name == "nt" else "darwin" if sys.platform == "darwin" else "linux"
    url = f"https://dl.google.com/android/repository/platform-tools-latest-{host}.zip"
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    archive = tools / "platform-tools.zip"
    print("从 Google 官方站点下载 platform-tools…", flush=True)
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            resolved = (tools / member.filename).resolve()
            if not resolved.is_relative_to(tools.resolve()):
                raise DeployError("platform-tools 归档包含越界路径")
        bundle.extractall(tools)
    executable = tools / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    if os.name != "nt":
        executable.chmod(0o755)
    return str(executable.resolve())


def connect(executable: str, target: str) -> str:
    if not target or any(char.isspace() for char in target) or target.startswith("-"):
        raise DeployError("无效的设备地址或 serial")
    if re.fullmatch(r"[A-Za-z0-9_.-]+(?::[0-9]{1,5})?", target) is None:
        raise DeployError("设备地址应为 IPv4/主机名:端口，或 USB serial")
    # A dotted hostname/IP is a network endpoint. USB serials are left unchanged.
    serial = target if ":" in target or "." not in target else target + ":5555"
    if ":" in serial:
        result = subprocess.run([executable, "connect", serial], text=True,
                                capture_output=True, encoding="utf-8", errors="replace", timeout=25)
        if result.returncode or "cannot connect" in (result.stdout + result.stderr):
            raise DeployError((result.stdout + result.stderr).strip())
    return serial


def enabled_state(package_dump: str) -> int:
    match = re.search(r"User 0:[^\n]*\benabled=(\d+)", package_dump)
    if not match:
        raise DeployError("无法读取应用启用状态")
    return int(match.group(1))


def appop_mode(output: str) -> str:
    match = re.search(r"SYSTEM_ALERT_WINDOW:\s*([a-z_]+)", output)
    return match.group(1) if match else "default"


def service_list(value: str) -> list[str]:
    return [] if value in ("", "null") else [part for part in value.split(":") if part]


def encode_frame(*fields: str) -> bytes:
    return b"".join(str(len(data)).encode() + b"\r\n" + data + b"\r\n"
                    for data in (field.encode("utf-8") for field in fields)) + b"\r\n"


def read_frame(stream) -> list[str]:
    fields = []
    while True:
        header = stream.readline(34)
        if not header.endswith(b"\r\n"):
            raise DeployError("原生总线帧头无效")
        if header == b"\r\n":
            return fields
        try:
            length = int(header[:-2])
        except ValueError as error:
            raise DeployError("原生总线帧长度无效") from error
        if not 0 <= length <= 131072 or len(fields) >= 16:
            raise DeployError("原生总线帧超出限制")
        data = stream.read(length)
        if len(data) != length or stream.read(2) != b"\r\n":
            raise DeployError("原生总线帧不完整")
        fields.append(data.decode("utf-8"))


def probe_bus(adb: Adb, port: int) -> bool:
    forwarded = adb.run("forward", "tcp:0", f"tcp:{port}")
    local_port = forwarded.splitlines()[-1]
    try:
        if not local_port.isdigit():
            raise DeployError("ADB 未返回本地转发端口")
        with socket.create_connection(("127.0.0.1", int(local_port)), timeout=3) as connection:
            connection.settimeout(3)
            stream = connection.makefile("rb")
            # Joining first is mandatory; subscribing an unnamed client can crash old DDS firmware.
            for command in (
                ("request", "/bus/join", "tv.voice.probe." + uuid.uuid4().hex[:12]),
                ("request", "/bus/subscribe", "asr.speech.result"),
            ):
                connection.sendall(encode_frame(*command))
                while True:
                    frame = read_frame(stream)
                    if frame and frame[0] == "response":
                        if len(frame) > 2 and frame[2]:
                            raise DeployError("原生服务拒绝探测订阅")
                        break
        return True
    except (OSError, ValueError, DeployError):
        return False
    finally:
        if local_port.isdigit():
            adb.run("forward", "--remove", f"tcp:{local_port}", check=False)


def detect(adb: Adb, args) -> dict:
    props = {name: adb.shell("getprop", prop) for name, prop in (
        ("sdk", "ro.build.version.sdk"), ("device", "ro.product.device"), ("model", "ro.product.model"))}
    packages = {line.removeprefix("package:") for line in adb.shell("pm", "list", "packages").splitlines()
                if line.startswith("package:")}
    report = {"device": props, "supported": False, "reasons": [], "profile": None}
    sdk = int(props["sdk"]) if props["sdk"].isdigit() else 0
    if not 26 <= sdk <= 32:
        report["reasons"].append("此发布版本仅支持 Android 8–12L 检测范围；本机版本未适配")
    if "com.dangbei.lerad.rocky" not in packages:
        report["reasons"].append("缺少已适配的 Rocky / DDS 原生语音服务")
    if args.target_package not in packages:
        report["reasons"].append("目标播放器尚未安装；本项目不分发播放器或影视源")
    exact = json.loads((ROOT / "profiles/haqu-k1-pro.json").read_text(encoding="utf-8"))
    if props == exact["match"]:
        profile = exact
    elif args.experimental_profile:
        profile = json.loads((ROOT / "profiles/dangbei-dds-candidate.json").read_text(encoding="utf-8"))
    else:
        profile = None
        report["reasons"].append("没有精确匹配的已验证设备档案；可提交脱敏检测报告申请适配")
    if profile:
        report["profile"] = profile["id"]
        native_dump = adb.shell("dumpsys", "package", profile["nativePackage"])
        if enabled_state(native_dump) not in (0, 1):
            report["reasons"].append("原生语音服务已停用，请先恢复到可正常使用的状态")
        native_handler = profile["nativeHandler"].split("/", 1)[1]
        handler_dump = adb.shell("dumpsys", "package", profile["nativeHandler"].split("/", 1)[0])
        if native_handler not in handler_dump or 'Scheme: "db_voice"' not in handler_dump:
            report["reasons"].append("原生语音 URI 接口与适配档案不一致")
        target_dump = adb.shell("dumpsys", "package", args.target_package)
        # Activities are not always listed by dumpsys unless they have an intent filter.
        if args.search_receiver not in target_dump:
            report["reasons"].append("目标播放器未公开预期的搜索广播接口")
        if not report["reasons"]:
            report["busReady"] = probe_bus(adb, profile["busPort"])
            if not report["busReady"]:
                report["reasons"].append("原生语音消息接口不可用；先确认原生助手自身正常")
    report["supported"] = not report["reasons"]
    return report


def snapshot(adb: Adb, report: dict) -> dict:
    package_list = adb.shell("pm", "list", "packages")
    installed = "package:" + PACKAGE in package_list.splitlines()
    legacy_installed = "package:com.local.voiceinput" in package_list.splitlines()
    native = "com.dangbei.lerad.rocky"
    audio_policy = adb.shell("dumpsys", "media.audio_policy")
    available_inputs = audio_policy.split("- Available input devices:", 1)[-1].split("- HW Module", 1)[0]
    return {
        "format": 1, "serial": adb.serial, "profile": report["profile"], "device": report["device"],
        "bridgeWasInstalled": installed,
        "bridgeEnabledState": enabled_state(adb.shell("dumpsys", "package", PACKAGE)) if installed else None,
        "legacyWasInstalled": legacy_installed,
        "legacyEnabledState": enabled_state(adb.shell("dumpsys", "package", "com.local.voiceinput")) if legacy_installed else None,
        "accessibilityServices": adb.setting("enabled_accessibility_services"),
        "accessibilityEnabled": adb.setting("accessibility_enabled"),
        "nativeAlertWindow": appop_mode(adb.shell("appops", "get", native, "SYSTEM_ALERT_WINDOW")),
        "nativeEnabledState": enabled_state(adb.shell("dumpsys", "package", native)),
        "priorVoiceHandler": adb.shell("cmd", "package", "resolve-activity", "--brief", "-a",
                                       "android.intent.action.VIEW", "-d", URI),
        "bleInputWasConnected": "AUDIO_DEVICE_IN_WIRED_HEADSET" in available_inputs,
        "apkBackup": None, "mutations": [],
    }


def set_enabled(adb: Adb, package: str, state: int) -> None:
    commands = {0: "default-state", 1: "enable", 2: "disable", 3: "disable-user", 4: "disable-until-used"}
    if state not in commands:
        raise DeployError("无法恢复未知应用状态")
    adb.shell("pm", commands[state], "--user", "0", package)


def restore(adb: Adb, backup: Path) -> None:
    state = json.loads(backup.read_text(encoding="utf-8"))
    if state.get("format") != 1 or state.get("serial") != adb.serial:
        raise DeployError("备份与当前设备不匹配")
    expected = state["device"]
    for field, prop in (("device", "ro.product.device"), ("model", "ro.product.model")):
        if adb.shell("getprop", prop) != expected[field]:
            raise DeployError("设备型号与备份不一致，停止恢复")
    errors = []
    def attempt(action):
        try: action()
        except Exception as error: errors.append(str(error))
    attempt(lambda: adb.put_setting("enabled_accessibility_services", state["accessibilityServices"]))
    attempt(lambda: adb.put_setting("accessibility_enabled", state["accessibilityEnabled"]))
    attempt(lambda: adb.shell("appops", "set", "com.dangbei.lerad.rocky", "SYSTEM_ALERT_WINDOW", state["nativeAlertWindow"]))
    if state["bridgeWasInstalled"]:
        # Reinstalling a different signer/version is never done silently.
        # --apply refuses upgrades; this branch exists for forward-compatible backups.
        attempt(lambda: set_enabled(adb, PACKAGE, state["bridgeEnabledState"]))
    else:
        present = "package:" + PACKAGE in adb.shell("pm", "list", "packages").splitlines()
        if present:
            attempt(lambda: set_enabled(adb, PACKAGE, 3))
    if state["legacyWasInstalled"]:
        attempt(lambda: set_enabled(adb, "com.local.voiceinput", state["legacyEnabledState"]))
    preferred = component_from_resolution(state["priorVoiceHandler"])
    present = "package:" + PACKAGE in adb.shell("pm", "list", "packages").splitlines()
    if present:
        attempt(lambda: route_tool(adb, preferred if preferred and not preferred.startswith("android/") else "clear"))
        if state["profile"] == "haqu-k1-pro" and not state.get("bleInputWasConnected", True):
            def disconnect_added_input():
                apk_path = adb.shell("pm", "path", PACKAGE).splitlines()[0].removeprefix("package:")
                adb.shell("env", "CLASSPATH=" + apk_path, "app_process", "/system/bin",
                          PACKAGE + ".AudioRouteProbe", "--disconnect")
            attempt(disconnect_added_input)
    if errors:
        raise DeployError("部分恢复失败，请按备份核对：\n" + "\n".join(errors))
    print("已恢复无障碍设置、浮窗权限和应用状态；ADB 保持开启。")
    print("新增插件保留为停用状态；原语音入口已按备份恢复。")


def component_from_resolution(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        if re.fullmatch(r"[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+", line.strip()):
            return line.strip()
    return None


def route_tool(adb: Adb, handler: str) -> str:
    apk_path = adb.shell("pm", "path", PACKAGE).splitlines()[0].removeprefix("package:")
    return adb.shell("env", "CLASSPATH=" + apk_path, "app_process", "/system/bin",
                     PACKAGE + ".VoiceRouteTool", handler)


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def apply(adb: Adb, args, report: dict) -> Path:
    if not report["supported"]:
        raise DeployError("兼容性检测未通过，未修改设备")
    apk = Path(args.apk or ROOT / "dist/tv-voice-bridge.apk").resolve()
    if not apk.is_file():
        raise DeployError("缺少安装包。请下载完整 Release ZIP，或先编译并用 --apk 指定 APK。")
    expected_hash = args.sha256
    if not expected_hash and apk.parent == ROOT / "dist" and (apk.parent / "SHA256SUMS").is_file():
        expected_hash = (apk.parent / "SHA256SUMS").read_text().split()[0]
    actual_hash = hashlib.sha256(apk.read_bytes()).hexdigest()
    if expected_hash and actual_hash.lower() != expected_hash.lower():
        raise DeployError("APK SHA256 校验失败")
    state = snapshot(adb, report)
    if state["bridgeWasInstalled"]:
        raise DeployError("此设备已安装公开版插件。为保护签名和既有配置，本版本不会自动覆盖；请先备份并使用明确的升级流程。")
    existing = service_list(state["accessibilityServices"])
    if LEGACY_SERVICE in existing and not args.replace_legacy:
        raise DeployError("检测到此前的私人适配插件。需要迁移时显式增加 --replace-legacy；当前不改动。")
    folder = ROOT / "backups" / (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True)
    backup = folder / "state.json"
    atomic_json(backup, state)
    print(f"恢复记录：{backup}", flush=True)
    def mutation(label, action):
        state["mutations"].append(label)
        atomic_json(backup, state)
        return action()
    try:
        output = mutation("install-bridge", lambda: adb.run("install", str(apk), timeout=90))
        if "Success" not in output:
            raise DeployError(output or "安装没有返回 Success")
        profile = json.loads((ROOT / "profiles" / (report["profile"] + ".json")).read_text(encoding="utf-8"))
        configuration = {
            "profile": report["profile"], "busPort": profile["busPort"],
            "targetPackage": args.target_package, "homeActivity": args.home_activity,
            "searchReceiver": args.search_receiver, "searchAction": args.search_action,
            "searchExtra": args.search_extra, "searchDelayMs": args.search_delay,
            "audioTransaction": 0,
        }
        if profile["audioRoute"] == "haqu-ble-input":
            apk_path = adb.shell("pm", "path", PACKAGE).splitlines()[0].removeprefix("package:")
            # The read-only helper obtains the transaction from this exact firmware.
            probe = adb.shell("env", "CLASSPATH=" + apk_path, "app_process", "/system/bin",
                              PACKAGE + ".AudioRouteProbe")
            match = re.search(r'\{"wiredTransaction":\d+\}', probe)
            if not match:
                raise DeployError("无法验证本机音频路由接口")
            configuration["audioTransaction"] = json.loads(match.group())["wiredTransaction"]
        encoded = json.dumps(configuration, ensure_ascii=True, separators=(",", ":"))
        result = mutation("configure-bridge", lambda: adb.shell("am", "broadcast", "-a", PACKAGE + ".CONFIGURE",
                          "-n", RECEIVER, "--es", "json", encoded))
        if "configured" not in result or "result=0" not in result:
            raise DeployError("插件未确认保存部署配置")
        new_services = [item for item in existing if item != SERVICE
                        and not (args.replace_legacy and item == LEGACY_SERVICE)]
        new_services.append(SERVICE)
        mutation("enable-accessibility-service", lambda: adb.put_setting("enabled_accessibility_services", ":".join(new_services)))
        mutation("enable-accessibility", lambda: adb.put_setting("accessibility_enabled", "1"))
        mutation("restore-native-assistant-ui", lambda: adb.shell("appops", "set", profile["nativePackage"],
                                                                 "SYSTEM_ALERT_WINDOW", "default"))
        if args.replace_legacy and state["legacyWasInstalled"]:
            mutation("disable-legacy-bridge", lambda: set_enabled(adb, "com.local.voiceinput", 3))
        try:
            mutation("choose-voice-uri-handler", lambda: route_tool(adb, PACKAGE + "/.ResultActivity"))
        except DeployError:
            adb.shell("am", "broadcast", "-a", PACKAGE + ".CHOOSE_HANDLER", "-n", RECEIVER)
            print("系统需确认默认入口；电视若显示打开方式，请选 TV语音桥 / 始终。", flush=True)
            adb.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", URI)
        resolved = ""
        for _ in range(45):
            resolved = adb.shell("cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.VIEW", "-d", URI)
            if PACKAGE + "/.ResultActivity" in resolved:
                break
            time.sleep(1)
        else:
            raise DeployError("语音结果默认入口未设置，开始回滚")
        state["completed"] = True
        state["apkSha256"] = actual_hash
        atomic_json(backup, state)
        print("部署完成。请分别测试：输入框听写；桌面说“我想看熊出没”；其他原生助手指令。")
        print("恢复命令：python deploy.py --target " + shlex.quote(adb.serial) + " --restore " + shlex.quote(str(backup)))
        return backup
    except Exception:
        print("部署未完成，正在回滚已记录修改…", file=sys.stderr, flush=True)
        try:
            restore(adb, backup)
        except Exception as recovery_error:
            print("自动恢复未完全成功：" + str(recovery_error), file=sys.stderr)
            print("请保留恢复记录：" + str(backup), file=sys.stderr)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--target", help="TV IPv4/hostname[:5555] or USB serial")
    result.add_argument("--adb", help="Explicit adb executable")
    result.add_argument("--download-adb", action="store_true", help="Download Google official platform-tools if absent")
    group = result.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Default: read-only compatibility check")
    group.add_argument("--apply", action="store_true", help="Deploy only after successful preflight")
    group.add_argument("--restore", type=Path, help="Restore a device-specific state.json")
    result.add_argument("--apk", help="Bridge APK; default dist/tv-voice-bridge.apk")
    result.add_argument("--sha256", help="Expected APK SHA256")
    result.add_argument("--replace-legacy", action="store_true", help="Explicitly migrate the earlier private adapter")
    result.add_argument("--experimental-profile", action="store_true", help="Opt into unverified Rocky/DDS candidate devices")
    result.add_argument("--target-package", default=DEFAULT_TARGET)
    result.add_argument("--home-activity", default="com.github.tvbox.osc.ui.activity.HomeActivity")
    result.add_argument("--search-receiver", default="com.github.tvbox.osc.receiver.SearchReceiver")
    result.add_argument("--search-action", default="android.content.movie.search.Action")
    result.add_argument("--search-extra", default="title")
    result.add_argument("--search-delay", type=int, default=5000)
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        for key in ("target_package", "home_activity", "search_receiver", "search_action", "search_extra"):
            if not NAME.fullmatch(getattr(args, key)):
                raise DeployError("无效的组件配置：" + key)
        if not 1000 <= args.search_delay <= 15000:
            raise DeployError("搜索延迟必须为 1000–15000 毫秒")
        target = args.target or input("电视 IP[:5555] 或 USB serial：").strip()
        executable = adb_path(args.adb, args.download_adb)
        adb = Adb(executable, connect(executable, target))
        if adb.run("get-state") != "device":
            raise DeployError("ADB 尚未授权；请在电视上确认电脑连接")
        if args.restore:
            restore(adb, args.restore.resolve())
            return 0
        report = detect(adb, args)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.apply:
            apply(adb, args, report)
        return 0 if report["supported"] else 2
    except (DeployError, OSError, subprocess.TimeoutExpired, ValueError) as error:
        print("停止：" + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
