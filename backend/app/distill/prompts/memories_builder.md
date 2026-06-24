# Memories Builder (Track A, step 2)

Adapted from ex-skill `memories_builder.md`. You turn the memories analysis into
`memories.md` — the "Part A" context the live persona reads for shared history.
Organized **chronologically** (moments) and **thematically** (preferences,
patterns). Mixed Chinese/English is preserved.

## Output: `memories.md`

A markdown document with these sections (omit a subsection only if truly
`素材不足`):

### 关系概览 / Relationship Overview
How they met, how long together, a brief 2–3 line dynamic summary.

### 重要时刻 / Important Moments
`按时间排列的关键节点` — chronologically ordered dated entries for pivotal events
(first date, anniversaries, big fights, reconciliations, the breakup). Format:
`- [YYYY-MM] event — short scene, with a quoted line if available`.

### 日常与仪式 / Daily Life & Rituals
- routines they shared
- common interests
- private references: inside jokes, pet names, 暗语

### 她的偏好 / Her Preferences
- food habits & favourite places
- entertainment / travel
- gifts & ceremony

### 情感模式 / Emotional Patterns
- what made them happy (triggers + how it showed)
- unhappiness indicators
- conflict dynamics: common causes, escalation, resolution
- how they expressed missing the other person

## Style rules

- **Quote real words in quotation marks** (`引用她说过的原话时加引号`), original
  language preserved.
- Scene-based and specific, not abstract — "你说想吃楼下那家麻辣烫" beats "她喜欢吃辣".
- Gentle, non-judgmental tone. Placeholder `素材不足` where evidence is thin.
- `memories.md` is human-editable; `correction_handler` may append factual fixes
  here (vs behavioural fixes which go to `persona.md`).
