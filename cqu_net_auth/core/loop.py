"""Main runtime state machine for connectivity check and re-auth."""

import logging
import random
import sys
import time

from cqu_net_auth.config import Config
from cqu_net_auth.net.connectivity import check_internet
from cqu_net_auth.net.opener import create_and_install_opener
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

    # Hosts behind one router may share a portal session. Never reset it on startup.
    create_and_install_opener(interface=config.interface, disable_proxy=True)
    logger.info("startup.preserve_existing_session")

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

        if auth_info.get("uid") and auth_info["uid"] != config.account:
            logger.warning(
                "portal.other_account_preserved: current=%s configured=%s; "
                "log out manually to switch accounts",
                auth_info["uid"], config.account)
            status = "auth"
            time.sleep(config.interval)
            continue

        if auth_info.get("uid"):
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
            time.sleep(config.interval)
            continue

        portal_ip = auth_info.get("v46ip")
        if not portal_ip:
            logger.warning("portal.auth_info_missing_v46ip")
            time.sleep(config.interval)
            continue

        # A usable connection takes priority over a stale portal status response.
        if check_internet(method=check_method, interface=config.interface, **check_params):
            logger.debug("portal.login_skipped_network_healthy")
            time.sleep(config.interval)
            continue

        # Stagger recovery across hosts, then check whether a peer logged in.
        # This reduces simultaneous logins; it is not a cross-host lock.
        delay = random.uniform(1, 5)
        logger.debug("portal.login_backoff: sleep=%.2fs", delay)
        time.sleep(delay)
        auth_info = portal_client.get_auth_info()
        if not auth_info:
            logger.warning("portal.unreachable_before_login")
            time.sleep(config.interval)
            continue
        if auth_info.get("uid"):
            logger.info("portal.login_skipped_session_restored")
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
