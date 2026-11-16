#!/usr/bin/env python3
"""跨平台啟動器（Windows / macOS / Linux），只用標準函式庫。

  python scripts/launcher.py check              檢查 Python / Node 版本
  python scripts/launcher.py setup              建 venv、裝後端依賴、npm ci、build 前端
  python scripts/launcher.py start              啟動 API(8000) + 單一 worker；服務 build 後的前端
  python scripts/launcher.py dev                同上，另開 Vite dev server(5173，proxy /api)
  python scripts/launcher.py seed               補齊 Demo 資料（不覆蓋）
  python scripts/launcher.py reset --confirm    清空 Demo DB 並重新 seed（破壞性）
  python scripts/launcher.py test               後端 pytest + 前端 typecheck/build
  python scripts/launcher.py e2e                Playwright 瀏覽器 E2E
預設只綁 127.0.0.1。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
VENV = BACKEND / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NPM = "npm.cmd" if os.name == "nt" else "npm"
HOST, PORT = "127.0.0.1", int(os.environ.get("SIGNALDESK_PORT", "8000"))


def die(msg: str, code: int = 1):
    print(f"[錯誤] {msg}", file=sys.stderr)
    sys.exit(code)


def check() -> None:
    if sys.version_info < (3, 11):
        die(f"需要 Python 3.11 以上，目前 {sys.version.split()[0]}。請從 https://www.python.org 安裝較新版本。")
    print(f"Python {sys.version.split()[0]} OK")
    node = shutil.which("node")
    if not node:
        die("找不到 Node.js。請安裝 Node 20.19+ 或 22.12+（Vite 8 的需求）：https://nodejs.org")
    v = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    m = re.match(r"v(\d+)\.(\d+)", v)
    major, minor = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if not ((major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major >= 23):
        die(f"Node {v} 太舊；需要 20.19+ 或 22.12+。")
    print(f"Node {v} OK")
    if not shutil.which(NPM):
        die("找不到 npm。")


def run(cmd, cwd=None, env=None, check_rc=True):
    print("$", " ".join(map(str, cmd)))
    r = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {}), "PYTHONUTF8": "1"})
    if check_rc and r.returncode != 0:
        die(f"命令失敗（exit {r.returncode}）")
    return r.returncode


def setup() -> None:
    check()
    if not PY.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    run([str(PY), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.lock.txt")])
    run([NPM, "ci"], cwd=FRONTEND)
    run([NPM, "run", "build"], cwd=FRONTEND)
    if not (ROOT / ".env").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")
        print("已由 .env.example 建立 .env（不含任何金鑰）")
    print("\nsetup 完成。下一步：python scripts/launcher.py start")


def need_py():
    if not PY.exists():
        die("尚未 setup。請先執行：python scripts/launcher.py setup")


def serve(dev: bool) -> None:
    need_py()
    (ROOT / "data").mkdir(exist_ok=True)
    env = {"PYTHONUTF8": "1"}
    run([str(PY), "-m", "app.seed"], cwd=BACKEND, env=env)
    procs: list[subprocess.Popen] = []
    try:
        api = subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app_factory", "--factory", "--host", HOST, "--port", str(PORT)], cwd=BACKEND, env={**os.environ, **env})
        procs.append(api)
        time.sleep(1.0)
        worker = subprocess.Popen([str(PY), "-m", "app.worker"], cwd=BACKEND, env={**os.environ, **env})
        procs.append(worker)
        if dev:
            procs.append(subprocess.Popen([NPM, "run", "dev"], cwd=FRONTEND))
        print(f"\nSignalDesk Lab 已啟動： http://{HOST}:{PORT}   （dev 模式前端： http://{HOST}:5173）\nCtrl+C 停止（API 與 worker 一起關閉）\n")
        while True:
            for p in procs:
                if p.poll() is not None:
                    if p is worker and p.returncode != 0:
                        print("[警告] worker 結束（可能已有另一個 worker 在執行）；API 繼續運作。")
                        procs.remove(p)
                        break
                    die(f"子程序提前結束（exit {p.returncode}）")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止中…")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    rest = sys.argv[2:]
    if cmd == "check":
        check()
    elif cmd == "setup":
        setup()
    elif cmd == "start":
        serve(False)
    elif cmd == "dev":
        serve(True)
    elif cmd == "seed":
        need_py()
        run([str(PY), "-m", "app.seed"], cwd=BACKEND)
    elif cmd == "reset":
        need_py()
        run([str(PY), "-m", "app.seed", "--reset", *rest], cwd=BACKEND)
    elif cmd == "test":
        need_py()
        run([str(PY), "-m", "pytest", "tests", "-q"], cwd=BACKEND)
        run([NPM, "run", "build"], cwd=FRONTEND)
    elif cmd == "e2e":
        need_py()
        run([str(PY), "-m", "pytest", "e2e", "-q", "-p", "no:cacheprovider"], cwd=ROOT)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
