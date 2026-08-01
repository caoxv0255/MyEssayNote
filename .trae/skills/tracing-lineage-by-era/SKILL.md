---
name: tracing-lineage-by-era
description: >-
  Trace the historical evolution of a research topic across eras by combining
  Semantic Scholar search results with the local paper index, segmenting
  papers into time buckets (default 5-year spans, user-configurable
  breakpoints), extracting each era's dominant paradigm, key breakthroughs,
  and remaining problems from 3-5 representative papers per bucket, and
  emitting a Mermaid timeline or Markdown table into the Obsidian vault.
  Invoke this skill when the user says "脉络", "演进", "分年代",
  "lineage by era", or "这个领域怎么发展起来的" for a research topic that
  spans multiple years. Do NOT use this skill for single-team retrospectives
  or single-paper recaps/reviews — 不要用于单团队追溯或单篇论文综述 (use
  tracing-lineage-by-team for team scopes, recapping-paper-feynman /
  synthesizing-literature-review for single-paper work).
---

# Tracing Lineage By Era

## Purpose

This skill is the **macro-level historical-evolution builder** of the academic
PKM workflow. Given a research topic (e.g., "attention mechanism"), it stitches
together a cross-era narrative — how the dominant paradigm shifted decade by
decade — and writes the result as a timeline artifact the user can revisit
during spaced review.

Unlike micro skills that operate on one focal paper (`linking-paper-concepts`)
or team-scoped skills that follow one lab's output (`tracing-lineage-by-team`),
this skill is **topic-centric and time-sliced**: it answers "how did this
field develop over the years", not "who worked on what" or "what relates to
this one paper".

## Core Principle

**Every paper named in the lineage must be real, DOI-verifiable, and
attributable to its era by publication year.** A lineage narrative is useless
if it cites a paper that does not exist, misdates a breakthrough, or invents a
"dominant paradigm" that no real paper advocated. Therefore:

1. Paper candidates come only from Semantic Scholar + the local `_index.csv` —
   never from the model's parametric memory.
2. Any paper mentioned in the final output MUST carry a `citekey` + `DOI`.
3. Before the output is written, all DOIs are routed through the
   `fact-checking-citations` skill for existence verification.
4. The "dominant paradigm / key breakthrough / remaining problem" triplet for
   each era is grounded in the abstracts/TLDRs of that era's representative
   papers — not in free-form generation.

## Input

- **Required**: a research topic, given as free-text keywords.
  - Example: `attention mechanism`, `graph neural network`, `diffusion model`.
- **Optional**:
  - Era breakpoints, e.g., `断点: 2006, 2014, 2017, 2020`. If omitted, the
    skill falls back to **5-year spans** anchored at the earliest paper year
    found in the merged set.
  - Per-era representative-paper count, default **3–5**. User may widen to
    `3-8` for foundational eras.
  - Output format preference: `mermaid` (default) or `table`.
  - `直接写入` / `auto-write`: skip the confirmation step and write the note
    immediately.

### Topic → query normalization

The raw topic is normalized into an S2 search query:

- Lowercase; strip filler words ("的", "the", "mechanism" is kept because it
  is load-bearing in "attention mechanism").
- If the topic contains a well-known acronym (e.g., "GNN"), expand to the full
  phrase for the S2 query but keep the acronym for display.
- The normalized string is what gets passed to `s2_search.py`.

## Pipeline

### Step 1 — Pull topic papers from Semantic Scholar

Call the local script (owned by this skill):

```
python d:\Desktop\论文\.trae\skills\tracing-lineage-by-era\resources\s2_search.py \
    "<normalized topic>" --limit 1000
```

- `--limit 1000` is the hard cap (the skill never pulls more than 1000).
- The script returns papers sorted by `citationCount` descending, with fields:
  `title, authors, year, venue, citationCount, externalIds, abstract, tldr,
  embedding.specter_v2`.
- The JSON is captured in memory for the next step.

**Why 1000?** A lineage that spans 20+ years needs depth per era; 1000 gives
roughly 3–8 papers per 5-year bucket after citation pruning. Pulling more
would hit S2 rate limits without materially changing the era-level narrative.

### Step 2 — Merge with local `_index.csv`

Read `d:\Desktop\论文\_index.csv`. Match rows whose `title` or `tldr` or
`area` contains the topic keywords (case-insensitive substring OR simple
token overlap ≥ 2 tokens). For each matched local row:

- Normalize to the same schema as the S2 result (title / authors / year /
  venue / citationCount / doi / abstract / tldr).
- `citekey` is taken from the local row's `id` (DBLP-style key) — local rows
  are the **only** source of citekeys, because S2 does not know the user's
  BibTeX keys.
- If a local row and an S2 row share the same DOI, **merge**: keep S2's
  `citationCount`/`embedding` (richer) and the local row's `citekey`/
  `local_pdf` (only in local). Do not duplicate.

The merged set is the working corpus for era segmentation.

### Step 3 — Segment by era

Determine the year range from the merged set (`min_year`..`max_year`).

- If the user supplied breakpoints, use them directly. Validate that every
  paper falls into exactly one bucket; papers before the first breakpoint go
  into a leading "早期 (<{bp0})" bucket, papers after the last breakpoint go
  into a trailing "近期 (≥{bpN})" bucket.
- Otherwise, use **5-year spans** anchored at `min_year`:
  `[min_year, min_year+5)`, `[min_year+5, min_year+10)`, …
- Buckets with fewer than 3 papers are **merged into the adjacent bucket**
  (do not emit a 1-2-paper era; it carries no "paradigm").

Each bucket is labeled `YYYY–YYYY` (inclusive start, exclusive end).

### Step 4 — Pick representatives + extract the era triplet

For each era bucket, with `k = 3–5` (user-tunable):

1. **Rank** the bucket's papers by `citationCount` descending.
2. **Diversify**: after taking the top `ceil(k/2)` by citation, fill the rest
   by maximizing venue diversity (don't take 5 papers from the same venue)
   and recency within the bucket (so the era's *end-state* paradigm is
   represented, not just its founding paper).
3. **Extract the triplet** for the era, grounded in the representatives'
   abstracts/TLDRs only:
   - **主导范式 (dominant paradigm)**: one phrase, e.g., "RNN + attention
     on encoder-decoder".
   - **关键突破 (key breakthrough)**: 1–2 sentences naming the specific
     contribution, each tied to a representative paper by `citekey`.
   - **遗留问题 (remaining problems)**: 1–2 sentences, drawn from the
     "limitations / future work" language in the abstracts, NOT invented.

If the representatives' abstracts do not support a clean triplet (e.g., all
5 papers are applications with no methodological shift), mark the era as
**"无显著范式更迭（应用扩展期）"** rather than fabricating a paradigm shift.

### Step 5 — Emit timeline + write to vault

Two output formats; `mermaid` is the default, `table` is the fallback when
the Mermaid syntax would exceed ~40 nodes (Obsidian rendering gets sluggish).

#### Mermaid timeline (default)

```mermaid
timeline
    title Attention Mechanism 脉络 (1990–2024)
    section 1990–1995 : 早期信号 : 主导范式: 手工特征
    section 1996–2000 : ...
    section 2014–2018 : 突破期 : 主导范式: 软注意力
                       : [[bahdanau2014]] 提出加性注意力
                       : [[vaswani2017]] 自注意力替代循环结构
                       : 遗留: 长序列 O(n²) 复杂度
    section 2019–2024 : ...
```

Every `[[citekey]]` wikilink MUST point to a note in `Literature/@citekey.md`
or be annotated `([[citekey]] {DOI})` if the note does not yet exist.

#### Markdown table (fallback)

```markdown
## Attention Mechanism 分年代脉络

| 年代 | 主导范式 | 关键突破 | 遗留问题 | 代表作 |
|------|---------|---------|---------|--------|
| 2014–2018 | 软注意力 / 自注意力 | [[bahdanau2014]](DOI:10.48550/arXiv.1409.0473) 提出加性注意力；[[vaswani2017]](DOI:10.5555/3295222.3295349) 自注意力替代循环 | 长序列 O(n²) 复杂度；位置编码表达力弱 | bahdanau2014, vaswani2017, luong2015, ... |
| ... | | | | |
```

#### Write protocol

1. Target path: `d:\Desktop\论文\obsidian-vault\Reviews\{topic}-lineage.md`.
   - `{topic}` is the slugified topic (lowercase, hyphens, no spaces).
   - Create the `Reviews/` folder if it does not exist.
2. If the file already exists: **preserve the frontmatter and any
   `> [!user-note]` callouts**, replace only the timeline/table section and
   the `## 脉络依据` section. Never overwrite user-authored prose outside
   callouts.
3. Always append a `## 脉络依据` (provenance) section listing, per era, the
   representative papers with `citekey + DOI + citationCount + year + venue`,
   so the user can audit the narrative.
4. Append a `## 引用反查记录` section placeholder — the
   `fact-checking-citations` skill will fill it after DOI verification.
5. Confirm the exact path and node/row count to the user after writing.

## Anti-Hallucination (Mandatory)

This is the non-negotiable guardrail. The lineage output is **blocked from
being written** until the following passes:

### A1. Citekey + DOI on every paper mention

Any paper named in the timeline, the table, or the triplet prose MUST appear
as `[[citekey]]` (wikilink) AND carry its DOI, either inline
`([[citekey]] {DOI})` or in the `## 脉络依据` table. A bare author-year like
`[Vaswani et al., 2017]` without a citekey/DOI is a **hallucination risk**
and is rejected before write.

- `citekey` source: the local `_index.csv` `id` field. If a paper came only
  from S2 (no local row), synthesize a citekey as `firstauthor{year}` (e.g.,
  `vaswani2017`) and flag it `citekey=合成` in `## 脉络依据` so the user knows
  it is not yet in their BibTeX.

### A2. Route all DOIs through `fact-checking-citations`

Before writing the note, collect every distinct DOI mentioned in the output
and hand the text to the `fact-checking-citations` skill:

```
请反查以下 lineage 文本中所有引用的 DOI 真实性：
<full timeline/table text>
```

The fact-checking skill will:
- Verify each DOI exists via Crossref (fallback: S2).
- Verify title/author/year match.
- Return `VERIFIED` / `NOT_FOUND` / `MISMATCH` per citation.

### A3. Write-blocking on failure

- If **any** DOI returns `NOT_FOUND`: **do not write the note**. Remove the
  offending paper from the lineage, re-derive the era triplet from the
  remaining representatives, and re-run A2. Only write once all DOIs verify.
- If a DOI returns `MISMATCH` (e.g., title drift): keep the paper but annotate
  it `⚠️ DOI核对存疑` in `## 脉络依据`, and surface the mismatch in the
  response to the user. The note may still be written, but the warning is
  visible.
- If the `fact-checking-citations` skill itself is unavailable (script
  missing, network down): **fall back to writing the note with a prominent
  banner** at the top:

  ```
  > [!warning] 引用未反查
  > fact-checking-citations 暂不可用，本脉络中的 DOI 尚未经过外部核对。
  > 请在 skill 恢复后重跑反查。
  ```

  The banner is mandatory; silent unverified writes are forbidden.

### A4. Triplet grounding

The "主导范式 / 关键突破 / 遗留问题" text for each era must be traceable to
the representatives' `abstract` / `tldr` fields. If the model cannot point to
a supporting sentence in an abstract, the triplet line is dropped and the era
is labeled per Step 4's "无显著范式更迭" rule. Never paraphrase from
parametric memory.

## Failure Strategies

### F1. S2 rate limit (primary failure mode)

When `s2_search.py` exhausts its 429 retries (5 attempts, exponential backoff
1s→2s→4s→8s→16s) and returns an empty or partial list:

1. **Prioritize the local `_index.csv`**. Run Step 2's local match on its own
   and proceed with the local-only corpus. The local index is the trusted
   fallback; it has `citation_count` and `tldr` columns sufficient for era
   segmentation.
2. Print a clear banner in the response (not just the note):

   ```
   > [!warning] S2 限速降级
   > Semantic Scholar 限速，本次脉络仅基于本地 _index.csv（N 篇）。
   > 覆盖度可能不足，建议配置 S2_API_KEY 后重跑。
   ```
3. If the local index also returns fewer than 10 papers for the topic, **stop
   and ask the user** whether to retry S2 later or proceed with a thin
   lineage. Do not fabricate coverage.
4. Anti-hallucination (A1–A4) still applies in full to the local-only path —
   local rows carry DOIs that must still be verified.

### F2. `_index.csv` missing or empty

- If `_index.csv` is absent: the skill cannot proceed on the local path. Rely
  solely on S2 (Step 1 only). Warn that citekeys will all be `合成` and
  recommend the user build the local index first.
- If `_index.csv` exists but has zero topic matches: proceed with S2-only
  results; citekeys are `合成` for every paper.

### F3. Topic too broad / too narrow

- **Too broad** (e.g., "machine learning"): S2 returns 1000 papers but they
  span every subfield and the era triplets become meaningless. Detect this
  when the top-1000 papers' titles share <30% token overlap with the query.
  Ask the user to narrow the topic (e.g., "machine learning for protein
  structure") before proceeding.
- **Too narrow** (e.g., a single paper title): fewer than 3 eras after
  bucketing. Ask the user to broaden; otherwise emit a 1-era "spotlight"
  instead of a lineage and suggest `recapping-paper-feynman`.

### F4. Network / script errors

- `requests` not installed: print `pip install requests` and abort.
- `s2_search.py` file not found: print the expected absolute path and abort.
- Crossref down during A2: fall back to S2-based DOI verification
  (`s2_verify.py --doi`); if both down, apply A3's unverified-write banner.

### F5. Era bucketing edge cases

- All papers in one year: emit a single-era spotlight (see F3).
- Gaps > 5 years between buckets: label the gap `断代期 (YYYY–YYYY)` and note
  "本时期无 matching 论文；可能是子领域转向或检索词遗漏" — do not invent
  papers to fill the gap.

## Cross-Skill Dependencies

This skill calls scripts and skills owned elsewhere. Always reference them by
absolute project path so the dependency is explicit:

- `d:\Desktop\论文\.trae\skills\tracing-lineage-by-era\resources\s2_search.py`
  — owned by this skill; Step 1 data source.
- `d:\Desktop\论文\.trae\skills\fact-checking-citations\SKILL.md`
  — invoked in A2 for DOI verification. **Blocking dependency**: the note is
  not written until this skill returns (or the A3 banner fallback applies).
- `d:\Desktop\论文\_index.csv`
  — local paper index; Step 2 data source and F1 fallback. Read-only.
- `d:\Desktop\论文\obsidian-vault\Reviews\`
  — write target for Step 5. Created on demand.

This skill does **not** call `linking-paper-concepts` (single-paper radius),
`tracing-lineage-by-team` (team-scoped), or `synthesizing-literature-review`
(cross-cutting synthesis without era slicing). If the user's request fits one
of those, route them there instead — see the negative conditions in the
frontmatter description.

## Interaction Contract

1. **Acknowledge**: echo the resolved topic, the era range, and the bucket
   plan (breakpoints or 5-year default) so the user can confirm before the
   (rate-limit-sensitive) S2 pull.
2. **Report data-source status**: before showing results, state whether S2
   and/or local index supplied the corpus (e.g., "S2 拉取 847 篇 + 本地匹配
   23 篇，去重后 856 篇进入分年代")。
3. **Show the timeline/table** for review.
4. **Show the DOI verification report** from `fact-checking-citations`
   (inline summary, full report in `## 引用反查记录`).
5. **Ask before writing** unless `直接写入` was given. Confirm path:
   `obsidian-vault\Reviews\{topic}-lineage.md`.
6. **Write & confirm**: report the exact file path, node/row count, and the
   count of `VERIFIED` vs `MISMATCH` citations.

## Constraints

- This skill operates on **one topic at a time**. If the user asks for
  multiple topics, run sequentially.
- This skill does **not** trace a single author/lab — that is
  `tracing-lineage-by-team`. Route "X 课题组的工作脉络" there.
- This skill does **not** recap a single paper — that is
  `recapping-paper-feynman`. Route "这篇论文讲了什么" there.
- This skill does **not** synthesize a cross-cutting review without era
  structure — that is `synthesizing-literature-review`.
- The 5-year default is a heuristic, not a law. The user may set any
  breakpoints; the skill obeys them verbatim.
- Representative-paper count is capped at 8 per era to keep the timeline
  readable; more than 8 is a review, not a lineage.
- The Mermaid timeline is capped at ~40 nodes; beyond that, auto-switch to
  the Markdown table format.
- All file writes target `obsidian-vault\Reviews\{topic}-lineage.md` only.
  This skill never touches `Literature/@citekey.md` notes, MOC files, or
  `_index.csv`.
- The skill must state its limitations in every output: "脉络基于 S2 +
  本地索引的论文集合，受检索词与覆盖度限制；跨年代范式判断需结合原文阅读
  最终确认。"
