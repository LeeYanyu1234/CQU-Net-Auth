import socket
import urllib.request
import http.client
import logging


class IfaceHTTPConnection(http.client.HTTPConnection):
    def __init__(
        self,
        host,
        port=None,
        timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None,
        blocksize=8192,
        source_interface=None,
    ):
        super().__init__(
            host,
            port,
            timeout=timeout,
            source_address=source_address,
            blocksize=blocksize,
        )
        self.source_interface: str = source_interface
        self._create_connection = self.create_connection

    def create_connection(
        self,
        address,
        timeout=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None,
        *,
        all_errors=False,
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
                    sock.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_BINDTODEVICE,
                        (self.source_interface + "\0").encode("utf-8"),
                    )
                elif source_address:
                    sock.bind(source_address)
                sock.connect(sa)
                exceptions.clear()
                return sock
            except OSError as exc:
                if not all_errors:
                    exceptions.clear()
                exceptions.append(exc)
                if sock is not None:
                    sock.close()

        if len(exceptions):
            try:
                if not all_errors:
                    raise exceptions[0]
                raise ExceptionGroup("create_connection failed", exceptions)
            finally:
                exceptions.clear()
        else:
            raise OSError("getaddrinfo returns an empty list")


class SourceInterfaceHandler(urllib.request.HTTPHandler):
    def __init__(self, source_interface=None):
        self.source_interface = source_interface
        super().__init__()

    def http_open(self, req):
        return self.do_open(
            IfaceHTTPConnection,
            req,
            source_interface=self.source_interface,
        )


class SourceAddressHandler(urllib.request.HTTPHandler):
    def __init__(self, source_address=None):
        self.source_address = source_address
        super().__init__()

    def http_open(self, req):
        return self.do_open(
            http.client.HTTPConnection,
            req,
            source_address=self.source_address,
        )


def get_interface_ip(interface):
    import fcntl
    import struct

    logger = logging.getLogger()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(
            fcntl.ioctl(
                sock.fileno(),
                0x8915,
                struct.pack("256s", bytes(interface[:15], "utf-8")),
            )[20:24]
        )
    except Exception as e:
        logger.debug(f"failed to get interface IP for {interface}: {e}")
        return None


def create_and_install_opener(interface=None, source_address=None):
    if interface:
        opener = urllib.request.build_opener(
            SourceInterfaceHandler(source_interface=interface)
        )
    elif source_address:
        opener = urllib.request.build_opener(SourceAddressHandler((source_address, 0)))
    else:
        return

    urllib.request.install_opener(opener)
