"""Offline regressions for hosts sharing one router's portal session."""

import unittest
from contextlib import ExitStack
from unittest.mock import Mock, call, patch

from cqu_net_auth.config import Config
from cqu_net_auth.core.loop import run_loop
from cqu_net_auth.portal.client import PortalClient


class StopLoop(Exception):
    """Stop the daemon at a simulated polling interval."""


class SharedSessionTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            account="test-account", password="test-password", term_type="pc",
            interval=180, check_with_http=True, http_url="https://example.com",
            interface="", file_path="test-ip.txt", mail_enable=False,
            mail_sender="", mail_auth_code="", mail_to=(), mail_cooldown=300,
        )
        self.online = {"uid": self.config.account, "v46ip": "10.0.0.1"}
        self.offline = {"uid": "", "v46ip": "10.0.0.1"}
        self.portal = Mock(spec=PortalClient)
        self.portal.get_auth_info.return_value = self.online
        self.portal.login.return_value = (1, "ok")
        self.notifier = Mock()
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.sleep = stack.enter_context(patch(
            "cqu_net_auth.core.loop.time.sleep", side_effect=StopLoop))
        self.check = stack.enter_context(patch(
            "cqu_net_auth.core.loop.check_internet", return_value=True))
        self.record = stack.enter_context(patch(
            "cqu_net_auth.core.loop.record_ip_to_file"))
        self.read = stack.enter_context(patch(
            "cqu_net_auth.core.loop.read_last_portal_ip_from_file", return_value=None))
        stack.enter_context(patch("cqu_net_auth.core.loop.create_and_install_opener"))
        stack.enter_context(patch("cqu_net_auth.core.loop.random.uniform", return_value=2.5))

    def tearDown(self):
        # No automatic path may kick the router's existing session offline.
        self.portal.logout.assert_not_called()

    def run_until_poll(self):
        with self.assertRaises(StopLoop):
            run_loop(self.config, self.portal, self.notifier)

    def test_startup_reuses_existing_session_and_records_ip(self):
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.record.assert_called_once_with(
            "test-ip.txt", uid=self.config.account, portal_ip="10.0.0.1")
        self.sleep.assert_called_once_with(180)

    def test_different_account_is_preserved(self):
        self.portal.get_auth_info.return_value = {
            "uid": "another-account", "v46ip": "10.0.0.1"}
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.record.assert_not_called()
        self.notifier.notify_portal_ip_changed.assert_not_called()

    def test_usable_internet_prevents_login_despite_unauthenticated_status(self):
        self.portal.get_auth_info.return_value = self.offline
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.check.assert_called_once_with(
            method="http", interface="", url="https://example.com")

    def test_offline_login_uses_fresh_ip_after_backoff(self):
        self.portal.get_auth_info.side_effect = [
            self.offline, {"v46ip": "10.0.0.2"}]
        self.check.side_effect = [False, True]
        self.sleep.side_effect = [None, StopLoop]
        self.run_until_poll()
        self.portal.login.assert_called_once_with(
            self.config.account, self.config.password, "pc", "10.0.0.2")
        self.assertEqual(self.sleep.call_args_list, [call(2.5), call(180)])
        self.record.assert_called_once_with(
            "test-ip.txt", uid=self.config.account, portal_ip="10.0.0.2")

    def test_peer_logging_in_during_backoff_prevents_duplicate_login(self):
        self.portal.get_auth_info.side_effect = [
            self.offline, self.online, self.online]
        self.check.return_value = False
        self.sleep.side_effect = [None, StopLoop]
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.assertEqual(self.sleep.call_args_list, [call(2.5), call(180)])

    def test_unreachable_portal_does_not_trigger_login(self):
        self.portal.get_auth_info.return_value = None
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.sleep.assert_called_once_with(180)

    def test_unreachable_portal_after_backoff_does_not_trigger_login(self):
        self.portal.get_auth_info.side_effect = [self.offline, None]
        self.check.return_value = False
        self.sleep.side_effect = [None, StopLoop]
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.assertEqual(self.sleep.call_args_list, [call(2.5), call(180)])

    def test_missing_portal_ip_does_not_trigger_login(self):
        self.portal.get_auth_info.return_value = {"result": 0}
        self.run_until_poll()
        self.portal.login.assert_not_called()

    def test_transient_probe_failure_preserves_authenticated_session(self):
        self.check.return_value = False
        self.sleep.side_effect = [None, StopLoop]
        self.run_until_poll()
        self.portal.login.assert_not_called()
        self.assertEqual(self.portal.get_auth_info.call_count, 2)
        self.assertEqual(self.sleep.call_args_list, [call(180), call(180)])

    def test_reused_session_still_notifies_ip_change(self):
        self.read.return_value = "10.0.0.9"
        self.run_until_poll()
        self.notifier.notify_portal_ip_changed.assert_called_once_with(
            self.config.account, "10.0.0.9", "10.0.0.1")
        self.portal.login.assert_not_called()

    def test_bad_credentials_still_exit(self):
        self.portal.get_auth_info.return_value = self.offline
        self.portal.login.return_value = (0, "密码错误")
        self.check.return_value = False
        self.sleep.side_effect = None
        with self.assertRaises(SystemExit) as caught:
            run_loop(self.config, self.portal, self.notifier)
        self.assertEqual(caught.exception.code, -1)
        self.portal.login.assert_called_once()

    def test_server_cooldown_is_still_respected(self):
        self.portal.get_auth_info.return_value = self.offline
        self.portal.login.return_value = (0, "请等待5分钟后再试")
        self.check.return_value = False
        self.sleep.side_effect = [None, StopLoop]
        self.run_until_poll()
        self.assertEqual(self.sleep.call_args_list, [call(2.5), call(300)])


if __name__ == "__main__":
    unittest.main()
