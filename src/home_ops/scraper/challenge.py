"""Anti-bot challenge and verification detector for scraper runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChallengeKind(StrEnum):
    CAPTCHA = "CAPTCHA"
    CLOUDFLARE = "CLOUDFLARE"
    DATADOME = "DATADOME"
    PERFDRIVE = "PERFDRIVE"
    LOGIN_PAYWALL = "LOGIN_PAYWALL"
    RATE_LIMIT = "RATE_LIMIT"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


@dataclass(frozen=True)
class ChallengeResult:
    kind: ChallengeKind
    detected: bool
    details: str


_SIGNATURES: list[tuple[ChallengeKind, tuple[str, ...]]] = [
    (
        ChallengeKind.CLOUDFLARE,
        ("shieldsquare", "cf-browser-verification", "cf-challenge", "cf_challenge"),
    ),
    (
        ChallengeKind.PERFDRIVE,
        ("validate.perfdrive.com", "ssk=block"),
    ),
    (
        ChallengeKind.DATADOME,
        ("datadome", "geo.captcha-delivery.com"),
    ),
    (
        ChallengeKind.CAPTCHA,
        ("g-recaptcha", "h-captcha", "cf-turnstile"),
    ),
    (
        ChallengeKind.LOGIN_PAYWALL,
        ("login-required", "inicia sesion para continuar", "inicia sesión para continuar"),
    ),
]


def detect_challenge(
    html: str,
    status_code: int = 200,
    url: str = "",
) -> ChallengeResult:
    """Detect anti-bot challenges or access restrictions in HTTP responses."""
    if status_code == 429:
        return ChallengeResult(
            kind=ChallengeKind.RATE_LIMIT,
            detected=True,
            details="HTTP 429 Rate Limit",
        )

    html_lower = html.lower() if html else ""

    for kind, sigs in _SIGNATURES:
        for sig in sigs:
            if sig in html_lower:
                return ChallengeResult(
                    kind=kind,
                    detected=True,
                    details=f"{kind.value} challenge detected ({sig})",
                )

    if status_code != 200:
        return ChallengeResult(
            kind=ChallengeKind.UNKNOWN,
            detected=True,
            details=f"HTTP status {status_code}",
        )

    return ChallengeResult(
        kind=ChallengeKind.NONE,
        detected=False,
        details="Clean page",
    )
