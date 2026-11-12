# Model card: Sentinel injection classifier

A binary classifier that outputs the probability that a text contains a prompt-injection or jailbreak attempt. It is one component of Sentinel; the rules engine and decision layer sit around it. The weights are not distributed: `sentinel train` produces them.

## Model

- **Default:** `microsoft/deberta-v3-xsmall` (MIT, about 70M parameters including embeddings), fine-tuned as a two-class sequence classifier. Max length 256, lr 5e-5, batch 16, up to 6 epochs with early stopping, float32.
- **Compared:** `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, 22M parameters), fine-tuned on the same data (lr 8e-5, otherwise the same). It is the other row in every results table.
- **Why DeBERTa is the default:** selection used validation data and an OOD-dev half of SPML only. With the original training set MiniLM scored higher on validation and trained four times faster, so it was my first default. After adding augmentation and two extra public datasets, DeBERTa recalled clearly more of the OOD-dev attacks at the validation 1%-FPR threshold (ablation table in the README), with no rise in validation hard-benign false positives, so it replaced MiniLM. The trade-off: it is about two to three times slower per prompt and much slower to train on a CPU.
- **A regression I want to be upfront about:** on the 60-item hard-benign test set the new default blocks more benign prompts than the first model did (see the before/after table in the README; three of the blocks are one templated question). The selection rule only guarded the 19 hard-benign validation examples, which was too few. The previous model can be reproduced with the command in the README.
- **How this came about:** I had first planned DeBERTa alone. A CPU run was far too slow on a heavily loaded shared machine, so I stopped it, trained MiniLM on the CPU for a while, and then moved training to a GPU, where both fit easily. Training and inference choose `cuda` when available and fall back to the CPU (`--device` or `SENTINEL_DEVICE` to override).
- **Precision matters:** with the library versions here, DeBERTa's checkpoint loads in float16 by default and training in that dtype produced NaNs after the first optimiser step; the code loads in float32 explicitly.
- **Input:** text after Sentinel's normaliser, truncated to 256 tokens at training time (the extra data is length-filtered to fit). At inference, longer inputs are scored in overlapping windows and the maximum is taken.
- **Output:** a logit margin, converted to a probability with temperature scaling fitted on the validation split.

## Training data

Downloaded by script at pinned revisions (`sentinel data`), never redistributed:

| Source | Licence | Use |
|---|---|---|
| neuralchemy/Prompt-injection-dataset | Apache-2.0 | train, validation, in-distribution test |
| jackhhao/jailbreak-classification | Apache-2.0 | train, validation, in-distribution test |
| Hand-written sets in `data/hand_written/` | MIT | train, validation, test (separate halves) |
| deepset/prompt-injections | Apache-2.0 | out-of-distribution test only, never used for any choice |
| SPML Chatbot Prompt Injection | MIT | split once by a fixed seed: one half is OOD-dev (model selection only), the other half OOD-test (reported) |
| hendzh/PromptShield | Apache-2.0 (dataset card) | extra training data: a length-filtered sample (up to 2000 per class, at most 800 characters) of its train split |
| Lakera/gandalf_ignore_instructions | MIT (dataset card) | extra training data: attacks only |
| Augmentation (`src/sentinel/augment.py`) | MIT (mine) | derived from the training rows only: obfuscated variants, attacks embedded in benign context, benign text quoting attacks |
| databricks-dolly-15k | CC-BY-SA-3.0 | benign validation and test only; not used for training |

Exact duplicates and near-duplicates (character n-gram TF-IDF cosine >= 0.9) between training data and any validation or test set were removed before training. Counts are in the training block below.

## Training

<!-- BEGIN:training -->
- **Shipped default: `microsoft/deberta-v3-xsmall`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 13270 training rows, 1605 validation rows; 6 epochs, lr 5e-05, batch 16, max length 256, seed 42; 465 s of training.
  - epoch 1: train loss 0.226, validation PR-AUC 0.9893, ROC-AUC 0.9928
  - epoch 2: train loss 0.062, validation PR-AUC 0.9940, ROC-AUC 0.9966
  - epoch 3: train loss 0.035, validation PR-AUC 0.9961, ROC-AUC 0.9973
  - epoch 4: train loss 0.015, validation PR-AUC 0.9662, ROC-AUC 0.9901
  - epoch 5: train loss 0.012, validation PR-AUC 0.9945, ROC-AUC 0.9968
- **Compared: `sentence-transformers/all-MiniLM-L6-v2`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 13270 training rows, 1605 validation rows; 6 epochs, lr 8e-05, batch 16, max length 256, seed 42; 177 s of training.
  - epoch 1: train loss 0.221, validation PR-AUC 0.9937, ROC-AUC 0.9962
  - epoch 2: train loss 0.064, validation PR-AUC 0.9957, ROC-AUC 0.9970
  - epoch 3: train loss 0.028, validation PR-AUC 0.9967, ROC-AUC 0.9978
  - epoch 4: train loss 0.013, validation PR-AUC 0.9956, ROC-AUC 0.9972
- Selection rule, fixed before I looked at any test set: among variants trained on the same data, take the highest OOD-dev recall at the validation 1%-FPR threshold, provided the validation hard-benign false-positive rate does not rise and validation PR-AUC drops by no more than 0.005. See the ablation table.
- CPU training time, **estimate** for `microsoft/deberta-v3-xsmall`: `scripts/bench_cpu_train.py` timed 12 real steps at 2.95 s/step with 3 threads (12 logical cores; system-wide CPU utilisation 53% just before the run), which extrapolates to about 204.1 minutes for 5 epochs (4150 steps), excluding validation passes. It is an extrapolation, and a busier machine is slower.
- CPU training time, **estimate** for `sentence-transformers/all-MiniLM-L6-v2`: `scripts/bench_cpu_train.py` timed 12 real steps at 1.14 s/step with 3 threads (12 logical cores; system-wide CPU utilisation 84% just before the run), which extrapolates to about 63.1 minutes for 4 epochs (3320 steps), excluding validation passes. It is an extrapolation, and a busier machine is slower.
- Split sizes after de-duplication: train 13270 (7966 attacks), train_base 5864 (3112 attacks), train_aug 7445 (4329 attacks), train_ext 10861 (6109 attacks), val 1605 (621 attacks), test_indist 1187 (562 attacks), test_deepset 660 (261 attacks), test_spml 597 (300 attacks), test_spml_dev 599 (300 attacks), test_hard_benign 60 (0 attacks), test_attacks 26 (26 attacks), test_obfuscated 53 (47 attacks), test_dolly_benign 992 (0 attacks), test_indirect 80 (60 attacks).
<!-- END:training -->

Reproduce: `sentinel train` (uses a GPU if one is visible, otherwise the CPU; timings are above; GPU runs are not bit-for-bit repeatable, so expect small differences). The comparison model: `sentinel train --base sentence-transformers/all-MiniLM-L6-v2 --lr 8e-5 --out models/minilm`, then `sentinel eval --also models/minilm`.

## Evaluation

Thresholds are chosen on validation data only and the test sets are untouched until the final run.

<!-- BEGIN:thresholds -->
Chosen on the validation split only (n=1605): block at calibrated score >= 0.985 (1% validation FPR), flag at >= 0.850 (3%), agreement threshold 0.071 (10%). Policy: {"t_flag": 0.8501494383395667, "t_block": 0.9849128292791913, "t_agree": 0.0714967731633372, "rule_block_high": true}
<!-- END:thresholds -->

<!-- BEGIN:headline -->
| Headline (Sentinel, block decision) | Value | 95% Wilson interval | Counts |
|---|---|---|---|
| False-positive rate on hard-benign text (blocked / benign prompts that talk about injection) | 8.3% | 3.6% to 18.1% | 5 of 60 |
| Recall on deepset/prompt-injections (out of distribution) | 39.5% | 33.7% to 45.5% | 103 of 261 |
| Recall on SPML (out of distribution) | 54.7% | 49.0% to 60.2% | 164 of 300 |
| False-positive rate on everyday benign (Dolly-15k held out) | 0.2% | 0.1% to 0.7% | 2 of 992 |
| Recall on deepset counting a flag as a catch (flagged prompts still reach the model) | 73.2% | | n=261 attacks |
| In-distribution F1 (secondary; the training data is partly synthetic) | 0.962 | | n=1187 |
<!-- END:headline -->

Variant selection (validation and OOD-dev only):

<!-- BEGIN:ablation -->
| Variant (selection uses validation + OOD-dev only) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | OOD-dev recall @ val 1% FPR | OOD-dev FPR | Val hard-benign FPR |
|---|---|---|---|---|---|---|---|
| v1 (original data, 3 epochs, no dev selection) | 5864 | 3 | 0.9967 | 0.9346 | 29.0% | 0.0% | 0.0% (n=19) |
| base data + early stop on dev | 5864 | 5 | 0.9949 | 0.9501 | 35.7% | 0.0% | 0.0% (n=19) |
| base + augmentation | 7445 | 4 | 0.9930 | 0.9632 | 23.0% | 0.0% | 0.0% (n=19) |
| base + extra public data | 10861 | 5 | 0.9964 | 0.9478 | 34.0% | 0.0% | 0.0% (n=19) |
| base + augmentation + extra data | 13270 | 4 | 0.9952 | 0.9581 | 33.0% | 0.0% | 0.0% (n=19) |
| base + augmentation + extra data, lr 5e-5 | 13270 | 6 | 0.9963 | 0.9373 | 31.0% | 0.0% | 0.0% (n=19) |
| DeBERTa-v3-xsmall, augmentation + extra data | 13270 | 5 | 0.9955 | 0.9275 | 53.0% | 0.0% | 0.0% (n=19) |
<!-- END:ablation -->

Before and after the second training round, same test splits:

<!-- BEGIN:before_after -->
| Set | Recall block, before | after | Recall flag-or-block, before | after | Classifier recall @1% FPR, before | after |
|---|---|---|---|---|---|---|
| deepset (OOD, untouched) | 35.2% | 39.5% | 46.0% | 73.2% | 16.1% | 28.4% |
| SPML OOD-test | 40.0% | 54.7% | 50.3% | 67.3% | 48.7% | 63.3% |
| SPML OOD-dev (selection only) | 37.7% | 53.3% | 52.0% | 65.0% | 45.7% | 62.7% |
| In-distribution | 95.4% | 93.2% | 97.7% | 97.0% | 95.9% | 95.4% |
| Obfuscated | 100.0% | 100.0% | 100.0% | 100.0% | 57.4% | 40.4% |
| Plain attacks | 96.2% | 84.6% | 100.0% | 100.0% | n/a | n/a |
| Indirect (SYNTHETIC) | 88.3% | 93.3% | 93.3% | 100.0% | 23.3% | 50.0% |

| Benign side | False-positive rate (block), before | after | n |
|---|---|---|---|
| Hard-benign (talks about injection) | 1.7% [1 of 60] | 8.3% [5 of 60] | 60 |
| Everyday (Dolly-15k held out) | 0.3% [3 of 992] | 0.2% [2 of 992] | 992 |
| SPML OOD-test benign | 0.0% [0 of 297] | 0.0% [0 of 297] | 297 |
| deepset benign | 1.5% [6 of 399] | 1.0% [4 of 399] | 399 |
<!-- END:before_after -->

Full per-set tables with intervals, for every system, are in the README and `docs/data/eval.json`. The indirect-injection set is synthetic and small.

<!-- BEGIN:language -->
| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |
|---|---|---|---|---|---|
| EN | 336 | 164 | 40.2% | 1.2% | 32.9% |
| DE | 233 | 85 | 35.3% | 0.7% | 18.8% |
<!-- END:language -->

Reproduce: `sentinel eval`, then `python scripts/render_docs.py`.

## Intended use

Screening text before it is sent to a language model, as one layer among several, with the decision (allow, flag, block) reviewed by an operator-defined policy. Blocks and flags are logged so false positives can be found and thresholds revisited.

## Limitations and risks

- It is not a security guarantee. Adaptive attackers, multi-turn attacks and unseen phrasings will get through, and the model has not been tested against any adversarial optimisation.
- Training data is overwhelmingly English; recall on German is measurably worse (table above). Other languages were not tested.
- Training data is partly synthetic, so in-distribution scores overstate real-world performance. Out-of-distribution recall and hard-benign false-positive rate are the numbers to trust more, and their intervals are wide because the test sets are small.
- It can over-block benign text that discusses injection or contains trigger words. Sentinel's decision layer reduces this by treating quoted or discussed examples as lower severity, but does not eliminate it.
- Fine-tuned on short texts (128 tokens); long documents rely on the windowing heuristic.
- The comparison with a public third-party detector was not run.

## Licence

The code and my fine-tuned weights are MIT. Inherited terms: the base model and the Apache-2.0 datasets require attribution (given above); Dolly (CC-BY-SA) is used only for validation and testing, not training.
