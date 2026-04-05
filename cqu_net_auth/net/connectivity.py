"""Network connectivity checks used by the loop."""

import logging
import socket
import urllib.error
import urllib.request

from .opener import create_and_install_opener, get_interface_ip


def is_internet_connected(host="223.6.6.6", port=53, timeout=3, interface=None):
    """Probe reachability via TCP connect (DNS endpoint by default)."""
    logger = logging.getLogger()
    interface_ip = None
    if interface:
        interface_ip = get_interface_ip(interface)
        if not interface_ip:
            logger.debug("net.interface_ip_unavailable: %s", interface)

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if interface_ip:
            conn.bind((interface_ip, 0))
        conn.settimeout(timeout)
        conn.connect((host, port))
        conn.close()
        return True
    except OSError as exc:
        logger.debug("net.socket_check_failed: %s", exc)
        return False


def is_http_connected(url="https://www.baidu.com", timeout=3, interface=None):
    """Probe reachability via HTTP HEAD request."""
    logger = logging.getLogger()
    create_and_install_opener(interface=interface)
    req = urllib.request.Request(url, method="HEAD")
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
        return response.getcode() == 200
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.debug("net.http_check_failed: %s", exc)
        return False


def check_internet(method="http", interface=None, **kwargs):
    """Dispatch connectivity check method."""
    if method == "socket":
        return is_internet_connected(interface=interface, **kwargs)
    if method == "http":
        return is_http_connected(interface=interface, **kwargs)
    raise ValueError("method must be 'socket' or 'http'")
