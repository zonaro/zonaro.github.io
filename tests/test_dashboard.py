"""Checks the local dashboard API without needing GitHub credentials."""

import importlib.util
import json
from pathlib import Path
import secrets
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/portfolio_dashboard.py"
spec = importlib.util.spec_from_file_location("portfolio_dashboard", SCRIPT)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class DashboardTests(unittest.TestCase):
    def test_list_reads_metadata_only(self):
        calls = []

        def fake_gh(*args, **kwargs):
            calls.append(args)
            self.assertEqual(args[:2], ("repo", "list"))
            return json.dumps([
                {"name": "PrivateApp", "nameWithOwner": "zonaro/PrivateApp", "isPrivate": True,
                 "description": "Resumo autorizado", "repositoryTopics": [{"name": "portfolio-secondary"}]},
                {"name": "PublicApp", "nameWithOwner": "zonaro/PublicApp", "isPrivate": False,
                 "description": "Projeto público", "repositoryTopics": []},
            ])

        with patch.object(dashboard, "gh", side_effect=fake_gh):
            repos = dashboard.repo_list()
        self.assertEqual(len(calls), 1)
        self.assertEqual(repos[0]["category"], "secondary")
        self.assertTrue(repos[0]["private"])
        self.assertEqual(repos[1]["category"], "hidden")

    def test_update_preserves_other_topics(self):
        calls = []

        def fake_gh(*args, input_text=None):
            calls.append((args, input_text))
            if args[:2] == ("api", "repos/zonaro/MyApp/topics"):
                return json.dumps({"names": ["flutter", "portfolio-secondary", "linux"]})
            if args[:3] == ("api", "--method", "PUT"):
                return input_text
            self.fail(f"Unexpected command: {args}")

        with patch.object(dashboard, "gh", side_effect=fake_gh):
            result = dashboard.update_category("MyApp", "primary", ["flutter", "linux", "portfolio-secondary"])
        self.assertEqual(result["topics"], ["flutter", "linux", "portfolio-primary"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(calls[1][1])["names"], result["topics"])

    def test_concurrent_topic_change_blocks_write(self):
        with patch.object(dashboard, "gh", return_value=json.dumps({"names": ["new-topic"]})) as mocked:
            with self.assertRaises(dashboard.ApiError) as caught:
                dashboard.update_category("MyApp", "catalog", ["old-topic"])
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(mocked.call_count, 1)

    def test_conflicting_topics_flagged(self):
        self.assertEqual(dashboard.category_of(["portfolio-primary", "portfolio-catalog"]), "conflict")
        self.assertEqual(dashboard.category_of(["something-else"]), "hidden")

    def test_http_requires_token_and_origin(self):
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        server.token = secrets.token_urlsafe(32)
        server.preview_ready = False
        server.job_lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(path, method="GET", token=None, origin=None, data=None):
            headers = {}
            if token:
                headers["X-Dashboard-Token"] = token
            if origin:
                headers["Origin"] = origin
            if data is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(data).encode()
            try:
                with urlopen(Request(base + path, data=data, headers=headers, method=method), timeout=5) as response:
                    return response.status, response.read().decode()
            except HTTPError as exc:
                return exc.code, exc.read().decode()

        try:
            code, body = request("/")
            self.assertEqual(code, 200)
            self.assertIn(server.token, body)
            self.assertEqual(request("/api/repos")[0], 403)
            self.assertEqual(request("/api/classify", method="POST", token=server.token,
                                     data={"name": "a", "category": "primary", "expected_topics": []})[0], 403)
            with patch.object(dashboard, "repo_list", return_value=[{"name": "Example"}]):
                code, body = request("/api/repos", token=server.token)
            self.assertEqual(code, 200)
            self.assertIn("Example", body)
            with patch.object(dashboard, "update_category", return_value={"name": "Example", "category": "primary", "topics": ["portfolio-primary"]}):
                code, body = request("/api/classify", method="POST", token=server.token,
                                     origin=base, data={"name": "Example", "category": "primary", "expected_topics": []})
            self.assertEqual(code, 200)
            self.assertIn("portfolio-primary", body)
            self.assertEqual(request("/api/publish", method="POST", token=server.token,
                                     origin=base, data={"confirm": "PUBLICAR"})[0], 409)
            with patch.object(dashboard, "run_local", return_value="Prévia criada"):
                code, body = request("/api/preview", method="POST", token=server.token, origin=base, data={})
            self.assertEqual(code, 200)
            self.assertIn("Prévia criada", body)
            self.assertTrue(server.preview_ready)
            self.assertEqual(request("/api/publish", method="POST", token=server.token,
                                     origin=base, data={"confirm": "NÃO"})[0], 409)
            with patch.object(dashboard, "run_local", return_value="Commit publicado") as mocked:
                code, body = request("/api/publish", method="POST", token=server.token,
                                     origin=base, data={"confirm": "PUBLICAR"})
            self.assertEqual(code, 200)
            self.assertIn("Commit publicado", body)
            mocked.assert_called_once_with("bash", "scripts/update-portfolio.sh", "--publish", "--yes", timeout=300)
            self.assertFalse(server.preview_ready)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
