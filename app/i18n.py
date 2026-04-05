import base64
import json
from functools import lru_cache
from pathlib import Path

from fastapi import Request

DEFAULT_LOCALE = "en"
LOCALE_COOKIE_NAME = "listerine_locale"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache
def available_locales() -> tuple[str, ...]:
    locales = sorted(path.stem for path in LOCALES_DIR.glob("*.json"))
    if DEFAULT_LOCALE not in locales:
        raise RuntimeError(f"Default locale '{DEFAULT_LOCALE}' is missing.")
    return tuple(locales)


@lru_cache
def load_catalog(locale: str) -> dict[str, object]:
    normalized_locale = locale if locale in available_locales() else DEFAULT_LOCALE
    with (LOCALES_DIR / f"{normalized_locale}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_locale(request: Request) -> str:
    requested_locale = request.query_params.get("lang")
    if requested_locale in available_locales():
        return requested_locale

    cookie_locale = request.cookies.get(LOCALE_COOKIE_NAME)
    if cookie_locale in available_locales():
        return cookie_locale

    accepted_locales = request.headers.get("accept-language", "")
    for entry in accepted_locales.split(","):
        locale = entry.split(";")[0].strip().lower()
        if not locale:
            continue
        candidates = [locale]
        if "-" in locale:
            candidates.append(locale.split("-", 1)[0])
        for candidate in candidates:
            if candidate in available_locales():
                return candidate

    return DEFAULT_LOCALE


def translate(locale: str, key: str, **params: object) -> str:
    value = _resolve_key(load_catalog(locale), key)
    if value is None and locale != DEFAULT_LOCALE:
        value = _resolve_key(load_catalog(DEFAULT_LOCALE), key)
    if value is None:
        return key
    if not isinstance(value, str):
        raise TypeError(f"Translation key '{key}' must resolve to a string.")
    if not params:
        return value
    return value.format(**params)


def translator_for(locale: str):
    return lambda key, **params: translate(locale, key, **params)


def encode_catalog(locale: str) -> str:
    serialized = json.dumps(load_catalog(locale), separators=(",", ":"))
    return base64.b64encode(serialized.encode("utf-8")).decode("ascii")


def _resolve_key(catalog: dict[str, object], key: str) -> object | None:
    current: object = catalog
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
