# CCF-A 论文自动化爬取与分类存储系统

> 自动爬取中国计算机学会（CCF）A 类会议/期刊（第七版，87 个 venue）近三年论文，
> 按领域分类存储，筛选高影响力论文并下载 PDF，配合 AI 工具进行高效阅读。

## 目录结构

```
d:\Desktop\论文\
├── _index.csv            # 全量论文清单（Stage1 输出，每行一篇）
├── _high_impact.csv      # 高影响力论文清单（Stage3 输出，含 local_pdf 路径）
├── _abstracts.jsonl      # 完整摘要（Stage2 输出，每行 JSON）
├── _venue_report.txt     # 各 venue 爬取统计
├── _crawl_log.txt        # 运行日志
├── README.md             # 本文件
│
├── AI/                   # 人工智能（17 venues）
│   ├── AAAI/
│   │   ├── 2023/
│   │   │   └── <论文标题>/
│   │   │       ├── paper.pdf      # arXiv PDF（如可获取）
│   │   │       └── meta.json      # 元数据（标题/作者/引用数/摘要/DOI 等）
│   │   ├── 2024/
│   │   └── 2025/
│   ├── ICML/
│   ├── NeurIPS/
│   ├── CVPR/
│   └── ...
├── Database/             # 数据库/数据挖掘/内容检索（10 venues）
├── Networks/             # 计算机网络（6 venues）
├── Security/             # 网络与信息安全（9 venues）
├── Software/             # 软件工程/系统软件/程序设计语言（10 venues）
├── Theory/               # 计算机科学理论（7 venues）
├── Graphics/             # 计算机图形学（4 venues）
├── HCI/                  # 人机交互（4 venues）
├── Architecture/         # 体系结构/并行与分布/存储（12 venues）
└── Interdisciplinary/    # 交叉/综合/新兴（8 venues）
```

## 数据文件说明

### `_index.csv` — 全量论文清单

| 字段 | 说明 |
|------|------|
| id | DBLP key（唯一标识） |
| title | 论文标题 |
| authors | 作者列表（分号分隔） |
| year | 发表年份 |
| venue | 会议/期刊缩写（如 AAAI、CVPR） |
| kind | conf 或 journal |
| area | 子领域代码（ai/database/security 等） |
| area_folder | 子领域文件夹名（AI/Database/Security 等） |
| stream | DBLP stream 路径 |
| type | DBLP 类型（Conference/Editorial 等） |
| doi | DOI（如有） |
| ee | 电子版链接 |
| arxiv_id | arXiv ID（如有） |
| citation_count | OpenAlex 引用数（Stage2 填充） |
| tldr | 摘要前 300 字（Stage2 填充） |
| local_pdf | 本地 PDF 相对路径（Stage3 填充） |

### `_high_impact.csv` — 高影响力论文

筛选规则：引用数 ≥ 30 **或** 每个 venue×year 引用排名前 12。

### `meta.json` — 单篇论文元数据

每篇高分论文目录下的 `meta.json` 包含完整元数据，可用脚本或 AI 工具读取。

## CCF-A Venue 列表（第七版，87 个）

| 子领域 | 文件夹 | Venue 数 | 代表性会议/期刊 |
|--------|--------|----------|-----------------|
| 人工智能 | AI | 17 | AAAI, IJCAI, ICML, NeurIPS, ICLR, ACL, EMNLP, CVPR, ICCV, ECCV, KR, AAMAS, COLT, TPAMI, IJCV, JMLR, AIJ |
| 数据库/数据挖掘 | Database | 10 | SIGMOD, VLDB, ICDE, KDD, SIGIR, WWW, TKDE, TOIS, TODS, VLDBJ |
| 计算机网络 | Networks | 6 | SIGCOMM, NSDI, INFOCOM, CoNEXT, TON, JSAC |
| 网络与信息安全 | Security | 9 | S&P, CCS, USENIXSec, NDSS, CRYPTO, EUROCRYPT, TIFS, TDSC, JCS |
| 软件工程/程序设计 | Software | 10 | ICSE, FSE, ASE, ISSTA, POPL, PLDI, OOPSLA, TOSEM, TSE, TOPS |
| 计算机科学理论 | Theory | 7 | STOC, FOCS, SODA, LICS, JACM, TOCT, SICOMP |
| 计算机图形学 | Graphics | 4 | SIGGRAPH, CHI, TOG, TVCG |
| 人机交互 | HCI | 4 | UIST, CSCW, IUI, IMWUT |
| 体系结构/存储 | Architecture | 12 | ISCA, MICRO, HPCA, ASPLOS, SC, PPoPP, DAC, USENIX ATC, FAST, TOCS, TACO, IEEE TC |
| 交叉/综合/新兴 | Interdisciplinary | 8 | ICDM, CIKM, WSDM, RecSys, ICRA, IROS, TPDS, TIST |

## 爬虫使用方法

### 环境依赖

```bash
pip install requests
```

### 三阶段流水线

```bash
# Stage 1: DBLP 爬取全量论文清单（87 venue × 3 年）
python ccf_crawler.py stage1 --years 2023-2025

# Stage 2: OpenAlex 批量富化引用数/摘要（可断点续跑）
python ccf_crawler.py stage2

# Stage 3: 筛高分论文 → arXiv 下载 PDF → 分层目录 + meta.json
python ccf_crawler.py stage3

# 一键执行三阶段
python ccf_crawler.py all --years 2023-2025

# 查看爬取报告
python ccf_crawler.py report
```

### 断点续跑

- **Stage 1**: 每个 venue×year 的结果缓存在 `state/dblp_cache/`，重跑时自动跳过已缓存的
- **Stage 2**: 富化结果追加到 `state/_enriched.jsonl`，重跑时自动跳过已富化的
- **Stage 3**: PDF 下载有 `PDF_CAP` 安全阀（默认 1500），避免下载过多

### DBLP 限速策略

DBLP 会对高频请求封禁（返回 429 或断开连接）。本工具的应对策略：
- 请求间隔 8 秒（`DBLP_DELAY = 8.0`）
- 429 错误：等待 30 秒后重试（最多 3 次）
- 连接错误：等待 30 秒后重试
- 熔断器：连续 3 次失败 → 暂停 600 秒
- 缓存机制：支持中断后恢复

## 推荐阅读工作流

### 1. 文献管理：Zotero

- 将 `_high_impact.csv` 导入 Zotero（用 DOI 或标题批量检索）
- 按领域（area_folder）建立分类集合
- 用 Zotero 插件 `Better BibTeX` 管理引用

### 2. PDF 阅读 + AI 翻译：知云文献翻译 / 沉浸式翻译

- **知云文献翻译**：左侧 PDF + 右侧 AI 翻译，划词即译，支持多引擎
- **沉浸式翻译**：浏览器插件，可翻译 arXiv/会议网页，保留排版
- 将 `paper.pdf` 拖入知云即可阅读，配合 `meta.json` 查看引用数/摘要

### 3. AI 辅助提问：ChatPDF / pdf.ai

- 上传 PDF 到 [ChatPDF](https://www.chatpdf.com/) 或 [pdf.ai](https://pdf.ai/)
- 可针对论文内容提问、生成摘要、提取关键贡献
- 适合快速筛选论文是否值得精读

### 4. 对比阅读

- 用 `_index.csv` 按 venue + year 排序，对比同一方向不同会议的论文
- 用 `_high_impact.csv` 按引用数排序，找到各领域高影响力论文
- 用 `_abstracts.jsonl` 批量分析摘要，聚类相似主题

### 5. 导出引用

- 如需复杂引用格式（毕业论文等），可将 Zotero 库导出为 EndNote
- EndNote 对中文论文引用格式支持更好（GB/T 7714 等）

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_YEAR_START` | 2023 | 起始年份 |
| `DEFAULT_YEAR_END` | 2025 | 结束年份 |
| `DBLP_DELAY` | 8.0 | DBLP 请求间隔（秒） |
| `ARXIV_DELAY` | 3.5 | arXiv 请求间隔（秒） |
| `HIGH_MIN_CIT` | 30 | 高影响力论文引用阈值 |
| `HIGH_TOPN` | 12 | 每个 venue×year 取 top N |
| `PDF_CAP` | 1500 | PDF 下载总数上限 |
| `MAX_PAGES_PER_VY` | 20 | 每 venue×year 最多拉 20 页（2000 篇） |

## 常见问题

**Q: 为什么某些 venue 某年论文数为 0？**
A: 部分会议是双年会（如 ICCV/ECCV 在非举办年只有少量论文），或该年会议尚未召开。

**Q: DBLP 被封了怎么办？**
A: 等待 10-15 分钟后重跑 `stage1`，已缓存的会自动跳过。也可增大 `DBLP_DELAY`。

**Q: 如何扩展到更多年份？**
A: `python ccf_crawler.py stage1 --years 2020-2025`

**Q: OpenAlex 引用数为空？**
A: 部分新论文（2024-2025）在 OpenAlex 中尚未被收录，或 DOI 不匹配。可手动在 Semantic Scholar 查询。
"# MyEssayNote" 
