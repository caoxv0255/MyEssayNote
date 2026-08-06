---
name: reading-paper-pre-questions
description: >-
  Generate cognitive pre-reading questions for an academic paper based on its
  title, abstract, and optional venue/author/year metadata before deep reading.
  Use this skill when the user mentions "预读", "读前提问", "pre-reading",
  "预读问题", wants to activate prior knowledge and set reading anchors before
  reading a paper, or pastes a paper title/abstract and asks what to focus on.
  Do NOT use this skill for post-reading summarization, Feynman recap
  (费曼复述), literature review synthesis across multiple papers, or any
  after-reading activity — it is strictly a pre-reading cognitive priming tool.
---

# Reading Paper Pre-Questions

## Purpose

This skill is the **pre-reading cognitive primer** of the academic PKM
workflow. It produces a structured set of pre-reading questions that the reader
should attempt to answer *before* opening the full PDF. The goal is not to
summarize the paper, but to activate prior knowledge, generate testable
predictions, and plant critical reading anchors so that the actual reading is
goal-directed rather than passive consumption.

**Why pre-reading questions matter:** Reading a paper cold (no prior activation)
leads to "读完就忘". Pre-reading questions force the reader to (1) retrieve
what they already know, (2) commit to a prediction before reading (which makes
confirmation and surprise salient), and (3) carry specific critical anchors into
the reading that act as attention filters.

This skill is the **first step** of the micro-reading workflow:

```
reading-paper-pre-questions  →  (user reads PDF)  →  recapping-paper-feynman  →  linking-paper-concepts
```

## Core Principle

**Pre-reading, not post-reading.** This skill operates only on the title and
abstract (or title alone if abstract is unavailable). It must NEVER read the
full paper body, methods, results, or conclusions. If the user pastes full-paper
text, the skill should ignore everything after the abstract and explicitly warn
the user that only the abstract was used.

**Questions, not answers.** The skill generates *questions*, not summaries or
predictions of what the paper says. The questions should be answerable by the
reader's own knowledge, not by the abstract. Questions that can be answered by
copy-pasting from the abstract are low-quality and must be revised.

## Input

The skill accepts a paper identifier in any of these forms:

| Input form | Example | Fields available |
|-----------|---------|-----------------|
| Full metadata paste | "Title: ...\nAbstract: ...\nVenue: CVPR\nAuthors: ...\nYear: 2023" | All fields |
| Title + abstract paste | "Attention Is All You Need\nWe propose a new..." | title, abstract |
| Title only | "Segment Anything" | title only (degraded mode) |
| Citekey | `vaswani2017` or `conf/iccv/KirillovMRMRGXW23` | resolve via sources |
| DOI | `10.5555/3295222.3295349` | resolve via local CSV |

Optional fields that enrich question quality:
- `venue` — e.g., CVPR, NeurIPS, SIGGRAPH (helps calibrate expectations)
- `authors` — e.g., "Kirillov; Dollár; Girshick" (helps activate author-prior)
- `year` — e.g., 2023 (helps place in timeline)
- `area` — e.g., AI, Graphics, HCI (helps select domain-appropriate questions)

## Source Priority

When the input is a citekey or DOI rather than a full paste, the skill resolves
metadata using this strict priority order:

### Priority 1: User-provided paste (highest)

If the user directly pastes the title and/or abstract, use the pasted content
verbatim. Do not overwrite user-provided content with data from other sources —
the user may be working with a corrected or newer version of the abstract.

### Priority 2: Local `_high_impact.csv` lookup by citekey

If the user provides a citekey (e.g., `conf/iccv/KirillovMRMRGXW23`) or a title
that matches a row in `d:\Desktop\论文\_high_impact.csv`, read the CSV and
extract:
- `title` → title
- `tldr` → abstract (Semantic Scholar TLDR; treat as abstract substitute)
- `authors` → authors (semicolon-separated)
- `year` → year
- `venue` → venue
- `doi` → DOI (for cross-checking)

**CSV columns:** `id,title,authors,year,venue,kind,area,area_folder,stream,type,doi,ee,arxiv_id,citation_count,tldr,local_pdf`

The `id` column is the citekey. Match case-insensitively. If the user provides
a short citekey (e.g., `vaswani2017`) that does not match the full `id` format
(e.g., `conf/nips/VaswaniSPUJGKP17`), attempt a suffix/contains match.

### Priority 3: Obsidian literature note `Literature/@citekey.md`

If Priority 2 fails (citekey not in `_high_impact.csv`) or if the CSV's TLDR is
too short for quality question generation, read the corresponding Obsidian
literature note at:

```
d:\Desktop\论文\obsidian-vault\Literature\@{citekey}.md
```

Extract the abstract from the note's frontmatter (`abstract:` field) or from the
`## Abstract` section in the note body.

### Priority 4: `_abstracts.jsonl` fallback

If the literature note does not exist, search `d:\Desktop\论文\_abstracts.jsonl`
for a matching `id` and extract the `abstract` field. Each line is a JSON object
with `id`, `title`, `abstract`, `citation_count`.

### Priority 5: Title-only degraded mode (lowest)

If all sources fail to provide an abstract, fall back to **title-only degraded
mode** (see Failure Strategies below).

> **Note on external API calls:** This skill does NOT call Semantic Scholar or
> Crossref. It relies entirely on local data sources. If local sources have no
> abstract, the skill degrades gracefully rather than making network calls —
> pre-reading questions should be fast and offline-capable.

## Three-Layer Questioning Framework

The skill generates questions in three cognitive layers, each with a distinct
purpose. For the full template bank with examples, see
`resources/pre-reading-question-bank.md`.

### Layer 1: Activation Layer (激活层 — 先验知识)

**Goal:** Activate prior knowledge so the reader retrieves what they already
know before reading. This creates "hooks" in long-term memory for the new
content to attach to.

**Mechanism:** Ask the reader to articulate what they already know about the
paper's keywords, domain, or problem area. These questions should be answerable
*without* reading the paper — they test the reader's existing mental models.

**Output:** 3 questions selected from the 5 activation templates in the
question bank, adapted to the paper's domain.

Example (for "Attention Is All You Need"):
> - 在读这篇论文之前，你对"注意力机制"（attention mechanism）了解多少？请用自己的话描述。
> - RNN/LSTM 在处理长序列时的主要瓶颈是什么？你遇到过哪些具体场景？
> - "序列转导"（sequence transduction）任务通常如何建模？你熟悉哪些经典方法？

### Layer 2: Prediction Layer (预测层 — 假设生成)

**Goal:** Force the reader to commit to a prediction *before* reading, so that
reading becomes a confirmation-or-surprise process rather than passive intake.
Predictions that are wrong are remembered better than predictions that are
right — this is the "hypercorrection effect" leveraged here.

**Mechanism:** Based on the title and abstract, ask the reader to predict the
paper's method, results, or conclusions *in their own words*. The questions
should be specific enough to be falsifiable.

**Output:** 3 questions selected from the 5 prediction templates.

Example (for "Segment Anything"):
> - 基于标题，你预测这篇论文的"可提示的分割"（promptable segmentation）会用什么类型的 prompt？为什么？
> - 你预期 SA-1B 数据集的规模在什么量级？请给出你的估算并说明依据。
> - 如果让你设计一个"通用分割模型"，你会遇到哪些关键挑战？你猜论文解决了哪些、没解决哪些？

### Layer 3: Critical Layer (批判层 — 阅读锚点)

**Goal:** Plant specific critical anchors that the reader should verify,
challenge, or look for during reading. These are not pre-reading questions to
answer now, but rather "reading alarms" that should go off when the reader
encounters the relevant section.

**Mechanism:** Generate specific, verifiable claims or checkpoints derived from
the abstract's claims. Each anchor should correspond to a specific section of
the paper (method, eval, limitations).

**Output:** 3 questions selected from the 5 critical templates.

Example (for "3D Gaussian Splatting"):
> - 论文声称"实时渲染"——阅读时请锚定具体的 FPS 数字和测试场景规模，判断"实时"的定义。
> - 锚点：训练时间。摘要暗示训练比 NeRF 快——请记录具体训练时长对比数据。
> - 批判锚点：论文未提及的局限。你认为 3DGS 在哪些场景可能失效？阅读时留意是否被回避。

## Output Format

The output is a fixed Markdown structure designed to be pasted directly into the
`## 预读问题` section of an Obsidian literature note (the section is created by
the `literature-note.md` Templater template).

```markdown
## 预读问题

> 生成时间: {{YYYY-MM-DD HH:MM}}
> 数据来源: {{user-paste | _high_impact.csv | Literature/@citekey.md | _abstracts.jsonl | title-only-degraded}}
> 论文: {{title}}
> Citekey: {{citekey or "N/A"}}

### 激活层（先验知识）

在读正文之前，请先尝试回答以下问题。答不出也没关系——记录你的"空白点"本身就是预读的价值。

1. {{activation_question_1}}
2. {{activation_question_2}}
3. {{activation_question_3}}

### 预测层（假设生成）

基于标题和摘要，请在读正文**之前**写下你的预测。读完后回来对照——预测错误的点往往是你记忆最深的点。

1. {{prediction_question_1}}
2. {{prediction_question_2}}
3. {{prediction_question_3}}

### 批判层（阅读锚点）

以下问题不是现在回答的，而是阅读时的"锚点"——读到相关章节时，留意是否触发这些锚点。

1. {{critical_question_1}}
2. {{critical_question_2}}
3. {{critical_question_3}}

### 预读自检

- [ ] 我已尝试回答激活层问题（即使答不上来）
- [ ] 我已写下预测层假设（至少 2 条具体预测）
- [ ] 我已标记批判层锚点为"阅读时留意"
- [ ] 我知道自己的最大知识空白点是：______
```

### Output Constraints

- **Language:** Match the paper's primary language. For English papers, the
  questions may be in Chinese (for a Chinese reader) or English — default to
  Chinese unless the user requests English. Technical terms keep original
  English with Chinese gloss on first use.
- **Count:** Exactly 3 questions per layer (9 total), unless degraded mode.
- **No answers:** The output contains ONLY questions, never answers or
  summaries of the paper. If the model is tempted to fill in an answer, it must
  stop and rephrase as a question.
- **No full-paper content:** Never include quotes or paraphrases from the paper
  body. Only title + abstract + metadata are used.
- **Citekey placeholder:** If resolved from CSV/note, fill in the citekey. If
  the user pasted raw text without a citekey, leave `{{citekey}}` as `N/A`.

## Failure Strategies

### Abstract missing → Title-only degraded mode

When no abstract is available from any source, the skill enters **degraded
mode** and generates questions based on the title alone. In this mode:

- Activation layer: 3 questions about keywords/concepts parsed from the title
- Prediction layer: 3 **open-ended** prediction questions (broader, less
  specific — the reader has less to anchor predictions on)
- Critical layer: 3 generic reading-anchor questions (since no claims to verify)

The output must include a degraded-mode warning:

```markdown
> ⚠️ 降级模式：未找到摘要，仅基于标题生成问题。问题质量低于完整模式。
> 建议补充摘要后重新生成（粘贴摘要或提供 citekey 让 Skill 查本地库）。
```

### Title ambiguous or too generic

If the title is too generic to generate domain-specific questions (e.g., "A
Survey on X" with no further context), the skill should:
1. Flag the ambiguity to the user
2. Ask the user to provide at least the area/domain or a 1-sentence description
3. If user cannot provide more, generate generic pre-reading questions and mark
   them as `LOW_QUALITY`

### Citekey not found in any source

If the user provides a citekey that matches nothing in `_high_impact.csv`, no
literature note, and no `_abstracts.jsonl` entry:
1. Report which sources were checked
2. Ask the user to paste the title and abstract directly
3. Do NOT fabricate metadata — never invent an abstract

### Abstract too short (TLDR only)

If the only available abstract is a Semantic Scholar TLDR (typically 1-2
sentences, common in `_high_impact.csv`'s `tldr` field):
1. Use the TLDR but mark the source as `_high_impact.csv (tldr, truncated)`
2. Generate questions with reduced specificity
3. Warn the user that TLDR-based questions may miss nuances

### Multiple papers match the same title

If a title search returns multiple papers (e.g., common survey titles):
1. List the candidates with authors + year + venue
2. Ask the user to disambiguate
3. Do not generate questions until disambiguated

## Interaction Protocol

### Typical invocation

```
User: 预读 vaswani2017
       (or: "读前提问 conf/iccv/KirillovMRMRGXW23")
       (or: pastes title + abstract)
```

### Skill response flow

1. **Parse input** — identify citekey, DOI, title, abstract, and optional
   metadata from the user's message.
2. **Resolve metadata** — apply Source Priority (Priority 1 → 5) to obtain
   title + abstract + optional fields.
3. **Select questions** — from `resources/pre-reading-question-bank.md`, select
   3 templates per layer (9 total), adapted to the paper's domain and the
   available metadata richness.
4. **Adapt questions** — replace template placeholders with paper-specific
   keywords, concepts, and claims extracted from the title/abstract.
5. **Render output** — fill the fixed Markdown template.
6. **Write to note** — if a literature note exists at
   `Literature/@{citekey}.md`, append/replace the `## 预读问题` section.
   If no note exists, output the Markdown for the user to paste manually.
7. **Print summary** — one line: "已生成 N 条预读问题（激活 {a} / 预测 {p} / 批判 {c}），数据来源：{source}。"

### When to ask for clarification

The skill should ask for clarification (rather than guessing) when:
- The citekey matches multiple papers
- The title is too generic without any disambiguating metadata
- The user's intent is ambiguous (e.g., "帮我看看这篇论文" could mean pre-read
  or summarize — confirm pre-read intent)

## Question Quality Checklist

Before outputting, verify each question against this checklist:

- [ ] **Not answerable from abstract alone** — if the question's answer is a
  direct copy-paste from the abstract, revise it.
- [ ] **Specific to this paper** — generic questions like "这篇论文的创新点是什么？"
  are banned; replace with paper-specific questions.
- [ ] **Actionable** — the reader knows what to do (retrieve, predict, or watch
  for) after reading the question.
- [ ] **Domain-appropriate** — AI paper questions differ from HCI paper
  questions; calibrate to the `area` field.
- [ ] **Layer-correct** — activation questions test prior knowledge, prediction
  questions ask for hypotheses, critical questions set reading anchors. Do not
  mix layers.

## Constraints

- This skill does NOT read the full paper. It operates on title + abstract +
  metadata only.
- This skill does NOT generate summaries, paraphrases, or answers. It generates
  questions only.
- This skill does NOT call external APIs (Semantic Scholar, Crossref). It relies
  on local data sources (`_high_impact.csv`, `_abstracts.jsonl`, literature
  notes).
- This skill does NOT handle multiple papers in one invocation. One paper per
  call. For multi-paper pre-reading, invoke once per paper.
- This skill does NOT replace the reading itself. It is a cognitive primer, not
  a substitute for reading.
- The output is always structured Markdown matching the `## 预读问题` section
  format. No free-form prose.

## Relationship to Other Skills

| Skill | Relationship | Boundary |
|-------|-------------|----------|
| `recapping-paper-feynman` | Downstream — runs AFTER reading | Pre-questions ends where Feynman recap begins |
| `linking-paper-concepts` | Downstream — after reading, finds related papers | Pre-questions may mention candidate links but does not resolve them |
| `fact-checking-citations` | Not called by this skill | Pre-questions do not verify citations (no claims made) |
| `synthesizing-literature-review` | Sibling — macro skill | Pre-questions is per-paper; review synthesis is cross-paper |

## References

- Question template bank: `resources/pre-reading-question-bank.md`
- Local data source: `d:\Desktop\论文\_high_impact.csv`
- Local data source: `d:\Desktop\论文\_abstracts.jsonl`
- Literature notes: `d:\Desktop\论文\obsidian-vault\Literature\@{citekey}.md`
- Workflow design doc: `d:\Desktop\论文\.trae\documents\academic-pkm-skill-workflow.md`
