"""Perform a real campus portal logout and verify the account is offline."""

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqu_net_auth.exceptions import PortalClientError
from cqu_net_auth.portal.client import PortalClient

from module_tests.common import exit_fail, exit_ok, print_config_summary, print_json, require_config


def main() -> None:
    config = require_config("account")
    print_config_summary(config)

    account = str(config["account"])
    client = PortalClient(timeout=10, interface=config.get("interface") or None)

    before_info = client.get_auth_info()
    if before_info is None:
        exit_fail("无法访问校园网认证状态接口")

    print_json("\n登出前认证状态:", before_info)
    portal_ip = before_info.get("v46ip")
    if not portal_ip:
        exit_fail("认证状态里没有 v46ip，无法发起登出")

    if before_info.get("uid") != account:
        print(f"\n提示: 当前登录账号不是脚本账号。当前账号={before_info.get('uid')}，脚本账号={account}")

    try:
        logout_ok = client.logout(account, portal_ip)
    except PortalClientError as exc:
        exit_fail(f"登出参数无效: {exc}")

    print(f"\n登出接口返回: {logout_ok}")
    if not logout_ok:
        exit_fail("登出接口返回失败")

    time.sleep(1)
    after_info = client.get_auth_info()
    if after_info is None:
        exit_fail("登出接口返回成功，但无法再次查询认证状态")

    print_json("\n登出后认证状态:", after_info)
    if after_info.get("uid") == account:
        exit_fail(f"登出后仍显示脚本账号在线: {account}")

    exit_ok("登出成功，脚本账号已不再显示为在线")


if __name__ == "__main__":
    main()
