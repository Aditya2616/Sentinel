# Sentinel: research notes

Research notes from before the build. Licences marked "API" were read from the Hugging Face API (2026-11-12); everything else is from the linked sources and flagged where I have not verified it.

## 1. The threat

- **OWASP LLM01:2025 Prompt Injection** covers *direct* injection (the user types the attack) and *indirect* injection (instructions hidden in retrieved documents, web pages, emails or tool output). OWASP's position is that there is probably no fool-proof prevention because models are probabilistic, so defences must be layered: input screening, least-privilege tools, output checks, monitoring and audit. Sentinel is one layer (input and retrieved-content screening plus audit), and the README must say so. <https://genai.owasp.org/llmrisk/LLM01/>
- **Indirect injection** was formalised by Greshake et al. (2023). **BIPIA** (Yi et al., 2023, 5 scenarios, 250 attacker goals; <https://arxiv.org/abs/2312.14197>) and **AgentDojo** (ETH, 97 tasks / 629 security cases; <https://github.com/ethz-spylab/agentdojo>) are the benchmarks. Both are agent/QA harnesses, too heavy to reproduce here; I will use their *attack-goal styles* as the template for my own small indirect test set and say so.
- Attack families the rules should cover: instruction override ("ignore previous instructions"), role / persona / system-prompt spoofing (DAN, "developer mode", fake `system:` turns, ChatML / `[INST]` / `<|im_start|>` tokens), prompt-leak requests, delimiter and markup smuggling (fake closing tags, markdown/HTML comments, hidden text), encoding and obfuscation (base64, hex, ROT13, leetspeak, homoglyphs, zero-width and bidi characters, spaced-out letters), data exfiltration via markdown image URLs, and (indirect) instructions addressed to the assistant inside documents.

## 2. Why classifiers over-trigger on benign text

- **InjecGuard / PIGuard** (arXiv 2410.22770, ACL 2025, <https://huggingface.co/leolee99/PIGuard>) defines *over-defense*: guard models latch onto trigger words ("ignore", "bypass", "system prompt") and flag benign text. Their NotInject benchmark (339 benign samples, three difficulty tiers by trigger-word count) drops many open and commercial detectors toward ~60% accuracy, near chance, and names ProtectAI v2 as significantly over-defended. Their remedy (MOF) is to train so the model does not shortcut on trigger words.
- **Implication for Sentinel:** the hard case is benign text *about* injection (security teaching, translation of "ignore" text, quoting an attack for analysis, ordinary "disregard the previous email"). I will (a) put a hand-written hard-benign set in training and a *separate* one in test, (b) report false-positive rate on it as a headline metric, (c) design the decision layer so a rule hit alone is a *flag* unless severity is high or the classifier agrees. NotInject itself is not used for training (I have not verified its licence; I will check before using it as an extra eval only).
- Meta's Prompt Guard 2 card also says benign/malicious distribution shift hurts and recommends fine-tuning on domain data. It is gated under the Llama 4 community licence (API: `other`, gated manual), so **excluded from the repo and the default comparison**; it can be an optional local comparison if the user has access.

## 3. Existing detectors

| Tool | Licence | Notes |
|---|---|---|
| ProtectAI `deberta-v3-base-prompt-injection-v2` | Apache-2.0 (API), 184M params | Binary injection classifier, base deberta-v3-base. Training data mix includes some non-commercial-risk sources per third-party notes; weights themselves Apache-2.0. Would have been a good comparison baseline (~0.7 GB download); I did not run it. Reported over-defense (InjecGuard). |
| Meta Prompt Guard 2 (22M / 86M) | Llama 4 community, gated | Excluded, see above. |
| LLM Guard (Protect AI) | MIT (secondary sources) | Scanner library, wraps the ProtectAI model. Reference design for input/output scanners with risk scores. |
| Rebuff | open source | Heuristics + LLM check + vector DB of known attacks + canary tokens. Canary tokens are a worthwhile idea for prompt-leak detection but need the downstream model, so out of scope (noted in SPEC as future work). |
| NeMo Guardrails (NVIDIA) | Apache-2.0 | Dialog-flow control (Colang), not a single-prompt detector. Different layer. |
| Lakera Guard | commercial | Not usable offline. Lakera's public contributions: Gandalf/Mosscap datasets and the PINT benchmark (<https://github.com/CheckPointSW/pint-benchmark>). Vendor numbers (98%, <50 ms) are unverified; I do not repeat them. |
| HiddenLayer dataset review | n/a | Ranks public datasets by quality; deepset is "use with caution" (small, narrow). <https://www.hiddenlayer.com/research/evaluating-prompt-injection-datasets> |

## 4. Datasets (licences from the HF API)

| Dataset | Licence | Size | Verdict |
|---|---|---|---|
| `neuralchemy/Prompt-injection-dataset` | Apache-2.0 | core 4,391 / 941 / 942 (group-aware split, no augmentation); 29 attack categories, severity, source field, includes a `benign` hard-negative category | **Primary training source.** I will use `core` (no augmented near-duplicates). Quality caveat: partly synthetic/templated; I will audit duplicates and check the split myself. |
| `jackhhao/jailbreak-classification` | Apache-2.0 | ~1.3k (jailbreak vs benign) | **Training**, adds long persona-style jailbreaks. Skewed to long prompts. Check overlap with neuralchemy. |
| `deepset/prompt-injections` | Apache-2.0 | 546 train / 116 test, EN+DE (+FR) | **Held-out OOD test only** (never trained on). Small, multilingual, partly political; "use with caution". Useful for showing the English-trained model's limits on German. |
| `reshabhs/SPML_Chatbot_Prompt_Injection` | MIT | 10k-100k, system-prompt + user prompt pairs | **Second OOD set** (different construction: injection judged against a system prompt). Use user-prompt text only, subsample. |
| `Lakera/mosscap_prompt_injection` | MIT | 279k, unlabelled | Excluded: "many of them are not actual injections", no labels. |
| `hackaprompt/hackaprompt-dataset` | MIT but gated | large, unlabelled | Excluded (gated, unlabelled). |
| `xTRam1/safe-guard-prompt-injection` | **no licence declared** (API) | ~10k synthetic | Excluded, cannot confirm redistribution or use rights. |
| `tatsu-lab/alpaca` | CC-BY-NC-4.0 | 52k | Excluded (non-commercial). |
| `databricks/databricks-dolly-15k` | CC-BY-SA-3.0 | 15k | **Benign negatives pool** for realistic-traffic FPR. ShareAlike: only used at train/eval time via download script, nothing redistributed. |
| Hand-written sets (mine, MIT) | MIT | ~200+ | `hard_benign` (talks about injection, security education, quoting attacks, code that mentions "system prompt"), `obfuscated_attacks`, `indirect` (documents/tool outputs with and without embedded instructions). Split into train-visible and test-only halves with different templates. |

Known issues to handle: duplicate and near-duplicate prompts across sources (dedupe on normalised text and report counts), label noise in "jailbreak" sets (some benign roleplay labelled malicious), language mismatch (deepset is largely German), length bias (jailbreak = long, benign = short; a classifier can learn length). I will measure length-only and TF-IDF baselines to expose such shortcuts, and keep the hard-benign set length-matched.

## 5. Base model choice

Candidates (licences from API): `microsoft/deberta-v3-xsmall` (MIT, ~22M backbone + 48M embeddings), `microsoft/deberta-v3-small` (MIT, ~44M backbone), `microsoft/MiniLM-L12-H384-uncased` (MIT, 33M), `answerdotai/ModernBERT-base` (Apache-2.0, 149M), `distilbert-base-uncased` (Apache-2.0, 67M), `google/electra-small-discriminator` (Apache-2.0, 14M). DeBERTa-v3 beats MiniLMv2-small by ~1.2 pts on MNLI and beats ModernBERT on sample efficiency in a controlled comparison (<https://arxiv.org/abs/2504.08716>); ProtectAI and deepset both chose DeBERTa-v3 for this task.

**Original choice: `deberta-v3-xsmall`.** On the CPU I train on, a DeBERTa step took far too long, so the shipped model is `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, 22M parameters) fine-tuned as a classifier; see `MODEL_CARD.md`. Baselines: rules only, and TF-IDF (word + char n-grams) + logistic regression. A comparison against the ProtectAI v2 detector was planned and not run.

Environment checked: transformers 5.7.0, torch 2.11.0+cpu, scikit-learn 1.8.0, fastapi 0.136.1, 12 CPU threads. Transformers 5 API changes (Trainer args, tokenizer behaviour) must be verified against installed docs during build; I will write a plain PyTorch loop if Trainer causes friction.

## 6. Open questions I am carrying into the build

1. Does the xsmall model hold FPR below a few percent on hard-benign text, or does the rule+classifier decision layer have to do the work? Evidence will decide the thresholds.
2. Indirect injection has no good public labelled set under a usable licence; I will build a small honest one and label it "synthetic, small".
3. Multilingual: out of scope for training; reported as a limitation using deepset's German rows.

## Sources

- OWASP LLM01: <https://genai.owasp.org/llmrisk/LLM01/>
- InjecGuard / PIGuard: <https://arxiv.org/abs/2410.22770>, <https://huggingface.co/leolee99/PIGuard>
- BIPIA: <https://arxiv.org/abs/2312.14197>; AgentDojo: <https://github.com/ethz-spylab/agentdojo>
- ProtectAI v2: <https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2>
- Prompt Guard 2: <https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-22M>
- deepset dataset: <https://huggingface.co/datasets/deepset/prompt-injections>
- neuralchemy dataset: <https://huggingface.co/datasets/neuralchemy/Prompt-injection-dataset>
- jackhhao: <https://huggingface.co/datasets/jackhhao/jailbreak-classification>
- SPML: <https://huggingface.co/datasets/reshabhs/SPML_Chatbot_Prompt_Injection>; Mosscap: <https://huggingface.co/datasets/Lakera/mosscap_prompt_injection>
- PINT benchmark: <https://github.com/CheckPointSW/pint-benchmark>; HiddenLayer review: <https://www.hiddenlayer.com/research/evaluating-prompt-injection-datasets>
- DeBERTaV3 vs ModernBERT: <https://arxiv.org/abs/2504.08716>
