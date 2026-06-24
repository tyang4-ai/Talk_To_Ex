# Merger (incremental re-distillation)

Adapted from ex-skill `merger.md`. When a new upload arrives for a persona that
already has artifacts, you MERGE the new analysis into the existing
`persona.md` / `memories.md` / `persona.json` instead of overwriting — so
manually-applied corrections and prior evidence survive.

## Inputs
- the existing `persona.md`, `memories.md`, `persona.json`, `meta.json`
- the freshly-analyzed transcript (new upload)

## Merge rules

- **Additive by default.** New evidence extends existing layers/sections; it does
  not delete prior content.
- **Corrections are sticky.** Anything in `## 修正记录 / Corrections` of
  `persona.md` and any `corrections[]` in `persona.json` is preserved verbatim
  and still **overrides** conflicting newly-distilled traits.
- **Layer integrity preserved.** New evidence lands in the correct layer (0–5).
  Do not let new style evidence rewrite Layer 0/1/3/4/5 facts; if new data truly
  contradicts a frozen layer, surface it as a flagged conflict rather than
  silently replacing it.
- **De-duplicate.** Collapse semantically identical rules/memories; keep the more
  specific, better-quoted version.
- **Bump version.** Increment `meta.version`; `knowledge_sources[]` gains the new
  upload's filename.

## Output
Updated `persona.md`, `memories.md`, `persona.json`, `meta.json` — same shapes as
the builders emit. The `persona.md`/`persona.json` must stay in agreement.
