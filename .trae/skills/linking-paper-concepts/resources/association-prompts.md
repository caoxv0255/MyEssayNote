# 四路关联检索策略详解

本文档是 `linking-paper-concepts` Skill 的 resources 参考，逐路说明同源 / 同人 / 同引 / 同义四种关联检索的检索逻辑、数据来源、排序策略与输出格式，并各配一个示例。

> 约定：focal paper（焦点论文）记为 **F**，其 citekey 记为 `F.key`，DOI 记为 `F.doi`，S2 paperId 记为 `F.s2id`。候选论文记为 **C**。

---

## 总览

| 路数 | 名称 | 信号本质 | 数据来源 | 是否联网 | 强度优先级 |
|------|------|---------|---------|---------|-----------|
| ① | 同源 | 同会议/同年份 | `_index.csv` | 否（纯本地） | 3 |
| ② | 同人 | 共享一作/通讯 | `_index.csv` `authors` | 否（纯本地） | 2 |
| ③ | 同引 | 共享参考文献 | `citation_graph.py`（S2 `/references`） | 是 | 1（最强） |
| ④ | 同义 | 语义相似 | `s2_search.py`（`embedding.specter_v2` 余弦） | 是 | 4 |

- 强度优先级用于多路命中同一候选时的主关联类型选择：同引 > 同人 > 同源 > 同义。
- ① ② 路纯本地、无网络依赖，是 S2 限速降级时唯一可用的两路。
- ③ ④ 路依赖 Semantic Scholar API；③ 需要参考文献列表，④ 需要向量嵌入。

---

## ① 同源（同 venue 同 year）

### 检索逻辑

同一会议/期刊、同一年份发表的论文，往往处于同一研究社区、同一波范式浪潮。这是最弱的关联信号——它只说明"在同一时间同一地点出现"，并不保证内容相关——但召回率高、成本极低（纯本地查询），适合作为基础候选池。

具体判定：
- `venue` 字段精确匹配（注意 venue 归一化：`NeurIPS` / `NIPS` / `Conference on Neural Information Processing Systems` 应通过 `_venue_map.json` 归一为同一 key）。
- `year` 字段精确匹配。
- 排除 focal paper 自身。

### 数据来源

- **`_index.csv`**：全量论文索引（约 12 万行），含 `citekey, title, authors, year, venue, doi, citation_count, area` 等字段。
- **`_venue_map.json`**：venue 别名归一化映射，用于把不同写法的会议名统一。
- 纯本地，零网络开销。

### 排序策略

1. 主排序：`citation_count` 降序（高被引优先，因为高被引的同源论文更可能是该年该会的代表作，关联价值更高）。
2. 次排序：`title` 字母序（稳定排序，保证可复现）。
3. 截断：取前 8 篇。

### 输出格式

```
- [[@{C.key}]] — 同源：同发表于 {venue} ({year})。
```

### 示例

**F** = `vaswani2017`（Attention Is All You Need, NeurIPS 2017）

`_index.csv` 中 `venue=NeurIPS AND year=2017` 的同源候选（节选）：

| citekey | 标题 | citation_count |
|---------|------|---------------|
| he2017deep | Deep Reinforcement Learning ... | 15234 |
| silver2017mastering | Mastering the game of Go ... | 9821 |
| devlin2019bert | BERT ... | — |

排序后取前 8，输出行示例：

```
- [[@he2017deep]] — 同源：同发表于 NeurIPS (2017)。
- [[@silver2017mastering]] — 同源：同发表于 NeurIPS (2017)。
```

> 注意：同源路会召回大量与 F 内容无关的论文（如上例的围棋与强化学习）。这是设计如此——同源提供"广撒网"的基础池，后续同引/同义路负责精排。用户可在审阅阶段剔除无关项。

---

## ② 同人（共享一作 / 通讯作者）

### 检索逻辑

共享第一作者或通讯作者的论文，意味着同一核心研究者（或同一团队）的连续工作线。这通常暗示方法论的延续、实验设置的复用、或同一课题的系列发表，关联强度高于单纯的同源。

具体判定：
- 解析 F 的 `authors` 字段（分号或逗号分隔），提取**第一作者姓氏**（family name）。
- 若 `authors` 字段含通讯作者标记（如 `*` 或 `corresponding`），提取通讯作者姓氏。
- 在 `_index.csv` 全表中匹配：任一候选 C 的第一作者姓氏 == F 的第一作者姓氏 **OR** 候选 C 的第一作者姓氏 == F 的通讯作者姓氏 **OR** 候选 C 的通讯作者姓氏 == F 的第一作者姓氏。
- 排除 F 自身。

### 数据来源

- **`_index.csv`** 的 `authors` 字段。字段格式约定：`Family1, Given1; Family2, Given2; ...`，通讯作者以 `*` 后缀标注（与 Better BibTeX 导出一致）。
- 纯本地，零网络开销。

### 排序策略

1. 主排序：`year` 降序（最新工作优先，因为近期同作者工作更可能反映当前研究主线）。
2. 次排序：`citation_count` 降序。
3. 截断：取前 8 篇。

### 输出格式

```
- [[@{C.key}]] — 同人：共享一作 {family}。
- [[@{C.key}]] — 同人：共享通讯作者 {family}。
```

### 示例

**F** = `vaswani2017`，第一作者 `Vaswani`，通讯作者 `Vaswani`（自引场景）。

更典型的示例：**F** = `devlin2019`（BERT），第一作者 `Devlin`，通讯作者 `Devlin`。

`_index.csv` 中第一作者为 `Devlin` 的候选：

| citekey | 标题 | year | 关系 |
|---------|------|------|------|
| devlin2018bert_pre | BERT: Pre-training ... (预印本) | 2018 | 共享一作 Devlin |
| devlin2017margin | Margin-based ... | 2017 | 共享一作 Devlin |

输出行示例：

```
- [[@devlin2018bert_pre]] — 同人：共享一作 Devlin。
- [[@devlin2017margin]] — 同人：共享一作 Devlin。
```

> 通讯作者场景示例：若 F 的通讯作者为 `Bengio`，则匹配所有通讯作者或一作为 `Bengio` 的论文，标注"共享通讯作者 Bengio"。

---

## ③ 同引（共享参考文献 / co-citation）

### 检索逻辑

两篇论文若共享大量参考文献，说明它们建立在相似的理论基础与先行工作之上——这是内容层面最强的关联信号之一（co-citation 分析的经典思路）。同引路直接衡量"知识谱系的交叠"。

具体判定：
1. 调用 `citation_graph.py --references {F.doi 或 F.s2id}` 获取 F 的参考文献集合 `Ref(F)`（一组 DOI 或 S2 paperId）。
2. 候选池 = ① ② 路已浮现的候选 + 从 `_index.csv` 按 `citation_count` 取的前 50 篇高引邻居（限定同 `area` 子领域，避免池过大）。
3. 对每个候选 C，调用 `citation_graph.py --references {C.doi}` 获取 `Ref(C)`。
4. 计算交叠：`shared = |Ref(F) ∩ Ref(C)|`，`jaccard = shared / |Ref(F) ∪ Ref(C)|`。
5. 仅保留 `shared ≥ 3` 的候选。

### 数据来源

- **`citation_graph.py`**（位于 `building-citation-timeline/resources/`）：封装 Semantic Scholar `/references` 端点，返回指定论文的参考文献列表。
- **`_index.csv`**：用于构建候选池与 area 过滤。
- 需要 S2 API；无 key 时限速 ~100 req/5min，有 key 时 ~1 req/s。
- 大量候选的参考文献获取应使用 S2 `/paper/batch` 端点（单次 ≤500）以降低请求数。

### 排序策略

1. 主排序：`shared`（共享参考文献绝对数）降序——绝对数更能反映谱系交叠深度。
2. 次排序：`jaccard` 降序——归一化后排除"参考文献极多的综述型论文"造成的虚高 shared。
3. 截断：取前 8 篇。

### 输出格式

```
- [[@{C.key}]] — 同引：共享 {shared} 篇参考文献 ({jaccard_pct}% Jaccard)。
```

### 示例

**F** = `vaswani2017`，`Ref(F)` 含 36 篇参考文献（含 Bahdanau2014、Sutskever2014、Bahdanau2014 等）。

候选 `devlin2019`（BERT），`Ref(C)` 含 45 篇。交集计算：

```
Ref(F) ∩ Ref(C) = {bahdanau2014, sutskever2014, cho2014, ...}  共 12 篇
|Ref(F) ∪ Ref(C)| = 36 + 45 - 12 = 69
jaccard = 12 / 69 ≈ 0.174 ≈ 17%
```

输出行：

```
- [[@devlin2019]] — 同引：共享 12 篇参考文献 (17% Jaccard)。
```

> 降级说明：当 S2 限速时，本路退化为"本地启发式同引"——用 `_index.csv` 的 `venue + area + 标题关键词重合度` 作为 co-citation 的代理，并在理由中明确标注"同引(本地启发式)"，绝不伪装成精确 Jaccard。

---

## ④ 同义（语义相似）

### 检索逻辑

基于论文的 SPECTer v2 向量嵌入计算余弦相似度，捕捉"主题与方法层面的语义接近性"。前三路分别基于发表元数据（同源）、人员（同人）、引用谱系（同引），而同义路独立于这三类结构信号，能发现"既不同源、也不同人、又不互引，但讨论的是同一问题"的论文。

具体判定：
1. 调用 `s2_search.py --embedding {F.doi 或 F.s2id}` 获取 F 的 `embedding.specter_v2` 向量（768 维）。
2. 候选池 = ① ② ③ 路已浮现的候选；对每个 C 获取其 SPECTer v2 向量，计算与 F 的余弦相似度。
3. 若候选池中有嵌入的候选不足 5 篇，扩展池：调用 `s2_search.py --similar {F.s2id}` 获取 S2 推荐相似论文，补充进候选池。
4. 仅保留 `cosine ≥ 0.5` 的候选。

### 数据来源

- **`s2_search.py`**（位于 `tracing-lineage-by-era/resources/`）：封装 Semantic Scholar 检索与 embedding 取回。
- SPECTer v2 嵌入由 S2 对论文标题+摘要联合编码生成，768 维，适合学术语义相似度。
- 需要 S2 API；embedding 字段需在请求中显式声明 `fields=embedding.specter_v2`。

### 排序策略

1. 主排序：`cosine` 降序（语义越相似越靠前）。
2. 次排序：`citation_count` 降序（同等语义相似度下，高被引论文优先，因关联价值更高）。
3. 截断：取前 8 篇。
4. 阈值：`cosine < 0.5` 的候选一律剔除（SPECTer v2 的 0.5 大致对应"明显同主题"的经验阈值）。

### 输出格式

```
- [[@{C.key}]] — 同义：语义相似 (cosine = {score:.3f})。
```

### 示例

**F** = `vaswani2017`，SPECTer v2 向量 `v_F`。

候选 `press2021`（Train Short, Test Long），SPECTer v2 向量 `v_C`。余弦相似度：

```
cosine(v_F, v_C) = 0.72
```

（两篇都讨论注意力机制与序列建模，语义接近但不互引、不同源。）

输出行：

```
- [[@press2021]] — 同义：语义相似 (cosine = 0.72)。
```

> 降级说明：S2 限速时本路**完全不可用**（无本地嵌入库），输出中显式标注"同义路因 S2 限速不可用"，而非静默省略。用户需知晓召回缺失了语义维度。

---

## 多路命中与去重

当同一候选 C 同时被多路命中（如既同源又同引），按以下规则合并：

1. **主关联类型**取强度优先级最高者：同引 > 同人 > 同源 > 同义。
2. **次关联类型**追加在理由后，用分号分隔。
3. 示例：C 既同引（shared=8）又同源（NeurIPS 2017）：

```
- [[@devlin2019]] — 同引：共享 8 篇参考文献 (12% Jaccard)；亦同源 (NeurIPS 2017)。
```

候选表中 `关联类型` 列填主类型，`关联理由` 列含全部命中路。

---

## 输出汇总（四路合一）

最终写入 literature note `## 关联` 章节的完整示例（以 `vaswani2017` 为 F）：

```markdown
## 关联

<!-- 由 linking-paper-concepts 生成，请勿手动编辑本注释与下方列表；自定义评述请写在列表下方。 -->

- [[@devlin2019]] — 同引：共享 12 篇参考文献 (17% Jaccard)；亦同源 (NeurIPS 2017)。
- [[@press2021]] — 同义：语义相似 (cosine = 0.720)。
- [[@he2017deep]] — 同源：同发表于 NeurIPS (2017)。
- [[@silver2017mastering]] — 同源：同发表于 NeurIPS (2017)。
- [[@devlin2018bert_pre]] — 同人：共享一作 Devlin。
```

降级场景（S2 限速，仅本地三路）的输出会带顶部警告横幅，且不含同义路、同引路标注为"本地启发式"。
