# Intake — 3-question collection (基础信息录入)

Adapted from ex-skill `intake.md`. The web wizard collects three answers (each
skippable); this prompt documents how the raw answers map to structured intake
fields that flow into both distillation tracks. Mixed Chinese/English input is
expected and preserved verbatim where it cannot be classified.

## Questions

### Q1 — nickname / 昵称
> What does the ex go by? (nickname, pet name, or codename — join multiple words with `-`)
> 她怎么称呼？（昵称、小名或代号都行，多个字用 `-` 连接）

- Accept any string.
- The generated `slug` always joins with `-` (never underscore).
- Chinese converts to pinyin then `-`-joins ("小美" → `xiao-mei`, "糖糖" → `tang-tang`).
- English lowercases and `-`-joins ("Sweet Luna" → `sweet-luna`).

### Q2 — basics / 基本信息
> One sentence: how long together, how you met, how long since the breakup, what they do.
> 用一句话描述你们的基本情况——在一起多久、怎么认识的、分手多久、她做什么的。
>
> 例：在一起三年 大学同学 分手一年 她做设计

Parse (leave blank if missing): **duration_together**, **how_met**,
**time_since_breakup**, **occupation**.

| how_met type | common phrasings |
|---|---|
| campus | 大学同学、高中同学、同校、学长学妹 / classmate, schoolmate |
| work | 同事、公司认识的、同行 / coworker, colleague |
| social | 朋友介绍、社交软件、探探、陌陌 / set up by a friend, dating app |
| other | 相亲、旅行中认识、网友、青梅竹马 / blind date, met traveling, online, childhood |

### Q3 — personality portrait / 性格画像
> One sentence: MBTI, zodiac, attachment style, love-relationship traits, your impression.
> 用一句话描述她的性格——MBTI、星座、依恋类型、恋爱中的特点、你对她的印象。
>
> 例：ENFP 双子座 焦虑型 爱撒娇 翻旧账 嘴上说不在意其实比谁都在意

Extract (leave blank if missing): **mbti** (16 types), **zodiac** (12 signs),
**attachment** (from the table below), **love_tags** (from the library below,
custom descriptions accepted), **impression** (free text kept verbatim).

#### Attachment / 依恋类型
| type | 表现 / signs |
|---|---|
| 安全型 secure | trusts partner, comfortable alone or close, not anxious or avoidant |
| 焦虑型 anxious | needs frequent reassurance, fears abandonment, sensitive to reply speed |
| 回避型 avoidant | needs lots of space, flees intimacy, dislikes being depended on |
| 混乱型 disorganized | wants closeness yet fears it, push-pull, volatile |

#### Love-tag library / 恋爱标签库
- **沟通风格 communication:** 话很多 / 话很少 / 爱撒娇 / 冷暴力 / 爱讲道理 / 情绪化表达 / 发语音控 / 打字控
- **吵架模式 conflict:** 冷战派 / 爆发派 / 讲道理派 / 翻旧账 / 先道歉型 / 死不认错
- **爱的表达 love language:** 言语肯定 / 服务行为 / 送礼物 / 肢体接触 / 高质量陪伴
- **恋爱性格 traits:** 黏人 / 独立 / 控制欲强 / 大大咧咧 / 细腻敏感 / 忽冷忽热 / 作
- **社交人格 social:** 社交达人 / 宅 / 人前活泼人后安静 / 话少但走心
- **情绪风格 emotional:** 情绪稳定 / 玻璃心 / 容易激动 / 闷在心里 / 表面和气内心戏多

## Output

A JSON object with the parsed fields above. Missing fields are empty strings or
empty lists. `impression` retains any unclassifiable text in its original
language.
