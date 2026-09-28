"""Multi-country Cadastre and Land Registry module for Home-Ops."""

from home_ops.cadastre.registry import (
    CADASTRE_REGISTRY,
    CadastreProvider,
    get_cadastre_provider,
)

__all__ = ["CadastreProvider", "CADASTRE_REGISTRY", "get_cadastre_provider"]
