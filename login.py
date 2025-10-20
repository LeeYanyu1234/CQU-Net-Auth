"""
# -*- coding: utf-8 -*-
# @Author       : LeeYanyu1234 (343820386@qq.com)
# @Date         : 2025-10-01
# @LastEditors  : LeeYanyu1234 (343820386@qq.com)
# @Description  : 用于自动尝试连接网络
"""
import subprocess
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
from datetime import datetime
import psutil


logger = None
ANDROID_AUTH_URL = "http://10.254.7.4:801/eportal/portal/login?callback=dr1005&login_method=1&user_account=%2C1%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&ua=Mozilla%2F5.0%20(Linux%3B%20Android%208.0.0%3B%20SM-G955U%20Build%2FR16NW)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F134.0.0.0%20Mobile%20Safari%2F537.36%20Edg%2F134.0.0.0&term_type=2&jsVersion=4.2&terminal_type=2&lang=zh-cn&v=9451&lang=zh"
PC_AUTH_URL = "http://10.254.7.4:801/eportal/portal/login?callback=dr1004&login_method=1&user_account=%2C0%2C{account}&user_password={password}&wlan_user_ip={ip}&wlan_user_ipv6=&wlan_user_mac=000000000000&wlan_ac_ip=&wlan_ac_name=&ua=Mozilla%2F5.0%20(Windows%20NT%2010.0%3B%20Win64%3B%20x64)%20AppleWebKit%2F537.36%20(KHTML%2C%20like%20Gecko)%20Chrome%2F134.0.0.0%20Safari%2F537.36%20Edg%2F134.0.0.0&term_type=1&jsVersion=4.2&terminal_type=1&lang=zh-cn&v=9875&lang=zh"
AUTH_INFO_URL = "http://10.254.7.4/drcom/chkstatus?callback=dr1002&jsVersion=4.X&v=5505&lang=zh"
UNBIND_URL = "http://10.254.7.4:801/eportal/portal/mac/unbind?callback=dr1002&user_account={account}&wlan_user_mac=000000000000&wlan_user_ip={int_ip}&jsVersion=4.2&v=6024&lang=zh"
LOGOUT_URL = "http://10.254.7.4:801/eportal/portal/logout"

WIFI_NAME = "WLAN"
ETH_NAME = "以太网"
SSID = "CQU_WiFi"


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


def is_socket_connected(host="223.6.6.6", port=53, timeout=3, interface=None):
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


def check_internet(method="socket", interface=None, **kwargs):
    """检查互联网连接状态"""
    return (
        is_socket_connected(interface=interface, **kwargs)
        and is_http_connected(interface=interface, **kwargs)
    )


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
        return None


def login(account: str, password: str, term_type: str, ip: str, timeout=3, interface=None):
    """认证校园网"""
    create_and_install_opener(interface=interface)
    auth_url = ANDROID_AUTH_URL if term_type == "android" else PC_AUTH_URL
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


def save_ip_to_file(file_path=r"D:\BaiduSyncdisk\IP share\Desktop IP.txt"):
    """保存当前的ipv4地址到文件中"""
    ip_info = get_ipv4_information()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"{timestamp} - {ip_info}\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"已保存到 {file_path}\n{content.strip()}")


def get_ipv4_information():
    """获取当前ipv4网络信息（类型+地址）"""
    addrs = psutil.net_if_addrs()
    result = {}
    for iface, addr_list in addrs.items():
        for addr in addr_list:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                result[iface] = addr.address
    return result


def get_active_network():
    """判断当前使用WiFi还是以太网"""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    active_interfaces = []
    for iface, s in stats.items():
        if s.isup and iface in addrs:
            active_interfaces.append(iface)

    if not active_interfaces:
        return "未连接网络"

    for iface in active_interfaces:
        name = iface.lower()
        if "wi-fi" in name or "wifi" in name or "wlan" in name:
            return "Wi-Fi"
        elif "ethernet" in name or "eth" in name or "lan" in name:
            return "以太网"

    return f"检测到网络接口: {', '.join(active_interfaces)}"


def get_enabled_adapters():
    """返回当前启用的网络适配器列表"""
    result = subprocess.run("netsh interface show interface",
                            shell=True, capture_output=True, text=True)
    enabled = []
    for line in result.stdout.splitlines():
        if "已启用" in line:
            if WIFI_NAME in line:
                enabled.append(WIFI_NAME)
            if ETH_NAME in line:
                enabled.append(ETH_NAME)
    return enabled


def enable_adapter(adapter_name):
    """启用适配器"""
    subprocess.run(
        f'netsh interface set interface "{adapter_name}" enabled', shell=True)
    logger.info(f"{adapter_name} 已启用")


def disable_adapter(adapter_name):
    """禁用适配器"""
    subprocess.run(
        f'netsh interface set interface "{adapter_name}" disabled', shell=True)
    logger.info(f"{adapter_name} 已禁用")


def toggle_network(ssid="CQU_WiFi"):
    """切换适配器 WLAN/以太网"""
    enabled_adapters = get_enabled_adapters()
    if WIFI_NAME in enabled_adapters:
        # WiFi 正在使用，切换到以太网
        enable_adapter(ETH_NAME)
        disable_adapter(WIFI_NAME)
        logger.info("已切换到以太网")
    else:
        # 以太网正在使用，切换到 WiFi
        enable_adapter(WIFI_NAME)
        disable_adapter(ETH_NAME)
        logger.info("已切换到 WiFi")
        if not is_connected_target_wifi(ssid):
            connect_target_wifi(ssid)


def is_connected_target_wifi(ssid):
    """检查当前是否已经连接到指定 WiFi"""
    result = subprocess.run("netsh wlan show interfaces",
                            shell=True, capture_output=True, text=True)
    return ssid in result.stdout and "状态" in result.stdout and "已连接" in result.stdout.lower()


def connect_target_wifi(ssid):
    """连接指定 WiFi，并设置为自动连接"""
    # 尝试直接连接（需要之前保存过 WiFi 密码）
    subprocess.run(
        f'netsh wlan connect name="{ssid}" ssid="{ssid}"', shell=True)
    # 设置为自动连接
    subprocess.run(
        f'netsh wlan set profileparameter name="{ssid}" connectionmode=auto', shell=True)
    logger.info(f"已尝试连接 {ssid} 并设置为自动连接")


def parse_args():
    global logger
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str,
                        default=os.getenv("ACCOUNT", ""), help="校园网账户(学/工号)")
    parser.add_argument("--password", type=str,
                        default=os.getenv("PASSWORD", ""), help="校园网密码")
    parser.add_argument("--term_type", type=str, default=os.getenv(
        "TERM_TYPE", "pc"), choices=["android", "pc"], help="登录设备类型")
    parser.add_argument("--log_level", type=str, default=os.getenv(
        "LOG_LEVEL", "info"), choices=["debug", "info"], help="日志级别")
    parser.add_argument("--interval", type=int,
                        default=os.getenv("INTERVAL", 180), help="检查网络状态的间隔时间(秒)")
    parser.add_argument("--check_with_http", action='store_true', default=os.getenv("CHECK_WITH_HTTP",
                        "False").lower() in ('true', 'yes', '1', 't', 'y'), help="使用 HTTP 连接的的结果检查网络状态，默认为 False")
    parser.add_argument("--http_url", type=str, default=os.getenv("HTTP_URL",
                        "https://www.baidu.com"), help="使用 HTTP 检查网络状态时访问的 URL, 仅在 --check_with_http 为 true 时有效")
    parser.add_argument("--interface", type=str,
                        default=os.getenv("INTERFACE", ""), help="指定使用的网络接口名称，如eth0、wlan0等")
    parser.add_argument("--ssid", type=str,
                        default=os.getenv("SSID", ""), help="目标WiFi名称")
    parser.add_argument("--file_path", type=str,
                        default=os.getenv("FILE_PATH", ""), help="保存文件地址")

    args = parser.parse_args()

    set_logger(args.log_level)

    if not args.account or not args.password:
        logger.error("未指定校园网账户或密码")
        sys.exit(-1)

    if args.term_type not in ["android", "pc"]:
        logger.error("登录设备类型必须为 android 或 pc")
        sys.exit(-1)

    if os.name == "nt" and args.interface:
        logger.error("Windows系统不支持指定网络接口")
        sys.exit(-1)

    return args.account, args.password, args.term_type, args.interval, args.check_with_http, args.http_url, args.interface, args.ssid, args.file_path


def main():
    global logger
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))

    account, password, term_type, interval, check_with_http, http_url, interface, ssid, file_path = parse_args()

    if interface:
        logger.info(f"认证网络接口 {interface}")

    attempt_count = 0
    max_attempts_before_switch = 10

    logger.info(f"每{interval}秒检查一次网络状态, 如果掉线则重新认证, CTRL+C 停止程序")

    check_method = "http" if check_with_http else "socket"
    check_params = {"url": http_url} if check_with_http else {}

    status = "init"  # init/auth/unauth/uncertain
    while True:
        # 如果是 auth 状态，则检查 Internet 连接, 绕过对认证服务器的访问
        if status == "auth" and check_internet(method=check_method, interface=interface, **check_params):
            logger.debug(f"网络连接正常, {interval}秒后重新检查网络状态...")
            time.sleep(interval)
            continue
        else:  # 未认证
            auth_info = get_auth_info(interface=interface)  # 尝试获取认证信息
            if not auth_info:
                logger.warning(f"无法连接认证服务器")
                time.sleep(3)
                attempt_count += 1
                if attempt_count >= max_attempts_before_switch:
                    logger.info("尝试次数达到上限，切换网络适配器")
                    toggle_network(ssid)
                    attempt_count = 0
                status = "uncertain"
                continue

            # 如果当前已认证, 且 uid 与 account 不一致, 则先注销当前认证账户
            if "uid" in auth_info and auth_info["uid"] != account:
                if logout(auth_info["uid"], auth_info["v46ip"], interface=interface):
                    logger.info(f"已注销 {auth_info['uid']}")
                    status = "unauth"
                    continue
                else:
                    logger.error(f"注销 {auth_info['uid']} 失败")
                    status = "uncertain"
                    continue

            # 如果当前已认证, 且 uid 与 account 一致, 则不需要重新认证
            if "uid" in auth_info:
                logger.debug(f"已认证 {auth_info['uid']}")
                # 记录ip地址
                save_ip_to_file(file_path)
                status = "auth"
                continue

            # 执行认证
            result, msg = login(account, password, term_type,
                                auth_info['v46ip'], interface=interface)
            if not result:
                status = "unauth"
                if msg in ["账号不存在", "密码错误"]:
                    logger.error(f"认证失败 {account}({term_type}): {msg}")
                    sys.exit(-1)
                elif "等待5分钟" in msg:
                    logger.warning(f"触发共享上网检测, 等待 5 分钟...")
                    time.sleep(300)
                    logger.info("等待结束")
                else:
                    logger.warning(f"认证失败 {account}({term_type}): {msg}")
            else:
                status = "auth"
                logger.info(f"认证成功 {account}({term_type})")
                # 记录ip地址
                save_ip_to_file(file_path)


if __name__ == "__main__":
    main()
