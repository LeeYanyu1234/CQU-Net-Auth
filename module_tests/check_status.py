"""Query and print the current campus portal login status."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqu_net_auth.portal.client import PortalClient

from module_tests.common import exit_fail, exit_ok, print_config_summary, print_json, require_config


def main() -> None:
    config = require_config("account")
    print_config_summary(config)

    client = PortalClient(timeout=10, interface=config.get("interface") or None)
    auth_info = client.get_auth_info()
    if auth_info is None:
        exit_fail("无法访问校园网认证状态接口")

    print_json("\n认证状态原始信息:", auth_info)

    expected_account = str(config["account"])
    actual_account = auth_info.get("uid")
    if actual_account == expected_account:
        exit_ok(f"当前已登录，账号正确: {actual_account}")
    if actual_account:
        exit_fail(f"当前已登录，但账号不匹配。当前账号={actual_account}，期望账号={expected_account}")

    portal_ip = auth_info.get("v46ip")
    if portal_ip:
        exit_ok(f"当前未登录，但已获取到门户 IP: {portal_ip}")

    exit_fail("状态接口可访问，但没有返回 uid 或 v46ip")


if __name__ == "__main__":
    main()
