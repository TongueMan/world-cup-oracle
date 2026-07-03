"""数据采集脚本 — MVP: 从 fixture 复制到 normalized。"""
import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wcpa.shared.paths import FIXTURES_DIR, NORMALIZED_DIR


def main():
    """MVP: 将 fixture 文件复制到 normalized 目录。"""
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)

    for fixture_file in FIXTURES_DIR.glob("*.json"):
        dest = NORMALIZED_DIR / fixture_file.name
        shutil.copy2(fixture_file, dest)
        print(f"Copied: {fixture_file.name} → {dest}")

    print(f"\nData collection complete (MVP: fixture copy).")


if __name__ == "__main__":
    main()
