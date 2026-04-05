import smtplib
from email.header import Header
from email.mime.text import MIMEText


def send_qq_mail(sender, auth_code, to_addr, subject, body, smtp_host="smtp.qq.com", smtp_port=465, timeout=10):
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = Header(subject, "utf-8")

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as server:
        server.login(sender, auth_code)
        server.sendmail(sender, [to_addr], msg.as_string())
