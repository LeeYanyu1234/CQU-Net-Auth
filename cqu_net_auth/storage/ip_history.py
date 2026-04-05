"""Helpers for persisting recent IP observations."""

import logging
import os
import re
import socket
import time


def get_local_ipv4_primary():
    """Get primary outbound local IPv4 address, or None on failure."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("223.6.6.6", 53))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
        return None
    except OSError:
        return None


def build_proxy_env_template(ip: str, port: int = 7890) -> str:
    """Build shell proxy exports with the provided IP and port."""
    return (
        f"export http_proxy=http://{ip}:{port}\n"
        f"export https_proxy=http://{ip}:{port}\n"
        f"export all_proxy=socks5h://{ip}:{port}\n"
        "export no_proxy=localhost,127.0.0.1,::1"
    )


def record_ip_to_file(file_path: str, *, uid: str | None = None, portal_ip: str | None = None):
    """Prepend one IP record and keep only the latest 10 non-empty lines."""
    logger = logging.getLogger()
    if not file_path:
        return

    local_ip = get_local_ipv4_primary()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    new_line = f"{ts}\tuid={uid or ''}\tlocal_ip={local_ip or ''}\tportal_ip={portal_ip or ''}\n"

    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        old_lines: list[str] = []
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                old_lines = file.readlines()
        except FileNotFoundError:
            old_lines = []

        old_lines = [line for line in old_lines if line.strip()]
        merged = ([new_line] + old_lines)[:10]

        with open(file_path, "w", encoding="utf-8") as file:
            file.writelines(merged)

        logger.info("storage.ip_record_updated: %s", file_path)
    except OSError as exc:
        logger.warning("storage.ip_record_failed: %s", exc)


def read_last_portal_ip_from_file(file_path: str) -> str | None:
    """Read the newest portal_ip value from record file."""
    logger = logging.getLogger()
    if not file_path:
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                match = re.search(r"portal_ip=([^\s]+)", line)
                if match:
                    value = match.group(1).strip()
                    return value or None
        return None
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("storage.read_last_portal_ip_failed: %s", exc)
        return None
