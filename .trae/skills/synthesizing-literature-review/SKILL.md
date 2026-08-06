---
name: synthesizing-literature-review
description: >-
  Synthesize a structured literature review skeleton across a collection of
  papers by clustering them along method / data / metric / contribution
  dimensions, then emit a five-section review (introduction, categorized
  synthesis, method comparison table, research trends, gaps and outlook) into
  the Obsidian vault's Reviews folder. Invoke this skill when the user says
  "综述", "literature review", "对比这几篇", or "synthesize review", or
  provides a citekey list / topic + count and asks for a cross-paper
  synthesis. Do NOT use this skill for single-paper reading (use
  reading-paper-pre-questions or recapping-paper-feynman) or for pure
  chronological timeline output (use building-citation-timeline or
  tracing-lineage-by-era).
---

# Synthesizing Literature Review

## Purpose

This skill is the **macro-level synthesis engine** of the academic PKM
workflow. Given a set of papers (by citekey list or by topic + count), it
reads each paper's material, clusters them along a four-dimensional taxonomy
(method / data / metric / contribution), and produces a five-section review
skeleton that the user can then flesh out. It is the cross-paper counterpart
to the single-paper micro skills (`reading-paper-pre-questions`,
`recapping-paper-feynman`, `linking-paper-concepts`).

Unlike lineage-tracing skills that emphasize temporal evolution, this skill
emphasizes **structural comparison**: how do these papers differ in method,
data, metric, and contribution, and where are the gaps?

## Core Principle

**Anti-hallucination is the core constraint.** A literature review is the
single highest-risk skill for citation fabrication, because the model is
tempted to (a) invent papers that fit a category neatly, (b) misattribute
claims to real papers, and (c) conflate methods across papers. This skill
resists all three by enforcing:

1. **Source-grounded clustering.** Every paper assigned to a cluster must be
   backed by material actually read from the local library (literature note
   or `_abstracts.jsonl`). The model never clusters a paper it has not read.
2. **Mandatory fact-checking before any citation is finalized.** Every
   citation placeholder `[cite:DOI]` (or `[cite:citekey]` /
   `[cite:"TITLE_FRAGMENT"]`) in the skeleton MUST be routed through
   `fact-checking-citations` before the review file is written. A citation
   that was never checked must never appear as if it were verified.
3. **Claim-level grounding.** Any comparative claim ("A outperforms B on X")
   must be traceable to the abstract / annotation of the cited paper. The
   fact-checking handoff carries the claim text alongside the citation so
   `fact-checking-citations` can run its claim-support check.

## Input

The skill accepts one of two input forms:

| Form | Example | Notes |
|------|---------|-------|
| Citekey list | `vaswani2017, devlin2019, radford2019` | Explicit paper set; preferred for "对比这几篇" |
| Topic + count | `"综述 attention mechanism, 8 篇"` | Skill selects the N papers from local index first |

For the topic+count form, paper selection uses this priority:
1. `_high_impact.csv` rows whose `area` / `title` matches the topic, sorted
   by `citation_count` desc.
2. If too few, expand via `_index.csv` title/area keyword match.
3. If still too few, ask the user to provide more citekeys or relax the
   count. Do NOT pad the set with papers the user did not ask for.

The output topic slug is derived from the user's topic (or, for citekey-list
input, from the shared `area` of the papers, confirmed with the user). The
slug is lowercased, hyphenated, ASCII-only (transliterate Chinese topics to
pinyin or keep an English gloss).

## Pipeline

### Step 1 — Read source material per paper

For each input paper, read in this strict priority order. Stop as soon as a
layer yields enough to fill the four clustering dimensions (method / data /
metric / contribution); do not skip a usable layer just because a richer one
exists.

1. **Obsidian literature note** (preferred) —
   `d:\Desktop\论文\obsidian-vault\Literature\@{citekey}.md`. Read frontmatter
   (`title`, `authors`, `year`, `venue`, `doi`, `abstract`, `area`) and the
   ZotLit-synced annotation area (`## Annotations` / `## 高亮`, plus any
   `## 费曼复述` or `## 关联` the user has already built). This is the
   richest source because it carries the user's own reading effort.
2. **`_abstracts.jsonl`** (fallback) — search for the matching `id` and
   extract `abstract`, `title`, `citation_count`. This is the degraded path
   when no literature note exists yet.
3. **`_high_impact.csv` / `_index.csv`** (last resort) — metadata only, no
   abstract. Flag the paper as `METADATA_ONLY` in the clustering table; its
   cluster assignment will be marked `LOW_CONFIDENCE`.

For every paper, extract a structured digest keyed by the four clustering
dimensions:

| Dimension | What to extract | Source |
|-----------|----------------|--------|
| 方法 (method) | Technical route, core mechanism, model family | annotation area / abstract |
| 数据 (data) | Datasets used, scale, domain | annotation area / abstract |
| 指标 (metric) | Evaluation metrics, reported numbers, baselines | annotation area / abstract |
| 贡献 (contribution) | Stated contributions (intro bullets / abstract claims) | annotation area / abstract |

If a dimension cannot be filled from the available source (e.g., the
abstract does not mention datasets), leave it blank rather than guessing.
Blank dimensions are explicitly surfaced in the comparison table as `—`.

### Step 2 — Cluster by taxonomy

Load the full taxonomy and clustering rules from
[`resources/review-skeleton.md`](resources/review-skeleton.md). The summary
below is the execution contract.

Cluster each paper along four orthogonal dimensions:

1. **方法分类法 (method taxonomy)** — by technical route: 基于规则 / 统计
   学习 / 深度学习 / 混合 (see `resources/review-skeleton.md` §七 for the
   full taxonomy, judgment rules, and how to extend it for non-AI domains).
2. **数据聚类 (data clustering)** — by dataset family / scale / domain.
3. **指标聚类 (metric clustering)** — by evaluation protocol (e.g.,
   accuracy vs. efficiency vs. robustness).
4. **贡献维度 (contribution dimension)** — by the type of contribution
   (new method / new dataset / new metric / new analysis / replication).

A paper may belong to multiple sub-clusters within a dimension (e.g., a
method that is both "深度学习" and "混合" because it combines a neural
encoder with a rule-based decoder). Record all applicable labels; do not
force a single bucket.

The clustering step produces an internal assignment table (never shown
verbatim to the user) that drives Step 3.

### Step 3 — Generate the five-section review skeleton

Produce the skeleton following the five-section structure defined in
[`resources/review-skeleton.md`](resources/review-skeleton.md):

1. **引言 (Introduction)** — problem definition, scope, motivation, paper
   selection criteria, structure preview.
2. **分类综述 (Categorized synthesis)** — one sub-section per method
   cluster; within each, narrate how papers in the cluster approach the
   problem and where they differ.
3. **方法对比表 (Method comparison table)** — the fixed-template table
   (方法 | 数据集 | 指标 | 优势 | 局限), one row per paper.
4. **研究趋势 (Research trends)** — cross-paper patterns over method
   family / data scale / metric focus / contribution type.
5. **空白与展望 (Gaps and outlook)** — empty cells in the comparison
   table, missing metric coverage, empty clusters, open problems.

Every citation in the skeleton is written as a placeholder:
- If DOI known: `[cite:10.xxx/yyy]`
- If only citekey known: `[cite:vaswani2017]`
- If only title fragment known: `[cite:"Attention Is All You Need"]`

The placeholder format is deliberately non-final — it signals "this
citation has NOT yet been verified" and must be resolved in Step 4 before
the file is written. The skeleton is held in memory; it is **not** written
to disk until Step 4 completes.

### Step 4 — Verify every citation placeholder via fact-checking-citations

This is the **anti-hallucination gate**. Before writing the review file,
collect every `[cite:...]` placeholder together with the claim it supports,
and hand the full set to `fact-checking-citations`.

Handoff format (one entry per placeholder):

```
{
  "placeholder": "[cite:10.5555/3295222.3295349]",
  "raw_span": "Vaswani et al., 2017",
  "claim": "提出纯注意力架构 Transformer,移除循环与卷积",
  "doi": "10.5555/3295222.3295349",
  "citekey": "vaswani2017"
}
```

`fact-checking-citations` returns `VERIFIED` / `MISMATCH` / `NOT_FOUND` /
`UNSUPPORTED` / `INCONCLUSIVE` per placeholder. Apply the resolution rules:

| Result | Action |
|--------|--------|
| `VERIFIED` + `SUPPORTED` | Replace placeholder with final citation `[[vaswani2017]] (DOI:10.5555/3295222.3295349)`. |
| `VERIFIED` + `UNSUPPORTED` | Keep citation but add inline warning `⚠️ 论断未被摘要支持`; include in "需人工核对" list. Do NOT silently drop. |
| `MISMATCH` | Attempt to correct (wrong year, wrong author); if unresolvable, mark `⚠️ 元数据不符` and ask the user. |
| `NOT_FOUND` | **Remove the citation and the sentence relying on it**, or ask the user to supply a DOI. Never write an unverified citation into the review. |
| `INCONCLUSIVE` | Keep citation but mark `⚠️ 未核对(无摘要)`; include in "需人工核对" list. |
| fact-checking-citations unavailable | **Abort the write.** Print the skeleton with all placeholders intact and a prominent banner (see Failure Strategies). Never write a review whose citations were never checked. |

The final citation format in the written review is the Obsidian wikilink
`[[citekey]]` (resolves to `Literature/@citekey.md`), with a parenthetical
DOI on first mention for traceability: `[[vaswani2017]] (DOI:10.5555/3295222.3295349)`.

### Step 5 — Write output to Reviews/{topic}-review.md

Write the verified review to:

```
d:\Desktop\论文\obsidian-vault\Reviews\{topic-slug}-review.md
```

If the file already exists, append a dated new version under an
`## 更新记录` section rather than overwriting (preserves revision history).
If the directory `Reviews\` does not exist, create it.

The file frontmatter follows the project convention:

```yaml
---
type: review
topic: attention-mechanism
paper_count: 8
citekeys: [vaswani2017, devlin2019, ...]
generated: 2026-07-21
fact_check_status: passed  # or "partial", "failed"
unverified_citations: []   # list of placeholders that remain unresolved
---
```

After writing, print a one-line summary:

> 已生成综述骨架: {topic} ({N} 篇),引用反查 {passed}/{total} 通过,写入 Reviews/{topic}-review.md。

## Anti-Hallucination Protocol (Summary)

The full protocol is enforced in Step 4 above. The non-negotiable rules:

1. **No citation is written to the review file without passing
   fact-checking-citations.** This includes citations inside the comparison
   table and inside the trends section.
2. **No paper is assigned to a cluster without having been read**
   (literature note, abstract, or at minimum metadata). The model's
   parametric memory of "what paper X is about" is not a substitute for
   reading the local source.
3. **No comparative claim ("A outperforms B") is written unless both A and
   B's abstracts/annotations support the claim.** If only one side supports
   it, the claim is downgraded to "A reports X; B does not address X" —
   never fabricated into a head-to-head.
4. **Blank cells are honest.** A dimension the source does not cover is
   left as `—`, not guessed.
5. **fact-checking-citations unavailability aborts the write.** A review
   with unchecked citations is worse than no review.

## Failure Strategies

### Literature note missing for some papers

When `Literature/@{citekey}.md` does not exist for a subset of papers:

1. **Degrade to abstract mode** for those papers: read `_abstracts.jsonl`
   (priority) or `_high_impact.csv` / `_index.csv` `tldr` field.
2. Mark those papers' digests as `(abstract-only)` in the internal
   clustering table.
3. In the comparison table, prefix their `方法` cell with `📜` and add a
   note under the table: "📜 标记的论文仅基于摘要聚类,方法细节可能不完整。"
4. Do NOT refuse to run — degraded clustering is still useful. But do NOT
   silently pretend the abstract is as rich as a full annotation.

### All literature notes missing (abstract-only run)

If NO paper has a literature note:

1. Run the full pipeline in abstract-only mode.
2. Add a prominent banner at the top of the review:

   ```
   > ⚠️ 降级模式:本综述全部基于摘要生成,未使用任何 ZotLit annotation。
   > 方法/贡献维度的聚类可能较粗,建议为关键论文补建 literature note 后重跑。
   ```

3. Reduce the expected depth of the 方法对比表 — abstracts rarely contain
   enough method detail to fill `优势` / `局限` cells reliably. Fill what
   the abstract supports; mark the rest `— (需读全文)`.

### Paper not found in any local source

If a citekey resolves to nothing (not in `_index.csv`, `_abstracts.jsonl`,
`_high_impact.csv`, and no literature note):

1. Report which citekeys were unresolvable.
2. Ask the user to either supply the DOI / paste the abstract, or drop the
   paper from the set.
3. Do NOT fabricate metadata for the missing paper.

### fact-checking-citations unavailable

Scripts missing, network down, or `fact-checking-citations` skill not
installed:

1. **Abort the write** (see Step 4 table).
2. Print the skeleton inline with all `[cite:...]` placeholders intact.
3. Print a prominent banner:

   ```
   > ⛔ 引用反查不可用,综述未写入 vault。
   > 请配置 fact-checking-citations 后重跑。
   > 骨架已展示供审阅聚类结构,但所有引用均为未校验占位符。
   ```

4. The skeleton is still useful for the user to review the clustering, but
   it must not be written to the vault as if it were a verified review.

### Too few papers for a meaningful review (<3)

1. Warn the user that a review with <3 papers is degenerate (no clustering
   possible, no trends to identify).
2. Offer to either (a) expand the set via `linking-paper-concepts` on the
   focal papers, or (b) proceed but label the output as a "对比笔记
   (comparison note)" rather than a full review.
3. Do not pad the set with papers the user did not ask for.

### Too many papers (>30)

1. Warn that clustering quality degrades above ~30 papers.
2. Offer to either (a) subsample by stratifying across method clusters, or
   (b) split into multiple sub-reviews by method family.
3. Do not silently truncate.

### Cluster is empty or singleton

1. An empty cluster is still listed in the 分类综述 section, with a note
   "本类暂无入选论文" — this is itself a gap signal (see 空白与展望).
2. A singleton cluster is listed, but the narrative notes that no
   within-cluster comparison is possible; cross-cluster comparison still
   applies.

## Cross-Skill Dependencies

| Direction | Skill | Trigger | What passes across |
|-----------|-------|---------|--------------------|
| calls | `fact-checking-citations` | Before writing the review file (Step 4, every run) | `(placeholder, raw_span, claim, doi, citekey)` tuples; receives VERIFIED / MISMATCH / NOT_FOUND / UNSUPPORTED / INCONCLUSIVE per citation |
| may call | `linking-paper-concepts` | When input is topic+count and the local index yields too few papers | Topic + focal citekeys; receives candidate related citekeys to expand the set |
| is called by | (none) | — | — |

This skill does **not** call `tracing-lineage-by-era`,
`tracing-lineage-by-team`, or `building-citation-timeline`: those are
temporal-evolution skills, while this skill is structural comparison. If
the user asks "这个领域怎么演进的", route them to `tracing-lineage-by-era`
instead.

## Interaction Contract

1. **Acknowledge**: repeat the resolved paper set (citekeys + titles) and
   the topic slug, so the user can confirm the right papers were picked up.
2. **Report source status**: before showing the skeleton, state how many
   papers had literature notes vs. abstract-only vs. metadata-only (e.g.,
   "5 篇有 literature note,2 篇仅摘要,1 篇仅元数据")。
3. **Show the skeleton draft** (with `[cite:...]` placeholders) for user
   review BEFORE running fact-checking — the user may want to edit
   clustering or drop a paper.
4. **Run fact-checking-citations** and report the per-citation results.
5. **Write & confirm**: after writing, report the exact file path, the
   number of citations, and how many passed verification.

## Constraints

- This skill operates on **≥3 papers**. For 1–2 papers, route to
  `linking-paper-concepts` (1 paper) or a manual comparison note (2 papers).
- This skill does **not** read full PDFs. It relies on literature notes and
  abstracts. If the user wants a full-text-grounded review, they should
  run ZotLit annotation on the papers first.
- This skill does **not** generate the final prose of a publishable survey.
  It generates a **skeleton** (structure + comparison table + placeholders
  for narrative) that the user fleshes out. The 分类综述 section is written
  in bullet-point narrative, not publishable paragraphs.
- Every citation in the written file is an Obsidian wikilink `[[citekey]]`
  pointing to a literature note. Citations to papers without a literature
  note use `[[citekey]]?` (the `?` marks a dangling link the user should
  resolve by running ZotLit import).
- This skill **never** writes a citation that has not passed
  `fact-checking-citations`. If fact-checking is unavailable, the file is
  not written.
- The SKILL.md stays ≤ 500 lines; the full taxonomy, comparison table
  template, trend-analysis playbook, and citation format rules live one
  level deep in `resources/review-skeleton.md`.

## References

- Review skeleton template & taxonomy: [`resources/review-skeleton.md`](resources/review-skeleton.md)
- Anti-hallucination infrastructure: `fact-checking-citations` skill (`d:\Desktop\论文\.trae\skills\fact-checking-citations\SKILL.md`)
- Local data sources: `d:\Desktop\论文\_abstracts.jsonl`, `d:\Desktop\论文\_high_impact.csv`, `d:\Desktop\论文\_index.csv`
- Literature notes: `d:\Desktop\论文\obsidian-vault\Literature\@{citekey}.md`
- Output location: `d:\Desktop\论文\obsidian-vault\Reviews\{topic}-review.md`
- Workflow design doc: `d:\Desktop\论文\.trae\documents\academic-pkm-skill-workflow.md`
