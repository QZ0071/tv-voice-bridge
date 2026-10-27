import importlib.util
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy", ROOT / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class FakeAdb:
    """Stateful fake, including failures after individual device mutations."""
    serial = "test-device:5555"

    def __init__(self, model="HQK1Pro", fail_config=False):
        self.model, self.fail_config = model, fail_config
        self.calls = []
        self.packages = {"com.huawei.himovceie", "com.dangbei.lerad.rocky", "com.dangbei.leard.leradlauncher"}
        self.states = {name: 0 for name in self.packages}
        self.settings = {"enabled_accessibility_services": "com.example.reader/.Service",
                         "accessibility_enabled": "1"}
        self.alert = "ignore"
        self.handler = "com.dangbei.leard.leradlauncher/com.dangbei.voice_business.VoiceCenterActivity"

    def run(self, *args, **kwargs):
        self.calls.append(tuple(args))
        if args[0] == "install":
            self.packages.add(deploy.PACKAGE)
            self.states[deploy.PACKAGE] = 0
            return "Success"
        raise AssertionError(args)

    def shell(self, *args, **kwargs):
        args = tuple(map(str, args))
        self.calls.append(args)
        if args[:1] == ("getprop",):
            return {"ro.build.version.sdk": "28", "ro.product.device": "marconi",
                    "ro.product.model": self.model}[args[1]]
        if args == ("pm", "list", "packages"):
            return "\n".join("package:" + value for value in sorted(self.packages))
        if args[:2] == ("pm", "path"):
            return "package:/data/app/test/base.apk"
        if args[:2] == ("dumpsys", "package"):
            package = args[2]
            return (f"User 0: installed=true enabled={self.states.get(package, 0)}\n"
                    'Scheme: "db_voice"\ncom.dangbei.voice_business.VoiceCenterActivity\n'
                    "com.github.tvbox.osc.receiver.SearchReceiver")
        if args == ("dumpsys", "media.audio_policy"):
            return "- Available input devices:\nAUDIO_DEVICE_IN_WIRED_HEADSET\n- HW Module 1:"
        if args[:2] == ("appops", "get"):
            return "SYSTEM_ALERT_WINDOW: " + self.alert
        if args[:2] == ("appops", "set"):
            self.alert = args[-1]
            return ""
        if args[:3] == ("cmd", "package", "resolve-activity"):
            return "priority=0\n" + self.handler
        if args[:2] == ("am", "broadcast"):
            if args[3].endswith(".CONFIGURE"):
                if self.fail_config:
                    return 'Broadcast completed: result=1, data="configuration-rejected"'
                return 'Broadcast completed: result=0, data="configured"'
            return "Broadcast completed: result=0"
        if args[:1] == ("env",):
            if args[-1].endswith("AudioRouteProbe"):
                return '{"wiredTransaction":50}'
            if "VoiceRouteTool" in args[-2]:
                self.handler = args[-1]
                return "preferred=" + args[-1]
            raise AssertionError(args)
        if args[:2] == ("pm", "disable-user"):
            self.states[args[-1]] = 3
            return "disabled-user"
        if args[:2] in (("pm", "enable"), ("pm", "default-state")):
            self.states[args[-1]] = 1 if args[1] == "enable" else 0
            return "ok"
        raise AssertionError(args)

    def setting(self, key):
        return self.settings.get(key, "null")

    def put_setting(self, key, value):
        self.calls.append(("put_setting", key, value))
        self.settings[key] = value


class DeploymentTests(unittest.TestCase):
    def args(self, *extra):
        return deploy.parser().parse_args(["--target", "test-device:5555", *extra])

    def test_protocol_join_frame_is_utf8_length_delimited(self):
        self.assertEqual(deploy.read_frame(io.BytesIO(deploy.encode_frame("publish", "中文"))),
                         ["publish", "中文"])
        self.assertEqual(deploy.encode_frame("request", "/bus/join", "probe").split(b"\r\n")[1], b"request")

    def test_protocol_rejects_oversize_and_truncated_frames(self):
        for data in (b"999999999\r\n", b"4\r\na\r\n", b"-1\r\n"):
            with self.assertRaises(deploy.DeployError): deploy.read_frame(io.BytesIO(data))

    def test_unknown_tv_does_not_probe_or_mutate(self):
        adb = FakeAdb(model="unverified-tv")
        with patch.object(deploy, "probe_bus") as probe:
            report = deploy.detect(adb, self.args())
        self.assertFalse(report["supported"])
        probe.assert_not_called()
        self.assertTrue(all(call[0] in ("getprop", "pm") for call in adb.calls))

    def test_known_tv_checks_bus_but_does_not_change_settings(self):
        adb = FakeAdb()
        before = dict(adb.settings)
        with patch.object(deploy, "probe_bus", return_value=True):
            report = deploy.detect(adb, self.args())
        self.assertTrue(report["supported"])
        self.assertEqual(adb.settings, before)
        self.assertFalse(any(call[0] in ("install", "put_setting") for call in adb.calls))

    def test_successful_apply_preserves_other_accessibility_services_and_rolls_back(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "bridge.apk"; apk.write_bytes(b"test-apk")
            args = self.args("--apply", "--apk", str(apk))
            report = {"supported": True, "profile": "haqu-k1-pro",
                      "device": {"sdk": "28", "device": "marconi", "model": "HQK1Pro"}}
            with patch.object(deploy, "ROOT", root):
                (root / "profiles").mkdir()
                (root / "profiles/haqu-k1-pro.json").write_text((ROOT / "profiles/haqu-k1-pro.json").read_text())
                backup = deploy.apply(adb, args, report)
                self.assertIn("com.example.reader/.Service", adb.settings["enabled_accessibility_services"])
                self.assertIn(deploy.SERVICE, adb.settings["enabled_accessibility_services"])
                self.assertEqual(adb.alert, "default")
                self.assertTrue(json.loads(backup.read_text())["completed"])
                deploy.restore(adb, backup)
            self.assertEqual(adb.settings["enabled_accessibility_services"], "com.example.reader/.Service")
            self.assertEqual(adb.alert, "ignore")
            self.assertEqual(adb.states[deploy.PACKAGE], 3)
            self.assertIn("VoiceCenterActivity", adb.handler)

    def test_failed_configuration_triggers_rollback(self):
        adb = FakeAdb(fail_config=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "profiles").mkdir()
            (root / "profiles/haqu-k1-pro.json").write_text((ROOT / "profiles/haqu-k1-pro.json").read_text())
            apk = root / "bridge.apk"; apk.write_bytes(b"test-apk")
            report = {"supported": True, "profile": "haqu-k1-pro",
                      "device": {"sdk": "28", "device": "marconi", "model": "HQK1Pro"}}
            with patch.object(deploy, "ROOT", root), self.assertRaises(deploy.DeployError):
                deploy.apply(adb, self.args("--apk", str(apk)), report)
        self.assertEqual(adb.settings["enabled_accessibility_services"], "com.example.reader/.Service")
        self.assertEqual(adb.alert, "ignore")
        self.assertEqual(adb.states[deploy.PACKAGE], 3)

    def test_existing_bridge_is_never_overwritten(self):
        adb = FakeAdb(); adb.packages.add(deploy.PACKAGE)
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "bridge.apk"; apk.write_bytes(b"test-apk")
            with self.assertRaisesRegex(deploy.DeployError, "不会自动覆盖"):
                deploy.apply(adb, self.args("--apk", str(apk)), {
                    "supported": True, "profile": "haqu-k1-pro", "device": {}})
        self.assertFalse(any(call[0] == "install" for call in adb.calls))

    def test_restore_refuses_different_device(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "state.json"
            backup.write_text(json.dumps({"format": 1, "serial": "another-device"}))
            with self.assertRaisesRegex(deploy.DeployError, "不匹配"):
                deploy.restore(adb, backup)
        self.assertEqual(adb.calls, [])

    def test_installer_never_changes_home_input_method_or_closes_adb(self):
        source = (ROOT / "deploy.py").read_text(encoding="utf-8")
        for prohibited in ('"tcpip"', '"reboot"', '"uninstall"', '"set-home-activity"',
                           '"adb_enabled"', '"default_input_method"'):
            self.assertNotIn(prohibited, source)


if __name__ == "__main__": unittest.main()
