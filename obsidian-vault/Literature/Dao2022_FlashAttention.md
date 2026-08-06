---
type: literature-note
status: read
citekey: dao2022
title: "FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness"
authors:
  - Tri Dao
  - Daniel Y. Fu
  - Stefano Ermon
  - Atri Rudra
  - Christopher Ré
venue: NeurIPS
year: 2022
topic: efficient-transformer
tags:
  - attention
  - transformer
  - memory-efficient
  - llm-systems
source_review: "[[attention-v0.2-gate2]]"
---

# FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness

## Metadata

- **Authors**: Tri Dao, Daniel Y. Fu, Stefano Ermon, Atri Rudra, Christopher Ré
- **Venue**: NeurIPS 2022
- **Topic**: Efficient Transformer / Attention Optimization
- **Tags**: #attention #transformer #memory-efficient #llm-systems

## Problem

Modern Transformer models rely heavily on attention mechanisms.
However, the standard attention algorithm requires storing large
intermediate matrices during computation.

Although attention has quadratic computational complexity with
respect to sequence length, the practical bottleneck is often not
only computation but also memory access between GPU high-bandwidth
memory and on-chip SRAM.

The paper asks:

> How can we compute exact attention more efficiently without changing
> the mathematical result?

## Key Idea

FlashAttention introduces an IO-aware attention algorithm.

Instead of materializing the full attention matrix:

```
QKᵀ → softmax → multiply V
```

FlashAttention uses tiling and recomputation strategies.

The algorithm keeps frequently used data in fast GPU SRAM and avoids
repeated reads/writes to slower HBM memory.

The key insight is:

> Attention efficiency depends not only on FLOPs, but also on how data
> moves through the hardware memory hierarchy.

## Architecture

FlashAttention consists of three main ideas:

1. **Tiling** — The attention computation is divided into smaller blocks
   that fit into fast on-chip memory.
2. **Online softmax** — The algorithm computes softmax statistics
   incrementally without storing the entire attention matrix.
3. **Recomputation** — During backward propagation, some intermediate
   values are recomputed instead of stored, reducing memory usage.

Together, these techniques maintain exact attention results while
reducing memory overhead.

## Why Important

FlashAttention changed the optimization perspective of Transformer
models.

Before this work, attention acceleration often focused on changing
the mathematical formulation, such as approximate or sparse attention.

FlashAttention shows that significant improvements can also come from
hardware-aware algorithm design while keeping exact attention.

It became an important building block for modern large language model
training and long-context research.

## Connection

**Citekey**: [[dao2022]] (this paper)

FlashAttention connects three research areas:

```
Attention Models
       |
       v
Transformer Architecture
       |
       v
Efficient AI Systems
```

Related papers in vault:

- [[attention-v0.2-gate2]] — auto-generated attention lineage review
- [[Vaswani2017]] — Transformer original paper (to be added in next D stage note)
- [[velickovic2017]] — GAT (graph attention predecessor, to be added)

Research question:

> Can future attention mechanisms achieve better scaling by jointly
> optimizing algorithms, architectures, and hardware?
