"""
notebooklm.py — NotebookLM AP 端對端自動化入口
執行方式：python notebooklm.py [--test] [--serve] [--publish path/to/data.json]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── 常數設定 ──────────────────────────────────────────────────────────────────

AP_HOST        = "http://127.0.0.1:8085"
PUBLISH_ENDPOINT = f"{AP_HOST}/api/v1/publish_artifact"
OUTPUT_DIR     = Path("notebooklm_ap/outputs")
SERVER_MODULE  = "notebooklm_ap.server:app"
SERVER_LOG     = Path("notebooklm_ap/server.log")

# Mock 測試資料（對應 schema.py 中的必填欄位）
MOCK_PAYLOAD = {
    "project_name": "COW_Training — Baseline Run",
    "objective":    "驗證 NotebookLM AP 資料流是否正常運作",
    "status":       "success",
    "key_metrics": {
        "accuracy":  0.9231,
        "loss":      0.0412,
        "epochs":    50,
        "duration":  "12m 34s"
    },
    "conclusion":   "Baseline 訓練順利完成，準確率達 92.31%，損失收斂穩定，可進入下一輪超參數調優。"
}


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    """帶時間戳的彩色 log 輸出。"""
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERR": "\033[91m"}
    reset  = "\033[0m"
    prefix = colors.get(level, "") + f"[{level}]" + reset
    print(f"{prefix} {msg}")


def ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"輸出目錄確認：{OUTPUT_DIR.resolve()}")


def wait_for_server(timeout: int = 15) -> bool:
    """輪詢直到 AP 伺服器回應 200，或超時。"""
    try:
        import requests
    except ImportError:
        log("找不到 requests 套件，請先執行 pip install requests", "ERR")
        return False

    log("等待 AP 伺服器就緒…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{AP_HOST}/health", timeout=1)
            if r.status_code == 200:
                log("AP 伺服器已就緒", "OK")
                return True
        except Exception:
            pass
        time.sleep(1)
    log(f"伺服器在 {timeout}s 內未回應", "ERR")
    return False


# ── 核心功能 ──────────────────────────────────────────────────────────────────

def start_server() -> subprocess.Popen | None:
    """
    在背景啟動 uvicorn AP 伺服器。
    若伺服器已在執行（port 佔用），跳過並繼續。
    """
    import requests
    try:
        r = requests.get(f"{AP_HOST}/health", timeout=1)
        if r.status_code == 200:
            log("偵測到 AP 伺服器已在執行，跳過啟動", "WARN")
            return None
    except Exception:
        pass

    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log(f"啟動 AP 伺服器（log → {SERVER_LOG}）")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", SERVER_MODULE, "--reload",
         "--host", "127.0.0.1", "--port", "8085"],
        stdout=open(SERVER_LOG, "w"),
        stderr=subprocess.STDOUT
    )
    return proc


def publish(payload: dict) -> bool:
    """
    將 payload 以 POST 送至 AP 伺服器，回傳是否成功。
    """
    try:
        import requests
    except ImportError:
        log("找不到 requests 套件，請先執行 pip install requests", "ERR")
        return False

    log(f"發送 artifact → {PUBLISH_ENDPOINT}")
    log(f"專案：{payload.get('project_name')}  |  狀態：{payload.get('status')}")

    try:
        r = requests.post(PUBLISH_ENDPOINT, json=payload, timeout=10)
    except requests.exceptions.ConnectionError:
        log("無法連線至 AP 伺服器，請確認伺服器正在執行", "ERR")
        return False

    if r.status_code == 200:
        resp = r.json()
        output_file = resp.get("output_file", "（未知路徑）")
        log(f"發布成功！輸出文件：{output_file}", "OK")
        return True
    elif r.status_code == 422:
        log("JSON Schema 驗證失敗（HTTP 422）", "ERR")
        log(f"詳細錯誤：{r.text}", "ERR")
        return False
    else:
        log(f"伺服器回傳非預期狀態碼：{r.status_code}", "ERR")
        log(r.text, "ERR")
        return False


def verify_output():
    """列出 outputs 目錄中最新生成的 Markdown 文件，並預覽前 20 行。"""
    md_files = sorted(OUTPUT_DIR.glob("*.md"), key=os.path.getmtime, reverse=True)
    if not md_files:
        log(f"outputs 目錄中尚無 Markdown 文件：{OUTPUT_DIR}", "WARN")
        return

    latest = md_files[0]
    log(f"最新輸出文件：{latest.name}", "OK")
    print("\n" + "─" * 60)
    lines = latest.read_text(encoding="utf-8").splitlines()
    for line in lines[:20]:
        print(line)
    if len(lines) > 20:
        print(f"… （共 {len(lines)} 行，僅預覽前 20 行）")
    print("─" * 60 + "\n")


# ── 流程組合 ──────────────────────────────────────────────────────────────────

def run_e2e(payload: dict):
    """
    完整端對端流程：
    1. 確認輸出目錄
    2. 啟動（或偵測）AP 伺服器
    3. 等待伺服器就緒
    4. 發布 artifact
    5. 驗證輸出文件
    """
    ensure_output_dir()
    proc = start_server()

    try:
        if not wait_for_server():
            sys.exit(1)

        success = publish(payload)
        if success:
            verify_output()
        else:
            sys.exit(1)

    finally:
        # 若本次腳本啟動了伺服器，流程結束後關閉
        if proc is not None:
            log("關閉本次啟動的 AP 伺服器")
            proc.terminate()
            proc.wait()


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NotebookLM AP 端對端自動化腳本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例：
  python notebooklm.py --test                     # 用 Mock 資料跑完整流程
  python notebooklm.py --publish result.json       # 發布真實訓練結果
  python notebooklm.py --serve                     # 僅啟動 AP 伺服器（前景）
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--test",
        action="store_true",
        help="使用內建 Mock Payload 執行完整端對端流程測試"
    )
    group.add_argument(
        "--publish",
        metavar="JSON_FILE",
        help="讀取指定 JSON 檔案並發布至 AP 伺服器"
    )
    group.add_argument(
        "--serve",
        action="store_true",
        help="在前景啟動 AP 伺服器（適合開發時使用）"
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  NotebookLM AP — 自動化腳本")
    print("═" * 60 + "\n")

    # ── --test：Mock 資料端對端測試 ──
    if args.test:
        log("模式：端對端測試（Mock Payload）")
        run_e2e(MOCK_PAYLOAD)

    # ── --publish：讀取真實 JSON 並發布 ──
    elif args.publish:
        json_path = Path(args.publish)
        if not json_path.exists():
            log(f"找不到指定的 JSON 檔案：{json_path}", "ERR")
            sys.exit(1)
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log(f"JSON 解析失敗：{e}", "ERR")
            sys.exit(1)
        log(f"模式：發布真實資料（{json_path.name}）")
        run_e2e(payload)

    # ── --serve：前景伺服器（開發模式）──
    elif args.serve:
        log("模式：前景啟動 AP 伺服器（Ctrl+C 停止）")
        ensure_output_dir()
        os.execlp(
            sys.executable,
            sys.executable, "-m", "uvicorn", SERVER_MODULE,
            "--reload", "--host", "127.0.0.1", "--port", "8085"
        )


if __name__ == "__main__":
    main()
