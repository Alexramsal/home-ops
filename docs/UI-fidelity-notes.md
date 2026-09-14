# UI.pen — cambio de verificación de fidelidad (2026-09-14)

Ref: proceso en UE del 2026-09-14 (diseño del panel público, Pencil MCP vía opencode).

## Verificación de fidelidad del contenido — pausada, no abandonada

Los números verificados contra la DB real (28 únicos, 170 observaciones, 142 repetidas, 14 con score ≥70,
mediana 3.618 €/m², semana única 2026-08-31 con 150 obs → media 3.865 / mediana 3.702 €/m², corte 2026-09-01)
SÍ están presentes y correctos en el diseño. Bien.

## Datos NO verificados — el agente inventó ejemplos (diseño ≠ datos)

| Dato en el diseño | Realidad en DB |
|---|---|
| "Piso Zona Centro, El Puerto — 185.000 €, 95 m², 1.947 €/m², score 78, -46% vs mediana" | NO existe |
| "Ático Paseo Marítimo, El Puerto — 295.000 €, 110 m², 2.681 €/m², score 74, -26%" | NO existe |
| "Apartamento Vista Bahía, El Puerto — 165.000 €, 72 m², 2.291 €/m², score 71, -37%" | NO existe |
| "Piso Zona Centro ... Score 78 ... Pendiente Auditoría" | NO existe |
| "github.com/arami/Home-Ops" (CTA) | REAL: repo es `AlejandroRS21/home-ops` |

El top #1 "Dúplex Plaza de Toros — 230.000 €, 130 m², 1.769 €/m², score 87, riesgo 10" SÍ es el real de la DB
([solo el nombre y dirección completa: "Dúplex en Plaza de Toros - Ayuntamiento, El Puerto de Santa María"]).

## Los 8 reales de la DB (score ≥70, para reemplazar los 3 inventados)

1. Dúplex en Plaza de Toros - Ayuntamiento, El Puerto de Santa María — 230.000 €, 130 m², 1.769 €/m², score 87
2. Piso en Casco Histórico - Ribera del Marisco, El Puerto de Santa María — 260.000 €, 110 m², 2.364 €/m², score 74
3. Piso en Centro, Jerez de la Frontera — 675.000 €, 371 m², 1.819 €/m², score 70
4. Piso en Plaza Topete, Centro Histórico - Plaza España, Cádiz — 595.000 €, 212 m², 2.807 €/m², score 70
5. Casa o chalet independiente en Centro, El Puerto de Santa María — 600.000 €, 415 m², 1.446 €/m², score 70
6. Casa o chalet independiente en Zahara Pueblo, Zahara de los Atunes — 590.000 €, 226 m², 2.611 €/m², score 70
7. Casa o chalet independiente en Valdelagrana, El Puerto de Santa María — 990.000 €, 372 m², 2.661 €/m², score 70
8. Casa o chalet independiente en Pinar Alto, El Puerto de Santa María — 785.000 €, 263 m², 2.985 €/m², score 70

## Para reanudar (próxima sesión)

Reabrir UI.pen en Pencil MCP y pedir: "Reemplaza las filas inventadas de la tabla por estos
datos reales (lista de arriba); usa solo estos 4 en la tabla compacta: fila 1 Dúplex 230k/130m²/1.769€/m²/87,
fila 2 Ribera del Marisco 260k/110m²/2.364€/m²/74, fila 3 Centro Jerez 675k/371m²/1.819€/m²/70,
fila 4 Plaza Topete Cádiz 595k/212m²/2.807€/m²/70. Corrige el CTA a AlejandroRS21/home-ops y el footer.
No inventes nada más". Conexión: lanzar primero Pencil Desktop (o verificar mcp pencil connected), luego
opencode run crítico.

Docs de respaldo generados: docs/UI-fidelity-notes.md (este) + engram session home-ops-public-results-20260914.