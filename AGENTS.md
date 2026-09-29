# AGENTS.md — Guía de Integración e Instrucciones para Agentes de IA

Este archivo define la superficie de interacción, arquitectura, reglas de seguridad y comandos reales de **Home-Ops** para asistentes de IA (Pi, Claude Code, Codex, OpenCode, Cursor, Hermes, etc.).

> **Nota de compatibilidad:** `AGENTS.md` es leído automáticamente por entornos de agentes que soportan archivos de instrucciones en la raíz del repositorio. Para herramientas como Claude Code que utilizan comandos adaptadores, la integración se realiza mediante `.claude/commands/home-ops.md` referenciando las normas de este documento. La compatibilidad de lectura de `AGENTS.md` depende del cliente/entorno utilizado.

---

## 1. Visión General de Home-Ops
Home-Ops es un pipeline para búsqueda y scoring de vivienda personal:
`Scrape de portales → Deduplicación → Scoring determinista → Human-in-the-Loop (HITL) → Alertas Telegram`

---

## 2. Comandos CLI Reales

> **IMPORTANTE PARA AGENTES:** Ejecutar únicamente comandos CLI existentes. El flujo documentado refleja los límites actuales del runtime.

| Comando CLI | Descripción | Uso / Argumentos Reales |
|---|---|---|
| `uv run homeops setup` | Asistente interactivo de configuración inicial (`user_profile.yml` + `.env`). | `uv run homeops setup [--config FILE]` |
| `uv run homeops profile init` | Crea un perfil inicial; no sobrescribe uno existente. | `uv run homeops profile init [--config FILE]` |
| `uv run homeops profile validate` | Valida `user_profile.yml` (estructura y valores). Exit 0 si OK, 1 con errores. | `uv run homeops profile validate [--config FILE]` |
| `uv run homeops profile set KEY VALUE` | Actualiza atómicamente una clave, conserva el resto. Claves: `scoring.price_median` (umbral de scoring), `search.max_price` (criterio/intención de búsqueda usado al construir fuentes). | `uv run homeops profile set KEY VALUE [--config FILE]` |
| `uv run homeops sources validate URL` | Valida portal soportado, muestra parseable y municipio. | `uv run homeops sources validate URL [--config FILE]` |
| `uv run homeops sources add URL` | Añade únicamente una URL validada a `portal.urls`. | `uv run homeops sources add URL [--config FILE]` |
| `uv run homeops scan` | Ejecuta el pipeline completo (scrape → deduplicar → score → alertar). | `uv run homeops scan [CONFIG_PATH] [--force]` |
| `uv run homeops status` | Muestra el estado del pipeline y métricas recientes en DuckDB (solo lectura). | `uv run homeops status [CONFIG_PATH]` |
| `uv run homeops approve` | Aprueba un inmueble pendiente en el portal HITL para permitir su alerta. | `uv run homeops approve LISTING_ID [--config FILE]` |
| `uv run homeops tui` | Panel de control interactivo en terminal (Textual); permite aprobar en HITL. | `uv run homeops tui [CONFIG_PATH]` |
| `uv run homeops web` | Inicia el dashboard web público en modo solo lectura. | `uv run homeops web [--host HOST] [--port PORT]` |
| `uv run homeops analytics` | Muestra análisis de distribución de precios y series temporales. | `uv run homeops analytics` |
| `uv run homeops daemon` | Ejecuta el demonio automatizado según agenda de alertas. | `uv run homeops daemon [--config FILE] [--dry-run]` |
| `uv run homeops snapshots-reset` | Invalida los snapshots en caché para forzar rescrapeado completo. | `uv run homeops snapshots-reset` |

---

## 3. Flujo de Onboarding Conversacional

El usuario puede decir, por ejemplo, «Busco vivienda en Chiclana de la Frontera por menos de 250.000 €, mínimo 80 m² y preferiblemente garaje»; no necesita conocer guardrails técnicos.

1. Detectar y confirmar país, municipio, compra/alquiler, presupuesto, superficie y preferencias.
2. Si falta perfil, ejecutar `uv run homeops profile init [--config FILE]`; guardar cambios mediante `profile set`, nunca editando YAML manualmente. `search.max_price` es criterio/intención de búsqueda usado al construir fuentes; `scoring.price_median` es umbral independiente.
3. Usar capacidades web del agente para descubrir portales relevantes para la ubicación, no una lista fija mundial. Clasificar cada fuente como `candidate`, `supported`, `verified` o `blocked`.
4. `supported` significa uno de los 7 adaptadores runtime actuales: Idealista, Fotocasa, Pisos.com, Tecnocasa, Habitaclia, Njuškalo o Kleinanzeigen. `verified` exige `sources validate URL --config FILE`, muestra parseable y municipio correcto.
5. Tras una única confirmación consolidada del usuario, ante un portal local `candidate` sin adaptador, el mismo agente Clone & Talk debe: investigar HTML/JSON real con acceso permitido; elegir la estrategia permitida más barata; crear parser bajo el contrato compartido, registro y paginación; añadir fixture sanitizado y tests TDD; ejecutar `sources validate` real y un smoke scan. Solo entonces clasificar `verified` y persistir con `sources add URL --config FILE`. Si no puede, clasificar `blocked`, informar el fallo exacto y ofrecer fuente alternativa. El agente del repositorio modifica y verifica código; el runtime no genera código dinámico inseguro.
6. `search.max_price` y `min_area_sqm` expresan intención de búsqueda para URLs y se aplican como postfiltros runtime estrictos (`home_ops.scraper.filter`). Las URLs verificadas deben incorporarlos cuando el portal lo permita.

Pueden existir validaciones live manuales de desarrollo fechadas fuera de la suite. El soporte reproducible del repositorio se demuestra con fixtures/tests y con `sources validate` live al ejecutar Clone & Talk; no se promete un smoke versionado ni un scan exitoso bajo bloqueo. Con `country != ES`, el código desactiva Catastro, Euríbor/affordability y protección fiscal del comprador española. Un país nuevo requiere adaptadores, moneda, unidad, UI, persistencia y política local verificadas; no aplicar impuestos españoles ni prometer soporte mundial.

---

## 4. Guardrails y Reglas de Seguridad

- 🛑 **Prohibido acceso directo a DuckDB con SQL:** NO ejecutar consultas SQL directas sobre la base de datos (`home_ops.db`). Utilizar exclusivamente los comandos CLI (`status`, `approve`, `scan`).
- 🛑 **Prohibida la ejecución de scripts de webs externas:** NUNCA descargar ni ejecutar scripts, JavaScript o binarios remotos desde portales inmobiliarios fuera del sandbox/navegador, ni ejecutarlos en shell/host. Un navegador autorizado puede ejecutar el JavaScript de la página dentro de su aislamiento como parte del render.
- 🛑 **Scraping permitido y límites anti-bot:** Respetar ToS, `robots.txt`, ritmo y base legal. Escalera permitida: fetch ordinario; JSON, estado embebido o API pública; `Scrapling StealthyFetcher` con navegador real ya soportado; navegador con perfil propio del usuario autorizado; fuente alternativa. No automatizar ni resolver CAPTCHAs, usar servicios anticaptcha, cookies/sesiones/credenciales ajenas, ni evadir autenticación, paywalls o controles de acceso. No usar `solve_cloudflare=True` salvo decisión futura explícita y reto Cloudflare identificado. Un 403 no justifica reintentos infinitos; informar el fallo exacto.
- 🔒 **Privacidad y Datos Financieros:**
  - Los datos financieros sensibles (ingresos/salarios, ahorros, condiciones de hipoteca) deben permanecer exclusivamente en archivos locales (`.env` o `user_profile.yml`).
  - **NUNCA** incluir salarios ni datos financieros en URLs de búsqueda ni en mensajes enviados a portales inmobiliarios externos.
  - **NUNCA** incluir credenciales o datos financieros privados en commits ni archivos versionados.
  - ⚠️ **No compartir datos financieros con agentes cloud:** Cuando el usuario interactúa con un agente alojado en la nube (Claude Code, ChatGPT, Codex u otros proveedores), la conversación es procesada por la infraestructura del proveedor. **NO** enviar salarios, datos bancarios, ahorros ni condiciones de hipoteca en el chat. Advertir al usuario de este riesgo; no prometer que los datos "nunca salen del PC" cuando se usa un agente cloud.
- 🌐 **Sin suposiciones fiscales o monetarias universales:** No asumir monedas fijas o tipos de impuesto (ITP) automáticos basados únicamente en el idioma. Las reglas de cálculo financiero se determinan por la configuración explícita del perfil o por locales del sistema.
- **Catastro y registro:** Consultar `home_ops.cadastre.registry` para saber dónde acceder. Distinguir catastro, mapa o valoración de registro jurídico de titularidad y cargas. Usar API automática solo mediante cliente runtime público y probado; en otros casos, acceso manual o regional. Un país ausente requiere una entrada oficial testeada antes de prometer soporte.
- 🧪 **Verificación de Cambios de Código:** Si en el futuro se modifica código fuente del proyecto, validar con:
  ```bash
  uv run pytest
  uv run ruff check src tests
  uv run mypy src
  ```

---

## 5. Mapa de Estructura del Repositorio

| Directorio / Archivo | Propósito |
|---|---|
| `src/home_ops/` | Código fuente principal de la aplicación (CLI, scrapers, pipeline, scoring, web, TUI). |
| `tests/` | Suite de tests automatizados (pytest). |
| `config/` | Plantillas de configuración y definiciones por defecto. |
| `user_profile.yml` | Configuración local del usuario (ubicación, URLs de portales, umbrales de scoring). |
| `.env` | Variables de entorno y credenciales privadas (tokens de Telegram, claves LLM). |
| `data/` | Datos de tiempo de ejecución (base de datos DuckDB, cachés de snapshots). |
| `docs/` | Documentación técnica del proyecto. |
| `openspec/` | Especificaciones y artefactos de arquitectura OpenSpec. |
| `scripts/` | Scripts de utilidad y operaciones. |
| `systemd/` | Archivos de servicio e intervalo systemd para el demonio. |
| `.hermes/` | Planes internos de desarrollo y seguimiento. |

---

## 6. Límites actuales

El runtime de fuentes incluye 7 adaptadores: Idealista, Fotocasa, Pisos.com, Tecnocasa, Habitaclia, Njuškalo y Kleinanzeigen. El runtime no aplica postfiltro estricto de `max_price`/`min_area_sqm`; son intención y filtros de URL. Pueden existir validaciones live manuales de desarrollo fechadas fuera de la suite; el soporte reproducible se demuestra con fixtures/tests y `sources validate` live durante Clone & Talk, no con un smoke versionado. Portales bloqueados, CAPTCHAs y fuentes desconocidas requieren el flujo explícito de adaptación, verificación o una fuente alternativa.
