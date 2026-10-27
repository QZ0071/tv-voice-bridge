#!/usr/bin/env python3
"""Apply a wallpaper collection to an existing CleanYourTV launcher; keep its dock intact."""
from pathlib import Path
import argparse
import datetime as dt
import json
import sys
import uuid
from deploy import Adb, DeployError, adb_path, connect, atomic_json

ROOT = Path(__file__).resolve().parent
LAUNCHER = "com.gathin.tvhome"
BASE = "/sdcard/Android/data/" + LAUNCHER + "/files"
DREAM = LAUNCHER + "/.ClockDream"
KEYS = ("screensaver_components", "screensaver_default_component", "screensaver_enabled")


def exists(adb, path):
    return adb.shell("ls", "-d", path, check=False).strip() == path


def remote(path):
    if not path.startswith(BASE + "/") or ".." in path or any(c.isspace() for c in path):
        raise DeployError("拒绝超出桌面专属目录的路径")
    return path


def load_collection(folder):
    folder = folder.resolve()
    data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    settings = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    images = []
    for item in data["images"]:
        name = item["file"]
        if Path(name).name != name or Path(name).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            raise DeployError("图集文件名无效")
        image = (folder / "images" / name).resolve()
        if not image.is_relative_to(folder / "images") or not image.is_file():
            raise DeployError("缺少图集图片：" + name)
        images.append(image)
    if not images or len({image.name for image in images}) != len(images):
        raise DeployError("图集为空或包含重复文件名")
    # A wallpaper collection must never override the owner's application layout.
    allowed = {"wallpaper", "wallpaper_rotation_minutes", "wallpaper_order", "wallpaper_dim",
               "clock_wallpaper", "clock_wallpaper_dim", "home_idle_clock_minutes", "clock_glow"}
    if set(settings) - allowed:
        raise DeployError("图集配置包含壁纸与屏保之外的字段")
    return images, settings


def restore(adb, backup):
    state = json.loads(backup.read_text(encoding="utf-8"))
    if state.get("kind") != "wallpapers-v1" or state["serial"] != adb.serial:
        raise DeployError("恢复记录与设备不匹配")
    if state.get("restored"):
        print("这份备份已经恢复。")
        return
    images = remote(BASE + "/wallpapers")
    old = remote(state["oldImages"])
    if state.get("newImagesActivated") and exists(adb, images):
        saved_new = remote(BASE + "/tvvb-restored-new-" + state["id"])
        adb.shell("mv", images, saved_new)
        state["newImagesActivated"] = False
        atomic_json(backup, state)
    if state.get("oldImagesMoved") and exists(adb, old):
        adb.shell("mv", old, images)
        state["oldImagesMoved"] = False
        atomic_json(backup, state)
    if state.get("configActivated"):
        original = backup.parent / "original-config.json"
        if state["hadConfig"]:
            adb.run("push", str(original), remote(BASE + "/config.json"))
        else:
            adb.shell("rm", "-f", remote(BASE + "/config.json"))
        state["configActivated"] = False
        atomic_json(backup, state)
    for key, value in state["dream"].items():
        adb.put_setting(key, value)
    adb.shell("am", "force-stop", LAUNCHER)
    adb.shell("am", "start", "-n", LAUNCHER + "/.MainActivity")
    state["restored"] = True
    atomic_json(backup, state)
    print("已恢复原壁纸、桌面配置与屏保设置。ADB 保持开启。")


def apply(adb, images, overlay, wallpaper_only=False):
    if "package:" not in adb.shell("pm", "path", LAUNCHER):
        raise DeployError("请先安装 CleanYourTV 桌面；本脚本不会替换现有桌面")
    if not wallpaper_only:
        package = adb.shell("dumpsys", "package", LAUNCHER)
        if "ClockDream" not in package:
            raise DeployError("当前桌面未提供 ClockDream 屏保；可更新桌面或用 --wallpaper-only")
    identity = uuid.uuid4().hex[:12]
    folder = ROOT / "backups" / ("wallpapers-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + identity)
    folder.mkdir(parents=True)
    backup = folder / "state.json"
    config = remote(BASE + "/config.json")
    collection = remote(BASE + "/wallpapers")
    stage = remote(BASE + "/tvvb-stage-" + identity)
    config_stage = remote(BASE + "/tvvb-config-" + identity + ".json")
    old = remote(BASE + "/tvvb-old-wallpapers-" + identity)
    had_config = exists(adb, config)
    current = {}
    if had_config:
        adb.run("pull", config, str(folder / "original-config.json"))
        current = json.loads((folder / "original-config.json").read_text(encoding="utf-8-sig"))
    if not isinstance(current, dict):
        raise DeployError("原桌面配置不是 JSON 对象，停止覆盖")
    state = {"kind": "wallpapers-v1", "id": identity, "serial": adb.serial,
             "oldImages": old, "hadConfig": had_config,
             "oldImagesMoved": False, "newImagesActivated": False, "configActivated": False,
             "dream": {key: adb.setting(key) for key in KEYS}}
    atomic_json(backup, state)
    changed = dict(current)
    changed.update(overlay)
    local_config = folder / "new-config.json"
    local_config.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("恢复记录：" + str(backup), flush=True)
    try:
        # Upload completely before changing the active collection. Old images are moved, never deleted.
        adb.shell("mkdir", "-p", stage)
        for image in images:
            adb.run("push", str(image), stage + "/" + image.name, timeout=60)
        adb.run("push", str(local_config), config_stage)
        if exists(adb, collection):
            adb.shell("mv", collection, old)
            state["oldImagesMoved"] = True
            atomic_json(backup, state)
        adb.shell("mv", stage, collection)
        state["newImagesActivated"] = True
        atomic_json(backup, state)
        adb.shell("mv", config_stage, config)
        state["configActivated"] = True
        atomic_json(backup, state)
        if not wallpaper_only:
            adb.put_setting("screensaver_components", DREAM)
            adb.put_setting("screensaver_default_component", DREAM)
            adb.put_setting("screensaver_enabled", "1")
        adb.shell("am", "force-stop", LAUNCHER)
        adb.shell("am", "start", "-n", LAUNCHER + "/.MainActivity")
        print(f"已配置 {len(images)} 张图片，每 {overlay['wallpaper_rotation_minutes']} 分钟轮换。")
        print("恢复：python wallpaper_deploy.py --target " + adb.serial + " --restore " + str(backup))
    except Exception:
        print("应用未完成，尝试恢复原设置…", file=sys.stderr)
        try:
            restore(adb, backup)
        except Exception as error:
            print("请保留恢复记录并手动核对：" + str(error), file=sys.stderr)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target")
    parser.add_argument("--adb")
    parser.add_argument("--download-adb", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--restore", type=Path)
    parser.add_argument("--collection", type=Path, default=ROOT / "wallpapers/nintendo")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--wallpaper-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.interval <= 1440:
            raise DeployError("轮换间隔必须为 1–1440 分钟")
        if not args.restore:
            images, settings = load_collection(args.collection)
            settings["wallpaper_rotation_minutes"] = args.interval
            if not args.apply:
                print(json.dumps({"images": [image.name for image in images], "config": settings},
                                 ensure_ascii=False, indent=2))
                print("以上为本地计划。加 --apply 才会连接电视并应用。")
                return 0
        target = args.target or input("电视 IP[:5555] 或 USB serial：").strip()
        executable = adb_path(args.adb, args.download_adb)
        adb = Adb(executable, connect(executable, target))
        if adb.run("get-state") != "device":
            raise DeployError("ADB 未授权")
        if args.restore:
            restore(adb, args.restore.resolve())
        else:
            apply(adb, images, settings, args.wallpaper_only)
        return 0
    except Exception as error:
        print("停止：" + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
