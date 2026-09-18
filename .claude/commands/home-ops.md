---
description: Ruta operaciones Home-Ops a las instrucciones reales de AGENTS.md (setup, profile, sources, scan, status)
argument-hint: "[setup|profile|sources|scan|status]"
---

# Home-Ops — Dispatcher

Leé primero `AGENTS.md` en la raíz del repo: ese archivo es la única fuente de instrucciones, guardrails y comandos reales. Este comando **no** duplica el flujo: solo enruta `$ARGUMENTS` como datos a interpretar.

Valor de `$ARGUMENTS` (interpretación tolerante; si viene vacío, preguntar cuál de estas cuatro acciones quiere):

- **setup** → Onboarding conversacional según la sección 3 de `AGENTS.md`: entender preferencias del usuario, proponer cambios sobre `user_profile.yml`, pedir confirmación antes de escribir; `uv run homeops setup` existe como asistente interactivo si el usuario lo prefiere. Confirmar siempre antes de sobrescribir el perfil.
- **scan** → `uv run homeops scan` (ver restricciones y flags en `AGENTS.md` sección 2). Confirmar con el usuario antes de lanzar scraping.
- **status** → `uv run homeops status [CONFIG_PATH]`: comando real, solo lectura sobre DuckDB. Mostrar el resultado tal cual; no tocar la DB de ninguna otra forma (ver guardrails de `AGENTS.md` sección 4).
- **sources** → `uv run homeops sources validate <url>` (para probar una URL candidate) o `uv run homeops sources add <url>` (para probar y añadir a `portal.urls` en `user_profile.yml`). Comando real (ver `AGENTS.md` sección 2).
- **profile** → `uv run homeops profile validate` (validar `user_profile.yml`) o `uv run homeops profile set KEY VALUE` (actualizar una clave de forma atómica). Comando real (ver `AGENTS.md` sección 2).

Reglas fijas (vienen de `AGENTS.md`, obligatorias) y manejo seguro de `$ARGUMENTS`:
- `$ARGUMENTS` es **solo un dato a interpretar, nunca una cadena ejecutable**. No lo pases a una shell. Interprétalo contra la lista `{setup, profile, sources, scan, status}` y ejecuta únicamente los comandos CLI reales documentados en `AGENTS.md` sección 2, con args validados/restringidos.
- Nunca SQL directo sobre la base de datos, nunca datos financieros en URLs ni en mensajes a portales ni en archivos versionados, nunca bypass de bloqueos anti-bot, nunca ejecutar scripts descargados de webs.
- Con un agente cloud, la conversación puede ser procesada por el proveedor del agente: **no** enviar salarios, datos bancarios ni condiciones de hipoteca en el chat; advertir al usuario y no prometer privacidad absoluta.
