# Home-Ops: Onboarding multi-agente ("clona y habla") — Plan de implementación

> **For Hermes:** implementar tarea a tarea (TDD, commit por tarea). Delegación de código: Pi (microtask pattern), verificación independiente.

**Goal:** Usuario clona el repo, abre su agente (Claude Code, Codex, OpenCode, Pi, Hermes), conversa en lenguaje natural → perfil configurado → `scan` funcionando. Sin formularios largos; comandos `/home-ops ...` donde el agente los soporte.

**Arquitectura:** `AGENTS.md` como fuente única de instrucciones (todos los agentes compatibles lo leen). Adapters mínimos por agente (sólo Claude Code necesita `.claude/commands/`). CLI nueva mínima: `homeops profile` y `homeops sources`. Defaults por locale en config. El agente no escribe SQL ni edita YAML a mano: pasa por CLI validada.

**Stack:** Python 3.12 + uv, typer (CLI existente), Textual (TUI), DuckDB, PyYAML. Sin deps nuevas.

---

## Fase 0 — Superficie para agentes (sin lógica nueva)

### Task 1: AGENTS.md en raíz del repo
**Objective:** Cualquier agente que abra el repo sabe qué es, qué comandos hay y qué no debe tocar.

**Files:**
- Create: `AGENTS.md`

**Contenido (secciones):**
1. Qué es Home-Ops (pipeline scrape→dedup→score→HITL, un párrafo).
2. Comandos reales: `uv run homeops setup|scan|tui|web|approve` + los nuevos de Fase 1-3.
3. Guardrails (reglas duras):
   - NO tocar la DB con SQL directo; usar CLI.
   - NO editar `user_profile.yml` a mano; usar `homeops profile set`.
   - Salario/ahorros/notes de financiación: datos privados → sólo `.env`/perfil local; NUNCA en URLs de scan ni en mensajes a portales.
   - Portales nuevos: sólo vía `homeops sources validate` (fetcher propio; sin saltar bloqueos).
   - Tras cambios: `uv run pytest`, `uv run ruff check src tests`, `uv run mypy src`.
4. Mapa del repo (1 tabla: directorio → propósito).

**Verificación:** agente de prueba (pi/opencode headless) responde correctamente "¿cómo añado un portal?" leyendo sólo AGENTS.md.

### Task 2: Comando slash Claude Code
**Files:**
- Create: `.claude/commands/home-ops.md`

**Contenido:** plantilla que mapea `$ARGUMENTS` ∈ {setup, scan, status, sources} a las instrucciones de AGENTS.md. Los demás agentes usan AGENTS.md directamente (Pi/OpenCode lo leen nativo).

**Verificación:** en Claude Code, `/home-ops status` ejecuta el equivalente CLI.

---

## Fase 1 — `homeops profile` (conversación → perfil validado)

### Task 3: `homeops profile validate`
**Objective:** Comando que valida `user_profile.yml` contra el loader real y lista campos faltantes. El agente lo usa tras conversar para saber qué falta.

**Files:**
- Create: `src/home_ops/cli/profile.py`
- Modify: `src/home_ops/cli/app.py` (registro `profile_app`)
- Test: `tests/test_profile_cli.py`

**Step 1 — test RED:**
```python
def test_validate_incomplete_profile(tmp_path):
    # perfil con sólo location → exit 1, stdout lista campos que faltan
    r = runner(["profile", "validate", "--config", str(cfg)])
    assert r.exit_code == 1
    assert "search.max_price" in r.stdout
```
**Step 2 — run:** `uv run pytest tests/test_profile_cli.py --no-cov -q` → FAIL
**Step 3 — implement:** `profile.validate()` → `load_config()`, diff contra `_REQUIRED_PATHS` (tupla de rutas dotted), print de faltantes, `raise typer.Exit(1)` si hay.
**Step 4 — GREEN + commit.**

### Task 4: `homeops profile set --json '<json>'`
**Files:** mismos + test.

**Reglas:** merge (no replace) sobre YAML existente, claves desconocidas preservadas, write atómico (`tmp → replace`), valores sensibles (tokens) rechazados aquí (van en `.env`). Roundtrip test a través del loader real.

---

## Fase 2 — Defaults por locale (DECIDIDO: NO archivos locales)

> **Decisión (2026-09-18):** los defaults regionales (ITP 6-10%, hipoteca 30 años, Europe/Madrid) YA viven en `BuyerProtectionConfig`/`ScheduleConfig` (src/home_ops/models/schema.py). Crear `config/locales/{es,en}.yml` duplicaría la fuente de verdad. El guard "explicit wins" ya lo garantiza Pydantic (`Config(**raw)`, campos ausentes → default, presentes → ganan). Verificado con tests/test_locale_defaults.py (3 tests). Cero archivos nuevos.

---

## Fase 3 — `homeops sources` (descubrimiento con validación)

### Task 6: `homeops sources validate <url>`
**Objective:** Validar que una URL candidata es un feed extraíble ANTES de añadirla. El agente propone URLs (búsqueda web fuera del repo); el CLI decide.

**Files:**
- Create: `src/home_ops/cli/sources.py`
- Test: `tests/test_sources_cli.py` (HTML de muestra local, sin red — monkeypatch fetcher)

**Comportamiento:** fetch con fetcher del proyecto → HTTP 200 + `>=1` item parseable por `_portal_parser` → `PASS (portal=<name>, items=N)`; sino `FAIL <causa real>` (HTTP code, 0 items, parser unknown). Exit 1 en FAIL. **Nunca** auto-bypassear Cloudflare/anti-bot.

### Task 7: `homeops sources add <url>`
**Comportamiento:** corre validate; sólo en PASS hace append a `portal.urls` (backup del YAML antes). FAIL no muta config (test lo prueba).

---

## Fase 4 — Docs + E2E

### Task 8: README — sección "Onboarding con tu agente"
```markdown
git clone ... && cd Home-Ops && uv sync
Abre tu agente y di: "configura mi búsqueda de vivienda en <tu zona>"
```
+ tabla de comandos + regla de privacidad (salario nunca sale del PC).

### Task 9: Smoke E2E manual (fuera de tests)
1. `homeops profile set --json '{"search":{"location":"Chiclana","max_price":250000}}'`
2. Conversación agente: frase libre → JSON → `profile set` → `profile validate` → 0 faltantes.
3. `homeops sources validate https://www.pisos.com/venta/pisos-cadiz/` → PASS.
4. `homeops scan user_profile.yml` → listings en DB → `homeops web` → 200.

---

## Verificación global (gate de cada fase)
```bash
uv run pytest -q                 # suite completa (≥686 hoy, cov ≥88%)
uv run ruff check src tests
uv run mypy src
timeout 6 uv run homeops tui     # pty smoke
```

## Riesgos / open questions
- `/home-ops <cmd>` no es sintaxis universal: adapters por agente; lenguaje natural = camino común. No prometer slash en todos.
- Mortgage affordability (salario→cuota máx): v0 informativa en `profile validate` output; cálculo real diferido (YAGNI) hasta que exista necesidad.
- Locale defaults: asunción — `loader.py` acepta merge post-load; verificar estructura real antes de Task 5.
- i18n TUI/web: nuevos strings ES/EN deben entrar en ambos catálogos (tests de paridad existen).

## Orden de riesgo (menor→mayor)
Fase 0 (docs) → Fase 1 (profile, puro) → Fase 2 (defaults) → Fase 3 (red) → Fase 4.
