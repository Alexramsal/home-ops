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
4. `supported` significa uno de los cinco adaptadores runtime actuales: Idealista, Fotocasa, Pisos.com, Tecnocasa o Habitaclia. `verified` exige `sources validate URL --config FILE`, muestra parseable y municipio correcto.
5. Informar las fuentes `blocked` sin intentar bypass. No tratar `candidate` desconocida como integrada; ofrecer crear un adaptador explícito con fixture, parser, tests, validación real y permiso del usuario.
6. Tras una única confirmación consolidada del usuario, añadir solo fuentes `verified` con `sources add URL --config FILE`; persistirlas para no redescubrirlas en cada scan.

El runtime está validado actualmente para España, EUR y m². Con `country != ES`, el código desactiva Catastro, Euríbor/affordability y protección fiscal del comprador española. Un país nuevo requiere adaptadores, moneda, unidad, UI, persistencia y política local verificadas; no aplicar impuestos españoles ni prometer soporte mundial.

---

## 4. Guardrails y Reglas de Seguridad

- 🛑 **Prohibido acceso directo a DuckDB con SQL:** NO ejecutar consultas SQL directas sobre la base de datos (`home_ops.db`). Utilizar exclusivamente los comandos CLI (`status`, `approve`, `scan`).
- 🛑 **Prohibida la ejecución de scripts de webs externas:** NUNCA descargar ni ejecutar scripts, JavaScript o binarios remotos desde portales inmobiliarios scraping.
- 🛑 **Respetar restricciones de scraping:** NO intentar bypasses de Cloudflare, CAPTCHAs ni mecanismos anti-bot. Si un portal bloquea o requiere ajustes, notificar al usuario. Validar que las fuentes pertenezcan a portales soportados.
- 🔒 **Privacidad y Datos Financieros:**
  - Los datos financieros sensibles (ingresos/salarios, ahorros, condiciones de hipoteca) deben permanecer exclusivamente en archivos locales (`.env` o `user_profile.yml`).
  - **NUNCA** incluir salarios ni datos financieros en URLs de búsqueda ni en mensajes enviados a portales inmobiliarios externos.
  - **NUNCA** incluir credenciales o datos financieros privados en commits ni archivos versionados.
  - ⚠️ **No compartir datos financieros con agentes cloud:** Cuando el usuario interactúa con un agente alojado en la nube (Claude Code, ChatGPT, Codex u otros proveedores), la conversación es procesada por la infraestructura del proveedor. **NO** enviar salarios, datos bancarios, ahorros ni condiciones de hipoteca en el chat. Advertir al usuario de este riesgo; no prometer que los datos "nunca salen del PC" cuando se usa un agente cloud.
- 🌐 **Sin suposiciones fiscales o monetarias universales:** No asumir monedas fijas o tipos de impuesto (ITP) automáticos basados únicamente en el idioma. Las reglas de cálculo financiero se determinan por la configuración explícita del perfil o por locales del sistema.
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

El runtime de fuentes está limitado a cinco adaptadores: Idealista, Fotocasa, Pisos.com, Tecnocasa y Habitaclia. El runtime no aplica aún postfiltro estricto de `max_price`/`min_area_sqm`; las URLs verificadas deben incorporar esos filtros cuando el portal lo permita. La validación actual cubre España, EUR y m²; otros países requieren trabajo explícito de adaptación y verificación. Portales bloqueados, CAPTCHAs y fuentes desconocidas no se sortean ni se consideran integrados automáticamente.
