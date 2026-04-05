from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    account: str
    password: str
    term_type: str
    interval: int
    check_with_http: bool
    http_url: str
    interface: str
    file_path: str
    mail_enable: bool
    mail_sender: str
    mail_auth_code: str
    mail_to: str
    mail_cooldown: int
