#!/usr/bin/env python3
"""Package only reviewed source/deployment files and the locally built APK."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
apk = ROOT / "app/build/outputs/apk/release/app-release.apk"
if not apk.is_file():
    raise SystemExit("Build assembleRelease first")
version = json.loads((apk.parent / "output-metadata.json").read_text())["elements"][0]["versionName"]
dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
target = dist / "tv-voice-bridge.apk"
target.write_bytes(apk.read_bytes())
checksum = hashlib.sha256(target.read_bytes()).hexdigest() + "  tv-voice-bridge.apk\n"
(dist / "SHA256SUMS").write_text(checksum, encoding="ascii")
archive = dist / f"tv-voice-bridge-{version}.zip"
allowed = ["deploy.py", "deploy.cmd", "deploy.sh", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]
allowed += [str(path.relative_to(ROOT)) for folder in ("profiles", "docs")
            for path in (ROOT / folder).rglob("*") if path.is_file()]
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
    for name in sorted(allowed):
        bundle.write(ROOT / name, name.replace("\\", "/"))
    bundle.write(target, "dist/tv-voice-bridge.apk")
    bundle.write(dist / "SHA256SUMS", "dist/SHA256SUMS")
print(archive.name)
print(checksum.strip())
