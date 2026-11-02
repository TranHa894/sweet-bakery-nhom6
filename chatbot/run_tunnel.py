"""Tự chạy web khi cần và tạo link Internet /website/."""

import argparse
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import socket
import subprocess
import sys
import time
from threading import Thread
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
QUICK_URL = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com(?=[/\s|"]|$)')


def find_cloudflared():
    for name in ("cloudflared-windows-amd64.exe", "cloudflared.exe"):
        binary = PROJECT_ROOT / "runtime" / name
        if binary.is_file():
            return str(binary)
    return shutil.which("cloudflared")


def public_website_url(line):
    match = QUICK_URL.search(line)
    if match and match.group(0) != "https://api.trycloudflare.com":
        return match.group(0) + "/website/"
    return None


def local_web_ready(port):
    """Chỉ GET kiểm tra; không tạo hội thoại hoặc gọi Qwen."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
            health = json.loads(response.read(8192))
        if not isinstance(health, dict) or health.get("status") != "ok" or "chat_mode" not in health:
            return False
        with urlopen(f"http://127.0.0.1:{port}/website/", timeout=3) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def wait_for_web(process, port, timeout=30):
    """Chờ web con sẵn sàng; không cần chờ Qwen nạp xong."""
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        if local_web_ready(port):
            return process.poll() is None
        time.sleep(0.2)
    return False


def stop_process(process, label):
    """Chỉ dừng tiến trình do lần chạy này tạo, không dừng web chạy riêng/Ollama."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired) as error:
        print("Chưa dừng được " + label + ": " + str(error), flush=True)


def read_output(process, lines):
    # Đọc pipe ở thread để Ctrl+C trên Windows không bị kẹt chờ dòng log.
    try:
        with process.stdout:
            for line in process.stdout:
                lines.put(line.strip())
    finally:
        lines.put(None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tự chạy web khi cần và tạo link Cloudflare.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--chat-mode", choices=["ollama", "rule"], default="ollama",
                        help="Chế độ cho web tự khởi động; web chạy sẵn giữ cấu hình cũ.")
    parser.add_argument("--prewarm", action=argparse.BooleanOptionalAction, default=True,
                        help="Nạp trước model như run_web.py; dùng --no-prewarm để tắt.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port phải từ 1 đến 65535.")
    binary = find_cloudflared()
    if binary is None:
        parser.exit(1, "Chưa tìm thấy cloudflared. Đặt cloudflared-windows-amd64.exe trong chatbot/runtime.\n")
    process, reader, web = None, None, None
    try:
        if local_web_ready(args.port):
            print("Dùng web đang chạy; khi dừng tunnel sẽ giữ web này.", flush=True)
        else:
            # Không chiếm cổng hoặc dừng một ứng dụng đang chạy trên máy.
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("127.0.0.1", args.port))
            except OSError:
                print(f"Cổng {args.port} đang bận hoặc không dùng được. "
                      "Thử --port 8001; không dừng ứng dụng đang dùng cổng.", flush=True)
                return 1
            command = [sys.executable, "-B", "-u", "-X", "utf8",
                       str(PROJECT_ROOT / "run_web.py"), "--port", str(args.port),
                       "--chat-mode", args.chat_mode]
            if not args.prewarm:
                command.append("--no-prewarm")
            print("Đang tự khởi động run_web.py...", flush=True)
            # Dùng chung Terminal để thấy log web; nhóm riêng không nhận Ctrl+C hai lần.
            web = subprocess.Popen(
                command, cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            if not wait_for_web(web, args.port):
                print("Web chưa khởi động thành công trong 30 giây. "
                      "Xem lỗi ở trên; chưa tạo tunnel.", flush=True)
                return 1
        process = subprocess.Popen(
            [binary, "tunnel", "--url", f"http://127.0.0.1:{args.port}"],
            cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        lines = Queue()
        reader = Thread(target=read_output, args=(process, lines), daemon=True)
        reader.start()
        print("Đang tạo link Internet... Dừng tunnel bằng Ctrl+C.", flush=True)
        website, connected, announced = None, False, False
        while True:
            if web is not None and web.poll() is not None:
                print("Web tự khởi động đã dừng; đang đóng tunnel.", flush=True)
                return 1
            try:
                line = lines.get(timeout=0.2)
            except Empty:
                continue
            if line is None:
                break
            website = public_website_url(line) or website
            connected = connected or "Registered tunnel connection" in line
            if website and connected and not announced:
                print("\n" + "=" * 64 + "\nLINK MỞ TRÊN ĐIỆN THOẠI / MÁY KHÁC:\n"
                      + website + "\n" + "=" * 64 + "\n", flush=True)
                announced = True
            if " ERR " in " " + line + " " or " WRN " in " " + line + " ":
                print("Cloudflare: " + line, flush=True)
        print("Tunnel đã dừng. Chạy lại run_tunnel.py để tạo link mới.", flush=True)
        return 1
    except KeyboardInterrupt:
        message = "Đang dừng tunnel và web tự khởi động." if web is not None else "Đang dừng tunnel; web chạy riêng vẫn được giữ."
        print("\n" + message, flush=True)
        return 0
    except OSError as error:
        print("Không khởi động được web/tunnel: " + str(error), flush=True)
        return 1
    finally:
        stop_process(process, "tunnel")
        stop_process(web, "web tự khởi động")
        if reader is not None:
            reader.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
