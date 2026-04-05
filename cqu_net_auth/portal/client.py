"""Portal API client and drcom response parsing."""

import json
import logging
import re
import socket
import urllib.error
import urllib.request

from cqu_net_auth.exceptions import PortalClientError
from cqu_net_auth.net.opener import create_and_install_opener

MOBILE_AUTH_URL = "http://login.cqu.edu.cn:801/eportal/portal/login?callback=dr1005&login_method=1&user_account=%2C1%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&term_ua=Mozilla%2F5.0%20(Linux%3B%20Android%208.0.0%3B%20SM-G955U%20Build%2FR16NW)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F144.0.0.0%20Mobile%20Safari%2F537.36%20Edg%2F144.0.0.0&term_type=2&jsVersion=4.2.2&terminal_type=2&lang=zh-cn&v=1176&lang=zh-cn"
PC_AUTH_URL = "http://login.cqu.edu.cn:801/eportal/portal/login?callback=dr1004&login_method=1&user_account=%2C0%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&term_ua=Mozilla%2F5.0%20(Windows%20NT%2010.0%3B%20Win64%3B%20x64)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F144.0.0.0%20Safari%2F537.36%20Edg%2F144.0.0.0&term_type=1&jsVersion=4.2.2&terminal_type=1&lang=zh-cn&v=1176&lang=zh-cn"
AUTH_INFO_URL = "http://login.cqu.edu.cn/drcom/chkstatus?callback=dr1002&jsVersion=4.X&v=5505&lang=zh"
UNBIND_URL = "http://login.cqu.edu.cn:801/eportal/portal/mac/unbind?callback=dr1002&user_account={account}&wlan_user_mac=000000000000&wlan_user_ip={int_ip}&jsVersion=4.2.2&v=6024&lang=zh"
LOGOUT_URL = "http://login.cqu.edu.cn:801/eportal/portal/logout"


def drcom_message_parser(drcom_message):
    """Parse drXXXX(...) wrapper into dict; return None if malformed."""
    if isinstance(drcom_message, bytes):
        try:
            drcom_message = drcom_message.decode("GB2312")
        except UnicodeDecodeError:
            return None

    match = re.search(r"dr\d+\((.*?)\);?", drcom_message)
    if not match:
        return None

    json_str = match.group(1)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


class PortalClient:
    """Lightweight client for CQU portal auth/status/logout endpoints."""

    def __init__(self, timeout=3, interface=None):
        self.timeout = timeout
        self.interface = interface
        self.logger = logging.getLogger()

    def get_auth_info(self):
        """Return current portal auth info, or None when unavailable."""
        create_and_install_opener(interface=self.interface)
        req = urllib.request.Request(AUTH_INFO_URL)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    return None
                return drcom_message_parser(response.read().decode("GB2312", errors="ignore"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.debug("portal.get_auth_info_failed: %s", exc)
            return None

    def login(self, account: str, password: str, term_type: str, ip: str):
        """Attempt portal login and return (result, message)."""
        create_and_install_opener(interface=self.interface)
        auth_url = MOBILE_AUTH_URL if term_type == "mobile" else PC_AUTH_URL
        req = urllib.request.Request(auth_url.format(
            account=account, password=password, ip=ip))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    return 0, "auth server error"
                result = drcom_message_parser(
                    response.read().decode("utf-8", errors="ignore"))
                if result:
                    return result.get("result", 0), result.get("msg", "unknown error")
                return 0, "unknown error"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.debug("portal.login_failed: %s", exc)
            return 0, f"network error: {exc}"

    def old_logout(self):
        """Fallback logout endpoint used when unbind says MAC not found."""
        create_and_install_opener(interface=self.interface)
        req = urllib.request.Request(LOGOUT_URL)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    return False
                body = response.read().decode("utf-8", errors="ignore")
                return ("Radius" in body and "æˆåŠŸ" in body) or ("success" in body.lower())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.debug("portal.old_logout_failed: %s", exc)
            return False

    def logout(self, account, ip):
        """Logout by unbinding MAC; fallback to old logout endpoint."""
        create_and_install_opener(interface=self.interface)
        try:
            int_ip = int.from_bytes(socket.inet_aton(ip), "big")
        except OSError as exc:
            raise PortalClientError(f"invalid ip for logout: {ip}") from exc

        url = UNBIND_URL.format(account=account, int_ip=int_ip)
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    return False
                result = drcom_message_parser(
                    response.read().decode("utf-8", errors="ignore"))
                if not result:
                    return False

                msg = result.get("msg", "")
                if ("MAC" in msg and "æˆåŠŸ" in msg) or ("success" in msg.lower()):
                    return True
                if ("mac" in msg.lower() and "ä¸å­˜åœ¨" in msg) or ("not" in msg.lower() and "exist" in msg.lower()):
                    return self.old_logout()
                return False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.debug("portal.logout_failed: %s", exc)
            return False
