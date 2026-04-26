"""Shared helpers for manual module verification scripts."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BAT = PROJECT_ROOT / "登录校园网脚本.bat"


def read_login_bat_args(bat_path: Path = DEFAULT_BAT) -> dict[str, str | bool]:
    """Extract CLI options from the existing Windows login batch file."""
    if not bat_path.exists():
        raise FileNotFoundError(f"login batch file not found: {bat_path}")

    content = bat_path.read_text(encoding="utf-8", errors="ignore")
    content = re.sub(r"\^\s*\r?\n", " ", content)

    match = re.search(r"python\s+\"%SCRIPT_DIR%login\.py\"(?P<args>.*?)(?:>>|$)", content, re.S)
    if not match:
        raise ValueError(f"cannot find python login.py command in {bat_path}")

    tokens = shlex.split(match.group("args"), posix=False)
    options: dict[str, str | bool] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            index += 1
            continue

        key = token[2:]
        next_index = index + 1
        if next_index >= len(tokens) or tokens[next_index].startswith("--"):
            options[key] = True
            index += 1
            continue

        options[key] = tokens[next_index].strip('"')
        index += 2

    return options


def require_config(*names: str) -> dict[str, str | bool]:
    config = read_login_bat_args()
    missing = [name for name in names if not config.get(name)]
    if missing:
        raise SystemExit("登录校园网脚本.bat 缺少参数: " + ", ".join(missing))
    return config


def print_config_summary(config: dict[str, str | bool]) -> None:
    print(f"配置来源: {DEFAULT_BAT}")
    print(f"校园网账号: {config.get('account', '')}")
    print(f"终端类型: {config.get('term_type', 'pc')}")

    http_url = config.get("http_url")
    if http_url:
        print(f"HTTP 检测地址: {http_url}")

    mail_sender = config.get("mail_sender")
    if mail_sender:
        print(f"发件邮箱: {mail_sender}")

    mail_to = config.get("mail_to")
    if mail_to:
        print(f"收件邮箱: {mail_to}")


def print_json(title: str, payload) -> None:
    print(title)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def exit_ok(message: str) -> None:
    print(f"\n成功: {message}")
    raise SystemExit(0)


def exit_fail(message: str) -> None:
    print(f"\n失败: {message}", file=sys.stderr)
    raise SystemExit(1)
