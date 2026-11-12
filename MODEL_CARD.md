# Model card: Sentinel injection classifier

A binary classifier that outputs the probability that a text contains a prompt-injection or jailbreak attempt. It is one component of Sentinel; the rules engine and decision layer sit around it. The weights are not distributed: `sentinel train` produces them.

## Model

- **Base (default):** `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, 22M parameters, 6 layers), loaded as a sequence-classification model with a freshly initialised two-class head.
- **Compared:** `microsoft/deberta-v3-xsmall` (MIT), fine-tuned with the same data, max length (256), epochs (3), batch size and seed. DeBERTa used lr 5e-5 and MiniLM lr 8e-5 (the usual higher rate for a small model); I did not tune either.
- **Why MiniLM is the default:** it has the higher best-epoch PR-AUC on the validation split (numbers below), and trains roughly four times faster. The test sets were not used to choose. The gap is small and from one seed per model.
- **How this came about:** I had first planned DeBERTa alone. A CPU run of it was far too slow on a heavily loaded shared machine (a step took well over 10 seconds), so I stopped it, trained MiniLM on the CPU for a while, and then moved training to a GPU, where both fit easily. Training and inference choose `cuda` when available and fall back to the CPU (`--device` or `SENTINEL_DEVICE` to override).
- **Precision matters:** with the library versions here, DeBERTa's checkpoint loads in float16 by default and training in that dtype produced NaNs after the first optimiser step; the code now loads in float32 explicitly.
- **Input:** text after Sentinel's normaliser, truncated to 128 tokens at training time. At inference, longer inputs are scored in overlapping windows and the maximum is taken.
- **Output:** a logit margin, converted to a probability with temperature scaling fitted on the validation split.

## Training data

Downloaded by script at pinned revisions (`sentinel data`), never redistributed:

| Source | Licence | Use |
|---|---|---|
| neuralchemy/Prompt-injection-dataset | Apache-2.0 | train, validation, in-distribution test |
| jackhhao/jailbreak-classification | Apache-2.0 | train, validation, in-distribution test |
| Hand-written sets in `data/hand_written/` | MIT | train, validation, test (separate halves) |
| deepset/prompt-injections | Apache-2.0 | out-of-distribution test only |
| SPML Chatbot Prompt Injection | MIT | out-of-distribution test only |
| databricks-dolly-15k | CC-BY-SA-3.0 | benign validation and test only; not used for training |

Exact duplicates and near-duplicates (character n-gram TF-IDF cosine >= 0.9) between training data and any validation or test set were removed before training. Counts are in the training block below.

## Training

<!-- BEGIN:training -->
- **Shipped default: `sentence-transformers/all-MiniLM-L6-v2`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 5864 training rows, 1605 validation rows; 3 epochs, lr 8e-05, batch 16, max length 256, seed 42; 92 s of training.
  - epoch 1: train loss 0.210, validation PR-AUC 0.9940, ROC-AUC 0.9960
  - epoch 2: train loss 0.058, validation PR-AUC 0.9971, ROC-AUC 0.9978
  - epoch 3: train loss 0.017, validation PR-AUC 0.9972, ROC-AUC 0.9977
- **Compared: `microsoft/deberta-v3-xsmall`** on NVIDIA GeForce RTX 5060 Ti (cuda, float32): 5864 training rows, 1605 validation rows; 3 epochs, lr 5e-05, batch 16, max length 256, seed 42; 401 s of training.
  - epoch 1: train loss 0.249, validation PR-AUC 0.9926, ROC-AUC 0.9948
  - epoch 2: train loss 0.074, validation PR-AUC 0.9961, ROC-AUC 0.9973
  - epoch 3: train loss 0.039, validation PR-AUC 0.9959, ROC-AUC 0.9970
- Selection: best validation PR-AUC 0.9972 for the default against 0.9961 for the other encoder; the higher validation score is the default. Test sets played no part in the choice.
- CPU (estimate): `scripts/bench_cpu_train.py` timed 12 real steps of the default model at 0.66 s/step with 3 threads (12 logical cores; system-wide CPU utilisation 96% just before the run), which extrapolates to about 12.1 minutes for the 1101 steps of a full run, excluding validation passes. It is an extrapolation, and a busier machine is slower.
- Split sizes after de-duplication: train 5864 (3112 attacks), val 1605 (621 attacks), test_indist 1183 (557 attacks), test_deepset 660 (261 attacks), test_spml 1194 (600 attacks), test_hard_benign 60 (0 attacks), test_attacks 26 (26 attacks), test_obfuscated 50 (44 attacks), test_dolly_benign 992 (0 attacks), test_indirect 80 (60 attacks).
<!-- END:training -->

Reproduce: `sentinel train` (uses a GPU if one is visible, otherwise the CPU; timings are above). The comparison model: `sentinel train --base microsoft/deberta-v3-xsmall --lr 5e-5 --out models/deberta-xsmall`, then `sentinel eval --also models/deberta-xsmall`.

## Evaluation

Thresholds are chosen on validation data only and the test sets are untouched until the final run.

<!-- BEGIN:thresholds -->
Chosen on the validation split only (n=1605): block at calibrated score >= 0.976 (1% validation FPR), flag at >= 0.735 (3%), agreement threshold 0.035 (10%). Policy: {"t_flag": 0.735244019557478, "t_block": 0.9761312796253355, "t_agree": 0.03473527046480624, "rule_block_high": true}
<!-- END:thresholds -->

<!-- BEGIN:headline -->
| Headline (Sentinel, block decision) | Value | 95% Wilson interval | Counts |
|---|---|---|---|
| False-positive rate on hard-benign text (blocked / benign prompts that talk about injection) | 1.7% | 0.3% to 8.9% | 1 of 60 |
| Recall on deepset/prompt-injections (out of distribution) | 35.2% | 29.7% to 41.2% | 92 of 261 |
| Recall on SPML (out of distribution) | 38.8% | 35.0% to 42.8% | 233 of 600 |
| False-positive rate on everyday benign (Dolly-15k held out) | 0.3% | 0.1% to 0.9% | 3 of 992 |
| In-distribution F1 (secondary; the training data is partly synthetic) | 0.972 | | n=1183 |
<!-- END:headline -->

Full per-set tables with intervals, for every system, are in the README and `docs/data/eval.json`. The indirect-injection set is synthetic and small.

<!-- BEGIN:language -->
| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |
|---|---|---|---|---|---|
| EN | 336 | 164 | 34.1% | 1.7% | 25.6% |
| DE | 233 | 85 | 37.6% | 1.4% | 27.1% |
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
