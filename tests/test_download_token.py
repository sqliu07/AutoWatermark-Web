from urllib.parse import parse_qs, urlparse

import pytest

from services import download_token


def test_build_signed_url_uses_url_encoding(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_TOKEN_SECRET", "test-secret-for-ci-only-at-least-32-bytes")

    url = download_token.build_signed_url(
        "/upload/demo.jpg",
        "demo.jpg",
        lang="zh-CN",
        note="hello world&x=1",
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/upload/demo.jpg"
    assert query["lang"] == ["zh-CN"]
    assert query["note"] == ["hello world&x=1"]
    assert "token" in query
    assert "expires" in query


def test_generate_token_requires_secret(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_TOKEN_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        download_token.generate_token("demo.jpg")


def test_token_is_bound_to_action_and_burn(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_TOKEN_SECRET", "test-secret-for-ci-only-at-least-32-bytes")

    token, expires = download_token.generate_token("demo.jpg", action="download", burn="1")

    assert download_token.verify_token("demo.jpg", token, expires, action="download", burn="1")
    assert not download_token.verify_token("demo.jpg", token, expires, action="preview", burn="1")
    assert not download_token.verify_token("demo.jpg", token, expires, action="download", burn="0")


def test_build_signed_url_adds_action_claim(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_TOKEN_SECRET", "test-secret-for-ci-only-at-least-32-bytes")

    url = download_token.build_signed_url("/api/download/demo.jpg", "demo.jpg", action="download", burn="1")
    query = parse_qs(urlparse(url).query)

    assert query["action"] == ["download"]
    assert query["burn"] == ["1"]
    assert download_token.verify_token(
        "demo.jpg",
        query["token"][0],
        query["expires"][0],
        action=query["action"][0],
        burn=query["burn"][0],
    )


@pytest.mark.parametrize("token", [None, 12, [], {}, "密钥", "a" * 33, "G" * 32])
def test_invalid_token_input_fails_closed(token):
    assert not download_token.verify_token("demo.jpg", token, "9999999999", action="preview")


@pytest.mark.parametrize("expires", [None, [], {}, True, 1.5, pytest.param("9" * 5000, id="overlong"),
                                    pytest.param(10 ** 5000, id="huge-integer"), "１２３", "-1"])
def test_invalid_expiry_input_fails_closed(expires):
    assert not download_token.verify_token("demo.jpg", "a" * 32, expires, action="preview")
