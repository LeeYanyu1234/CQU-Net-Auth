"""Configuration datamodel used by the runtime loop."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration parsed from CLI/environment."""

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
    mail_to: Tuple[str, ...]
    mail_cooldown: int
