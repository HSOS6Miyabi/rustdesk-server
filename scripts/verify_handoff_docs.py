#!/usr/bin/env python3
"""Validate links and essential fields in the Server handoff snapshot."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
snapshot_path = ROOT / "docs" / "HANDOFF_SNAPSHOT_2026-11-09.md"
files = (
    ROOT / "README.md",
    ROOT / "docs" / "HANDOFF.md",
    ROOT / "docs" / "IMPLEMENTATION_LEDGER.md",
    ROOT / "docs" / "TESTING.md",
    ROOT / "docs" / "environment-variables.md",
    ROOT / "src" / "device_deployment.rs",
    ROOT / "src" / "control_roles.rs",
    ROOT / "scripts" / "test_strict_combination.py",
)

def main():
    if not snapshot_path.is_file():
        raise AssertionError("The Server handoff snapshot is missing")
    for file in files:
        if not file.is_file():
            raise AssertionError(f"Required Server documentation or test is missing: {file}")
    snapshot = snapshot_path.read_text(encoding="utf-8")
    for heading in ("当前仓库状态", "主要文件与对应测试", "仍需完成的服务端真实环境工作", "接手顺序"):
        if heading not in snapshot:
            raise AssertionError(f"Server handoff section missing: {heading}")
    for token in ("282", "T001", "T022", "草稿", "正式", "MUST_LOGIN", "REQUIRE_DEVICE_DEPLOYMENT"):
        if token not in snapshot:
            raise AssertionError(f"Server handoff lacks: {token}")
    for url in re.findall(r"\[[^\]]+\]\(([^)]+)\)", snapshot):
        if url.startswith(("https://", "http://", "mailto:")):
            continue
        local = url.split("#", 1)[0]
        if local and not (snapshot_path.parent / local).resolve().is_file():
            raise AssertionError(f"Broken local handoff reference: {local}")
    for file in files[:4]:
        if "HANDOFF_SNAPSHOT_2026-11-09.md" not in file.read_text(encoding="utf-8"):
            raise AssertionError(f"Server handoff entry missing in {file}")
    print("Server handoff snapshot, local links and both repositories' task references verified.")

if __name__ == "__main__":
    try:
        main()
    except (AssertionError, ValueError) as error:
        print(f"Server documentation check did not pass: {error}", file=sys.stderr)
        sys.exit(1)
