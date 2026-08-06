---
name: recapping-paper-feynman
description: >-
  Evaluate a user's Feynman-style recap of a single academic paper against the
  paper's own text, score it on a four-dimensional rubric (accuracy,
  completeness, conciseness, analogy appropriateness), and return
  sentence-by-sentence annotations together with a list of missed key
  contributions — without revealing the corrected answers, so the user is nudged
  to repair their own understanding. Invoke this skill when the user says
  "费曼复述", "Feynman recap", "用大白话讲讲这篇论文", or "检查我的理解",
  or pastes a self-written plain-language summary of one paper and asks whether
  their understanding is correct. Do NOT use this skill to generate a summary
  from scratch, to produce abstracts, or to synthesize reviews across multiple
  papers — it only validates a recap the user has already written.
---

# Recapping Paper Feynman

## Purpose

This skill is the **post-reading comprehension check** of the academic PKM
workflow — the cognitive-engagement counterpart to `reading-paper-pre-questions`
(pre-reading priming). Its job is to cure "读完就忘" (read-and-forget) by
forcing the user to externalize their understanding in plain language, then
holding that externalization accountable against the paper's actual content.

It is deliberately **adversarial to the user's recap, not supportive of it**.
The skill does not congratulate; it locates the precise sentences where
understanding breaks down and forces the user to fix them themselves.

## Core Principle

**Never hand the user the answer.** The two failure modes this skill exists to
prevent are:

1. **Silent agreement** — "looks good!" feedback that lets a wrong recap pass.
2. **Answer leakage** — the model rewriting the user's sentence correctly, which
   feels like learning but produces zero retention (the user copied, not
   re-derived).

The AI's role is strictly **diagnostic + Socratic**: diagnose which sentences
are right / wrong / missing, locate the gap in the source text, and issue a
repair hint that points to *where and what to re-read* — never the corrected
sentence. If the user cannot repair it after the hint, that is the correct
outcome; they re-read the paper, which is the entire point.

Two hard guardrails:

- **Grounded, not generative.** Every correctness judgment is checked against
  the paper's own text (PDF or ZotLit-synced annotations), never against the
  model's parametric memory of "what Transformer is." If the source cannot be
  read, the skill degrades gracefully rather than guessing.
- **Single paper, user-owned recap.** The recap must already exist and be about
  exactly one paper. This skill never writes the recap for the user.

## Input

Two required inputs:

| Field | Required | Example | Notes |
|-------|----------|---------|-------|
| `recap` | yes | "Transformer 不用 RNN 了，靠注意力让每个词直接看所有词..." | The user's own plain-language retelling. Any length, any language. |
| `identifier` | yes | `vaswani2017` **or** `MCM-ICM\2017\Problem_B\B类-O奖--56731.pdf` | A citekey (preferred) or an absolute PDF path. |

Optional:

| Field | Example | Notes |
|-------|---------|-------|
| `scope` | "只检查方法部分" | Restrict the ground-truth digest and scoring to a section. |
| `lang` | `zh` / `en` | Output language of the annotation report. Default follows the recap's language. |
| `strictness` | `lenient` / `normal` / `strict` | Shifts the partial-credit thresholds. Default `normal`. |

If only a citekey is given, resolve it to a PDF path via the Zotero local API
(`http://localhost:23119/api/users/0/items?q={citekey}`) or the local
`_index.csv` / `_ccf_a.bib`. If only a PDF path is given, try to recover the
citekey from the literature note filename after ZotLit import.

## Pipeline

### Step 1 — Read the Paper (build the ground-truth digest)

Read the source in this strict priority order. Stop as soon as a layer yields
enough to build a faithful digest; do not skip a usable layer just because a
lower one is "richer."

1. **Obsidian literature note — ZotLit-synced annotation area (preferred).**
   Open `Literature/@{citekey}.md`. The annotation/highlight region is what the
   user themselves marked important while reading in the Zotero reader — it is
   the highest-signal, lowest-noise view of the paper. Locate it under the
   section the literature-note template reserves for synced highlights
   (typically `## Annotations` / `## 高亮`; follow whatever the project template
   defines). Extract: highlighted spans, the user's own margin notes, and the
   note's frontmatter (`title`, `authors`, `year`, `venue`, `doi`, `abstract`).
2. **PDF (fallback).** If the note does not exist, the annotation area is empty,
   or it lacks the section the user is asking about, read the PDF directly
   (text layer first; if absent, OCR the relevant pages only). Extract abstract,
   method, key results, stated contributions, and limitations.
3. **Local index only (last resort).** If neither is available, use
   `_abstracts.jsonl` / `_index.csv` for the abstract and metadata — but flag the
   digest as `LOW_CONFIDENCE (abstract-only)` in the report, because
   abstract-level checking cannot catch method-level misunderstandings.

From the chosen layer, build an internal **ground-truth digest** keyed by
claim, not by paragraph:

- Problem / motivation
- Core idea (one sentence)
- Method (mechanism, key equations in words)
- Key results (numbers, settings, baselines)
- Stated contributions (the paper's own bulleted claims)
- Limitations / scope

This digest is the yardstick for Steps 2–3. It is internal; it is never shown
verbatim to the user (that would be answer leakage).

### Step 2 — Score on the Four-Dimensional Rubric

Score the recap against the digest on four independent dimensions, each 0–25.
Load the full criteria and worked examples from
[`resources/feynman-rubric.md`](./resources/feynman-rubric.md); do not reinvent
the bands inline.

| Dimension | 0–25 | What it measures |
|-----------|------|------------------|
| 准确性 Accuracy | 0–25 | Are the stated facts correct vs. the source? |
| 完整性 Completeness | 0–25 | Are the key contributions / method / results present? |
| 简洁性 Conciseness | 0–25 | Is it free of filler, redundancy, and borrowed jargon the user can't actually wield? |
| 类比恰当性 Analogy | 0–25 | Do the analogies map cleanly, or do they import false structure? |

Total = sum, 0–100. Band: 90+ 优秀 / 70–89 良好 / 50–69 需改进 / <50 需重读.

Each dimension score must be accompanied by a one-line justification citing the
specific recap sentences that earned or lost points.

### Step 3 — Produce the Annotation Report

This is the user-facing output. Structure it exactly as below. The central
artifacts are the **逐句批注** table and the **修复提示** — both are Socratic
and never contain the corrected sentence.

```markdown
## 费曼复述批注 — @{citekey}

### 逐句批注

| # | 你的原句 | 判定 | 批注 |
|---|---------|------|------|
| 1 | "Transformer 不用 RNN 了" | ✅ 正确 | 与原文一致（§3.1 移除循环）。 |
| 2 | "靠注意力让每个词直接看所有词" | ⚠️ 部分错 | 方向对，但"所有词"在解码端不成立。回看 §3.2.3 的 masking。 |
| 3 | "位置信息靠 LayerNorm" | ✗ 错误 | 把两件无关的事混了。回看 §3.5（位置编码）与 §5.4（正则化）。 |
| 4 | — | ⊘ 遗漏 | 未提及"多头"机制为何有用。 |

判定图例：✅ 正确 / ⚠️ 部分错（方向对，细节错）/ ✗ 错误 / ⊘ 遗漏（该说没说）

### 漏掉的关键贡献

1. 多头注意力：让模型在不同表示子空间并行关注 —— 你完全没提。
2. 缩放点积注意力中 √d_k 的作用 —— 影响"为什么不会梯度爆炸"。
3. （仅列论文自己声明、且你该知道量级的贡献；不展开解释。）

### 修复提示（不给答案，只给路标）

- 第 2 句：重读 §3.2.3，画出编码器与解码器各自 attention 的"可见范围"差异。
- 第 3 句：把"位置编码"和"LayerNorm"分别写在两张卡片上，确认各自解决什么问题。
- 遗漏 #1：用一句话回答"如果只有一个 attention head 会损失什么"。

> 提示均为引导式。若你看完仍写不出，回到原文对应小节重读，而不是回来抄答案。

### 评分

| 维度 | 得分 / 25 | 一句话理由 |
|------|-----------|-----------|
| 准确性 | 17 | 4 句中 2 句有事实偏差（#2、#3）。 |
| 完整性 | 12 | 三项关键贡献缺失。 |
| 简洁性 | 22 | 表达干净，无冗余。 |
| 类比恰当性 | 18 | "直接看所有词"类比贴切，但掩盖了 masking。 |
| **总分** | **69 / 100** | **需改进** |
```

Writing rules for the report:

- **逐句批注** must cover *every* sentence in the recap (splitting run-ons). A
  recap with N sentences yields ≥ N rows; sentences that omit something the
  paper declares central get an extra ⊘ 遗漏 row (as in row 4 above).
- The **批注** column may reference the source by section number / page so the
  user can re-read precisely. It may **not** restate the correct fact.
- **漏掉的关键贡献** lists only contributions the paper itself declares
  (abstract / intro bullet list / conclusion) that the recap is missing at a
  level of detail the user should know given their `scope`. One-line each, no
  explanation.
- **修复提示** are imperative prompts to *do something* (re-read §X, draw a
  diagram, answer a sub-question), never declarative corrections. If a hint
  would require stating the answer to be useful, replace it with a question
  whose answer *is* the missing fact.
- The report is written into the literature note's `## 费曼复述` section
  (append a dated sub-section `### {YYYY-MM-DD} 复述批注`), so the user keeps a
  revision history. If the note does not exist yet, print the report inline and
  tell the user to import the note via ZotLit first.

### Step 4 — Verify Citations Mentioned in the Recap

If the recap refers to *any other paper* — by citekey (`[[bahdanau2014]]`),
`[Author, Year]`, `(DOI:...)`, a bare title, or "那篇 Bahdanau 的论文" — those
references are exactly the kind of claim an over-confident recap fabricates.
Route them through `fact-checking-citations` before finalizing the report.

Handoff: collect each mentioned reference as a `(raw_span, claim)` pair and pass
the full set to `fact-checking-citations`. It returns `VERIFIED` /
`MISMATCH` / `NOT_FOUND` / `UNSUPPORTED` per reference. Fold the results into the
report as an extra block:

```markdown
### 引用核对（由 fact-checking-citations 生成）

| 提及的论文 | 你的论断 | 状态 | 影响 |
|-----------|---------|------|------|
| [Bahdanau et al., 2014] | "Transformer 取代了它的 RNN 编码器" | ⚠️ MISMATCH | 论断方向对，但 Bahdanau 用的是 RNN+attention，非"编码器被取代"；第 2 句扣分已含此点。 |
| [Smith, 2020] | "和这篇思路一样" | ❌ NOT_FOUND | 该引用疑似幻觉，建议删除或给出 DOI。 |
```

If `fact-checking-citations` is unavailable (scripts missing, network down),
do **not** silently trust the citations — mark each as `UNCHECKED` in the report
and add a one-line reminder that citation verification was skipped. A citation
that was never checked must never appear as if it were verified.

## Failure Strategies

| Situation | Behavior |
|-----------|----------|
| **PDF unreadable** (scanned, encrypted, text layer missing, OCR infeasible) | Fall back to the Obsidian note's ZotLit annotation area + frontmatter abstract and do **limited verification**: score 准确性/完整性 only on claims that can be checked against annotations/abstract; mark 简洁性/类比 as `N/A (source-constrained)` and compute the total out of the scorable dimensions (rescaled). Add a prominent `⚠️ 有限校验：PDF 不可读，仅基于 annotation/摘要核对` banner. Do not guess method-level facts the annotations don't cover. |
| **Literature note missing AND PDF missing** | Cannot score. Ask the user to either paste the abstract (enables low-confidence checking) or provide a PDF path. Do not proceed on the model's prior knowledge. |
| **Annotation area empty but PDF present** | Use the PDF (Step 1 layer 2). Do not penalize the user for not having annotated. |
| **Recap too short to score** (e.g., one sentence) | Still produce 逐句批注 and a 漏掉的关键贡献 list; mark 完整性/简洁性 as `N/A (recap too short)` and say so. Encourage a second, longer attempt rather than inflating the score. |
| **Recap is actually a copy-paste of the abstract** | Detect verbatim/near-verbatim overlap with the source abstract; flag `⚠️ 疑似抄写摘要，非复述` and decline to score 简洁性/类比 meaningfully — a copied abstract is not a Feynman recap. Ask the user to rewrite in their own words. |
| **Recap mentions a citation that cannot be resolved** | Mark `NOT_FOUND` via the fact-checking-citations handoff; in the report, advise the user to delete it or supply a DOI. Do not score the citation as if it were real. |
| **fact-checking-citations scripts missing / network down** | Mark all mentioned citations `UNCHECKED` (see Step 4). Never present an unchecked citation as verified. |
| **User asks for the answer directly** | Refuse to provide the corrected sentence; re-issue a more pointed repair hint. This is the skill's defining behavior, not a limitation. |
| **Citekey resolves to multiple papers** | Disambiguate via Zotero API metadata (title/authors/year); if still ambiguous, list the candidates and ask the user to pick before scoring. |

## When This Skill Calls / Is Called By Other Skills

| Direction | Skill | Trigger | What passes across |
|-----------|-------|---------|--------------------|
| calls | `fact-checking-citations` | Recap mentions any other paper | `(raw_span, claim)` pairs; receives VERIFIED/MISMATCH/NOT_FOUND/UNSUPPORTED per reference |
| is called by | `reading-paper-pre-questions` | (Never — pre-questions is pre-reading, this is post-reading; the boundary is enforced in both descriptions) | — |
| is called by | `linking-paper-concepts` | (Never — linking is cross-paper discovery, this is single-paper validation) | — |

This skill does **not** call `synthesizing-literature-review`,
`tracing-lineage-by-era`, `tracing-lineage-by-team`, or
`building-citation-timeline`: those are macro skills operating across many
papers, and a Feynman recap is definitionally single-paper.

## Constraints

- **Single paper only.** A recap spanning two papers is out of scope; ask the
  user to split it.
- **No answer leakage.** The corrected sentence, the missing contribution's
  explanation, and the method's actual mechanism are never written into the
  user-facing report. Repair hints point to source locations and pose
  questions; they do not state facts.
- **Grounded in source text.** Every ✅/⚠️/✗ judgment must be traceable to a
  passage in the annotation area or PDF. If a claim cannot be grounded, mark it
  `INCONCLUSIVE` rather than guessing correct/wrong.
- **User owns the recap.** This skill never generates, rewrites, or
  auto-completes the recap. It only annotates an existing one.
- **Honest scoring.** Do not round up to make the user feel good; do not round
  down to seem rigorous. Report the rubric's score and the band it lands in,
  with per-dimension justifications.
- **Revision history.** Each run appends a dated sub-section to `## 费曼复述`
  so progress across attempts is visible.
- **Length.** This SKILL.md stays ≤ 500 lines; the full scoring criteria and
  worked examples live one level deep in `resources/feynman-rubric.md`.
