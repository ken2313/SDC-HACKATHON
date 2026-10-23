"""Tests for ai_client.py using a fake local AI server (no RunPod needed).

Run from the repo root:  python ai\\test_ai_client.py -v
"""
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import ai_client

GOOD_MOVEMENT = {"request_id": "t-1", "product_id": "milk", "movement_type": "OUT",
                 "quantity": 40, "day_of_week": 2, "recent_avg_usage": 10,
                 "usage_std": 2, "history_days": 30}


class FakeAI(BaseHTTPRequestHandler):
    mode = "ok"
    calls = 0
    last_token = None

    def do_POST(self):
        FakeAI.calls += 1
        FakeAI.last_token = self.headers.get("x-api-token")
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            if FakeAI.mode == "fail_then_ok" and FakeAI.calls == 1:
                self.send_response(500)
                self.end_headers()
                return
            if FakeAI.mode == "forbidden":
                self.send_response(403)
                self.end_headers()
                return
            if FakeAI.mode == "slow":
                time.sleep(1.5)
            rid = "someone-else" if FakeAI.mode == "wrong_id" else body["request_id"]
            data = json.dumps({"status": "Highly Unusual", "anomaly_score": 9.99,
                               "top_contributing_features": ["usage_ratio"],
                               "expected_range": [6.0, 14.0], "inference_ms": 1.5,
                               "device": "cuda", "model_version": "autoencoder-v1",
                               "request_id": rid}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client gave up (timeout test) - expected

    def log_message(self, *args):
        pass  # keep test output clean


class TestAIClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAI)
        cls.server.daemon_threads = True
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeAI.mode, FakeAI.calls, FakeAI.last_token = "ok", 0, None
        self.env = mock.patch.dict(os.environ, {"AI_BASE_URL": self.url,
                                                "INFERENCE_TOKEN": "test-token",
                                                "AI_TIMEOUT_S": "2"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    # --- normal ---
    def test_success_returns_ai_result(self):
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "Highly Unusual")
        self.assertEqual(r["request_id"], "t-1")
        self.assertIn("round_trip_ms", r)
        self.assertEqual(FakeAI.last_token, "test-token")

    # --- invalid input ---
    def test_invalid_input_is_rejected_without_calling_ai(self):
        bad = dict(GOOD_MOVEMENT, quantity=-5, day_of_week=9, movement_type="SIDEWAYS")
        r = ai_client.score_movement(bad)
        self.assertEqual(r["status"], "Invalid input")
        self.assertEqual(len(r["errors"]), 3)
        self.assertEqual(FakeAI.calls, 0)

    def test_boolean_quantity_is_rejected(self):
        r = ai_client.score_movement(dict(GOOD_MOVEMENT, quantity=True))
        self.assertEqual(r["status"], "Invalid input")

    def test_empty_input_does_not_crash(self):
        r = ai_client.score_movement(None)
        self.assertEqual(r["status"], "Invalid input")

    # --- edge cases / failures ---
    def test_missing_request_id_is_generated(self):
        m = dict(GOOD_MOVEMENT)
        del m["request_id"]
        r = ai_client.score_movement(m)
        self.assertTrue(r["request_id"])

    def test_no_url_configured_falls_back(self):
        del os.environ["AI_BASE_URL"]
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "AI unavailable")

    def test_server_down_falls_back(self):
        os.environ["AI_BASE_URL"] = "http://127.0.0.1:1"
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "AI unavailable")

    def test_retry_after_server_error_uses_same_request_id(self):
        FakeAI.mode = "fail_then_ok"
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "Highly Unusual")
        self.assertEqual(r["request_id"], "t-1")
        self.assertEqual(FakeAI.calls, 2)

    def test_forbidden_is_not_retried(self):
        FakeAI.mode = "forbidden"
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "AI unavailable")
        self.assertEqual(r["reason"], "HTTP 403")
        self.assertEqual(FakeAI.calls, 1)

    def test_timeout_falls_back(self):
        FakeAI.mode = "slow"
        os.environ["AI_TIMEOUT_S"] = "0.5"
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "AI unavailable")
        self.assertEqual(FakeAI.calls, 2)

    def test_mismatched_request_id_is_rejected(self):
        FakeAI.mode = "wrong_id"
        r = ai_client.score_movement(GOOD_MOVEMENT)
        self.assertEqual(r["status"], "AI unavailable")
        self.assertIn("request_id", r["reason"])


if __name__ == "__main__":
    unittest.main()