import json
from pathlib import Path

import pytest
from starlette.requests import Request

from app import i18n


@pytest.fixture(autouse=True)
def _clear_i18n_caches() -> None:
    i18n.available_locales.cache_clear()
    i18n.load_catalog.cache_clear()
    yield
    i18n.available_locales.cache_clear()
    i18n.load_catalog.cache_clear()


def _request(
    *,
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": query_string,
            "headers": headers or [],
        }
    )


def _write_locale(directory: Path, locale: str, payload: dict[str, object]) -> None:
    (directory / f"{locale}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_available_locales_requires_default_locale(tmp_path, monkeypatch) -> None:
    _write_locale(tmp_path, "de", {"common": {"app_name": "Listerine"}})
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    i18n.available_locales.cache_clear()
    i18n.load_catalog.cache_clear()

    with pytest.raises(RuntimeError):
        i18n.available_locales()


def test_load_catalog_translate_and_translator_cover_fallbacks(tmp_path, monkeypatch) -> None:
    _write_locale(
        tmp_path,
        "en",
        {
            "greeting": {"welcome": "Welcome {name}"},
            "group": {"label": {"one": "{count} list", "other": "{count} lists"}},
        },
    )
    _write_locale(tmp_path, "de", {"greeting": {}})
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    i18n.available_locales.cache_clear()
    i18n.load_catalog.cache_clear()

    assert i18n.available_locales() == ("de", "en")
    assert i18n.load_catalog("fr") == i18n.load_catalog("en")
    assert i18n.translate("en", "greeting.welcome", name="Taylor") == "Welcome Taylor"
    assert i18n.translate("en", "greeting.welcome") == "Welcome {name}"
    assert i18n.translate("de", "greeting.welcome", name="Alex") == "Welcome Alex"
    assert i18n.translate("de", "missing.key") == "missing.key"
    with pytest.raises(TypeError):
        i18n.translate("de", "group.label")

    translator = i18n.translator_for("en")
    assert translator("greeting.welcome", name="Sam") == "Welcome Sam"


def test_resolve_locale_uses_query_then_cookie_then_accept_language(monkeypatch) -> None:
    monkeypatch.setattr(i18n, "available_locales", lambda: ("en", "de"))

    assert i18n.resolve_locale(_request(query_string=b"lang=de")) == "de"
    assert i18n.resolve_locale(_request(headers=[(b"cookie", b"listerine_locale=de")])) == "de"
    assert (
        i18n.resolve_locale(_request(headers=[(b"accept-language", b"de-DE,de;q=0.9,en;q=0.8")]))
        == "de"
    )
    assert i18n.resolve_locale(_request(headers=[(b"accept-language", b"fr-CA, en;q=0.8")])) == "en"
    assert i18n.resolve_locale(_request(headers=[(b"accept-language", b"fr-CA")])) == "en"
    assert i18n.resolve_locale(_request()) == "en"
