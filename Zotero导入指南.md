# Zotero 导入与集合分类指南

## 概述

本文档记录了 CCF-A 论文和 MCM/ICM O 奖论文导入 Zotero 并进行集合分类的完整流程和最终状态。

## 最终 Zotero 库状态

### 总览

| 指标 | 数值 |
|------|------|
| 总条目数 | 14,629 篇 |
| 集合数 | 19 个 |
| CCF-A 论文 | 13,573 篇 (10 个子领域集合) |
| MCM/ICM 论文 | 1,038 篇 (7 个题号集合) |
| 未分类条目 | 18 篇 |

### 集合结构

```
CCF-A/                                    [根集合]
  ├─ AI (人工智能)                         6,285 篇
  ├─ Database (数据库/数据挖掘)             1,821 篇
  ├─ Graphics (计算机图形学)               1,244 篇
  ├─ Interdisciplinary (交叉/综合/新兴)     1,026 篇
  ├─ Security (网络与信息安全)               849 篇
  ├─ Software (软件工程)                    792 篇
  ├─ Networks (计算机网络)                  510 篇
  ├─ Architecture (体系结构)                509 篇
  ├─ HCI (人机交互)                        296 篇
  └─ Theory (计算机科学理论)                 241 篇

MCM-ICM/                                  [根集合]
  ├─ Problem A - MCM 连续型                262 篇
  ├─ Problem B - MCM 离散型                220 篇
  ├─ Problem C - MCM 数据分析              196 篇
  ├─ Problem D - ICM 运筹/网络             102 篇
  ├─ Problem E - ICM 可持续发展            102 篇
  ├─ Problem F - ICM 政策                   80 篇
  └─ 未分类                                 76 篇
```

### 标签体系

每篇论文都带有以下标签，可在 Zotero 左下角的标签选择器中筛选：

**CCF-A 论文标签**:
- `CCF-A` — 所有 CCF-A 论文
- venue 名称 (如 `AAAI`、`ICML`、`CVPR`)
- 子领域 (如 `AI`、`Database`、`Security`)
- 年份 (如 `2023`、`2024`、`2025`)
- `高引用(100+)` 或 `高引用(50+)` — 按引用数分级

**MCM/ICM 论文标签**:
- `MCM-ICM` — 所有美赛论文
- `O奖` — O 奖论文
- `Problem A` ~ `Problem F` — 按题号分类
- 年份

## 导入流程

### 第1步: BibTeX 导入 (Connector API)

通过 Zotero Connector API (端口 23119) 自动导入 BibTeX 文件：
- `_ccf_a.bib` — 12,178 篇 CCF-A 高影响力论文
- `_mcm.bib` — 459 篇 MCM/ICM O 奖论文

导入脚本: `zotero_import.py` (使用 Connector API, 无需启用本地 API)

### 第2步: 启用本地 API

1. Zotero > 编辑 > 首选项 > 高级 > 通用
2. 勾选 "允许其他应用程序与本计算机上的 Zotero 通信"
3. 本地 API 在 `http://localhost:23119/api` 可用

### 第3步: 集合分类 (Run JavaScript)

通过 Zotero 的 Run JavaScript 控制台执行 `zotero_collections.js`：
1. 读取 `_venue_map.json` (12,177 条 title→venue 映射)
2. 创建 19 个集合 (CCF-A 10 子领域 + MCM-ICM 7 题号 + 2 根集合)
3. 根据标题匹配 venue, 自动添加 venue 标签
4. 按 venue→area 映射分配到对应集合

### 第4步: 清理重复集合

多次运行分类脚本会产生重复集合, 通过 `zotero_cleanup.js` 删除:
- 第一轮: 删除 35 个空集合
- 第二轮: 删除 16 个重复集合 (条目保留在同名集合中)
- 最终: 19 个集合, 无重复

## 文件清单

`d:\Desktop\论文\` 目录下的关键文件：

### 数据文件
- `_ccf_a.bib` — CCF-A 高影响力论文 BibTeX (12,178 条)
- `_mcm.bib` (MCM-ICM/) — MCM/ICM BibTeX (459 条)
- `_high_impact.csv` — 高影响力论文索引 (含引用数)
- `_index.csv` — 全量论文清单 (120,797 篇)
- `_abstracts.jsonl` — 论文摘要 (83,360 篇)
- `_venue_map.json` — title→venue 映射 (12,177 条, 供集合分类用)

### 脚本文件
- `zotero_import.py` — Zotero 导入工具 (Connector API)
- `zotero_collections.js` — 集合分类脚本 (Run JavaScript)
- `zotero_cleanup.js` — 重复集合清理脚本

### 其他
- `_venue_report.txt` — 各 venue 爬取统计
- `Zotero导入指南.md` — 本文档
- `MCM-ICM/` — 美赛 O 奖论文 (503 文件, 按年份/题号分类)

## 使用建议

### 筛选阅读

1. 在 Zotero 左侧选择集合 (如 `AI (人工智能)`)
2. 点击标签选择器, 添加筛选 (如 `2024` + `高引用(100+)`)
3. 按引用数排序, 优先阅读高影响力论文

### 与 AI 阅读工具配合

- **知云文献翻译**: 直接打开 Zotero 管理的 PDF, 支持划词翻译
- **沉浸式翻译**: 浏览器插件, 翻译 Zotero 网页版摘要
- **ChatPDF**: 上传 PDF 后可对话式提问
- **pdf.ai**: AI 辅助阅读 PDF, 支持摘要和问答

### 推荐插件

- **Zotero PDF Translate**: 在 Zotero 内直接翻译选中文本
- **Zotero Better Notes**: 增强笔记功能, 支持模板化笔记
- **Zotero Style**: 界面美化, 显示引用数等信息

## 去重建议

由于测试导入可能产生少量重复条目, 建议执行去重:
1. 点击 Zotero 左侧面板的 "重复条目"
2. 检查并合并重复项
