#!/usr/bin/env python3
"""Local-only dashboard to curate GitHub repository topics with the logged-in gh CLI.

Never bind this server to a network interface: it exposes private repo names and
descriptions to the local authenticated user. It never reads repository READMEs.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import webbrowser

try:
    from scripts.portfolio_art import default_colors, make_cover_svg, sanitize_svg
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    # Direct execution: python3 scripts/portfolio_dashboard.py
    from portfolio_art import default_colors, make_cover_svg, sanitize_svg


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "scripts" / "dashboard"
OWNER = "zonaro"
TOPICS = {"portfolio-primary": "primary", "portfolio-secondary": "secondary", "portfolio-catalog": "catalog"}
CATEGORIES = {"hidden", *TOPICS.values()}
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
FIELDS = "name,nameWithOwner,description,isPrivate,repositoryTopics"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def gh(*args: str, input_text: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["gh", *args], input=input_text, text=True, capture_output=True,
            timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApiError(502, f"Não foi possível executar gh: {exc}") from exc
    if result.returncode:
        # Do not expose raw command arguments or credentials in an HTTP response.
        raise ApiError(502, f"GitHub CLI falhou: {result.stderr.strip()[:250]}")
    return result.stdout


def run_local(*args: str, timeout: int) -> str:
    try:
        result = subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApiError(502, f"A execução local falhou: {exc}") from exc
    if result.returncode:
        details = (result.stderr or result.stdout).strip()[-2500:]
        raise ApiError(409, f"Comando não concluído: {details}")
    return result.stdout.strip()[-6000:]


def topics_from_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return sorted({str(t.get("name", "")).lower() for t in raw if isinstance(t, dict) and t.get("name")})


def category_of(topics: list[str]) -> str:
    present = set(topics) & TOPICS.keys()
    return "conflict" if len(present) > 1 else TOPICS[next(iter(present))] if present else "hidden"


def repo_list() -> list[dict]:
    try:
        raw = json.loads(gh("repo", "list", OWNER, "--limit", "1000", "--json", FIELDS))
    except json.JSONDecodeError as exc:
        raise ApiError(502, "Resposta inválida ao listar repositórios") from exc
    if not isinstance(raw, list):
        raise ApiError(502, "Lista de repositórios inválida")
    result = []
    for repo in raw:
        name = repo.get("name", "")
        if not NAME_PATTERN.fullmatch(name) or repo.get("nameWithOwner", "").lower() != f"{OWNER}/{name}".lower():
            continue
        topics = topics_from_list(repo.get("repositoryTopics"))
        result.append({
            "name": name,
            "description": repo.get("description") or "",
            "private": bool(repo.get("isPrivate")),
            "topics": topics,
            "category": category_of(topics),
            "url": f"https://github.com/{OWNER}/{name}",
        })
    return sorted(result, key=lambda repo: repo["name"].casefold())


def update_category(name: str, category: str, expected_topics: list[str]) -> dict:
    if not NAME_PATTERN.fullmatch(name):
        raise ApiError(400, "Nome de repositório inválido")
    if category not in CATEGORIES:
        raise ApiError(400, "Categoria inválida")
    if not isinstance(expected_topics, list) or any(not isinstance(t, str) for t in expected_topics):
        raise ApiError(400, "Topics de origem inválidas")

    endpoint = f"repos/{OWNER}/{name}/topics"
    try:
        current_json = json.loads(gh("api", endpoint))
        current = sorted(current_json["names"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ApiError(502, "Não foi possível conferir as topics atuais") from exc

    # Optimistic concurrency: don't silently overwrite unrelated topic edits.
    if current != sorted(set(expected_topics)):
        raise ApiError(409, "As topics mudaram no GitHub. Atualize a lista antes de salvar.")
    updated = [topic for topic in current if topic not in TOPICS]
    if category != "hidden":
        updated.append(next(topic for topic, value in TOPICS.items() if value == category))
    updated.sort()
    if updated != current:
        try:
            response = json.loads(gh("api", "--method", "PUT", endpoint, "--input", "-",
                                     input_text=json.dumps({"names": updated})))
        except json.JSONDecodeError as exc:
            raise ApiError(502, "GitHub retornou confirmação inválida") from exc
        if sorted(response.get("names", [])) != updated:
            raise ApiError(502, "GitHub não confirmou as topics solicitadas")
    return {"name": name, "category": category, "topics": updated}


def update_description(name: str, description: str, expected_description: str) -> dict:
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ApiError(400, "Nome de repositório inválido")
    if (not isinstance(description, str) or len(description) > 350
            or not isinstance(expected_description, str)):
        raise ApiError(400, "Descrição inválida (máximo de 350 caracteres)")
    full_name = f"{OWNER}/{name}"
    try:
        current = json.loads(gh("api", f"repos/{OWNER}/{name}"))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiError(502, "Não foi possível conferir a descrição atual") from exc
    if current.get("full_name") != full_name:
        raise ApiError(409, "O repositório mudou. Atualize a lista")
    if (current.get("description") or "") != expected_description:
        raise ApiError(409, "A descrição mudou no GitHub. Atualize a lista antes de editar")
    if description != expected_description:
        gh("repo", "edit", full_name, "--description", description)
    return {"name": name, "description": description}


def delete_repository(name: str, confirmation: str, expected_topics: list[str], expected_private: bool) -> dict:
    """Delete only the exact owned repository the user confirmed in the UI.

    A fresh metadata request ensures the repository still matches the listing
    that the user reviewed. No README or source content is requested.
    """
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ApiError(400, "Nome de repositório inválido")
    full_name = f"{OWNER}/{name}"
    if name.casefold() == "zonaro.github.io":
        raise ApiError(403, "O repositório deste portfólio está protegido contra exclusão pelo painel")
    if confirmation != full_name:
        raise ApiError(400, f"Digite exatamente {full_name} para confirmar a exclusão")
    if (not isinstance(expected_topics, list)
            or any(not isinstance(topic, str) for topic in expected_topics)
            or not isinstance(expected_private, bool)):
        raise ApiError(400, "Dados de conferência inválidos. Atualize a lista")

    try:
        current = json.loads(gh("api", f"repos/{OWNER}/{name}"))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiError(502, "Não foi possível conferir o repositório antes da exclusão") from exc
    if (current.get("full_name") != full_name
            or current.get("owner", {}).get("login") != OWNER):
        raise ApiError(409, "A identidade do repositório mudou. Atualize a lista")
    if current.get("permissions", {}).get("admin") is not True:
        raise ApiError(403, "Sua conta não possui permissão de administrador para excluir este repositório")
    if (sorted(current.get("topics", [])) != sorted(set(expected_topics))
            or current.get("private") is not expected_private):
        raise ApiError(409, "Os dados do repositório mudaram. Atualize a lista antes de excluir")

    gh("repo", "delete", full_name, "--yes")
    return {"deleted": full_name}


def cover_path(name: str) -> Path:
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ApiError(400, "Nome de repositório inválido")
    return ROOT / "assets" / "portfolio-covers" / f"{name.lower()}.svg"


def current_cover(name: str) -> dict:
    path = cover_path(name)
    if path.is_symlink():
        raise ApiError(400, "Capa vinculada a arquivo externo não é permitida")
    custom = path.exists()
    try:
        svg = sanitize_svg(path.read_text(encoding="utf-8") if custom else make_cover_svg(name))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ApiError(400, f"Não foi possível abrir a capa: {exc}") from exc
    background, accent = default_colors(name)
    return {"name": name, "svg": svg, "custom": custom,
            "default_background": background, "default_accent": accent}


def update_cover(name: str, body: dict) -> dict:
    path = cover_path(name)
    if path.is_symlink():
        raise ApiError(400, "Capa vinculada a arquivo externo não é permitida")
    try:
        if body.get("mode") == "preset":
            svg = make_cover_svg(name, style=body.get("style", "orbits"),
                                 icon=body.get("icon", "auto"),
                                 background=body.get("background"), accent=body.get("accent"))
        elif body.get("mode") == "svg":
            svg = body.get("svg")
        else:
            raise ValueError("Modo de capa inválido")
        svg = sanitize_svg(svg)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return {"name": name, "svg": svg, "custom": True}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ZonaroDashboard/1"

    def _allowed_host(self) -> bool:
        return self.headers.get("Host", "") in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}",
        }

    def _authenticated(self) -> bool:
        return self.headers.get("X-Dashboard-Token") == self.server.token

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict | list) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self._allowed_host():
            return self._json(403, {"error": "Acesso permitido apenas via localhost"})
        path = urlsplit(self.path).path
        if path in {"/", "/dashboard.css", "/dashboard.js"}:
            filename = {"/": "index.html", "/dashboard.css": "dashboard.css", "/dashboard.js": "dashboard.js"}[path]
            data = (UI / filename).read_text(encoding="utf-8")
            if path == "/":
                data = data.replace("__DASHBOARD_TOKEN__", self.server.token)
            content_type = "text/html" if path == "/" else "text/css" if path.endswith(".css") else "text/javascript"
            return self._send(200, data.encode("utf-8"), content_type + "; charset=utf-8")
        if path not in {"/api/repos", "/api/cover"}:
            return self._json(404, {"error": "Rota inexistente"})
        if not self._authenticated():
            return self._json(403, {"error": "Sessão inválida"})
        try:
            if path == "/api/cover":
                name = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
                return self._json(200, current_cover(name))
            return self._json(200, {"repositories": repo_list()})
        except ApiError as exc:
            return self._json(exc.status, {"error": str(exc)})

    def do_POST(self) -> None:
        if not self._allowed_host() or not self._authenticated():
            return self._json(403, {"error": "Sessão inválida"})
        origin = self.headers.get("Origin")
        if origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
            return self._json(403, {"error": "Origem não permitida"})
        path = urlsplit(self.path).path
        if path not in {"/api/classify", "/api/description", "/api/cover", "/api/delete", "/api/preview", "/api/publish"}:
            return self._json(404, {"error": "Rota inexistente"})
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            return self._json(415, {"error": "Use application/json"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 2 or size > (110_000 if path == "/api/cover" else 8192):
                raise ValueError("Tamanho inválido")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Objeto esperado")
            if not self.server.job_lock.acquire(blocking=False):
                return self._json(409, {"error": "Outra operação ainda está em andamento"})
            try:
                if path == "/api/classify":
                    result = update_category(body.get("name", ""), body.get("category", ""), body.get("expected_topics"))
                    self.server.preview_ready = False
                    return self._json(200, result)
                if path == "/api/description":
                    result = update_description(body.get("name", ""), body.get("description"),
                                                body.get("expected_description"))
                    self.server.preview_ready = False
                    return self._json(200, result)
                if path == "/api/cover":
                    result = update_cover(body.get("name", ""), body)
                    self.server.preview_ready = False
                    return self._json(200, result)
                if path == "/api/delete":
                    result = delete_repository(body.get("name", ""), body.get("confirmation", ""),
                                               body.get("expected_topics"), body.get("expected_private"))
                    self.server.preview_ready = False
                    return self._json(200, result)
                if path == "/api/preview":
                    result = run_local("python3", "scripts/generate_portfolio.py", timeout=240)
                    status = run_local("git", "status", "--short", timeout=20)
                    self.server.preview_ready = True
                    return self._json(200, {"summary": result + "\nArquivos modificados:\n" + (status or "Nenhuma alteração")})
                if body.get("confirm") != "PUBLICAR" or not self.server.preview_ready:
                    raise ApiError(409, "Gere uma prévia nesta sessão e confirme PUBLICAR antes do envio")
                result = run_local("bash", "scripts/update-portfolio.sh", "--publish", "--yes", timeout=300)
                self.server.preview_ready = False
                return self._json(200, {"summary": result})
            finally:
                self.server.job_lock.release()
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            return self._json(400, {"error": f"Requisição inválida: {exc}"})
        except ApiError as exc:
            return self._json(exc.status, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        # Avoid printing private descriptions or request contents to terminals/logs.
        print(f"[dashboard] {self.address_string()} {fmt % args}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard local de curadoria de repositórios")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1024 e 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    server.token = secrets.token_urlsafe(32)
    server.preview_ready = False
    server.job_lock = threading.Lock()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Dashboard local: {url} (Ctrl+C para encerrar)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
