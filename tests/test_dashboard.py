"""Checks the local dashboard API without needing GitHub credentials."""

import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/portfolio_dashboard.py"
spec = importlib.util.spec_from_file_location("portfolio_dashboard", SCRIPT)
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


class DashboardTests(unittest.TestCase):
    def test_direct_script_entrypoints_import_art_module(self):
        scripts = SCRIPT.parent
        for name in ("portfolio_dashboard.py", "generate_portfolio.py"):
            with self.subTest(script=name):
                result = subprocess.run([sys.executable, str(scripts / name), "--help"],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_description_auto_save_checks_for_stale_data(self):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ("api", "repos/zonaro/Example"):
                return json.dumps({"full_name": "zonaro/Example", "description": "Antes"})
            if args[:2] == ("repo", "edit"):
                return ""
            self.fail(f"Unexpected command: {args}")

        with patch.object(dashboard, "gh", side_effect=fake_gh):
            result = dashboard.update_description("Example", "Depois", "Antes")
            self.assertEqual(result["description"], "Depois")
            self.assertEqual(calls[-1], ("repo", "edit", "zonaro/Example", "--description", "Depois"))
            with self.assertRaises(dashboard.ApiError) as caught:
                dashboard.update_description("Example", "Outro", "Desatualizado")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(len(calls), 3)

    def test_delete_requires_exact_confirmation_and_fresh_metadata(self):
        current = {"full_name": "zonaro/Example", "owner": {"login": "zonaro"},
                   "permissions": {"admin": True}, "topics": ["portfolio-catalog"], "private": True}
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ("api", "repos/zonaro/Example"):
                return json.dumps(current)
            if args[:2] == ("repo", "delete"):
                return ""
            self.fail(f"Unexpected command: {args}")

        with patch.object(dashboard, "gh", side_effect=fake_gh):
            with self.assertRaises(dashboard.ApiError):
                dashboard.delete_repository("Example", "Example", ["portfolio-catalog"], True)
            with self.assertRaises(dashboard.ApiError):
                dashboard.delete_repository("zonaro.github.io", "zonaro/zonaro.github.io", [], False)
            self.assertEqual(calls, [])
            with self.assertRaises(dashboard.ApiError) as caught:
                dashboard.delete_repository("Example", "zonaro/Example", ["portfolio-primary"], True)
            self.assertEqual(caught.exception.status, 409)
            self.assertNotIn(("repo", "delete", "zonaro/Example", "--yes"), calls)
            self.assertEqual(dashboard.delete_repository("Example", "zonaro/Example", ["portfolio-catalog"], True),
                             {"deleted": "zonaro/Example"})
        self.assertEqual(calls[-1], ("repo", "delete", "zonaro/Example", "--yes"))

    def test_cover_upload_is_sanitized_and_stored_locally(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(dashboard, "ROOT", Path(tmp)):
            result = dashboard.update_cover("Example", {"mode": "preset", "style": "grid", "icon": "game"})
            self.assertIn("<svg", result["svg"])
            self.assertTrue((Path(tmp) / "assets/portfolio-covers/example.svg").exists())
            self.assertTrue(dashboard.current_cover("Example")["custom"])
            with self.assertRaises(dashboard.ApiError):
                dashboard.update_cover("Example", {"mode": "svg", "svg":
                    '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'})
            with self.assertRaises(dashboard.ApiError):
                dashboard.update_cover("Example", {"mode": "svg", "svg":
                    '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://bad.example/a"/></svg>'})
            self.assertIn("<svg", dashboard.current_cover("Example")["svg"])

    def test_label_creation_recolor_and_assignment_preserve_unrelated_topics(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(dashboard, "ROOT", Path(tmp)):
            created = dashboard.upsert_label("Em desenvolvimento", "#Aa44CC", None, None)
            self.assertEqual(created["slug"], "em-desenvolvimento")
            self.assertEqual(created["label"]["color"], "#aa44cc")
            changed = dashboard.upsert_label("Em andamento", "#0dca9f", created["slug"], created["label"])
            self.assertEqual(changed["label"]["name"], "Em andamento")
            self.assertEqual(changed["slug"], created["slug"])
            with self.assertRaises(dashboard.ApiError) as stale:
                dashboard.upsert_label("Outro", "#00ff00", created["slug"], created["label"])
            self.assertEqual(stale.exception.status, 409)
            topics = ["flutter", "portfolio-primary", "linux"]
            calls = []

            def fake_gh(*args, input_text=None):
                calls.append((args, input_text))
                if args[:2] == ("api", "repos/zonaro/Public/topics"):
                    return json.dumps({"names": topics})
                if args[:3] == ("api", "--method", "PUT"):
                    return input_text
                self.fail(f"Unexpected gh command {args}")

            with patch.object(dashboard, "repo_list", return_value=[{"name": "Public", "private": False}]), \
                 patch.object(dashboard, "gh", side_effect=fake_gh):
                result = dashboard.update_repo_labels("Public", [created["slug"]], topics)
                self.assertEqual(result["topics"], sorted(topics + ["portfolio-label-em-desenvolvimento"]))
                self.assertEqual(len(calls), 2)
                with self.assertRaises(dashboard.ApiError) as conflict:
                    dashboard.update_repo_labels("Public", [created["slug"]], ["old-topic"])
                self.assertEqual(conflict.exception.status, 409)
            with patch.object(dashboard, "repo_list", return_value=[{"name": "Private", "private": True}]), \
                 patch.object(dashboard, "gh") as never_read:
                with self.assertRaises(dashboard.ApiError) as forbidden:
                    dashboard.update_repo_labels("Private", [created["slug"]], topics)
                self.assertEqual(forbidden.exception.status, 403)
                never_read.assert_not_called()

    def test_homepage_saves_public_only_and_rejects_unsafe_urls(self):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ("api", "repos/zonaro/Public"):
                return json.dumps({"full_name": "zonaro/Public", "private": False,
                                   "homepage": "https://before.example"})
            if args[:2] == ("repo", "edit"):
                return ""
            self.fail(f"Unexpected gh command {args}")

        with patch.object(dashboard, "repo_list", return_value=[{"name": "Public", "private": False}]), \
             patch.object(dashboard, "gh", side_effect=fake_gh):
            saved = dashboard.update_homepage("Public", "https://new.example/app", "https://before.example")
            self.assertEqual(saved["homepage"], "https://new.example/app")
            self.assertIn(("repo", "edit", "zonaro/Public", "--homepage", "https://new.example/app"), calls)
            with self.assertRaises(dashboard.ApiError) as stale:
                dashboard.update_homepage("Public", "", "outdated")
            self.assertEqual(stale.exception.status, 409)
            with self.assertRaises(dashboard.ApiError) as invalid:
                dashboard.update_homepage("Public", "javascript:alert(1)", "https://before.example")
            self.assertEqual(invalid.exception.status, 400)
        with patch.object(dashboard, "repo_list", return_value=[{"name": "Private", "private": True}]), \
             patch.object(dashboard, "gh") as never_read:
            with self.assertRaises(dashboard.ApiError) as forbidden:
                dashboard.homepage_info("Private")
            self.assertEqual(forbidden.exception.status, 403)
            never_read.assert_not_called()

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
            with urlopen(base + "/", timeout=5) as response:
                policy = response.headers["Content-Security-Policy"]
            self.assertIn("img-src 'self' data:", policy)
            self.assertIn("script-src 'self'", policy)
            self.assertNotIn("script-src 'self' data:", policy)
            self.assertEqual(request("/api/repos")[0], 403)
            self.assertEqual(request("/api/cover?name=Example")[0], 403)
            self.assertEqual(request("/api/classify", method="POST", token=server.token,
                                     data={"name": "a", "category": "primary", "expected_topics": []})[0], 403)
            self.assertEqual(request("/api/delete", method="POST", token=server.token,
                                     data={"name": "a", "confirmation": "zonaro/a", "expected_topics": [],
                                           "expected_private": False})[0], 403)
            with patch.object(dashboard, "repo_list", return_value=[{"name": "Example"}]):
                code, body = request("/api/repos", token=server.token)
            self.assertEqual(code, 200)
            self.assertIn("Example", body)
            with patch.object(dashboard, "update_category", return_value={"name": "Example", "category": "primary", "topics": ["portfolio-primary"]}):
                code, body = request("/api/classify", method="POST", token=server.token,
                                     origin=base, data={"name": "Example", "category": "primary", "expected_topics": []})
            self.assertEqual(code, 200)
            self.assertIn("portfolio-primary", body)
            with patch.object(dashboard, "current_cover", return_value={"name": "Example", "svg": "<svg/>", "custom": False}):
                code, body = request("/api/cover?name=Example", token=server.token)
                self.assertEqual(code, 200)
                self.assertIn("<svg/>", body)
            with patch.object(dashboard, "update_cover", return_value={"name": "Example", "svg": "<svg/>", "custom": True}):
                code, body = request("/api/cover", method="POST", token=server.token, origin=base,
                                     data={"name": "Example", "mode": "preset"})
                self.assertEqual(code, 200)
                self.assertIn('"custom": true', body)
            with patch.object(dashboard, "upsert_label", return_value={"slug": "commercial", "labels": {"commercial": {"name": "Comercial", "color": "#ff1100"}}}):
                code, body = request("/api/labels", method="POST", token=server.token,
                                     origin=base, data={"name": "Comercial", "color": "#ff1100"})
                self.assertEqual(code, 200)
                self.assertIn("commercial", body)
            with patch.object(dashboard, "update_repo_labels", return_value={"name": "Example", "labels": ["commercial"], "topics": []}):
                code, body = request("/api/assign-labels", method="POST", token=server.token,
                                     origin=base, data={"name": "Example", "labels": ["commercial"], "expected_topics": []})
                self.assertEqual(code, 200)
                self.assertIn("commercial", body)
            with patch.object(dashboard, "homepage_info", return_value={"name": "Example", "homepage": "https://example.com"}):
                code, body = request("/api/homepage?name=Example", token=server.token)
                self.assertEqual(code, 200)
                self.assertIn("https://example.com", body)
            with patch.object(dashboard, "update_homepage", return_value={"name": "Example", "homepage": "https://example.com"}):
                code, body = request("/api/homepage", method="POST", token=server.token,
                                     origin=base, data={"name": "Example", "homepage": "https://example.com",
                                                        "expected_homepage": ""})
                self.assertEqual(code, 200)
                self.assertIn("https://example.com", body)
            with patch.object(dashboard, "delete_repository", return_value={"deleted": "zonaro/Example"}) as mocked:
                code, body = request("/api/delete", method="POST", token=server.token, origin=base,
                                     data={"name": "Example", "confirmation": "zonaro/Example",
                                           "expected_topics": [], "expected_private": False})
                self.assertEqual(code, 200)
                self.assertIn("zonaro/Example", body)
                mocked.assert_called_once()
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
