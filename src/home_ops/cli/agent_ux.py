"""Agentic UX CLI subcommands for location, cadastre, and portal adapter inspection."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import typer
from rich.console import Console

from home_ops.cadastre.registry import get_cadastre_provider
from home_ops.cli.profile import COUNTRY_DEFAULTS
from home_ops.scraper.portals import PORTALS, Portal

console = Console()

location_app = typer.Typer(help="Location inspection commands.")
cadastre_app = typer.Typer(help="Official cadastre provider inspection.")
adapter_app = typer.Typer(help="Portal adapter verification.")


def _geocode_location(location: str) -> str | None:
    params = urllib.parse.urlencode({
        "q": location,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "1",
    })
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "Home-Ops/0.1 (location-inspect)"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        results = json.load(response)
    if not results:
        return None
    country_code = results[0].get("address", {}).get("country_code", "").upper()
    return country_code or None


@location_app.command("inspect")
def location_inspect(
    location: str = typer.Argument(..., help="Country code (ISO-2) or municipality name"),
) -> None:
    """Inspect location, default currency, units, timezone, and national rules."""
    municipality = location.strip()
    loc_clean = municipality.upper()
    if loc_clean in COUNTRY_DEFAULTS:
        country_code = loc_clean
    elif len(loc_clean) == 2:
        console.print(f"[bold red]Error:[/bold red] Country '{municipality}' is not supported.")
        raise typer.Exit(code=1)
    else:
        try:
            geocoded_country = _geocode_location(municipality)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] Geocoding failed: {exc}")
            raise typer.Exit(code=1) from exc
        if not geocoded_country:
            console.print(f"[bold red]Error:[/bold red] Could not geocode '{municipality}'.")
            raise typer.Exit(code=1)
        if geocoded_country not in COUNTRY_DEFAULTS:
            console.print(f"[bold red]Error:[/bold red] Country '{geocoded_country}' is not supported.")
            raise typer.Exit(code=1)
        country_code = geocoded_country

    _, currency, timezone, area_unit = COUNTRY_DEFAULTS[country_code]

    is_es = country_code in ("ES", "SPAIN")
    gates_status = "Active" if is_es else "Inactive"

    console.print(f"[bold cyan]Location Inspection:[/bold cyan] {municipality}")
    console.print(f"  [bold]Country Code:[/bold] {country_code}")
    console.print(f"  [bold]Currency:[/bold] {currency}")
    console.print(f"  [bold]Area Unit:[/bold] {area_unit}")
    console.print(f"  [bold]Timezone:[/bold] {timezone}")
    console.print(f"  [bold]Spanish National Gates:[/bold] {gates_status}")


@cadastre_app.command("show")
def cadastre_show(
    country_code: str = typer.Argument(..., help="ISO 2-letter country code"),
) -> None:
    """Show registered official cadastre or land registry provider metadata."""
    provider = get_cadastre_provider(country_code)
    if not provider:
        console.print(f"[bold red]Error:[/bold red] Cadastre provider for '{country_code}' not found.")
        raise typer.Exit(code=1)

    auto_label = "Automatic (OVC runtime)" if provider.is_automated else "Manual / Regional"
    console.print(f"[bold cyan]Official Cadastre Provider:[/bold cyan] {provider.country_name} ({provider.country_code})")
    console.print(f"  [bold]Authority:[/bold] {provider.authority_name}")
    console.print(f"  [bold]Portal URL:[/bold] {provider.portal_url}")
    if provider.api_url:
        console.print(f"  [bold]API URL:[/bold] {provider.api_url}")
    console.print(f"  [bold]Access Mode:[/bold] {auto_label}")
    console.print(f"  [bold]Description:[/bold] {provider.description}")


@adapter_app.command("verify")
def adapter_verify(
    portal_name: str = typer.Argument(..., help="Portal adapter name"),
) -> None:
    """Verify runtime support and parser state for a property portal adapter."""
    name_clean = portal_name.strip().lower()
    matching: list[Portal] = [
        p for p in PORTALS.values()
        if p.name.lower() == name_clean or any(name_clean in d for d in p.domains)
    ]

    if not matching:
        console.print(f"[bold red]Error:[/bold red] Portal adapter '{portal_name}' unsupported.")
        raise typer.Exit(code=1)

    portal = matching[0]
    console.print(f"[bold green]Adapter Verified:[/bold green] {portal.name} (PASS)")
    console.print(f"  [bold]Supported Domains:[/bold] {', '.join(portal.domains)}")
    console.print(f"  [bold]Parser Engine:[/bold] {portal.parser}")
