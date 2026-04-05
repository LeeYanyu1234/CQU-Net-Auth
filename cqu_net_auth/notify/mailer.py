"""SMTP helpers for outbound notification email."""

import smtplib
from collections.abc import Sequence
from email.header import Header
from email.mime.text import MIMEText


def send_qq_mail(sender, auth_code, to_addrs: Sequence[str], subject, body, smtp_host="smtp.qq.com", smtp_port=465, timeout=10):
    """Send a plain-text email through QQ SMTP over SSL."""
    recipients = [addr.strip() for addr in to_addrs if addr and addr.strip()]
    if not recipients:
        raise ValueError("no recipient email address provided")

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = Header(subject, "utf-8")

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as server:
        server.login(sender, auth_code)
        server.sendmail(sender, recipients, msg.as_string())
