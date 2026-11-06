#!/usr/bin/env python3
"""Generate the public portfolio from explicit GitHub repository topics.

Only public repositories have their README, image and extended metadata fetched.
For private repositories, the sole content fields read are name and description;
topics and visibility are used exclusively for the inclusion decision.
"""

from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
OWNER = "zonaro"
SITE = "https://zonaro.github.io"
TOPICS = {
    "portfolio-primary": "primary",
    "portfolio-secondary": "secondary",
    "portfolio-catalog": "catalog",
}
LIST_FIELDS = "name,nameWithOwner,description,isPrivate,repositoryTopics"
PUBLIC_FIELDS = (
    "openGraphImageUrl,usesCustomOpenGraphImage,primaryLanguage,"
    "homepageUrl,isFork,url,defaultBranchRef"
)


class GenerationError(Exception):
    pass


def gh(*args: str) -> str:
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, check=False, text=True, timeout=60
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise GenerationError(f"GitHub CLI indisponível: {exc}") from exc
    if result.returncode:
        raise GenerationError(
            f"gh {' '.join(args[:3])} falhou: {result.stderr.strip()[:300]}"
        )
    return result.stdout


def github_topics(raw: object) -> set[str]:
    if not isinstance(raw, list):
        return set()
    return {
        str(topic.get("name", "")).lower()
        for topic in raw
        if isinstance(topic, dict) and topic.get("name")
    }


@dataclass
class Project:
    name: str
    description: str
    category: str
    private: bool
    slug: str
    github_url: str | None = None
    homepage: str | None = None
    language: str | None = None
    image: str | None = None
    readme_html: str = ""

    def public_data(self) -> dict:
        # Never write private repo URLs, README content, or internal metadata.
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "private": self.private,
            "slug": self.slug,
            "url": f"/projects/{self.slug}/",
            "github_url": self.github_url,
            "homepage": self.homepage,
            "language": self.language,
            "image": self.image,
        }


def discover() -> tuple[list[Project], list[str], int]:
    raw = json.loads(gh("repo", "list", OWNER, "--limit", "1000", "--json", LIST_FIELDS))
    if not isinstance(raw, list):
        raise GenerationError("Resposta inesperada ao listar repositórios.")
    projects: list[Project] = []
    warnings: list[str] = []
    for repo in raw:
        name = str(repo.get("name", ""))
        full_name = str(repo.get("nameWithOwner", ""))
        if not name or full_name.rsplit("/", 1)[0].lower() != OWNER:
            continue
        found = github_topics(repo.get("repositoryTopics")) & TOPICS.keys()
        if not found:
            continue  # No topic => never published, public or private.
        if len(found) != 1:
            warnings.append(f"{name}: topics conflitantes ({', '.join(sorted(found))}); ignorado")
            continue
        category = TOPICS[next(iter(found))]
        slug = quote(name.lower(), safe="._-")
        projects.append(Project(
            name=name,
            description=str(repo.get("description") or ""),
            category=category,
            private=bool(repo.get("isPrivate")),
            slug=slug,
        ))
    projects.sort(key=lambda p: (list(TOPICS.values()).index(p.category), p.name.casefold()))
    return projects, warnings, len(raw)


SAFE_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "img",
    "pre", "code", "blockquote", "strong", "em", "b", "i", "del", "s", "br", "hr",
    "table", "thead", "tbody", "tr", "th", "td", "details", "summary", "kbd",
    "sup", "sub", "div", "span",
}
VOID_TAGS = {"img", "br", "hr"}


class CleanHTML(HTMLParser):
    """Small allowlist for GitHub-rendered public README HTML."""

    def __init__(self, repo: str, branch: str):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.repo = repo
        self.branch = branch

    def safe_url(self, value: str, image: bool) -> str | None:
        value = value.strip()
        if not value:
            return None
        if value.startswith("#") and not image:
            return value
        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"}:
            return value
        if parsed.scheme or value.startswith("//"):
            return None
        base = (
            f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/"
            if image else f"https://github.com/{self.repo}/blob/{self.branch}/"
        )
        return urljoin(base, value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in SAFE_TAGS:
            self.stack.append("")
            return
        values = dict(attrs)
        clean: list[str] = []
        for key in ("href", "src", "alt", "title"):
            value = values.get(key)
            if not value:
                continue
            if key in {"href", "src"}:
                value = self.safe_url(value, image=(key == "src"))
                if value is None:
                    continue
            clean.append(f' {key}="{html.escape(value, quote=True)}"')
        if tag == "a":
            clean.append(' rel="noopener noreferrer"')
        self.out.append(f"<{tag}{''.join(clean)}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS or not self.stack:
            return
        last = self.stack.pop()
        if last == tag:
            self.out.append(f"</{tag}>")
        elif last:
            # GitHub renders balanced HTML; malformed input is dropped safely.
            self.out.append(f"</{last}>")

    def handle_data(self, data: str) -> None:
        self.out.append(html.escape(data))

    def finish(self) -> str:
        while self.stack:
            tag = self.stack.pop()
            if tag:
                self.out.append(f"</{tag}>")
        return "".join(self.out)


def download_social_image(url: str, slug: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "repository-images.githubusercontent.com",
        "opengraph.githubassets.com",
    }:
        return None
    try:
        request = Request(url, headers={"User-Agent": "zonaro-portfolio-generator"})
        with urlopen(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(content_type)
            if not suffix:
                return None
            data = response.read(5_000_001)
            if len(data) > 5_000_000:
                return None
    except (OSError, URLError, ValueError):
        return None
    dest = ROOT / "assets" / "generated" / "covers" / f"{slug}{suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.read_bytes() != data:
        dest.write_bytes(data)
    return "/" + dest.relative_to(ROOT).as_posix()


def enrich_public(projects: list[Project], warnings: list[str], images: bool) -> None:
    for project in projects:
        if project.private:
            # Do not invoke repo view, README API or image download for private repos.
            continue
        full_name = f"{OWNER}/{project.name}"
        try:
            data = json.loads(gh("repo", "view", full_name, "--json", PUBLIC_FIELDS))
            project.github_url = f"https://github.com/{full_name}"
            homepage = data.get("homepageUrl")
            if homepage and urlsplit(homepage).scheme in {"https", "http"}:
                project.homepage = homepage
            language = data.get("primaryLanguage")
            if isinstance(language, dict):
                project.language = language.get("name")
            if images and data.get("usesCustomOpenGraphImage") and data.get("openGraphImageUrl"):
                project.image = download_social_image(data["openGraphImageUrl"], project.slug)
            branch = (data.get("defaultBranchRef") or {}).get("name") or "main"
            try:
                rendered = gh(
                    "api", f"repos/{full_name}/readme",
                    "-H", "Accept: application/vnd.github.html+json",
                )
                if len(rendered) > 500_000:
                    warnings.append(f"{project.name}: README excede 500 KB; descrição longa omitida")
                else:
                    cleaner = CleanHTML(full_name, branch)
                    cleaner.feed(rendered)
                    project.readme_html = cleaner.finish()
            except GenerationError:
                warnings.append(f"{project.name}: README público indisponível")
        except GenerationError as exc:
            warnings.append(f"{project.name}: metadados públicos indisponíveis ({exc})")


def e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def card(project: Project, number: int) -> str:
    image = (
        f'<img class="card-cover" src="{e(project.image)}" alt="Imagem de destaque de {e(project.name)}" loading="lazy">'
        if project.image else f'<span class="card-initial" aria-hidden="true">{e(project.name[:1].upper())}</span>'
    )
    detail = f"/projects/{project.slug}/"
    label = "DESTAQUE PRINCIPAL" if project.category == "primary" else "DESTAQUE SECUNDÁRIO"
    privacy = '<span class="private-label">PROJETO PRIVADO</span>' if project.private else '<span class="card-arrow">↗</span>'
    chips = '<span>Projeto privado</span>' if project.private else (f'<span>{e(project.language)}</span>' if project.language else '')
    classes = " project-card-primary" if project.category == "primary" else ""
    return (
        f'        <a class="project-card{classes}" data-curation="{project.category}" href="{detail}">\n'
        f'          <div class="card-meta"><span>{number:02d} / {label}</span>{privacy}</div>\n'
        f'          <div class="card-art card-art-generated">{image}</div>\n'
        f'          <div class="card-content"><h3>{e(project.name)}</h3><p>{e(project.description)}</p>'
        f'<div class="chips">{chips}</div></div>\n'
        '        </a>'
    )


def replace_region(source: str, label: str, generated: str) -> str:
    start = f"<!-- PORTFOLIO:{label}:START -->"
    end = f"<!-- PORTFOLIO:{label}:END -->"
    if source.count(start) != 1 or source.count(end) != 1:
        raise GenerationError(f"Marcadores de {label} ausentes ou duplicados no index.html")
    before, rest = source.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + "\n" + generated + "\n        " + end + after


def generate_index(projects: list[Project]) -> str:
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    featured = [p for p in projects if p.category in {"primary", "secondary"}]
    catalog = [p for p in projects if p.category == "catalog"]
    showcase = "\n".join(card(p, i) for i, p in enumerate(featured, 1)) or (
        '        <p class="catalog-empty">Nenhum destaque selecionado no GitHub.</p>'
    )
    listings = "\n".join(
        f'          <li><a href="/projects/{p.slug}/">{e(p.name)} <span>↗</span></a></li>'
        for p in catalog
    ) or '          <li class="catalog-empty">Nenhum projeto no catálogo.</li>'
    source = replace_region(source, "SHOWCASE", showcase)
    source = replace_region(source, "CATALOG", listings)
    source = re.sub(r'(<span id="repo-count">)\d+(</span>)', rf'\g<1>{len(catalog)}\g<2>', source)
    source = source.replace("Repositórios públicos selecionados", "Projetos selecionados")
    source = source.replace("Um índice navegável dos projetos disponíveis no meu GitHub, com curadoria de temas. Forks e adaptações também aparecem na lista.",
                            "Projetos selecionados por meio das topics de classificação do GitHub.")
    source = source.replace("repositórios encontrados", "projetos encontrados")
    return source


def project_page(project: Project) -> str:
    title = e(project.name)
    desc = e(project.description or "Projeto de Gabriel Forti Zonaro")
    body = project.readme_html if not project.private else (
        '<p>Projeto privado. Apenas o nome e a descrição autorizados foram publicados.</p>'
    )
    if not body:
        body = '<p>Este projeto ainda não tem um README público disponível.</p>'
    image_meta = f'<meta property="og:image" content="{SITE}{e(project.image)}">' if project.image else ''
    actions = (
        f'<a class="button button-primary" href="{e(project.github_url)}" target="_blank" rel="noopener noreferrer">Ver no GitHub ↗</a>'
        if project.github_url else ''
    )
    if project.homepage:
        actions += f'<a class="button button-ghost" href="{e(project.homepage)}" target="_blank" rel="noopener noreferrer">Abrir projeto ↗</a>'
    return f'''<!doctype html>
<html lang="pt-BR" data-persona="dev">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="theme-color" content="#160c15">
  <meta name="description" content="{desc}">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title} · Zonaro">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{SITE}/projects/{project.slug}/">
  {image_meta}
  <link rel="canonical" href="{SITE}/projects/{project.slug}/">
  <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
  <link rel="stylesheet" href="/assets/styles.css">
  <title>{title} · Zonaro — Beatbox & Code</title>
</head>
<body>
  <a class="skip-link" href="#conteudo">Pular para o conteúdo</a>
  <header class="site-header">
    <a class="brand" href="/"><img class="brand-logo" src="/assets/redclaw-logo.svg" alt="" width="47" height="47"><span class="brand-text">ZONARO<span class="brand-sub">BEATBOX & CODE</span></span></a>
    <nav class="persona-nav" aria-label="Portfólio"><a class="persona-link active" href="/">← Desenvolvedor</a><a class="persona-link" href="/beatbox/">♫ Beatboxer</a></nav>
  </header>
  <main id="conteudo" class="section-shell project-detail">
    <p class="section-kicker">{e(project.category.upper())} {'· PROJETO PRIVADO' if project.private else ''}</p>
    <h1>{title}</h1>
    <p class="project-detail-lead">{desc}</p>
    <div class="hero-actions">{actions}<a class="button button-ghost" href="/#destaques">Voltar ao portfólio ←</a></div>
    <article class="project-readme">{body}</article>
  </main>
  <footer class="site-footer"><span>© Gabriel Forti Zonaro</span><span>BEATBOX & CODE</span><a href="/">Início ↗</a></footer>
</body>
</html>
'''


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def generate(projects: list[Project]) -> None:
    write_if_changed(ROOT / "index.html", generate_index(projects))
    directory = ROOT / "projects"
    expected: set[Path] = set()
    for project in projects:
        page = directory / project.slug / "index.html"
        expected.add(page)
        write_if_changed(page, project_page(project))
    # Only generated project pages are stored here; stale pages must not remain public.
    if directory.exists():
        for page in directory.glob("*/index.html"):
            if page not in expected:
                page.unlink()
                if not any(page.parent.iterdir()):
                    page.parent.rmdir()
    covers = ROOT / "assets/generated/covers"
    if covers.exists():
        expected_covers = {ROOT / p.image.lstrip("/") for p in projects if p.image}
        for cover in covers.iterdir():
            if cover.is_file() and cover not in expected_covers:
                cover.unlink()
    write_if_changed(
        ROOT / "assets/generated/projects.json",
        json.dumps([p.public_data() for p in projects], ensure_ascii=False, indent=2) + "\n",
    )
    sitemap = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for pathname in ["/", "/beatbox/", "/llms.txt"] + [f"/projects/{p.slug}/" for p in projects]:
        node = ET.SubElement(sitemap, "url")
        ET.SubElement(node, "loc").text = SITE + pathname
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(sitemap, encoding="unicode") + "\n"
    write_if_changed(ROOT / "sitemap.xml", xml)
    intro = (ROOT / "llms.txt").read_text(encoding="utf-8").split("## Projetos abertos em destaque")[0].split("## Projetos selecionados")[0]
    llms = intro + "## Projetos selecionados\n"
    for p in projects:
        llms += f"- [{p.name}]({SITE}/projects/{p.slug}/): {p.description}\n"
    llms += "\n## Privacidade\nProjetos privados são apresentados apenas com nome e descrição curta.\n"
    write_if_changed(ROOT / "llms.txt", llms)
    profile = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
    profile["featured_public_repositories"] = [p.github_url for p in projects if not p.private and p.category in {"primary", "secondary"}]
    write_if_changed(ROOT / "profile.json", json.dumps(profile, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Só listar projetos, sem ler READMEs ou alterar arquivos")
    parser.add_argument("--no-images", action="store_true", help="Não baixar imagens de Social Preview")
    args = parser.parse_args()
    try:
        projects, warnings, total = discover()
        counts = {name: sum(p.category == name for p in projects) for name in TOPICS.values()}
        print(f"Repositórios consultados: {total} | incluídos: {len(projects)} | "
              + " | ".join(f"{name}: {count}" for name, count in counts.items()))
        for p in projects:
            print(f"  {p.category:9} {p.name} {'[PRIVADO: nome + descrição somente]' if p.private else ''}")
        if not args.dry_run:
            enrich_public(projects, warnings, images=not args.no_images)
            generate(projects)
            print("Arquivos estáticos gerados. Revise o diff antes de publicar.")
        for warning in warnings:
            print("AVISO:", warning, file=sys.stderr)
        if warnings:
            return 2  # Publication wrapper must not push ambiguous/incomplete content.
        return 0
    except (GenerationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
