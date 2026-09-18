# AGENTS.md — Guía de Integración e Instrucciones para Agentes de IA

Este archivo define la superficie de interacción, arquitectura, reglas de seguridad y comandos reales de **Home-Ops** para asistentes de IA (Pi, Claude Code, Codex, OpenCode, Cursor, Hermes, etc.).

> **Nota de compatibilidad:** `AGENTS.md` es leído automáticamente por entornos de agentes que soportan archivos de instrucciones en la raíz del repositorio. Para herramientas como Claude Code que utilizan comandos adaptadores, la integración se realiza mediante `.claude/commands/home-ops.md` referenciando las normas de este documento. La compatibilidad de lectura de `AGENTS.md` depende del cliente/entorno utilizado.

---

## 1. Visión General de Home-Ops
Home-Ops es un pipeline para búsqueda y scoring de vivienda personal:
`Scrape de portales → Deduplicación → Scoring determinista → Human-in-the-Loop (HITL) → Alertas Telegram`

---

## 2. Comandos CLI Reales

> ⚠️ **IMPORTANTE PARA AGENTES:** Ejecutar **ÚNICAMENTE** los comandos CLI que existen actualmente (ver tabla de la Sección 2). Todos los subcomandos documentados (`setup`, `profile`, `sources`, `scan`, `status`, `approve`, etc.) son plenamente funcionales.

| Comando CLI | Descripción | Uso / Argumentos Reales |
|---|---|---|
| `uv run homeops setup` | Asistente interactivo de configuración inicial (`user_profile.yml` + `.env`). | `uv run homeops setup [--config FILE]` |
| `uv run homeops profile validate` | Valida `user_profile.yml` (estructura y valores). Exit 0 si OK, 1 con errores. | `uv run homeops profile validate [--config FILE]` |
| `uv run homeops profile set KEY VALUE` | Actualiza una clave de `user_profile.yml` (ruta con puntos, p. ej. `scoring.thresholds.price_median`); escritura atómica, conserva el resto. | `uv run homeops profile set KEY VALUE [--config FILE]` |
| `uv run homeops sources validate URL` | Valida si una URL pertenece a un portal soportado y retorna ≥1 inmuebles parseables. | `uv run homeops sources validate URL` |
| `uv run homeops sources add URL` | Valida una URL y, si pasa, la añade a `portal.urls` en `user_profile.yml` de forma atómica. | `uv run homeops sources add URL [--config FILE]` |
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

Cuando el usuario interactúa con un agente para configurar Home-Ops ("configura mi búsqueda de vivienda en Cádiz", etc.):

1. **Entender preferencias mediante conversación:** Interpretar o consultar ubicación, presupuesto máximo (`search.max_price` / `scoring.thresholds.price_median`), requisitos de vivienda y zonas/fuentes deseadas.
2. **Aplicar configuración REAL:**
   - Opción A (Conversacional): Leer y actualizar de forma atómica el archivo `user_profile.yml` preservando las claves y estructuras existentes.
   - Opción B (Asistente CLI): Guiar al usuario para ejecutar `uv run homeops setup` si prefiere el asistente de terminal interactivo.
3. **Continuidad del Perfil:** Mantener los valores existentes (umbrales de scoring, schedulers, credenciales) al hacer actualizaciones; NUNCA sobrescribir el archivo completo borradores de campos previos.
4. **Confirmación Previa:** Solicitar confirmación explícita al usuario antes de guardar modificaciones en `user_profile.yml`.

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

## 6. Roadmap y Funcionalidades Futuras (En Desarrollo)

No hay funcionalidades en desarrollo bloqueadas actualmente; todos los subcomandos descritos en la Sección 2 (`setup`, `profile`, `sources`, `scan`, `status`, `approve`, `tui`, `web`, `analytics`, `daemon`, `snapshots-reset`) están completamente implementados y listos para su uso por parte de los agentes.
