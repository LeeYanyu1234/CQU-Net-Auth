"""Main runtime state machine for connectivity check and re-auth."""

import logging
import sys
import time

from cqu_net_auth.config import Config
from cqu_net_auth.exceptions import PortalClientError
from cqu_net_auth.net.connectivity import check_internet
from cqu_net_auth.notify.service import Notifier
from cqu_net_auth.portal.client import PortalClient
from cqu_net_auth.storage.ip_history import (
    read_last_portal_ip_from_file,
    record_ip_to_file,
)


def run_loop(config: Config, portal_client: PortalClient | None = None, notifier: Notifier | None = None):
    """Run the long-lived auth loop until process exit."""
    logger = logging.getLogger()

    portal_client = portal_client or PortalClient(interface=config.interface)
    notifier = notifier or Notifier(
        enabled=config.mail_enable,
        sender=config.mail_sender,
        auth_code=config.mail_auth_code,
        to_addrs=config.mail_to,
        cooldown=config.mail_cooldown,
    )

    if config.interface:
        logger.info("auth.interface: %s", config.interface)

    if config.file_path:
        logger.info("storage.ip_log_file: %s", config.file_path)

    logger.info("main.loop_start: interval=%ss", config.interval)

    check_method = "http" if config.check_with_http else "socket"
    check_params = {"url": config.http_url} if config.check_with_http else {}

    # status tracks the lightweight state machine of the auth workflow.
    status = "init"
    startup_checked = False
    last_portal_ip = read_last_portal_ip_from_file(config.file_path)
    if last_portal_ip:
        logger.info("storage.last_portal_ip_loaded: %s", last_portal_ip)

    while True:
        # Fast path: when authenticated and network is healthy, only sleep/recheck.
        if status == "auth" and check_internet(method=check_method, interface=config.interface, **check_params):
            logger.debug("main.network_healthy: sleep=%ss", config.interval)
            time.sleep(config.interval)
            continue

        # Pull current portal session info (uid/ip).
        auth_info = portal_client.get_auth_info()
        if not auth_info:
            logger.warning("portal.unreachable")
            status = "uncertain"
            time.sleep(config.interval)
            continue

        if "uid" in auth_info and auth_info["uid"] != config.account:
            try:
                if portal_client.logout(auth_info["uid"], auth_info["v46ip"]):
                    logger.info(
                        "portal.previous_account_logged_out: %s", auth_info["uid"])
                    status = "unauth"
                    continue
            except PortalClientError as exc:
                logger.warning("portal.logout_failed_invalid_input: %s", exc)
            logger.error(
                "portal.failed_to_logout_previous_account: %s", auth_info["uid"])
            status = "uncertain"
            time.sleep(config.interval)
            continue

        if "uid" in auth_info:
            logger.debug("portal.already_authenticated: %s", auth_info["uid"])
            status = "auth"
            portal_ip = auth_info.get("v46ip")
            wrote_ip_record = False

            if portal_ip and last_portal_ip and portal_ip != last_portal_ip:
                notifier.notify_portal_ip_changed(
                    config.account, last_portal_ip, portal_ip)

            if portal_ip:
                if portal_ip != last_portal_ip:
                    record_ip_to_file(config.file_path, uid=auth_info.get(
                        "uid"), portal_ip=portal_ip)
                    wrote_ip_record = True
                last_portal_ip = portal_ip

            if (not startup_checked) and auth_info.get("uid") == config.account:
                if not wrote_ip_record:
                    record_ip_to_file(config.file_path, uid=auth_info.get(
                        "uid"), portal_ip=portal_ip)
                startup_checked = True
            continue

        portal_ip = auth_info.get("v46ip")
        if not portal_ip:
            logger.warning("portal.auth_info_missing_v46ip")
            time.sleep(config.interval)
            continue

        result, msg = portal_client.login(
            config.account, config.password, config.term_type, portal_ip)
        if not result:
            status = "unauth"
            if msg in ["账号不存在", "密码错误"]:
                logger.error("portal.auth_failed_fatal: account=%s term_type=%s msg=%s",
                             config.account, config.term_type, msg)
                sys.exit(-1)
            if "等待5分钟" in msg:
                logger.warning("portal.share_network_check_triggered")
                time.sleep(300)
                logger.info("portal.share_network_wait_finished")
            else:
                logger.warning("portal.auth_failed_retry: account=%s term_type=%s msg=%s",
                               config.account, config.term_type, msg)
                time.sleep(config.interval)
        else:
            status = "auth"
            logger.info("portal.auth_success: account=%s term_type=%s",
                        config.account, config.term_type)
            if portal_ip and last_portal_ip and portal_ip != last_portal_ip:
                notifier.notify_portal_ip_changed(
                    config.account, last_portal_ip, portal_ip
                )
            last_portal_ip = portal_ip
            record_ip_to_file(config.file_path,
                              uid=config.account, portal_ip=portal_ip)
