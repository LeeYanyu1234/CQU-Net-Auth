import logging
import smtplib
import time

from cqu_net_auth.exceptions import NotificationError
from cqu_net_auth.notify.mailer import send_qq_mail


class Notifier:
    def __init__(self, enabled: bool, sender: str, auth_code: str, to_addr: str, cooldown: int):
        self.enabled = enabled
        self.sender = sender
        self.auth_code = auth_code
        self.to_addr = to_addr
        self.cooldown = cooldown
        self.last_sent_at = 0.0
        self.logger = logging.getLogger()

    def notify_portal_ip_changed(self, account: str, old_ip: str, new_ip: str) -> bool:
        if not self.enabled:
            return False

        now = time.time()
        if now - self.last_sent_at < self.cooldown:
            self.logger.debug("notify.skipped_cooldown: old=%s new=%s", old_ip, new_ip)
            return False

        subject = "CQU Portal IP Changed"
        body = (
            f"account: {account}\n"
            f"old_ip: {old_ip}\n"
            f"new_ip: {new_ip}\n"
            f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )

        try:
            send_qq_mail(self.sender, self.auth_code, self.to_addr, subject, body)
            self.last_sent_at = now
            self.logger.info("notify.mail_sent: %s -> %s", old_ip, new_ip)
            return True
        except (smtplib.SMTPException, OSError) as exc:
            err = NotificationError("failed to send notification email")
            self.logger.warning("notify.send_failed: %s", err)
            self.logger.debug("notify.send_failed.detail: %s", exc)
            return False
