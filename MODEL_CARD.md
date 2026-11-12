# Model card: Sentinel injection classifier

A binary classifier that outputs the probability that a text contains a prompt-injection or jailbreak attempt. It is one component of Sentinel; the rules engine and decision layer sit around it. The weights are not distributed: `sentinel train` produces them.

## Model

- **Base:** `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0, 22M parameters, 6 layers), loaded as a sequence-classification model with a freshly initialised two-class head.
- **Why not DeBERTa:** my first choice was `microsoft/deberta-v3-xsmall`, and the earlier training run used it. On the CPU I train on, which was shared with other jobs, a training step took well over 10 seconds, so a run was impractical. I stopped it and switched to MiniLM-L6, which was already in the local cache (no new download) and trains at roughly 4 seconds per step on the same loaded machine. I did not measure DeBERTa to convergence, so I cannot say how much accuracy the switch costs.
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
<!-- END:training -->

Reproduce: `sentinel train` (about the time above on 3 CPU threads; no GPU needed).

## Evaluation

Thresholds are chosen on validation data only and the test sets are untouched until the final run.

<!-- BEGIN:thresholds -->
<!-- END:thresholds -->

<!-- BEGIN:headline -->
<!-- END:headline -->

Full per-set tables with intervals, for every system, are in the README and `docs/data/eval.json`. The indirect-injection set is synthetic and small.

<!-- BEGIN:language -->
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
