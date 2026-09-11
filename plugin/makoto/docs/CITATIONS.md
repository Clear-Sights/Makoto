# Canonical Citations — manual seed

This file is the manual canonical source. Makoto reads it at install time and on every dispatcher invocation (mtime-gated). Author-Year strings extracted from this file are added to the `canonical_citations` SQLite table with `source = 'CITATIONS.md'`. The `content.phantom_citation` check then validates that Author-Year strings in Write/Edit content match an entry in this table.

## How to add

Either inline in prose (`Per Vaswani 2017, attention layers...`) or one per line — the same regex extracts both shapes.

## Seed entries

The following citations are recognized by Makoto. The list below is the initial seed; expand as needed.

### Foundational ML / NLP

- Vaswani 2017 — Attention Is All You Need
- Devlin 2019 — BERT: Pre-training of Deep Bidirectional Transformers
- Brown 2020 — Language Models are Few-Shot Learners (GPT-3)
- Radford 2019 — Language Models are Unsupervised Multitask Learners (GPT-2)
- Hochreiter 1997 — Long Short-Term Memory
- LeCun 1998 — Gradient-Based Learning Applied to Document Recognition
- Krizhevsky 2012 — ImageNet Classification with Deep CNNs (AlexNet)
- He 2016 — Deep Residual Learning for Image Recognition (ResNet)
- Goodfellow 2014 — Generative Adversarial Nets
- Kingma 2014 — Auto-Encoding Variational Bayes (VAE)

### Software engineering / verification

- Knight 1986 — Experimental Evaluation of N-Version Programming
- Leveson 1993 — An Investigation of the Therac-25 Accidents
- Wirth 1971 — Program Development by Stepwise Refinement
- Dijkstra 1968 — Go To Statement Considered Harmful
- Hoare 1969 — An Axiomatic Basis for Computer Programming

## Notes

- Extraction and normalization are defined in [citations.py](../state/citations.py).
