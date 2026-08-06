# 学术 PKM 工作流落地实施计划

## 摘要

本计划为已建 1.4 万篇 Zotero 库（19 集合、已去重、本地 API 已启用）的用户，落地一套"微观论文阅读 + 宏观研究脉络"的全套学术 PKM 工作流。技术栈为 **TRAE 自定义 Skill（交互引导）+ Obsidian（笔记载体与知识网络）** 两端组合，通过共享文件系统、Zotero 本地 API、本地数据索引三条链路衔接。核心设计原则：微观 Skill 走"认知参与型"（逼用户自己加工，治"读完就忘"），宏观 Skill 走"RAG 取证 + 引用反查防幻觉"（不依赖第二个 AI 兜底事实）。计划包含 8 个原子 Skill、Obsidian 骨架、Python 反查脚本，以及前置插件清单。

---

## 当前状态分析

### 已有资产（调研确认）

| 资产 | 状态 | 说明 |
|------|------|------|
| Zotero 库 | 14,629 篇 / 19 集合 / 已去重 | CCF-A 10 子领域 + MCM-ICM 7 题号 + 根集合 |
| Zotero 本地 API :23119 | 已启用 | 见 `Zotero导入指南.md` |
| `_index.csv` | 120,797 行 | 全量论文索引（含 venue/year/authors） |
| `_high_impact.csv` | 存在 | 高影响力论文子集 |
| `_abstracts.jsonl` | 83,360 条 | 摘要库 |
| `_ccf_a.bib` | 12,178 条 | BibTeX |
| `_venue_map.json` | 12,177 条 | venue 映射 |
| 现有脚本 | `zotero_collections.js`/`cleanup.js`/`dedupe.js`/`attach_pdfs.js` | 集合/去重/PDF 挂载 |
| PDF 资源 | `MCM-ICM\`、`AI\`、`Database\` 等 | 部分已挂载 |
| TRAE 项目技能目录 | **不存在**，需创建 `d:\Desktop\论文\.trae\skills\` | 全局技能已有 29 个（lark-*、frontend 等），项目级为空 |
| Obsidian vault | **不存在**，需创建 | — |
| Python 环境 | 3.10+ + `requests` 已可用 | `ccf_crawler.py` 已验证 |

### 关键调研结论（决策依据）

| 主题 | 结论 | 来源 |
|------|------|------|
| TRAE Skill 规范 | 项目技能放 `.trae/skills/{name}/SKILL.md`；frontmatter 仅 `name`+`description`；description 第三人称、含触发关键词与负向条件；触发由 description 语义匹配 | TRAE 官方文档 |
| Skill 设计铁律 | 职责绝对单一（一 Skill 一动作）；渐进式披露（SKILL.md ≤500 行，引用文件仅一层深度）；输入输出结构化；失败策略完备 | 同上 |
| ZotLit | 双端插件（Obsidian + Zotero），v1.1.12(2026-05)；需 Zotero 本地 API（已启用）；模板驱动生成 literature note；支持 citekey frontmatter、annotation 侧栏 | ZotLit GitHub / 文档 |
| 间隔重复插件 | `obsidian-spaced-repetition`；语法 `Q::A`/`Q?\n?\nA`；`#flashcards` 标签；SM-2 算法；调度数据写回 frontmatter | 社区文档 |
| Semantic Scholar API | `https://api.semanticscholar.org/graph/v1`；无 key 限速 ~100 req/5min，有 key ~1 req/s；支持 `/paper/search`、`/paper/{id}`、`/paper/batch`(≤500)、`/citations`、`/references`；字段含 citationCount、tldr、embedding.specter_v2 | S2 Graph API 文档 |
| Crossref API | `https://api.crossref.org/works`；带 `mailto` 进 polite pool；**`reference` 字段是出版商登记的参考文献列表**——引用反查防幻觉的关键 | Crossref 文档 |
| Elicit/Consensus | **均无公开免费 API**，仅 Web SaaS；不适合自动化管线，作为人工深度验证环节 | 搜索结论 |

---

## 假设与决策

1. **Skill 载体**：TRAE Skill 做交互引导（提问/费曼/关联/脉络），Obsidian 做笔记载体与知识网络——用户已确认"两者组合"。
2. **范围**：全套工作流（微观+宏观+Zotero 接入+知识库网络+复习钩子）——用户已确认。
3. **TRAE 项目根 = `d:\Desktop\论文\`**：使 `.trae/skills/` 与 `obsidian-vault/`、Zotero 数据文件同处一个项目，Skill 可直接读写 vault 内 markdown 与数据文件，零摩擦衔接。
4. **不全量导入 Obsidian**：1.4 万篇全量导入会卡。ZotLit 按需生成（读哪篇生成哪篇）；`_index.csv` 留在 TRAE 侧作索引，不进 vault。
5. **事实校验不外包给第二个 AI**：引用真伪用 Crossref + Semantic Scholar 脚本化反查（外部锚点），AI 只负责逻辑一致性校验。
6. **微观 Skill 拆 3 个、宏观 Skill 拆 5 个**：遵循 TRAE"职责绝对单一"铁律，不做大而全的单 Skill。
7. **citekey 为两端共同主键**：literature note 文件名 `@citekey.md` = Zotero citekey = Skill 内引用标识。

---

## 提议变更

### 变更 1：创建 TRAE 项目技能目录与 8 个 Skill

**路径**：`d:\Desktop\论文\.trae\skills\`

**为什么**：这是整套工作流的"大脑"——交互引导、检索、反查逻辑都封装在 Skill 里。项目级 Skill（而非全局）确保只在此论文项目生效。

**8 个 Skill 清单**：

| Skill 名 | 能力域 | 触发词 | 核心动作 |
|-----------|--------|--------|----------|
| `reading-paper-pre-questions` | 微观 | 预读/读前提问/pre-reading | 读 title+abstract 生成三层提问（激活/预测/批判），写入 note 的 `## 预读问题` |
| `recapping-paper-feynman` | 微观 | 费曼复述/Feynman recap | 校验用户复述，按四维量规打分，标注漏洞，不直接给答案只给修复提示 |
| `linking-paper-concepts` | 微观 | 关联/associate | 四路检索（同源/同人/同引/同义）候选论文，生成 `[[wikilink]]` 写入 `## 关联` |
| `tracing-lineage-by-era` | 宏观 | 脉络/分年代/lineage by era | S2 搜索 + 本地 `_index.csv`，按年代分段提炼范式演进，输出 Mermaid timeline |
| `tracing-lineage-by-team` | 宏观 | 团队脉络/trace team | S2 author API + 本地作者匹配，识别主题切换点，生成合作者网络 |
| `synthesizing-literature-review` | 宏观 | 综述/literature review | 按方法/数据/指标聚类，生成综述骨架，每个引用经反查校验 |
| `building-citation-timeline` | 宏观 | 引用时间线/citation graph | S2 citations/references 端点，前后向引用按年聚合，标注关键转折 |
| `fact-checking-citations` | 宏观(基础设施) | 引用反查/防幻觉/verify citations | Crossref+S2 双源核对 DOI/标题/论断，输出 VERIFIED/MISMATCH/NOT FOUND |

**每个 SKILL.md 的 frontmatter 格式**（以 `reading-paper-pre-questions` 为例）：

```yaml
---
name: reading-paper-pre-questions
description: Generate cognitive pre-reading questions for an academic paper based on its title, abstract, and venue before deep reading. Use this skill when the user mentions "预读", "读前提问", "pre-reading", wants to activate prior knowledge before reading a paper, or pastes a paper title/abstract and asks what to focus on. Do NOT use this skill for post-reading summarization, Feynman recap, or literature review synthesis across multiple papers.
---
```

**每个 Skill 配 `resources/` 目录**，存放：提问框架库、费曼量规、关联提示词、综述骨架模板、Python 脚本。

**关键脚本**（放 `fact-checking-citations/resources/`）：
- `crossref_verify.py`：按 DOI 查 Crossref，核对 title/author/year，提取 `reference` 字段做"A 是否真引用了 B"核对
- `s2_verify.py`：按 title 模糊搜 Semantic Scholar，核对论断是否被 abstract/tldr 支持
- `s2_search.py`（放 `tracing-lineage-by-era/resources/`）：主题搜索 + embedding 取回
- `author_cluster.py`（放 `tracing-lineage-by-team/resources/`）：作者论文聚类
- `citation_graph.py`（放 `building-citation-timeline/resources/`）：前后向引用图

**怎么实施**：用 skill-creator 流程，逐个创建 `.trae/skills/{name}/SKILL.md` + `resources/`。每个 Skill 遵循 ≤500 行、单一职责、失败策略完备。创建后用 3-5 个测试用例验证触发命中率与输出稳定性。

---

### 变更 2：创建 Obsidian Vault 骨架

**路径**：`d:\Desktop\论文\obsidian-vault\`

**目录结构**：

```
obsidian-vault\
├── .obsidian\                  # 插件安装后生成
├── Literature\                 # ZotLit 文献笔记（按需生成）
│   └── @citekey.md
├── Concepts\                   # 概念笔记（手写）
├── MOC\                        # Map of Content 索引
│   ├── 00-Dashboard.md         # Dataview 仪表盘
│   ├── by-era.md               # 分年代视图
│   ├── by-team.md              # 分团队视图
│   └── by-venue.md             # 分会议视图
├── Reviews\                    # 综述笔记（宏观 Skill 产物）
├── Templates\                  # Templater 模板
│   ├── literature-note.md      # ZotLit 模板（含预读/费曼/关联/卡片占位区）
│   ├── feynman-recap.md        # 费曼复述模板
│   ├── concept-note.md         # 概念笔记模板
│   └── flashcard-inline.md     # 间隔重复卡片片段
├── Scripts\                    # 镜像 .trae/skills 脚本
└── Attachments\
```

**为什么**：Obsidian 是笔记载体与知识网络。Vault 与 TRAE 项目同根，Skill 可直接读写 vault 内文件。按需生成（不全量导入）保证性能。

**关键模板**：`Templates/literature-note.md` 内含与 Skill 输出对齐的章节占位（`## 预读问题`、`## 费曼复述`、`## 关联`、`## 间隔重复卡片`、`## 引用反查记录`），frontmatter 字段与 Dataview 查询对齐（citekey/title/authors/year/venue/doi/area/citation_count）。

**MOC 视图**用 Dataview 查询动态生成：仪表盘（按 area 统计、按年代分布、高被引未读、待复习卡片）、分年代/分团队/分会议视图。

**怎么实施**：创建目录 → 写入 4 个 Templater 模板 → 写入 4 个 MOC Dataview 文件 → 配置插件 → 小批量验证（5 篇高引论文生成 literature note）。

---

### 变更 3：配置前置插件（Zotero + Obsidian + TRAE + 外部 API）

**为什么**：用户明确要求"尽早提出前置工作"。这是整套工作流能跑起来的地基。

#### Zotero 端

| 项目 | 状态 | 操作 |
|------|------|------|
| Zotero 7 ≥7.0.15 | 需确认 | ZotLit 最新版要求 |
| 本地 API :23119 | 已启用 | — |
| **Better BibTeX 插件** | 需安装 | 生成稳定 citekey，ZotLit 依赖 |
| **ZotLit Zotero 端** | 需安装 | 从 GitHub Releases 下载 `.xpi`，Zotero > 工具 > 插件 > 齿轮 > Install from File |
| PDF 附件挂载 | 部分完成 | 确认高影响力论文 PDF 已挂载 |

#### Obsidian 端

| 插件 | 用途 | 配置要点 |
|------|------|----------|
| **ZotLit** | Zotero 集成 | 设 Zotero API 端口 23119；literature note 路径 `Literature/{{citekey}}.md`；模板 `Templates/literature-note.md` |
| **Templater** | 模板化新建笔记 | 启用触发模板文件夹；配置费曼/概念模板 |
| **Dataview** | 动态查询视图 | 启用 JS 查询；配置 frontmatter 字段索引 |
| **Spaced Repetition** | 间隔重复 | 算法 SM-2；`#flashcards` 标签；调度数据存 frontmatter |
| Excalidraw（可选） | 手绘概念图 | 关联引导时画跨论文概念图 |
| Shell Commands（可选） | Obsidian 内调脚本 | 调用 `.trae/skills/*/resources/*.py` |

#### TRAE 端

| 项目 | 操作 |
|------|------|
| 项目技能目录 | 在 `d:\Desktop\论文\` 打开 TRAE，创建 `.trae/skills/`（自动识别） |
| Python 环境 | 确认 3.10+ + `requests`（已验证可用） |
| Semantic Scholar API key | 申请免费 key，设环境变量 `S2_API_KEY` |
| Crossref polite pool | 脚本 User-Agent 带 `mailto`，无需 key |

#### 外部 API

| 服务 | 必需 | 费用 | 接入 |
|------|------|------|------|
| Semantic Scholar | 是 | 免费 | 脚本 `requests` + `x-api-key` |
| Crossref | 是 | 免费 | 脚本 `requests` + `mailto` |
| Elicit/Consensus | 可选 | 付费/部分免费 | **无 API**，Skill 内引导人工操作 |

---

### 变更 4：建立两端衔接的四条链路

**为什么**：TRAE Skill 与 Obsidian 不在同一进程，需明确衔接机制才能"零摩擦"协作。

| 链路 | 机制 | 用途 |
|------|------|------|
| **A 共享文件系统** | TRAE 项目根 = vault 父目录，Skill 直接 Read/Write vault 内 `.md` | Skill 产物写入 note 对应章节；宏观产物写入 `Reviews\` |
| **B Zotero 本地 API** | 两端都调 `:23119` 获取条目元数据 | citekey→DOI 补全；ZotLit 原生调用生成 note |
| **C 本地数据索引** | Skill 优先查 `_index.csv`/`_abstracts.jsonl`/`_ccf_a.bib` | 1.4 万篇规模下避免每次调 API；citekey→DOI 快速映射 |
| **D 脚本镜像** | `.trae/skills/*/resources/*.py` 与 `obsidian-vault/Scripts/` 共享 | Obsidian 端 Shell Commands 调脚本；TRAE 端 Skill 直接调 |

**端到端示例**（精读 Vaswani 2017）：
1. Obsidian ZotLit 生成 `Literature/@vaswani2017.md`
2. TRAE："预读 vaswani2017" → `reading-paper-pre-questions` 写入 `## 预读问题`
3. 用户精读 PDF（Zotero 阅读器，ZotLit 同步高亮到 note）
4. TRAE："费曼复述 vaswani2017" → `recapping-paper-feynman` 校验写入 `## 费曼复述`；复述提"引用了 Bahdanau 2014"则触发 `fact-checking-citations`
5. TRAE："关联 vaswani2017" → `linking-paper-concepts` 四路检索写入 `## 关联`
6. 用户手写/Skill 生成 2 张间隔重复卡片
7. 每日 Obsidian SR 刷卡
8. 宏观："attention 脉络" → `tracing-lineage-by-era` 生成 `Reviews/attention-lineage.md`，引用全部经反查

---

## 实施步骤（按"谁动手"分区）

### Part A：TRAE 自动完成（我现在就做）

**A1. 创建 8 个 TRAE Skill（含 SKILL.md + resources）**
- 路径：`d:\Desktop\论文\.trae\skills\{skill-name}\`
- 8 个 Skill：`reading-paper-pre-questions`、`recapping-paper-feynman`、`linking-paper-concepts`、`tracing-lineage-by-era`、`tracing-lineage-by-team`、`synthesizing-literature-review`、`building-citation-timeline`、`fact-checking-citations`
- 每个 Skill 含 frontmatter（name + description + 触发词 + 负向条件）+ 主体指令 + resources 文档

**A2. 创建 5 个 Python 脚本（引用反查与检索）**
- `fact-checking-citations/resources/crossref_verify.py` — Crossref DOI 反查 + reference 字段核对
- `fact-checking-citations/resources/s2_verify.py` — Semantic Scholar 标题模糊搜 + 论断核对
- `tracing-lineage-by-era/resources/s2_search.py` — 主题搜索 + embedding
- `tracing-lineage-by-team/resources/author_cluster.py` — 作者论文聚类
- `building-citation-timeline/resources/citation_graph.py` — 前后向引用图

**A3. 创建 Obsidian Vault 骨架文件（目录 + 模板 + MOC）**
- 目录结构：`obsidian-vault\{Literature,Concepts,MOC,Reviews,Templates,Scripts,Attachments}\`
- 4 个 Templater 模板：`literature-note.md`、`feynman-recap.md`、`concept-note.md`、`flashcard-inline.md`
- 4 个 MOC Dataview 文件：`00-Dashboard.md`、`by-era.md`、`by-team.md`、`by-venue.md`

**A4. 生成详细配置指南**
- 路径：`d:\Desktop\论文\配置指南.md`
- 覆盖：Zotero 插件安装、Obsidian 插件安装与配置、TRAE 环境变量、API key 申请、端到端验证步骤

**A5. 验证脚本可运行**
- 用真实 DOI 测试 `crossref_verify.py`
- 用真实标题测试 `s2_verify.py`

---

### Part B：用户手动完成（按配置指南操作）

> 以下步骤需要你在 GUI 中操作（安装软件/插件、配置设置），无法由 TRAE 代劳。详见生成的 `配置指南.md`。

**B1. Zotero 端（预计 10 分钟）**
1. 更新 Zotero 7 至最新
2. 安装 Better BibTeX 插件
3. 安装 ZotLit Zotero 端 `.xpi`
4. 刷新所有条目 citekey

**B2. Obsidian 端（预计 20 分钟）**
1. 安装 Obsidian
2. 打开 `d:\Desktop\论文\obsidian-vault\` 作为 vault
3. 安装 4 个核心插件：ZotLit、Templater、Dataview、Spaced Repetition
4. 按 `配置指南.md` 配置各插件参数
5. 小批量验证：5 篇高引论文生成 literature note

**B3. TRAE 端（预计 5 分钟）**
1. 申请 Semantic Scholar API key
2. 设置环境变量 `S2_API_KEY`
3. 确认 TRAE 已识别 8 个项目 Skill

**B4. 全链路验证（预计 15 分钟）**
1. 选 1 篇代表作走完微观工作流
2. 选 1 个主题走完宏观脉络
3. 确认引用反查正常工作

---

## 风险与对策

| 风险 | 对策 |
|------|------|
| 1.4 万篇全量导入 Obsidian 卡顿 | 不全量导入；ZotLit 按需生成；`_index.csv` 留 TRAE 侧 |
| S2 无 key 限速严（100 req/5min） | 申请免费 key；脚本加缓存；批量用 `/paper/batch` |
| Crossref `reference` 字段部分缺失 | 双源核对：Crossref 查不到回退 S2 `/references` |
| AI 产生"论断幻觉"（引用真实但论断虚假） | `claim_supported_by_abstract` 做论断级核对；复杂论断标注置信度 |
| Skill 触发命中率不稳 | description 严格第三人称+触发词+负向条件；评测验证；避免职责重叠 |
| Dataview 万级笔记慢 | literature note 按 area 子目录分；Dataview 查询限定 FROM 子目录 |
| citekey 与 `_venue_map.json` 不一致 | Zotero API 统一获取 citekey；Skill 内做 title→citekey 映射 |
| Elicit/Consensus 无法自动化 | SKILL.md 引导用户手动操作，结果粘贴回 Obsidian 由反查核对 |

---

## 验证步骤

1. **Skill 触发验证**：对每个 Skill 输入 3-5 个触发短语（含正例与反例），确认命中正确 Skill 且不误触发其他 Skill
2. **反查脚本验证**：用已知真实 DOI（如 Vaswani 2017 的 `10.5555/3295222.3295349`）测 `crossref_verify.py` 返回 VERIFIED；用编造 DOI 测返回 NOT_FOUND
3. **论断核对验证**：测 `s2_verify.py` 的 `claim_supported_by_abstract`，用真实论断（"Transformer 用自注意力"）返回 True，用虚假论断（"Transformer 用 LSTM"）返回 False
4. **ZotLit 集成验证**：5 篇高引论文生成 literature note，检查 frontmatter 完整、annotation 同步、Dataview 查询能读到
5. **端到端微观验证**：1 篇论文走完预读→精读→费曼→关联→卡片全流程，确认各章节被正确写入
6. **端到端宏观验证**：1 个主题走完分年代脉络→综述，确认所有引用标 VERIFIED，无 NOT_FOUND
7. **间隔重复验证**：literature note 内卡片被 SR 插件识别，能进入复习队列，复习后 frontmatter 调度数据更新
