import os
import re
import sys
import time
import json
import signal
import socket
import logging
import urllib.request
import argparse
import http.client
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# 避免读取系统代理（如 Clash 残留 127.0.0.1 代理）导致认证请求失败
urllib.request.getproxies = lambda: {}

logger = None
MOBILE_AUTH_URL = "http://login.cqu.edu.cn:801/eportal/portal/login?callback=dr1005&login_method=1&user_account=%2C1%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&term_ua=Mozilla%2F5.0%20(Linux%3B%20Android%208.0.0%3B%20SM-G955U%20Build%2FR16NW)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F144.0.0.0%20Mobile%20Safari%2F537.36%20Edg%2F144.0.0.0&term_type=2&jsVersion=4.2.2&terminal_type=2&lang=zh-cn&v=1176&lang=zh-cn"
PC_AUTH_URL = "http://login.cqu.edu.cn:801/eportal/portal/login?callback=dr1004&login_method=1&user_account=%2C0%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&term_ua=Mozilla%2F5.0%20(Windows%20NT%2010.0%3B%20Win64%3B%20x64)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F144.0.0.0%20Safari%2F537.36%20Edg%2F144.0.0.0&term_type=1&jsVersion=4.2.2&terminal_type=1&lang=zh-cn&v=1176&lang=zh-cn"
AUTH_INFO_URL = "http://login.cqu.edu.cn/drcom/chkstatus?callback=dr1002&jsVersion=4.X&v=5505&lang=zh"
UNBIND_URL = "http://login.cqu.edu.cn:801/eportal/portal/mac/unbind?callback=dr1002&user_account={account}&wlan_user_mac=000000000000&wlan_user_ip={int_ip}&jsVersion=4.2.2&v=6024&lang=zh"
LOGOUT_URL = "http://login.cqu.edu.cn:801/eportal/portal/logout"


class IfaceHTTPConnection(http.client.HTTPConnection):
    """使用 setsockopt 的 SO_BINDTODEVICE 选项限制从指定的网络接口建立连接"""

    def __init__(
        self, host, port=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None, blocksize=8192, source_interface=None
    ):
        super().__init__(
            host, port, timeout=timeout,
            source_address=source_address, blocksize=blocksize
        )
        self.source_interface: str = source_interface
        self._create_connection = self.create_connection

    # this function is copied from socket.py
    # since we need to alter its behavior
    def create_connection(
        self, address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None, *, all_errors=False
    ):

        host, port = address
        exceptions = []
        for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(timeout)
                if self.source_interface:
                    # 使用 SO_BINDTODEVICE 选项绑定到指定的网络接口
                    sock.setsockopt(
                        socket.SOL_SOCKET, socket.SO_BINDTODEVICE,
                        (self.source_interface+"\0").encode('utf-8')
                    )
                elif source_address:
                    sock.bind(source_address)
                sock.connect(sa)
                # Break explicitly a reference cycle
                exceptions.clear()
                return sock

            except OSError as exc:
                if not all_errors:
                    exceptions.clear()  # raise only the last error
                exceptions.append(exc)
                if sock is not None:
                    sock.close()

        if len(exceptions):
            try:
                if not all_errors:
                    raise exceptions[0]
                raise ExceptionGroup("create_connection failed", exceptions)
            finally:
                # Break explicitly a reference cycle
                exceptions.clear()
        else:
            raise OSError("getaddrinfo returns an empty list")


class SourceInterfaceHandler(urllib.request.HTTPHandler):
    """自定义HTTP处理器，用于设置请求的源接口"""

    def __init__(self, source_interface=None):
        self.source_interface = source_interface
        super().__init__()

    def http_open(self, req):
        return self.do_open(IfaceHTTPConnection, req, source_interface=self.source_interface)


class SourceAddressHandler(urllib.request.HTTPHandler):
    """自定义HTTP处理器，用于设置请求的源地址"""

    def __init__(self, source_address=None):
        self.source_address = source_address
        super().__init__()

    def http_open(self, req):
        return self.do_open(http.client.HTTPConnection, req, source_address=self.source_address)


def get_interface_ip(interface):
    """使用fcntl获取指定网络接口的IPv4地址"""
    import fcntl
    import struct
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', bytes(interface[:15], 'utf-8'))
        )[20:24])
    except Exception as e:
        logger.debug(f"获取接口 {interface} 的IP地址失败: {e}")
        return None


def create_and_install_opener(interface=None, source_address=None):
    """创建并安装自定义opener以设置源地址"""
    if interface:
        opener = urllib.request.build_opener(
            SourceInterfaceHandler(source_interface=interface))
    elif source_address:
        opener = urllib.request.build_opener(
            SourceAddressHandler((source_address, 0)))
    # 未指定 interface 和 address 时使用默认的 opener，不需要额外操作
    else:
        return

    urllib.request.install_opener(opener)


def is_internet_connected(host="223.6.6.6", port=53, timeout=3, interface=None):
    """通过 socket 检查是否连接到互联网"""
    # 动态获取接口IP
    interface_ip = None
    if interface:
        interface_ip = get_interface_ip(interface)
        if not interface_ip:
            logger.debug(f"无法获取接口 {interface} 的IP地址，将使用系统默认接口")

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if interface_ip:
            conn.bind((interface_ip, 0))  # 绑定到指定接口
        conn.settimeout(timeout)
        conn.connect((host, port))
        conn.close()
        return True
    except Exception as e:
        logger.debug(f"Socket连接失败: {e}")
        return False


def is_http_connected(url="https://www.baidu.com", timeout=3, interface=None):
    """通过 http 检查是否连接到互联网"""
    create_and_install_opener(interface=interface)
    req = urllib.request.Request(url, method='HEAD')
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
        if response.getcode() == 200:
            return True
    except Exception as e:
        logger.debug(f"HTTP连接失败: {e}")
        return False


# def is_http_connected(url="https://www.baidu.com", timeout=3, interface=None):
#     """通过 http 检查是否连接到互联网"""
#     create_and_install_opener(interface=interface)
#     req = urllib.request.Request(url, method="HEAD")
#     try:
#         with urllib.request.urlopen(req, timeout=timeout) as response:
#             # 打印/记录 response 关键信息
#             logger.debug(f"HTTP response 对象: {response!r}")
#             logger.debug(f"HTTP status: {getattr(response, 'status', None)}")
#             logger.debug(f"HTTP code(getcode): {response.getcode()}")
#             logger.debug(f"HTTP final_url(geturl): {response.geturl()}")
#             logger.debug(f"HTTP headers:\n{response.headers}")

#             return response.getcode() == 200
#     except Exception as e:
#         logger.debug(f"HTTP连接失败: {e}")
#         return False


def check_internet(method="http", interface=None, **kwargs):
    """检查互联网连接状态"""
    if method == "socket":
        return is_internet_connected(interface=interface, **kwargs)
    elif method == "http":
        return is_http_connected(interface=interface, **kwargs)
    else:
        raise ValueError("method must be 'socket' or 'http'")


def get_local_ipv4_primary():
    """获取本机当前主要IPv4（默认出口），失败返回 None"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.6.6.6", 53))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
        return None
    except Exception:
        return None


def record_ip_to_file(file_path: str, *, uid: str | None = None, portal_ip: str | None = None):
    """记录一次IP到本地文件：
    - 最多保留10条
    - 新记录写在最前面
    - 超过10条的旧记录丢弃
    """
    if not file_path:
        return

    local_ip = get_local_ipv4_primary()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    new_line = f"{ts}\tuid={uid or ''}\tlocal_ip={local_ip or ''}\tportal_ip={portal_ip or ''}\n"

    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # 读取旧内容（最多保留9条旧的，加上新的=10）
        old_lines: list[str] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                old_lines = f.readlines()
        except FileNotFoundError:
            old_lines = []

        # 清理空行，避免文件里出现很多空记录
        old_lines = [ln for ln in old_lines if ln.strip()]

        # 新的放最前，截断到10条
        merged = [new_line] + old_lines
        merged = merged[:10]

        # 覆盖写回
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(merged)

        logger.info(f"已记录IP到文件(最多10条，最新在前): {file_path}")
    except Exception as e:
        logger.warning(f"记录IP失败: {e}")



def read_last_portal_ip_from_file(file_path: str) -> str | None:
    if not file_path:
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                match = re.search(r"portal_ip=([^\s]+)", line)
                if match:
                    value = match.group(1).strip()
                    return value or None
        return None
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"failed to read last portal_ip from file: {e}")
        return None

def drcom_message_parser(drcom_message):
    """将形如 `dr1004(...);` 或 `dr1002(...)` 的内容解析为 dict"""
    if isinstance(drcom_message, bytes):
        drcom_message = drcom_message.decode('GB2312')

    match = re.search(r'dr\d+\((.*?)\);?', drcom_message)
    if match:
        json_str = match.group(1)
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError:
            return None
    else:
        return None


def get_auth_info(timeout=3, interface=None):
    """获取 IP, ACCOUNT 等信息"""
    create_and_install_opener(interface=interface)
    req = urllib.request.Request(AUTH_INFO_URL)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.getcode() == 200:
                return drcom_message_parser(response.read().decode('GB2312'))
            return None
    except Exception as e:
        logger.debug(f"获取认证信息失败: {e}")
        return None


def login(account: str, password: str, term_type: str, ip: str, timeout=3, interface=None):
    """认证校园网"""
    create_and_install_opener(interface=interface)
    auth_url = MOBILE_AUTH_URL if term_type == "mobile" else PC_AUTH_URL
    req = urllib.request.Request(auth_url.format(
        account=account, password=password, ip=ip))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.getcode() != 200:
                return 0, "认证服务器异常"
            result = drcom_message_parser(response.read().decode('utf-8'))
            if result:
                return result.get("result", 0), result.get("msg", "未知错误")
            return 0, "未知错误"
    except Exception as e:
        return 0, f"网络错误: {e}"


def old_logout(timeout=3, interface=None):
    """传统注销方式"""
    create_and_install_opener(interface=interface)
    req = urllib.request.Request(LOGOUT_URL)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.getcode() == 200 and "Radius注销成功！" in response.read().decode('utf-8'):
                return True
            return False
    except Exception:
        return False


def logout(account, ip, timeout=3, interface=None):
    """注销当前认证账户"""
    create_and_install_opener(interface=interface)
    int_ip = int.from_bytes(socket.inet_aton(ip), 'big')
    url = UNBIND_URL.format(account=account, int_ip=int_ip)
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.getcode() == 200:
                result = drcom_message_parser(response.read().decode('utf-8'))
                if result and "解绑终端MAC成功！" in result.get("msg", ""):
                    return True
                elif result and "mac不存在" in result.get("msg", ""):
                    return old_logout(timeout=timeout, interface=interface)
                return False
            return False
    except Exception:
        return False



def send_qq_mail(sender, auth_code, to_addr, subject, body, smtp_host="smtp.qq.com", smtp_port=465, timeout=10):
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = Header(subject, "utf-8")

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as server:
        server.login(sender, auth_code)
        server.sendmail(sender, [to_addr], msg.as_string())

def set_logger(log_level: str):
    global logger
    if log_level and log_level.lower() == "debug":
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)



def get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default

def parse_args():
    global logger
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str,
                        default=os.getenv("ACCOUNT", ""), help="校园网账户(学/工号)")
    parser.add_argument("--password", type=str,
                        default=os.getenv("PASSWORD", ""), help="校园网密码")
    parser.add_argument("--term_type", type=str, default=os.getenv(
        "TERM_TYPE", "pc"), choices=["mobile", "pc"], help="登录设备类型")
    parser.add_argument("--log_level", type=str, default=os.getenv(
        "LOG_LEVEL", "info"), choices=["debug", "info"], help="日志级别")
    parser.add_argument("--interval", type=int,
                        default=get_env_int("INTERVAL", 5), help="检查网络状态的间隔时间(秒)")
    parser.add_argument("--check_with_http", action='store_true', default=os.getenv("CHECK_WITH_HTTP",
                        "False").lower() in ('true', 'yes', '1', 't', 'y'), help="使用 HTTP 连接的的结果检查网络状态，默认为 False")
    parser.add_argument("--http_url", type=str, default=os.getenv("HTTP_URL",
                        "https://www.baidu.com"), help="使用 HTTP 检查网络状态时访问的 URL, 仅在 --check_with_http 为 true 时有效")
    parser.add_argument("--interface", type=str,
                        default=os.getenv("INTERFACE", ""), help="指定使用的网络接口名称，如eth0、wlan0等")
    parser.add_argument("--file_path", type=str,
                        default=os.getenv("FILE_PATH", ""), help="记录IP到本地文件（可选）")

    parser.add_argument("--mail_enable", action='store_true', default=os.getenv("MAIL_ENABLE",
                        "False").lower() in ('true', 'yes', '1', 't', 'y'), help="Enable QQ mail notification on portal IP changes")
    parser.add_argument("--mail_sender", type=str,
                        default=os.getenv("MAIL_SENDER", ""), help="QQ mail sender address")
    parser.add_argument("--mail_auth_code", type=str,
                        default=os.getenv("MAIL_AUTH_CODE", ""), help="QQ SMTP auth code")
    parser.add_argument("--mail_to", type=str,
                        default=os.getenv("MAIL_TO", ""), help="Mail receiver address")
    parser.add_argument("--mail_cooldown", type=int,
                        default=get_env_int("MAIL_COOLDOWN", 300), help="Minimum seconds between notifications")

    args = parser.parse_args()

    set_logger(args.log_level)

    if not args.account or not args.password:
        logger.error("未指定校园网账户或密码")
        sys.exit(-1)

    if args.term_type not in ["mobile", "pc"]:
        logger.error("登录设备类型必须为 mobile 或 pc")
        sys.exit(-1)

    if os.name == "nt" and args.interface:
        logger.error("Windows系统不支持指定网络接口")
        sys.exit(-1)

    if args.mail_enable and (not args.mail_sender or not args.mail_auth_code or not args.mail_to):
        logger.error("mail_enable is set, but mail_sender/mail_auth_code/mail_to is missing")
        sys.exit(-1)

    return (
        args.account,
        args.password,
        args.term_type,
        args.interval,
        args.check_with_http,
        args.http_url,
        args.interface,
        args.file_path,
        args.mail_enable,
        args.mail_sender,
        args.mail_auth_code,
        args.mail_to,
        args.mail_cooldown,
    )


def main():
    global logger
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    (
        account,
        password,
        term_type,
        interval,
        check_with_http,
        http_url,
        interface,
        file_path,
        mail_enable,
        mail_sender,
        mail_auth_code,
        mail_to,
        mail_cooldown,
    ) = parse_args()

    if interface:
        logger.info(f"auth interface: {interface}")

    if file_path:
        logger.info(f"IP log file: {file_path}")

    logger.info(f"check network every {interval}s, auto re-auth on disconnect, CTRL+C to stop")

    check_method = "http" if check_with_http else "socket"
    check_params = {"url": http_url} if check_with_http else {}

    status = "init"  # init/auth/unauth/uncertain
    startup_checked = False
    last_portal_ip = read_last_portal_ip_from_file(file_path)
    if last_portal_ip:
        logger.info(f"loaded last portal IP from file: {last_portal_ip}")
    last_mail_sent_at = 0.0

    while True:
        if status == "auth" and check_internet(method=check_method, interface=interface, **check_params):
            logger.debug(f"network looks healthy, recheck in {interval}s")
            time.sleep(interval)
            continue

        auth_info = get_auth_info(interface=interface)
        if not auth_info:
            logger.warning("cannot reach auth server")
            status = "uncertain"
            time.sleep(interval)
            continue

        if "uid" in auth_info and auth_info["uid"] != account:
            if logout(auth_info["uid"], auth_info["v46ip"], interface=interface):
                logger.info(f"logged out previous account: {auth_info['uid']}")
                status = "unauth"
                continue
            logger.error(f"failed to logout previous account: {auth_info['uid']}")
            status = "uncertain"
            time.sleep(interval)
            continue

        if "uid" in auth_info:
            logger.debug(f"already authenticated: {auth_info['uid']}")
            status = "auth"
            portal_ip = auth_info.get("v46ip")

            if portal_ip and last_portal_ip and portal_ip != last_portal_ip:
                now = time.time()
                if mail_enable and (now - last_mail_sent_at >= mail_cooldown):
                    subject = "CQU Portal IP Changed"
                    body = (
                        f"account: {account}\n"
                        f"old_ip: {last_portal_ip}\n"
                        f"new_ip: {portal_ip}\n"
                        f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                    try:
                        send_qq_mail(mail_sender, mail_auth_code, mail_to, subject, body)
                        last_mail_sent_at = now
                        logger.info(f"portal IP changed, mail sent: {last_portal_ip} -> {portal_ip}")
                    except Exception as e:
                        logger.warning(f"failed to send mail: {e}")

            if portal_ip:
                if portal_ip != last_portal_ip:
                    record_ip_to_file(file_path, uid=auth_info.get("uid"), portal_ip=portal_ip)
                last_portal_ip = portal_ip

            if (not startup_checked) and auth_info.get("uid") == account:
                record_ip_to_file(file_path, uid=auth_info.get("uid"), portal_ip=portal_ip)
                startup_checked = True
            continue

        portal_ip = auth_info.get("v46ip")
        if not portal_ip:
            logger.warning("auth_info missing v46ip, skip this round")
            time.sleep(interval)
            continue

        result, msg = login(account, password, term_type, portal_ip, interface=interface)
        if not result:
            status = "unauth"
            if msg in ["\u8d26\u53f7\u4e0d\u5b58\u5728", "\u5bc6\u7801\u9519\u8bef"]:
                logger.error(f"auth failed {account}({term_type}): {msg}")
                sys.exit(-1)
            elif "\u7b49\u5f855\u5206\u949f" in msg:
                logger.warning("triggered sharing-network check, wait 5 minutes")
                time.sleep(300)
                logger.info("wait finished")
            else:
                logger.warning(f"auth failed {account}({term_type}): {msg}")
                time.sleep(interval)
        else:
            status = "auth"
            logger.info(f"auth success {account}({term_type})")
            last_portal_ip = portal_ip
            record_ip_to_file(file_path, uid=account, portal_ip=portal_ip)


if __name__ == "__main__":
    main()
