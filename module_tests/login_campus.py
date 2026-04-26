"""Perform a real campus network login and verify the logged-in account."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqu_net_auth.portal.client import PortalClient

from module_tests.common import exit_fail, exit_ok, print_config_summary, print_json, require_config


def main() -> None:
    config = require_config("account", "password")
    print_config_summary(config)

    account = str(config["account"])
    password = str(config["password"])
    term_type = str(config.get("term_type") or "pc")

    client = PortalClient(timeout=10, interface=config.get("interface") or None)
    auth_info = client.get_auth_info()
    if auth_info is None:
        exit_fail("无法访问校园网认证状态接口，登录前无法获取门户 IP")

    print_json("\n登录前认证状态:", auth_info)

    portal_ip = auth_info.get("v46ip")
    if not portal_ip:
        exit_fail("认证状态里没有 v46ip，无法发起登录")

    result, msg = client.login(account, password, term_type, portal_ip)
    print(f"\n登录接口返回: result={result}, msg={msg}")
    if not result:
        exit_fail(f"登录失败: {msg}")

    time.sleep(1)
    after_info = client.get_auth_info()
    if after_info is None:
        exit_fail("登录接口返回成功，但无法再次查询认证状态")

    print_json("\n登录后认证状态:", after_info)
    if after_info.get("uid") != account:
        exit_fail(f"登录后账号不匹配。当前账号={after_info.get('uid')}，期望账号={account}")

    exit_ok(f"校园网登录成功，当前账号: {account}")


if __name__ == "__main__":
    main()
