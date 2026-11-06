"""Offline tests: no GitHub account or credentials required."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_portfolio.py"
spec = importlib.util.spec_from_file_location("portfolio_generator", SCRIPT)
generator = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)


class GeneratorTests(unittest.TestCase):
    repos = [
        {"name": "public-one", "nameWithOwner": "zonaro/public-one", "description": "Public demo",
         "isPrivate": False, "repositoryTopics": [{"name": "portfolio-primary"}]},
        {"name": "private-one", "nameWithOwner": "zonaro/private-one", "description": "Private demo",
         "isPrivate": True, "repositoryTopics": [{"name": "portfolio-secondary"}]},
        {"name": "hidden-private", "nameWithOwner": "zonaro/hidden-private", "description": "Must hide",
         "isPrivate": True, "repositoryTopics": [{"name": "flutter"}]},
        {"name": "hidden-public", "nameWithOwner": "zonaro/hidden-public", "description": "Must hide",
         "isPrivate": False, "repositoryTopics": []},
        {"name": "conflict", "nameWithOwner": "zonaro/conflict", "description": "Conflicting topics",
         "isPrivate": False, "repositoryTopics": [{"name": "portfolio-primary"}, {"name": "portfolio-catalog"}]},
    ]

    def fake_gh(self, *args):
        if args[:2] == ("repo", "list"):
            return json.dumps(self.repos)
        if args[:2] == ("repo", "view"):
            self.assertEqual(args[2], "zonaro/public-one")
            return json.dumps({"openGraphImageUrl": None, "usesCustomOpenGraphImage": False,
                               "primaryLanguage": {"name": "Python"}, "homepageUrl": None,
                               "defaultBranchRef": {"name": "main"}})
        if args[:2] == ("api", "repos/zonaro/public-one/readme"):
            return '<h2>Example</h2><p>Some <a href="docs/intro.md">documentation</a>.</p>'
        self.fail(f"Unexpected gh command (possibly a PRIVATE README read): {args}")

    def test_explicit_topics_only_and_conflicts(self):
        with patch.object(generator, "gh", side_effect=self.fake_gh):
            projects, warnings, total = generator.discover()
        self.assertEqual(total, 5)
        self.assertEqual([p.name for p in projects], ["public-one", "private-one"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("conflict", warnings[0])

    def test_private_repository_only_uses_name_and_description(self):
        with patch.object(generator, "gh", side_effect=self.fake_gh):
            projects, warnings, _ = generator.discover()
            generator.enrich_public(projects, warnings, images=False)
        private = next(p for p in projects if p.private)
        self.assertEqual(private.name, "private-one")
        self.assertEqual(private.description, "Private demo")
        self.assertIsNone(private.github_url)
        self.assertIsNone(private.image)
        self.assertEqual(private.readme_html, "")
        self.assertIn("Example", next(p for p in projects if not p.private).readme_html)

    def test_sanitizer_discards_script_and_javascript_urls(self):
        clean = generator.CleanHTML("zonaro/public-one", "main")
        clean.feed('<a href="javascript:alert(1)" onclick="bad()">Click</a>'
                   '<img src="https://example.org/a.png" onerror="bad()">'
                   '<script>alert(1)</script>')
        result = clean.finish()
        self.assertNotIn("javascript:", result)
        self.assertNotIn("onclick", result)
        self.assertNotIn("<script", result)

    def test_static_generation_is_repeatable_and_private_page_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text(
                '<div><!-- PORTFOLIO:SHOWCASE:START -->old<!-- PORTFOLIO:SHOWCASE:END --></div>'
                '<ul><!-- PORTFOLIO:CATALOG:START -->old<!-- PORTFOLIO:CATALOG:END --></ul>'
                '<span id="repo-count">45</span>', encoding="utf-8")
            (root / "llms.txt").write_text('# Profile\n\n## Projetos abertos em destaque\nOld\n', encoding="utf-8")
            (root / "profile.json").write_text('{"featured_public_repositories":[]}', encoding="utf-8")
            with patch.object(generator, "ROOT", root), patch.object(generator, "gh", side_effect=self.fake_gh):
                projects, warnings, _ = generator.discover()
                generator.enrich_public(projects, warnings, images=False)
                generator.generate(projects)
                before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                generator.generate(projects)
                after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            private_html = (root / "projects/private-one/index.html").read_text(encoding="utf-8")
            self.assertNotIn("github.com/zonaro/private-one", private_html)
            self.assertNotIn("README", private_html)
            self.assertIn("Private demo", private_html)
            self.assertFalse(any(b"hidden-private" in contents for contents in after.values()))


if __name__ == "__main__":
    unittest.main()
