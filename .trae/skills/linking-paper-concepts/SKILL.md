---
name: linking-paper-concepts
description: >-
  Discover papers related to a focal paper through four complementary
  association channels — same venue/year (同源), shared first or
  corresponding author (同人), shared references (同引), and semantic
  similarity via SPECTer v2 embeddings (同义) — then emit pasteable
  Obsidian wikilinks into the literature note's "## 关联" section.
  Invoke this skill when the user says "关联", "这篇和哪些有关",
  "建立链接", "associate", or "find related papers" for a single focal
  paper. Do NOT use this skill for cross-era lineage tracing (use
  tracing-lineage-by-era) or for synthesizing a full literature review
  across many papers (use synthesizing-literature-review).
---

# Linking Paper Concepts

## Purpose

This skill is the **micro-level knowledge-network builder** of the academic
PKM workflow. Given one focal paper, it surfaces candidate related papers
through four orthogonal association channels and writes the results as
`[[wikilink]]` lines directly into the paper's Obsidian literature note.

Unlike macro skills that span eras or teams, this skill stays **within the
single-paper radius**: it answers "what else in my library is connected to
*this* paper, and why?" — not "how did this field evolve over a decade."

## Core Principle

**Every association must carry a machine-verifiable reason.** A bare
`[[wikilink]]` without an association type and a one-sentence rationale is
useless for spaced review. The four channels are deliberately non-overlapping
so that the user can see *why* each candidate surfaced:

| Channel | Chinese | Signal | Data source |
|---------|---------|--------|-------------|
| 1 | 同源 | same venue + same year | local `_index.csv` |
| 2 | 同人 | shared first/corresponding author | local `_index.csv` `authors` |
| 3 | 同引 | shared references (co-citation) | `citation_graph.py` (S2 `/references`) |
| 4 | 同义 | semantic similarity | `s2_search.py` (`embedding.specter_v2` cosine) |

Channels 1–2 are pure-local (no network). Channel 3 needs S2 references.
Channel 4 needs S2 embeddings. This split drives the failure strategy below.

## Input

- **Required**: the focal paper's `citekey` (e.g., `vaswani2017`).
- The citekey is the shared primary key across Zotero, `_index.csv`,
  `_ccf_a.bib`, and the Obsidian literature note filename (`Literature/@citekey.md`).

### Resolution path (citekey → metadata)

1. Look up `citekey` in local `_index.csv` to obtain
   `title`, `authors`, `year`, `venue`, `doi`.
2. If `_index.csv` lacks the row, fall back to `_ccf_a.bib`
   (BibTeX entry keyed by citekey).
3. If still unresolved, query Zotero local API
   `http://localhost:23119/api/users/0/items?q={citekey}&format=keys`
   to recover the DOI, then re-resolve.
4. If the citekey cannot be resolved at all, **stop** and ask the user to
   confirm the citekey or provide the DOI. Do not fabricate metadata.

## Four-Channel Association Retrieval

Detailed per-channel logic lives in
[`resources/association-prompts.md`](resources/association-prompts.md).
The summary below is the execution contract.

### Channel 1 — 同源 (same venue, same year)

- **Query**: `SELECT * FROM _index.csv WHERE venue = {focal_venue} AND year = {focal_year} AND citekey != {focal_citekey}`
- **Rationale template**: "同发表于 `{venue}` ({year})。"
- **Sort**: by `citation_count` descending (from `_index.csv` if present,
  else by S2 `citationCount` cached locally).
- **Cap**: top 8 candidates.
- **Pure local** — no API call.

### Channel 2 — 同人 (shared first / corresponding author)

- **Query**: parse `authors` field of focal paper; extract first author
  family name and corresponding-author marker (if present). Match any other
  row in `_index.csv` whose `authors` shares the first-author family name
  OR the corresponding author.
- **Rationale template**: "共享一作 `{family}`。" or "共享通讯作者 `{family}`。"
- **Sort**: by recency (year desc), then citation_count desc.
- **Cap**: top 8 candidates.
- **Pure local** — no API call.

### Channel 3 — 同引 (shared references / co-citation)

- **Query**: call `citation_graph.py --references {doi_or_s2id}` to fetch
  the focal paper's reference list. For each candidate already surfaced by
  channels 1–2 (plus up to 50 high-citation neighbors from `_index.csv`),
  fetch its reference list and compute the Jaccard intersection with the
  focal set.
- **Rationale template**: "共享 {n} 篇参考文献 ({pct}% Jaccard)。"
- **Sort**: by shared-reference count desc, then Jaccard desc.
- **Cap**: top 8 candidates with shared count ≥ 3.
- **Needs S2** `/references` endpoint.

### Channel 4 — 同义 (semantic similarity)

- **Query**: call `s2_search.py --embedding {doi_or_s2id}` to fetch the
  focal paper's `embedding.specter_v2` vector. Compute cosine similarity
  against the SPECTer v2 embeddings of all candidates surfaced so far
  (channels 1–3). If too few candidates have embeddings, expand the pool
  via `s2_search.py --similar {doi_or_s2id}` (S2 recommended-similar).
- **Rationale template**: "语义相似 (cosine = {score:.3f})。"
- **Sort**: by cosine similarity desc.
- **Cap**: top 8 candidates with cosine ≥ 0.5.
- **Needs S2** embeddings endpoint.

## Output Format

The skill produces two artifacts.

### Artifact 1 — Candidate table (shown to user for review)

```markdown
## 关联候选（{citekey}）

| # | citekey | 标题 | 关联类型 | 关联理由 |
|---|---------|------|---------|---------|
| 1 | devlin2019 | BERT | 同引 | 共享 12 篇参考文献 (18% Jaccard)。 |
| 2 | radford2019 | Language Models are Unsupervised Multitask Learners | 同人 | 共享一作 family。 |
| 3 | press2021 | Train Short, Test Long | 同义 | 语义相似 (cosine = 0.72)。 |
| ... | | | | |
```

### Artifact 2 — Pasteable wikilink block (written into the note)

For each approved candidate, generate one line:

```
- [[@devlin2019]] — 同引：共享 12 篇参考文献 (18% Jaccard)。
- [[@radford2019]] — 同人：共享一作 family。
- [[@press2021]] — 同义：语义相似 (cosine = 0.72)。
```

These lines are written **directly** into the focal paper's literature note
at `Literature/@{citekey}.md`, under the `## 关联` section.

### Write protocol

1. Read `Literature/@{citekey}.md`.
2. Locate the `## 关联` heading.
   - If it exists: replace the section body (between `## 关联` and the next
     `##` heading) with the new wikilink block. Preserve any user-authored
     prose paragraphs outside the generated block by wrapping them in a
     `> [!user-note]` callout.
   - If it does not exist: append the `## 关联` section at the end of the
     note (before `## 引用反查记录` if present).
3. If the note file does not exist at all, **do not create it** — this skill
   assumes ZotLit has already generated the literature note. Instead, print
   the wikilink block and instruct the user to run ZotLit import first.
4. Never overwrite frontmatter or other sections.

### Multi-channel deduplication

A candidate may surface via multiple channels (e.g., both 同源 and 同引).
Deduplicate by citekey. In the table, list the **strongest** channel first
(priority: 同引 > 同人 > 同源 > 同义) and append other channels in the
rationale: "同引：共享 8 篇参考文献；亦同源 (NeurIPS 2017)。"

## Failure Strategies

### S2 API rate limit (channels 3 & 4 unavailable)

When `s2_search.py` or `citation_graph.py` returns HTTP 429, or when three
consecutive retries with exponential backoff (1s, 2s, 4s) all fail:

1. **Degrade to local three-channel mode**: run only channels 1 (同源),
   2 (同人), and a *heuristic* channel 3 that uses `_index.csv` shared
   `venue` + `area` + overlapping title keywords as a proxy for co-citation
   (clearly labeled "同引(本地启发式)" in the rationale).
2. Omit channel 4 (同义) entirely — there is no local embedding store.
3. Print a clear banner in the output:

   ```
   > [!warning] S2 限速降级
   > 语义相似(同义)与精确同引不可用，本次仅输出同源/同人/本地启发式同引三路结果。
   > 建议配置 S2_API_KEY 后重跑以获得完整四路关联。
   ```

4. Do NOT silently drop channels — the user must know which signals are
   missing so they can judge the recall of the result.

### Partial failures

| Failure | Action |
|---------|--------|
| `_index.csv` not found | Stop; instruct user to run the index build step. |
| `citation_graph.py` not found | Skip channel 3; warn that cross-skill script is missing. |
| `s2_search.py` not found | Skip channel 4; warn that cross-skill script is missing. |
| Focal paper has no DOI / S2 ID | Channels 3–4 unavailable; run channels 1–2 only with a warning. |
| Focal paper has no SPECTer v2 embedding | Skip channel 4; channels 1–3 still run. |
| Literature note file missing | Print wikilink block; do not create the note. |
| Zotero local API down | Channels 1–2 still work from `_index.csv`; only citekey→DOI resolution for channels 3–4 is blocked. Warn the user. |

### Empty results

If a channel returns zero candidates, say so explicitly in the table rather
than omitting the channel. The user needs to know the association was
*searched and found empty*, not *forgotten*.

```
| — | (同义无候选) | — | 同义 | 语义相似度均低于 0.5 阈值。 |
```

## Cross-Skill Dependencies

This skill calls scripts owned by other skills. Always reference them by
their project-relative path so the dependency is explicit:

- `d:\Desktop\论文\.trae\skills\building-citation-timeline\resources\citation_graph.py`
  — used for channel 3 (reference list fetch + Jaccard).
- `d:\Desktop\论文\.trae\skills\tracing-lineage-by-era\resources\s2_search.py`
  — used for channel 4 (SPECTer v2 embedding fetch + cosine).

If either script is absent, this skill degrades gracefully (see Failure
Strategies) rather than crashing.

This skill does **not** call `fact-checking-citations` — association
candidates are drawn from the local library and S2, which are already
trusted sources. If the user later cites a related paper in a macro skill,
*that* skill routes through fact-checking.

## Interaction Contract

1. **Acknowledge**: repeat the resolved focal paper (citekey + title) so the
   user can confirm the right paper was picked up.
2. **Report channel status**: before showing results, state which channels
   ran successfully and which degraded (e.g., "同义路因 S2 限速已降级")。
3. **Show candidate table** for review.
4. **Ask before writing**: confirm with the user which candidates to keep
   (default: all). Do not auto-write the note without confirmation unless
   the user pre-approved with "直接写入" / "auto-write".
5. **Write & confirm**: after writing, report the exact file path and the
   number of wikilinks inserted.

## Constraints

- This skill operates on **one focal paper at a time**. If the user asks to
  relate multiple papers, invoke this skill once per paper sequentially.
- This skill does **not** generate prose narratives about why papers relate
  — it outputs structured association lines only. Narrative synthesis is the
  job of `synthesizing-literature-review`.
- This skill does **not** trace temporal evolution — that is
  `tracing-lineage-by-era`. If the user asks "attention 怎么演进的", route
  them there instead.
- The local heuristic co-citation (degraded channel 3) is explicitly labeled
  as heuristic and must never be presented as precise Jaccard.
- Embedding cosine ≥ 0.5 is a soft threshold; the skill reports the raw
  score so the user can judge.
- All file writes target `Literature/@{citekey}.md` only. This skill never
  touches MOC files, Reviews, or other notes.

## Detailed Channel Reference

For the full retrieval logic, data-source specifics, sorting rationale, and
worked examples per channel, see
[`resources/association-prompts.md`](resources/association-prompts.md).
