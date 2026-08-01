---
name: fact-checking-citations
description: >-
  Verify that citations in AI-generated text correspond to real papers by
  cross-checking DOIs and titles against Crossref and Semantic Scholar APIs,
  and checking whether cited claims actually appear in the referenced paper's
  abstract or reference list. Invoke when the user says "引用反查", "防幻觉",
  "fact-check", "verify citations", "核对引用", or whenever another skill
  produces text containing citations that need verification. Do NOT use this
  skill for generating new content — only for verification of existing citations.
---

# Fact-Checking Citations

## Purpose

This skill is the **anti-hallucination infrastructure** of the entire academic
PKM workflow. Every other skill that produces citations (literature reviews,
lineage narratives, paper recaps) MUST route its citations through this skill
before presenting them to the user.

## Core Principle

**Never trust a second AI to verify a first AI's facts.** Citation authenticity
is verified against external databases (Crossref, Semantic Scholar), not against
another language model. The AI's role here is limited to: parsing citations,
calling verification scripts, and formatting the report.

## Input

Text containing citations in any of these formats:
- `[Author, Year]` — e.g., `[Vaswani et al., 2017]`
- `(DOI:10.xxx/yyy)` — e.g., `(DOI:10.5555/3295222.3295349)`
- `[[citekey]]` — e.g., `[[vaswani2017]]`
- Inline claims with citations — e.g., "Vaswani et al. (2017) proposed relative position encoding"

## Verification Pipeline

### Step 1: Parse Citations

Extract every citation entity from the input text. For each, capture:
- Raw text span
- Author names (if present)
- Year (if present)
- DOI (if present)
- Citekey (if present)
- Associated claim (the sentence containing the citation, minus the citation itself)

### Step 2: Resolve to Canonical ID

Priority order for resolving a citation to a canonical paper ID:
1. If DOI present → use DOI directly
2. If citekey present → look up in local `_ccf_a.bib` or query Zotero local API (`http://localhost:23119/api/users/0/items?q={citekey}&format=keys`) to get DOI
3. If only author+year+title fragments → call `s2_verify.py --search "title keywords"` to find the paper

### Step 3: Verify Existence (Crossref)

For each resolved DOI, run:
```
python resources/crossref_verify.py <doi>
```
This returns `VERIFIED` / `NOT_FOUND` / `ERROR` plus metadata (title, authors, year, reference list).

If Crossref returns `NOT_FOUND`, fall back to Semantic Scholar:
```
python resources/s2_verify.py --doi <doi>
```

### Step 4: Verify Title/Author/Year Match

Compare the parsed citation's metadata against the Crossref/S2 returned metadata:
- Title similarity > 80% (fuzzy match) → OK
- Author family name match → OK
- Year match (±1 year tolerance) → OK

If any mismatch → flag as `MISMATCH` with details.

### Step 5: Verify Claim Support (Anti-Claim-Hallucination)

This is the **critical step** that catches "the citation is real but the claim
about it is fabricated."

For each citation with an associated claim, run:
```
python resources/s2_verify.py --claim-check <paper_id> "<claim text>"
```

This checks whether the claim text appears in or is supported by the paper's
abstract or TLDR. The script returns:
- `SUPPORTED` — claim keywords found in abstract/tldr
- `UNSUPPORTED` — claim keywords NOT found (potential claim hallucination)
- `INCONCLUSIVE` — paper has no abstract/tldr available

### Step 6: Verify "A Cited B" Relationships

If the text claims "Paper A cited Paper B" (common in lineage narratives),
verify that B actually appears in A's reference list:
```
python resources/crossref_verify.py --check-reference <doi_A> <doi_B>
```

This uses Crossref's `reference` field (publisher-registered reference list).
If Crossref doesn't have references for A, fall back to S2:
```
python resources/s2_verify.py --check-reference <paperId_A> <paperId_B>
```

### Step 7: Generate Report

Output a structured Markdown report:

```markdown
## 引用反查报告

| # | 引用文本 | DOI | 状态 | 论断核对 | "A引B"核对 | 备注 |
|---|---------|-----|------|---------|-----------|------|
| 1 | [Vaswani et al., 2017] | 10.5555/3295222.3295349 | ✅ VERIFIED | ✅ SUPPORTED | — | 标题/作者/年份匹配 |
| 2 | [Smith, 2020] | 10.1234/fake | ❌ NOT_FOUND | — | — | DOI不存在 |
| 3 | [Wang et al., 2019] | 10.5678/real | ⚠️ MISMATCH | ❌ UNSUPPORTED | — | 年份不符；论断"提出LSTM"不在摘要中 |

### 汇总
- 总引用数: 3
- ✅ 全部通过: 1
- ❌ 失败: 1 (NOT_FOUND)
- ⚠️ 需人工核对: 1 (MISMATCH + UNSUPPORTED)

### 建议操作
- 引用 #2: 删除或替换为真实文献
- 引用 #3: 核对年份；论断可能为幻觉，需查原文确认
```

The report is also written to the relevant Obsidian note's `## 引用反查记录` section.

## Rate Limiting

- Crossref: ≥1.1s between requests (polite pool with `mailto` in User-Agent)
- Semantic Scholar without API key: ≥3s between requests (~100 req/5min)
- Semantic Scholar with API key (`S2_API_KEY` env var): ≥1s between requests (~1 req/s)
- Batch verification: use S2 `/paper/batch` endpoint (≤500 papers per call)

## Failure Strategies

- **Network timeout**: Retry once after 5s; if still fails, mark as `ERROR (network)` and suggest manual verification
- **DOI missing and title search returns 0 results**: Mark as `NOT_FOUND` and prompt user to provide DOI manually
- **Abstract unavailable for claim check**: Mark as `INCONCLUSIVE` — do not assume the claim is false
- **Script not found**: Print the expected path and instruct user to run `配置指南.md` setup first
- **API key missing**: `s2_verify.py` works without key but at lower rate; warn user about throttling

## When Other Skills Should Call This Skill

| Caller Skill | When to Call | What to Check |
|-------------|-------------|---------------|
| `synthesizing-literature-review` | Before outputting any review with citations | All citations: existence + claim support |
| `tracing-lineage-by-era` | Before outputting lineage narrative | All citations + "A cited B" relationships |
| `tracing-lineage-by-team` | Before outputting team lineage | All citations |
| `recapping-paper-feynman` | When user's recap mentions other papers | Citations mentioned in recap |
| `building-citation-timeline` | Implicitly (uses same S2 API) | Not needed — timeline data comes from API directly |

## Constraints

- This skill does NOT generate new text or citations. It only verifies.
- This skill does NOT use a language model to judge whether a claim is true. It checks whether claim keywords appear in the paper's abstract/tldr — a necessary but not sufficient condition.
- Complex claims (multi-sentence, nuanced) that pass the keyword check may still be misattributed. The report marks these as `SUPPORTED (keyword match)` not `SUPPORTED (semantic)` to remind the user that keyword overlap ≠ semantic entailment.
- The skill must clearly state its limitations in every report: "Keyword-based claim check reduces but does not eliminate claim hallucination risk. For critical claims, read the original paper."
