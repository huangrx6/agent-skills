#!/usr/bin/env python3
"""启动一个或多个本地服务，等待端口与可选 HTTP 路径就绪后运行验收命令，结束后安全回收。

只依赖 Python 3.10+ 标准库，跨平台可用。
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def wait_for_http(host: str, port: int, path: str, timeout: float) -> bool:
    normalized = path if path.startswith("/") else f"/{path}"
    url = f"http://{host}:{port}{normalized}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status < 500:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True
        except OSError:
            pass
        time.sleep(0.15)
    return False


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="启动一个或多个本地服务并等待就绪后执行命令，结束时自动停止服务"
    )
    parser.add_argument(
        "--server",
        action="append",
        dest="servers",
        required=True,
        help="服务启动命令（可重复传入）",
    )
    parser.add_argument(
        "--port",
        action="append",
        dest="ports",
        type=int,
        required=True,
        help="对应服务监听的端口号（数量需与 --server 一致）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="端口探测主机地址（默认 127.0.0.1）",
    )
    parser.add_argument(
        "--path",
        default="",
        help="可选 HTTP 就绪检查路径（如 / 或 /health），留空则仅探测 TCP 端口",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="每个服务等待就绪的超时秒数（默认 30）",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="服务就绪后执行的验收命令（建议放在 -- 之后）",
    )
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("错误：未指定要在服务就绪后运行的命令（请在 -- 后填写）", file=sys.stderr)
        return 2
    if len(args.servers) != len(args.ports):
        print("错误：--server 与 --port 的数量必须一一对应", file=sys.stderr)
        return 2

    processes: list[subprocess.Popen] = []
    try:
        for index, (cmd, port) in enumerate(zip(args.servers, args.ports), start=1):
            print(f"[with_server] 启动服务 {index}/{len(args.servers)}: {cmd}")
            popen_kwargs: dict = {
                "shell": True,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
            }
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(cmd, **popen_kwargs)
            processes.append(proc)

            if not wait_for_port(args.host, port, args.timeout):
                if proc.poll() is not None:
                    stderr_text = (proc.stderr.read() if proc.stderr else b"").decode(
                        "utf-8", errors="replace"
                    ).strip()
                    raise RuntimeError(
                        f"服务 {index} 提前退出（退出码 {proc.returncode}）：{stderr_text}"
                    )
                raise RuntimeError(f"等待 {args.host}:{port} 就绪超时（{args.timeout}s）")

            if args.path and not wait_for_http(args.host, port, args.path, args.timeout):
                raise RuntimeError(
                    f"等待 http://{args.host}:{port}{args.path} 返回非 5xx 超时（{args.timeout}s）"
                )
            print(f"[with_server] 服务 {index} 已就绪（{args.host}:{port}）")

        print(f"[with_server] 执行命令: {' '.join(command)}")
        result = subprocess.run(command, check=False)
        return result.returncode
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    finally:
        for index, proc in enumerate(reversed(processes), start=1):
            stop_process(proc)
            print(f"[with_server] 已停止服务 {len(processes) - index + 1}")


if __name__ == "__main__":
    sys.exit(main())
