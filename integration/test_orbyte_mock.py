"""Tests for the simulated Orbyte layer.

Run from the repo root:  python integration\\test_orbyte_mock.py -v
"""
import os
import tempfile
import threading
import unittest
from unittest import mock

import orbyte_mock as om

CAFE, MART = "BIZ-CAFE-001", "BIZ-MART-002"


class TestOrbyteMock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "actions.jsonl")
        self.env = mock.patch.dict(os.environ, {"ORBYTE_MOCK_LOG": self.log})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    # --- normal ---
    def test_known_business_and_user(self):
        self.assertEqual(om.get_business(CAFE)["source"], "orbyte-simulated")
        ctx = om.get_user_context("u-emp-1")
        self.assertEqual(ctx["role"], "employee")
        self.assertIn("inventory.record_movement", ctx["permissions"])

    def test_role_permissions_match_demo(self):
        self.assertTrue(om.has_permission("u-emp-1", CAFE, "inventory.record_movement"))
        self.assertTrue(om.has_permission("u-emp-1", CAFE, "anomaly.review"))
        self.assertFalse(om.has_permission("u-emp-1", CAFE, "po.approve"))
        self.assertFalse(om.has_permission("u-mgr-1", CAFE, "po.approve"))
        self.assertTrue(om.has_permission("u-owner-1", CAFE, "po.approve"))

    def test_log_and_read_back(self):
        r = om.log_completed_action(CAFE, "u-owner-1", "po.approve", {"po_id": "PO-1"}, "req-1")
        self.assertTrue(r["logged"])
        actions = om.get_actions(CAFE)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["details"]["po_id"], "PO-1")

    # --- invalid ---
    def test_unknown_business_and_user_return_none(self):
        self.assertIsNone(om.get_business("BIZ-NOPE"))
        self.assertIsNone(om.get_user_context("u-nobody"))

    def test_unknown_user_or_action_is_denied(self):
        self.assertFalse(om.has_permission("u-nobody", CAFE, "inventory.view"))
        self.assertFalse(om.has_permission("u-owner-1", CAFE, "delete.everything"))

    def test_require_permission_raises(self):
        with self.assertRaises(om.PermissionDenied):
            om.require_permission("u-emp-1", CAFE, "po.approve")

    def test_log_unknown_user_is_rejected(self):
        r = om.log_completed_action(CAFE, "u-nobody", "po.approve")
        self.assertFalse(r["logged"])
        self.assertFalse(os.path.exists(self.log))

    # --- edge cases ---
    def test_cross_business_is_denied(self):
        self.assertFalse(om.has_permission("u-owner-2", CAFE, "po.approve"))
        self.assertTrue(om.has_permission("u-owner-2", MART, "po.approve"))

    def test_duplicate_request_id_logged_once(self):
        om.log_completed_action(CAFE, "u-owner-1", "po.approve", None, "req-dup")
        r = om.log_completed_action(CAFE, "u-owner-1", "po.approve", None, "req-dup")
        self.assertFalse(r["logged"])
        self.assertEqual(len(om.get_actions(CAFE)), 1)

    def test_concurrent_duplicates_logged_once(self):
        threads = [threading.Thread(target=om.log_completed_action,
                                    args=(CAFE, "u-owner-1", "po.approve", None, "req-race"))
                   for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(om.get_actions(CAFE)), 1)

    def test_businesses_are_isolated_in_log(self):
        om.log_completed_action(CAFE, "u-owner-1", "po.approve", None, "req-a")
        om.log_completed_action(MART, "u-owner-2", "po.approve", None, "req-b")
        self.assertEqual(len(om.get_actions(CAFE)), 1)
        self.assertEqual(len(om.get_actions(MART)), 1)

    def test_corrupt_log_line_is_skipped(self):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("this is not json\n")
        r = om.log_completed_action(CAFE, "u-owner-1", "po.approve", None, "req-c")
        self.assertTrue(r["logged"])
        self.assertEqual(len(om.get_actions(CAFE)), 1)


if __name__ == "__main__":
    unittest.main()