"""Send a real test email with mail settings from the login batch file."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqu_net_auth.notify.mailer import send_qq_mail

from module_tests.common import exit_fail, exit_ok, print_config_summary, require_config


def main() -> None:
    config = require_config("mail_sender", "mail_auth_code", "mail_to")
    print_config_summary(config)

    recipients = tuple(
        item.strip()
        for item in str(config["mail_to"]).replace(";", ",").split(",")
        if item.strip()
    )
    if not recipients:
        exit_fail("mail_to 没有有效收件人")

    subject = "CQU-Net-Auth 邮件发送模块测试"
    body = (
        "这是一封来自 CQU-Net-Auth module_tests/send_mail.py 的真实测试邮件。\n"
        "如果你收到这封邮件，说明邮件发送模块可以正常工作。"
    )

    try:
        send_qq_mail(
            str(config["mail_sender"]),
            str(config["mail_auth_code"]),
            recipients,
            subject,
            body,
        )
    except Exception as exc:
        exit_fail(f"邮件发送失败: {exc}")

    exit_ok("测试邮件已发送，请检查收件邮箱")


if __name__ == "__main__":
    main()
