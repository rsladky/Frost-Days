"""Utilitaires partagés : résolution d'URL via l'API data.gouv et téléchargement."""

from __future__ import annotations

import shutil
import unicodedata
from pathlib import Path

import requests

from frost_days import config

_TIMEOUT = 60


def normalize(text: str) -> str:
    """Minuscule, sans accents ni espaces superflus — pour comparer des noms."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


def resolve_resource_url(slug: str, *must_contain: str) -> str | None:
    """Retourne l'URL de la 1re ressource du dataset dont l'URL contient tous les
    fragments donnés. ``None`` si l'API est injoignable ou rien ne correspond."""
    try:
        resp = requests.get(
            config.DATAGOUV_API.format(slug=slug), timeout=_TIMEOUT
        )
        resp.raise_for_status()
        resources = resp.json().get("resources", [])
    except (requests.RequestException, ValueError):
        return None

    for res in resources:
        url = res.get("url") or ""
        if all(fragment in url for fragment in must_contain):
            return url
    return None


def download(url: str, dest: Path) -> Path:
    """Télécharge ``url`` vers ``dest`` (en streaming) s'il n'existe pas déjà.

    Le téléchargement se fait dans un fichier temporaire renommé à la fin, pour
    éviter de laisser un fichier partiel en cache en cas d'interruption."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            shutil.copyfileobj(resp.raw, fh)
    tmp.replace(dest)
    return dest
