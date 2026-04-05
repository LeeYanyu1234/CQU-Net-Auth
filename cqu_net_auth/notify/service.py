"""Notification service with cooldown-based mail sending."""

import logging
import smtplib
import time
import socket

from cqu_net_auth.exceptions import NotificationError
from cqu_net_auth.notify.mailer import send_qq_mail
from cqu_net_auth.storage.ip_history import build_proxy_env_template


class Notifier:
    """Send portal IP-change notifications with rate limiting."""

    def __init__(self, enabled: bool, sender: str, auth_code: str, to_addr: str, cooldown: int):
        self.enabled = enabled
        self.sender = sender
        self.auth_code = auth_code
        self.to_addr = to_addr
        self.cooldown = cooldown
        self.last_sent_at = 0.0
        self.logger = logging.getLogger()

    def notify_portal_ip_changed(self, account: str, old_ip: str, new_ip: str) -> bool:
        """Send one notification when portal IP changes and cooldown allows it."""
        if not self.enabled:
            return False

        now = time.time()
        if now - self.last_sent_at < self.cooldown:
            self.logger.debug(
                "notify.skipped_cooldown: old=%s new=%s", old_ip, new_ip)
            return False

        subject = "CQU Portal IP Changed"
        host_name = socket.gethostname()
        proxy_template = build_proxy_env_template(new_ip)
        body = (
            f"account: {account}\n"
            f"host: {host_name}\n"
            f"old_ip: {old_ip}\n"
            f"new_ip: {new_ip}\n"
            f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "proxy_env_template:\n"
            f"{proxy_template}\n"
        )

        try:
            send_qq_mail(self.sender, self.auth_code,
                         self.to_addr, subject, body)
            self.last_sent_at = now
            next_send_at = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(now + self.cooldown)
            )
            self.logger.info("notify.mail_sent: %s -> %s", old_ip, new_ip)
            self.logger.info("notify.next_send_available_at: %s", next_send_at)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            err = NotificationError("failed to send notification email")
            self.logger.warning("notify.send_failed: %s", err)
            self.logger.debug("notify.send_failed.detail: %s", exc)
            return False

