"""Command-line parsing and environment-backed configuration."""

import argparse
import logging
import os
import sys

from cqu_net_auth.config import Config
from cqu_net_auth.logging_setup import set_logger


def get_env_int(name: str, default: int) -> int:
    """Read an integer from env; fall back to default when invalid."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_mail_recipients(raw_value: str) -> tuple[str, ...]:
    """Parse recipient list from comma/semicolon separated input."""
    normalized = raw_value.replace(";", ",")
    recipients = [item.strip() for item in normalized.split(",")]
    return tuple(item for item in recipients if item)


def parse_args() -> Config:
    """Build and validate runtime configuration from CLI + env vars."""
    logger = logging.getLogger()
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str,
                        default=os.getenv("ACCOUNT", ""))
    parser.add_argument("--password", type=str,
                        default=os.getenv("PASSWORD", ""))
    parser.add_argument(
        "--term_type",
        type=str,
        default=os.getenv("TERM_TYPE", "pc"),
        choices=["mobile", "pc"],
    )
    parser.add_argument(
        "--log_level",
        type=str,
        default=os.getenv("LOG_LEVEL", "info"),
        choices=["debug", "info"],
    )
    parser.add_argument("--interval", type=int,
                        default=get_env_int("INTERVAL", 5))
    parser.add_argument(
        "--check_with_http",
        action="store_true",
        default=os.getenv("CHECK_WITH_HTTP", "False").lower() in (
            "true", "yes", "1", "t", "y"),
    )
    parser.add_argument("--http_url", type=str,
                        default=os.getenv("HTTP_URL", "https://www.baidu.com"))
    parser.add_argument("--interface", type=str,
                        default=os.getenv("INTERFACE", ""))
    parser.add_argument("--file_path", type=str,
                        default=os.getenv("FILE_PATH", ""))

    parser.add_argument(
        "--mail_enable",
        action="store_true",
        default=os.getenv("MAIL_ENABLE", "False").lower() in (
            "true", "yes", "1", "t", "y"),
    )
    parser.add_argument("--mail_sender", type=str,
                        default=os.getenv("MAIL_SENDER", ""))
    parser.add_argument("--mail_auth_code", type=str,
                        default=os.getenv("MAIL_AUTH_CODE", ""))
    parser.add_argument("--mail_to", type=str,
                        default=os.getenv("MAIL_TO", ""))
    parser.add_argument("--mail_cooldown", type=int,
                        default=get_env_int("MAIL_COOLDOWN", 300))

    args = parser.parse_args()
    set_logger(args.log_level)
    logger = logging.getLogger()

    if not args.account or not args.password:
        logger.error("missing campus network account or password")
        sys.exit(-1)

    if args.term_type not in ["mobile", "pc"]:
        logger.error("term_type must be mobile or pc")
        sys.exit(-1)

    if os.name == "nt" and args.interface:
        logger.error("Windows does not support interface binding")
        sys.exit(-1)

    mail_recipients = parse_mail_recipients(args.mail_to)
    if args.mail_enable and (not args.mail_sender or not args.mail_auth_code or not mail_recipients):
        logger.error(
            "mail_enable is set, but mail_sender/mail_auth_code/mail_to is missing")
        sys.exit(-1)

    return Config(
        account=args.account,
        password=args.password,
        term_type=args.term_type,
        interval=args.interval,
        check_with_http=args.check_with_http,
        http_url=args.http_url,
        interface=args.interface,
        file_path=args.file_path,
        mail_enable=args.mail_enable,
        mail_sender=args.mail_sender,
        mail_auth_code=args.mail_auth_code,
        mail_to=mail_recipients,
        mail_cooldown=args.mail_cooldown,
    )
