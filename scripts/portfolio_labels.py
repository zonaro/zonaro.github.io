"""Colored public portfolio labels, assigned via GitHub repository topics.

The registry stores *definitions only*, never repository associations. An
unselected/private repository cannot leak through this tracked JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata


TOPIC_PREFIX = "portfolio-label-"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SLUG = 50 - len(TOPIC_PREFIX)


def label_slug(name: str) -> str:
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 48):
        raise ValueError("Nome da tag deve ter entre 1 e 48 caracteres")
    ascii_name = unicodedata.normalize("NFKD", name.strip()).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug or len(slug) > MAX_SLUG:
        raise ValueError(f"Nome da tag precisa formar um identificador de até {MAX_SLUG} caracteres")
    return slug


def load_labels(root: Path) -> dict[str, dict[str, str]]:
    path = root / "scripts" / "portfolio_labels.json"
    if path.is_symlink():
        raise ValueError("Registro de tags não pode ser um link simbólico")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Arquivo de tags inválido") from exc
    if not isinstance(data, dict) or set(data) != {"labels"} or not isinstance(data["labels"], dict):
        raise ValueError("Formato do arquivo de tags inválido")
    labels = data["labels"]
    if len(labels) > 100:
        raise ValueError("Limite de 100 tags excedido")
    for slug, meta in labels.items():
        if (not isinstance(slug, str) or len(slug) > MAX_SLUG or not SLUG_PATTERN.fullmatch(slug)
                or not isinstance(meta, dict) or set(meta) != {"name", "color"}
                or not isinstance(meta["name"], str) or not (1 <= len(meta["name"].strip()) <= 48)
                or not isinstance(meta["color"], str) or not HEX_PATTERN.fullmatch(meta["color"])):
            raise ValueError("Definição de tag inválida")
    return labels


def write_labels(root: Path, labels: dict[str, dict[str, str]]) -> None:
    path = root / "scripts" / "portfolio_labels.json"
    if path.is_symlink():
        raise ValueError("Registro de tags não pode ser um link simbólico")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"labels": labels}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def applied_labels(topics: list[str] | set[str], palette: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    return [{"slug": slug, **palette[slug]} for slug in sorted(palette)
            if TOPIC_PREFIX + slug in topics]
