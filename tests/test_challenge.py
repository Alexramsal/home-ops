"""Tests for anti-bot challenge detection and sources validation integration."""

from __future__ import annotations

from home_ops.scraper.challenge import (
    ChallengeKind,
    ChallengeResult,
    detect_challenge,
)


def test_detect_challenge_clean() -> None:
    res = detect_challenge("<html><body><h1>Normal Page</h1></body></html>")
    assert res == ChallengeResult(
        kind=ChallengeKind.NONE,
        detected=False,
        details="Clean page",
    )


def test_detect_challenge_cloudflare() -> None:
    res1 = detect_challenge("<div id='cf-browser-verification'></div>")
    assert res1.detected is True
    assert res1.kind == ChallengeKind.CLOUDFLARE

    res2 = detect_challenge("<script>var cf_challenge = true;</script>")
    assert res2.detected is True
    assert res2.kind == ChallengeKind.CLOUDFLARE

    res3 = detect_challenge("<html>ShieldSquare Anti-Bot</html>")
    assert res3.detected is True
    assert res3.kind == ChallengeKind.CLOUDFLARE


def test_detect_challenge_perfdrive() -> None:
    res1 = detect_challenge("<script src='https://validate.perfdrive.com/captcha'></script>")
    assert res1.detected is True
    assert res1.kind == ChallengeKind.PERFDRIVE

    res2 = detect_challenge("<html><body>Error ssk=block</body></html>")
    assert res2.detected is True
    assert res2.kind == ChallengeKind.PERFDRIVE


def test_detect_challenge_datadome() -> None:
    res1 = detect_challenge("<script src='https://geo.captcha-delivery.com/captcha/'></script>")
    assert res1.detected is True
    assert res1.kind == ChallengeKind.DATADOME

    res2 = detect_challenge("<html>DataDome protection active</html>")
    assert res2.detected is True
    assert res2.kind == ChallengeKind.DATADOME


def test_detect_challenge_captcha() -> None:
    res1 = detect_challenge("<div class='g-recaptcha' data-sitekey='xyz'></div>")
    assert res1.detected is True
    assert res1.kind == ChallengeKind.CAPTCHA

    res2 = detect_challenge("<div class='h-captcha' data-sitekey='abc'></div>")
    assert res2.detected is True
    assert res2.kind == ChallengeKind.CAPTCHA

    res3 = detect_challenge("<div class='cf-turnstile' data-sitekey='123'></div>")
    assert res3.detected is True
    assert res3.kind == ChallengeKind.CAPTCHA


def test_detect_challenge_login_paywall() -> None:
    res1 = detect_challenge("<div class='login-required'>Please log in</div>")
    assert res1.detected is True
    assert res1.kind == ChallengeKind.LOGIN_PAYWALL

    res2 = detect_challenge("<html>Inicia sesion para continuar</html>")
    assert res2.detected is True
    assert res2.kind == ChallengeKind.LOGIN_PAYWALL


def test_detect_challenge_rate_limit() -> None:
    res = detect_challenge("Too many requests", status_code=429)
    assert res.detected is True
    assert res.kind == ChallengeKind.RATE_LIMIT


def test_detect_challenge_unknown_status() -> None:
    res = detect_challenge("Internal Server Error", status_code=500)
    assert res.detected is True
    assert res.kind == ChallengeKind.UNKNOWN


def test_validate_source_challenge_detected() -> None:
    from home_ops.cli.sources import validate_source

    cf_html = "<html><div id='cf-challenge'>Cloudflare check</div></html>"
    ok, reason, count = validate_source(
        "https://www.pisos.com/venta/pisos-cadiz/",
        fetcher=lambda url: cf_html,
    )
    assert ok is False
    assert "Challenge detected" in reason or "CLOUDFLARE" in reason
    assert count == 0
