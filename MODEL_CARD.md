# Model card: Sentinel injection classifier

A binary classifier that outputs the probability that a text contains a prompt-injection or jailbreak attempt. It is one component of Sentinel; the rules engine and decision layer sit around it. The weights are not distributed: `sentinel train` produces them.

## Model

- **Default:** `microsoft/deberta-v3-xsmall` (MIT, <!--v:params_default-->70.8M<!--/v--> parameters including embeddings), fine-tuned as a two-class sequence classifier. Max length <!--v:max_len-->256<!--/v-->, lr <!--v:lr_default-->5e-05<!--/v-->, batch <!--v:batch-->16<!--/v-->, up to <!--v:epochs_max-->6<!--/v--> epochs with early stopping on validation plus OOD-dev, float32.
- **Compared:** `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, <!--v:params_alt-->22.7M<!--/v--> parameters), fine-tuned on the same data (lr <!--v:lr_alt-->8e-05<!--/v-->, otherwise the same). It is the other row in every results table.
- **How the default was chosen:** by a rule fixed before the round-two models were trained, using validation data and an OOD-dev half of SPML only. Each model gets its `balanced` block threshold (the lowest threshold with validation hard-benign false-positive rate at most <!--v:cap_hb-->2%<!--/v--> and everyday-benign at most <!--v:cap_dolly-->0.5%<!--/v-->); the model with the best OOD-dev recall at that threshold wins. DeBERTa won; the selection table below shows both.
- **History, so that nothing is hidden:** I first planned DeBERTa, trained MiniLM when CPU training was too slow, then moved training to a GPU. The first MiniLM model was the default for a while. In round one, augmentation and extra data raised out-of-distribution recall but also raised false blocks on hard-benign text (<!--v:r1_v1_fpr-->8.3%<!--/v--> on the <!--v:hb_v1_n-->60<!--/v-->-item v1 test set, which I looked at once). In round two I wrote a <!--v:val_hb_new-->132<!--/v-->-item hard-benign validation set and a <!--v:hn_train_n-->115<!--/v-->-item hard-negative training set, re-trained both encoders, and re-selected thresholds and the default by the rule above. Those v1 numbers are therefore not a clean test any more; hard-benign v2 (frozen before the round-two models were run) is.
- **Precision matters:** with the library versions here, DeBERTa's checkpoint loads in float16 by default and training in that dtype produced NaNs after the first optimiser step; the code loads in float32 explicitly.
- **Input:** text after Sentinel's normaliser, truncated to <!--v:max_len-->256<!--/v--> tokens at training time (the extra data is length-filtered to fit). At inference, longer inputs are scored in overlapping windows and the maximum is taken.
- **Output:** a logit margin, converted to a probability with temperature scaling fitted on the validation split.
- **Operating points:** `strict`, `balanced` (default) and `permissive`, stored with the model in `thresholds.json`; select with the `SENTINEL_PRESET` environment variable.

## Training data

Downloaded by script at pinned revisions (`sentinel data`), never redistributed:

| Source | Licence | Use |
|---|---|---|
| neuralchemy/Prompt-injection-dataset | Apache-2.0 | train, validation, in-distribution test |
| jackhhao/jailbreak-classification | Apache-2.0 | train, validation, in-distribution test |
| Hand-written sets in `data/hand_written/` | MIT | train, validation, test (separate halves) |
| deepset/prompt-injections | Apache-2.0 | out-of-distribution test only, never used for any choice |
| SPML Chatbot Prompt Injection | MIT | split once by a fixed seed: one half is OOD-dev (model selection only), the other half OOD-test (reported) |
| Hand-written round-two sets in `data/hand_written/` (mine, MIT) | MIT | <!--v:val_hb_new-->132<!--/v--> hard-benign validation items and <!--v:hn_train_n-->115<!--/v--> hard-negative training items (repeated <!--v:hn_repeat-->4)<!--/v--> times in training); the v2 test sets (<!--v:hb_v2_n-->91<!--/v--> hard-benign, <!--v:att_v2_n-->30<!--/v--> plain attacks) are frozen test data |
| hendzh/PromptShield | Apache-2.0 (dataset card) | extra training data: a length-filtered sample (up to 2000 per class, at most 800 characters) of its train split |
| Lakera/gandalf_ignore_instructions | MIT (dataset card) | extra training data: attacks only, all three splits |
| Augmentation (`src/sentinel/augment.py`) | MIT (mine) | derived from the training rows only: obfuscated variants, attacks embedded in benign context, benign text quoting attacks |
| databricks-dolly-15k | CC-BY-SA-3.0 | benign validation and test only; not used for training |

Exact duplicates and near-duplicates (character n-gram TF-IDF cosine >= 0.9) between training data and any validation or test set were removed before training. Counts are in the training block below.

## Training

<!-- BEGIN:training -->
- **Shipped default: `microsoft/deberta-v3-xsmall`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 13730 training rows, 1737 validation rows; 6 epochs at most, lr 5e-05, batch 16, max length 256, seed 42; 2126 s of training.
  - epoch 1: train loss 0.228, validation PR-AUC 0.9938, ROC-AUC 0.9959
  - epoch 2: train loss 0.058, validation PR-AUC 0.9941, ROC-AUC 0.9967
  - epoch 3: train loss 0.031, validation PR-AUC 0.9960, ROC-AUC 0.9971
  - epoch 4: train loss 0.018, validation PR-AUC 0.9963, ROC-AUC 0.9975
  - epoch 5: train loss 0.008, validation PR-AUC 0.9947, ROC-AUC 0.9965
- **Compared: `sentence-transformers/all-MiniLM-L6-v2`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 13730 training rows, 1737 validation rows; 6 epochs at most, lr 8e-05, batch 16, max length 256, seed 42; 136 s of training.
  - epoch 1: train loss 0.225, validation PR-AUC 0.9911, ROC-AUC 0.9944
  - epoch 2: train loss 0.059, validation PR-AUC 0.9910, ROC-AUC 0.9944
  - epoch 3: train loss 0.028, validation PR-AUC 0.9952, ROC-AUC 0.9968
  - epoch 4: train loss 0.010, validation PR-AUC 0.9932, ROC-AUC 0.9955
  - epoch 5: train loss 0.005, validation PR-AUC 0.9930, ROC-AUC 0.9962
- Selection rule, fixed before the round-two models were trained: each model gets its `balanced` block threshold (validation hard-benign FPR at most 2%, everyday-benign at most 0.5%); the model with the best OOD-dev recall at that threshold is the default. See the selection table.
- CPU training time, **estimate** for `microsoft/deberta-v3-xsmall`: `scripts/bench_cpu_train.py` timed 12 real steps at 2.16 s/step with 3 threads (12 logical cores; system-wide CPU utilisation 23% just before the run), which extrapolates to about 150.9 minutes for 5 epochs (4185 steps), excluding validation passes. It is an extrapolation, and a busier machine is slower.
- CPU training time, **estimate** for `sentence-transformers/all-MiniLM-L6-v2`: `scripts/bench_cpu_train.py` timed 12 real steps at 0.85 s/step with 3 threads (12 logical cores; system-wide CPU utilisation 25% just before the run), which extrapolates to about 59.2 minutes for 5 epochs (4185 steps), excluding validation passes. It is an extrapolation, and a busier machine is slower.
- Split sizes after de-duplication: train 13385 (7966 attacks), train_base 5864 (3112 attacks), train_aug 7445 (4329 attacks), train_ext 10861 (6109 attacks), val 1737 (621 attacks), test_indist 1187 (562 attacks), test_deepset 660 (261 attacks), test_spml 597 (300 attacks), test_spml_dev 599 (300 attacks), test_hard_benign 60 (0 attacks), test_hard_benign_v2 91 (0 attacks), test_attacks_v2 30 (30 attacks), test_attacks 26 (26 attacks), test_obfuscated 53 (47 attacks), test_dolly_benign 992 (0 attacks), test_indirect 80 (60 attacks), test_hard_benign_dedup 30 (0 attacks).
<!-- END:training -->

Reproduce: `sentinel train` (uses a GPU if one is visible, otherwise the CPU; timings are above; GPU runs are not bit-for-bit repeatable, so expect small differences). The comparison model: `sentinel train --base sentence-transformers/all-MiniLM-L6-v2 --lr 8e-5 --out models/minilm`, then `sentinel eval --also models/minilm`.

## Evaluation

Thresholds are chosen on validation data only and the test sets are untouched until the final run.

<!-- BEGIN:thresholds -->
Chosen on the validation split only. Rule, fixed before the round-two models were trained: the block threshold is the lowest threshold whose validation false-positive rate is within the caps below on hard-benign text (n=151) and on everyday benign text; the flag threshold uses looser caps. `balanced` is the default; select another with the `SENTINEL_PRESET` environment variable or `Sentinel.load(preset=...)`.

| Preset | Block caps (hard-benign / everyday val FPR) | Flag caps | Block threshold | Flag threshold | Rules may block alone |
|---|---|---|---|---|---|
| strict | 1% / 0.5% | 5% / 2% | 0.977 | 0.619 | True |
| balanced (default) | 2% / 0.5% | 10% / 2% | 0.975 | 0.346 | True |
| permissive | 5% / 1% | 20% / 3% | 0.948 | 0.123 | True |
<!-- END:thresholds -->

<!-- BEGIN:headline -->
| Headline (Sentinel, block decision, `balanced` preset) | Value | 95% Wilson interval | Counts |
|---|---|---|---|
| False-positive rate, hard-benign **v2** (frozen, evaluated once) | 1.1% | 0.2% to 6.0% | 1 of 91 |
| False-positive rate, hard-benign v1 (60 items; seen once before re-selection) | 0.0% | 0.0% to 6.0% | 0 of 60 |
| False-positive rate, hard-benign v1 with templated near-duplicates removed | 0.0% | 0.0% to 11.4% | 0 of 30 |
| Recall on deepset/prompt-injections (out of distribution, untouched) | 53.6% | 47.6% to 59.6% | 140 of 261 |
| Recall on SPML OOD-test half | 54.3% | 48.7% to 59.9% | 163 of 300 |
| Recall on plain attacks v2 (frozen) | 96.7% | 83.3% to 99.4% | 29 of 30 |
| False-positive rate on everyday benign (Dolly-15k held out) | 0.1% | 0.0% to 0.6% | 1 of 992 |
| Recall on deepset counting a flag as a catch (flagged prompts still reach the model) | 72.4% | | n=261 attacks |
| In-distribution F1 (secondary; the training data is partly synthetic) | 0.965 | | n=1187 |
<!-- END:headline -->

Selection between the two encoders (validation and OOD-dev only):

<!-- BEGIN:ablation -->
| Model (round two, same training data) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | Balanced block threshold | OOD-dev recall at it | OOD-dev FPR | Val hard-benign FPR | Val everyday FPR | OOD-dev recall at 1% / 2% / 5% hard-benign val FPR | Selected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DeBERTa-v3-xsmall classifier | 13730 | 5 | 0.9950 | 0.9416 | 0.975 | 52.3% | 1.0% | 2.0% (n=151) | 0.0% | 51% / 52% / 67% | yes |
| MiniLM-L6 classifier | 13730 | 5 | 0.9950 | 0.9225 | 0.978 | 34.0% | 0.0% | 0.7% (n=151) | 0.3% | 38% / 39% / 50% |  |
<!-- END:ablation -->

The first model, round one and round two, same test splits ("not run" means that model was never scored on that set):

Round-one selection, for the record:

<!-- BEGIN:ablation_round1 -->
| Variant (round one; selection used validation + OOD-dev only) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | OOD-dev recall @ val 1% FPR | OOD-dev FPR | Val hard-benign FPR (19 items) |
|---|---|---|---|---|---|---|---|
| v1 (original data, 3 epochs, no dev selection) | 5864 | 3 | 0.9967 | 0.9346 | 29.0% | 0.0% | 0.0% |
| base data + early stop on dev | 5864 | 5 | 0.9949 | 0.9501 | 35.7% | 0.0% | 0.0% |
| base + augmentation | 7445 | 4 | 0.9930 | 0.9632 | 23.0% | 0.0% | 0.0% |
| base + extra public data | 10861 | 5 | 0.9964 | 0.9478 | 34.0% | 0.0% | 0.0% |
| base + augmentation + extra data | 13270 | 4 | 0.9952 | 0.9581 | 33.0% | 0.0% | 0.0% |
| base + augmentation + extra data, lr 5e-5 | 13270 | 6 | 0.9963 | 0.9373 | 31.0% | 0.0% | 0.0% |
| DeBERTa-v3-xsmall, augmentation + extra data | 13270 | 5 | 0.9955 | 0.9275 | 53.0% | 0.0% | 0.0% |
<!-- END:ablation_round1 -->

<!-- BEGIN:before_after -->
| Set | Recall (block): first model | round 1 | round 2 | Recall (flag or block): first | round 1 | round 2 |
|---|---|---|---|---|---|---|
| deepset (OOD, untouched) | 35.2% | 39.5% | 53.6% | 46.0% | 73.2% | 72.4% |
| SPML OOD-test | 40.0% | 54.7% | 54.3% | 50.3% | 67.3% | 70.3% |
| SPML OOD-dev (selection only) | 37.7% | 53.3% | 52.7% | 52.0% | 65.0% | 71.7% |
| In-distribution | 95.4% | 93.2% | 94.5% | 97.7% | 97.0% | 98.0% |
| Obfuscated | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Plain attacks v1 | 96.2% | 84.6% | 100.0% | 100.0% | 100.0% | 100.0% |
| Plain attacks v2 (frozen) | not run | 90.0% | 96.7% | not run | 96.7% | 96.7% |
| Indirect (SYNTHETIC) | 88.3% | 93.3% | 91.7% | 93.3% | 100.0% | 98.3% |

| Benign side | FPR (block): first model | round 1 | round 2 | n |
|---|---|---|---|---|
| Hard-benign v2 (frozen) | not run | 16.5% (15/91) | 1.1% (1/91) | 91 |
| Hard-benign v1 (seen once) | 1.7% (1/60) | 8.3% (5/60) | 0.0% (0/60) | 60 |
| Hard-benign v1, distinct items | not run | 10.0% (3/30) | 0.0% (0/30) | 30 |
| Everyday (Dolly-15k held out) | 0.3% (3/992) | 0.2% (2/992) | 0.1% (1/992) | 992 |
| SPML OOD-test benign | 0.0% (0/297) | 0.0% (0/297) | 0.0% (0/297) | 297 |
| deepset benign | 1.5% (6/399) | 1.0% (4/399) | 1.0% (4/399) | 399 |
<!-- END:before_after -->

Full per-set tables with intervals, for every system, are in the README and `docs/data/eval.json`. The indirect-injection set is synthetic and small.

<!-- BEGIN:language -->
| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |
|---|---|---|---|---|---|
| EN | 336 | 164 | 54.9% | 0.6% | 43.3% |
| DE | 233 | 85 | 44.7% | 1.4% | 35.3% |
<!-- END:language -->

Reproduce: `sentinel eval`, then `python scripts/render_docs.py`.

## Intended use

Screening text before it is sent to a language model, as one layer among several, with the decision (allow, flag, block) reviewed by an operator-defined policy. Blocks and flags are logged so false positives can be found and thresholds revisited.

## Limitations and risks

- It is not a security guarantee. Adaptive attackers, multi-turn attacks and unseen phrasings will get through, and the model has not been tested against any adversarial optimisation.
- Training data is overwhelmingly English; recall on German is measurably worse (table above). Other languages were not tested.
- Training data is partly synthetic, so in-distribution scores overstate real-world performance. Out-of-distribution recall and hard-benign false-positive rate are the numbers to trust more, and their intervals are wide because the test sets are small.
- It can over-block benign text that discusses injection or contains trigger words. Sentinel's decision layer reduces this by treating quoted or discussed examples as lower severity, but does not eliminate it.
- Fine-tuned on texts truncated to <!--v:max_len-->256<!--/v--> tokens; long documents rely on the windowing heuristic.
- The comparison with ProtectAI's public detector is zero-shot and was added after my model and thresholds were fixed; see the README for the table and its caveats (training-data overlap with `jackhhao/jailbreak-classification`, small sets).

## Licence

The code and my fine-tuned weights are MIT. Inherited terms: the base model and the Apache-2.0 datasets require attribution (given above); Dolly (CC-BY-SA) is used only for validation and testing, not training.
