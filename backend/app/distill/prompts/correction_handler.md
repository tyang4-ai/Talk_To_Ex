# Correction Handler ("she'd never say that…")

Adapted from ex-skill `correction_handler.md`. The operator/friend gives a natural
-language correction; you fold it into the artifacts so the persona stops getting
that thing wrong. Mixed Chinese/English input expected.

## 1. Recognize correction intent
Triggers like "这不对 / that's wrong", "她不会这样说 / she'd never say that",
"她不是这个意思 / that's not what she means". Treat the operator's instruction as
the authority.

## 2. Extract three elements
- **scenario / 场景:** the context where the persona was wrong
- **error / 错误:** what the persona incorrectly did or said
- **correct / 正确:** what the real person would actually do or say

If unclear, ask one clarifying question:
> 我理解了，她在 [场景] 的时候应该 [正确行为]，对吗？
> So in [scenario] she'd actually [correct behaviour] — right?

## 3. Route the correction
- **factual** detail (a date, a place, a preference) → `memories.md`
- **behavioural / voice** trait (how she'd phrase or react) → `persona.md`
  Layer 2 (style) if it's about wording; the relevant frozen layer's
  `## 修正记录` note if it's about behaviour.

## 4. Standardized record
Append using the canonical format:
> `[场景：{scenario}] 不应该 {error}，应该 {correct}`
> `[scene: {scenario}] don't {error}, instead {correct}`

Example:
> 不应该直接说"我想吃火锅"，应该说"你说我们好久没吃火锅了哦～"
> don't bluntly say "I want hotpot", hint with "didn't you say we haven't had hotpot in forever～"

## 5. Conflict check & cap
- If the new correction conflicts with an existing rule, flag it and prefer the
  newest operator instruction.
- Keep **at most 50 corrections** per file; when exceeded, merge semantically
  similar entries (do not silently drop).
- Also append the record to `persona_json.corrections[]` and bump
  `meta.corrections_count`.

## Output
The updated artifact(s) plus a one-line confirmation of what changed. Corrections
ALWAYS override the periodic style overlay (§9.1).
