# Sentinel: full results

Everything on this page is generated from `docs/data/eval.json` (and the other files in `docs/data/`) by `scripts/render_docs.py`, and `python scripts/render_docs.py --check` fails if it drifts. The headline figures, the presets and the comparison with ProtectAI's public detector are in the [README](../README.md#results); how each number was produced and what it does not show is stated there and in [Limitations](../README.md#limitations).

## By test set and system

Recall and false-positive rate carry 95% Wilson intervals (in brackets). "Sentinel" is the full pipeline's `block` decision.

<!-- BEGIN:per_set -->
| Test set | n (attacks / benign) | System | Recall (block) | Recall (flag or block) | FPR (block) | F1 | ROC-AUC |
|---|---|---|---|---|---|---|---|
| In-distribution test (neuralchemy + jackhhao) | 1187 (562 / 625) | Rules only | 9.1% [7.0, 11.7] | 28.1% | 0.0% [0.0, 0.6] | 0.166 | n/a |
|  |  | TF-IDF + logistic regression | 89.0% [86.1, 91.3] | - | 0.6% [0.2, 1.6] | 0.938 | 0.994 |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 88.4% [85.5, 90.8] | - | 2.4% [1.5, 3.9] | 0.926 | 0.985 |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 49.8% [45.7, 53.9] | - | 0.0% [0.0, 0.6] | 0.665 | 0.985 |
|  |  | MiniLM-L6 classifier | 92.2% [89.7, 94.1] | - | 1.0% [0.4, 2.1] | 0.954 | 0.995 |
|  |  | DeBERTa-v3-xsmall classifier (default) | 94.3% [92.1, 95.9] | - | 1.1% [0.5, 2.3] | 0.965 | 0.994 |
|  |  | Sentinel (rules + classifier + decision) | 94.5% [92.3, 96.1] | 98.0% | 1.1% [0.5, 2.3] | 0.965 | 0.994 |
| deepset/prompt-injections (OOD, EN+DE) | 660 (261 / 399) | Rules only | 17.6% [13.5, 22.7] | 18.0% | 0.0% [0.0, 1.0] | 0.300 | n/a |
|  |  | TF-IDF + logistic regression | 17.6% [13.5, 22.7] | - | 0.0% [0.0, 1.0] | 0.300 | 0.741 |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 41.0% [35.2, 47.1] | - | 1.0% [0.4, 2.5] | 0.575 | 0.881 |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 7.7% [5.0, 11.5] | - | 0.0% [0.0, 1.0] | 0.142 | 0.881 |
|  |  | MiniLM-L6 classifier | 34.1% [28.6, 40.0] | - | 4.5% [2.9, 7.0] | 0.484 | 0.813 |
|  |  | DeBERTa-v3-xsmall classifier (default) | 43.3% [37.4, 49.4] | - | 1.0% [0.4, 2.5] | 0.598 | 0.889 |
|  |  | Sentinel (rules + classifier + decision) | 53.6% [47.6, 59.6] | 72.4% | 1.0% [0.4, 2.5] | 0.691 | 0.889 |
| SPML OOD-test half | 597 (300 / 297) | Rules only | 17.7% [13.8, 22.4] | 21.0% | 0.0% [0.0, 1.3] | 0.300 | n/a |
|  |  | TF-IDF + logistic regression | 10.7% [7.7, 14.7] | - | 0.0% [0.0, 1.3] | 0.193 | 0.771 |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 99.3% [97.6, 99.8] | - | 8.1% [5.5, 11.7] | 0.958 | 0.997 |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 86.7% [82.4, 90.1] | - | 0.0% [0.0, 1.3] | 0.929 | 0.997 |
|  |  | MiniLM-L6 classifier | 35.3% [30.1, 40.9] | - | 0.0% [0.0, 1.3] | 0.522 | 0.900 |
|  |  | DeBERTa-v3-xsmall classifier (default) | 54.3% [48.7, 59.9] | - | 0.0% [0.0, 1.3] | 0.704 | 0.946 |
|  |  | Sentinel (rules + classifier + decision) | 54.3% [48.7, 59.9] | 70.3% | 0.0% [0.0, 1.3] | 0.704 | 0.946 |
| Hard-benign v2 (frozen before the round-two models were run) | 91 (0 / 91) | Rules only | n/a | - | 0.0% [0.0, 4.1] | n/a | n/a |
|  |  | TF-IDF + logistic regression | n/a | - | 5.5% [2.4, 12.2] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | n/a | - | 37.4% [28.1, 47.6] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | n/a | - | 4.4% [1.7, 10.8] | n/a | n/a |
|  |  | MiniLM-L6 classifier | n/a | - | 3.3% [1.1, 9.2] | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | n/a | - | 1.1% [0.2, 6.0] | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | n/a | - | 1.1% [0.2, 6.0] | n/a | n/a |
| Hard-benign v1 (looked at once before the round-two re-selection) | 60 (0 / 60) | Rules only | n/a | - | 0.0% [0.0, 6.0] | n/a | n/a |
|  |  | TF-IDF + logistic regression | n/a | - | 5.0% [1.7, 13.7] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | n/a | - | 21.7% [13.1, 33.6] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | n/a | - | 1.7% [0.3, 8.9] | n/a | n/a |
|  |  | MiniLM-L6 classifier | n/a | - | 1.7% [0.3, 8.9] | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | n/a | - | 0.0% [0.0, 6.0] | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | n/a | - | 0.0% [0.0, 6.0] | n/a | n/a |
| Hard-benign v1, templated near-duplicates removed | 30 (0 / 30) | Rules only | n/a | - | 0.0% [0.0, 11.4] | n/a | n/a |
|  |  | TF-IDF + logistic regression | n/a | - | 6.7% [1.8, 21.3] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | n/a | - | 23.3% [11.8, 40.9] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | n/a | - | 3.3% [0.6, 16.7] | n/a | n/a |
|  |  | MiniLM-L6 classifier | n/a | - | 0.0% [0.0, 11.4] | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | n/a | - | 0.0% [0.0, 11.4] | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | n/a | - | 0.0% [0.0, 11.4] | n/a | n/a |
| Obfuscated attacks and benign | 53 (47 / 6) | Rules only | 68.1% [53.8, 79.6] | 89.4% | 0.0% [0.0, 39.0] | 0.810 | n/a |
|  |  | TF-IDF + logistic regression | 97.9% [88.9, 99.6] | - | 16.7% [3.0, 56.4] | 0.979 | 0.975 |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 83.0% [69.9, 91.1] | - | 50.0% [18.8, 81.2] | 0.876 | 0.826 |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 29.8% [18.7, 44.0] | - | 0.0% [0.0, 39.0] | 0.459 | 0.826 |
|  |  | MiniLM-L6 classifier | 100.0% [92.4, 100.0] | - | 16.7% [3.0, 56.4] | 0.989 | 0.961 |
|  |  | DeBERTa-v3-xsmall classifier (default) | 100.0% [92.4, 100.0] | - | 33.3% [9.7, 70.0] | 0.979 | 0.922 |
|  |  | Sentinel (rules + classifier + decision) | 100.0% [92.4, 100.0] | 100.0% | 33.3% [9.7, 70.0] | 0.979 | 0.922 |
| Plain attacks v1 (hand-written; informed the round-two rule fixes) | 26 (26 / 0) | Rules only | 50.0% [32.1, 67.9] | 69.2% | n/a | n/a | n/a |
|  |  | TF-IDF + logistic regression | 69.2% [50.0, 83.5] | - | n/a | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 84.6% [66.5, 93.9] | - | n/a | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 61.5% [42.5, 77.6] | - | n/a | n/a | n/a |
|  |  | MiniLM-L6 classifier | 92.3% [75.9, 97.9] | - | n/a | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | 92.3% [75.9, 97.9] | - | n/a | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | 100.0% [87.1, 100.0] | 100.0% | n/a | n/a | n/a |
| Plain attacks v2 (hand-written, frozen beforehand) | 30 (30 / 0) | Rules only | 26.7% [14.2, 44.4] | 33.3% | n/a | n/a | n/a |
|  |  | TF-IDF + logistic regression | 80.0% [62.7, 90.5] | - | n/a | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 100.0% [88.6, 100.0] | - | n/a | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 56.7% [39.2, 72.6] | - | n/a | n/a | n/a |
|  |  | MiniLM-L6 classifier | 90.0% [74.4, 96.5] | - | n/a | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | 96.7% [83.3, 99.4] | - | n/a | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | 96.7% [83.3, 99.4] | 96.7% | n/a | n/a | n/a |
| Everyday benign (Dolly-15k held out) | 992 (0 / 992) | Rules only | n/a | - | 0.0% [0.0, 0.4] | n/a | n/a |
|  |  | TF-IDF + logistic regression | n/a | - | 0.0% [0.0, 0.4] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | n/a | - | 0.0% [0.0, 0.4] | n/a | n/a |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | n/a | - | 0.0% [0.0, 0.4] | n/a | n/a |
|  |  | MiniLM-L6 classifier | n/a | - | 0.5% [0.2, 1.2] | n/a | n/a |
|  |  | DeBERTa-v3-xsmall classifier (default) | n/a | - | 0.0% [0.0, 0.4] | n/a | n/a |
|  |  | Sentinel (rules + classifier + decision) | n/a | - | 0.1% [0.0, 0.6] | n/a | n/a |
| Indirect injection in documents (SYNTHETIC) | 80 (60 / 20) | Rules only | 76.7% [64.6, 85.6] | 91.7% | 0.0% [0.0, 16.1] | 0.868 | n/a |
|  |  | TF-IDF + logistic regression | 36.7% [25.6, 49.3] | - | 5.0% [0.9, 23.6] | 0.530 | 0.849 |
|  |  | ProtectAI v2 zero-shot (threshold 0.5) | 80.0% [68.2, 88.2] | - | 5.0% [0.9, 23.6] | 0.881 | 0.962 |
|  |  | ProtectAI v2 zero-shot (balanced-target threshold) | 31.7% [21.3, 44.2] | - | 0.0% [0.0, 16.1] | 0.481 | 0.962 |
|  |  | MiniLM-L6 classifier | 63.3% [50.7, 74.4] | - | 5.0% [0.9, 23.6] | 0.768 | 0.932 |
|  |  | DeBERTa-v3-xsmall classifier (default) | 46.7% [34.6, 59.1] | - | 5.0% [0.9, 23.6] | 0.629 | 0.886 |
|  |  | Sentinel (rules + classifier + decision) | 91.7% [81.9, 96.4] | 98.3% | 5.0% [0.9, 23.6] | 0.948 | 0.886 |
<!-- END:per_set -->

The indirect-injection set (documents and tool outputs containing planted instructions) is **synthetic and small**, written by me; read its numbers as a smoke test, not a benchmark.

## How the model got here

**Round one: out-of-distribution recall.** My first model caught only <!--v:first_ood_range-->35 to 40%<!--/v--> of attacks from datasets it had never seen. I added augmentation (`src/sentinel/augment.py`: re-cased, re-punctuated, leetspeak, zero-width, homoglyph, spaced and base64 variants of attacks, attacks embedded in benign context, and benign text quoting attacks), two extra public datasets (PromptShield, Apache-2.0, a length-filtered sample; Lakera Gandalf, MIT, attacks only) and early stopping on an OOD-dev half of SPML. deepset stayed untouched; SPML was split once by a fixed seed into the OOD-dev half (selection only) and an OOD-test half (reported). Variants, compared on validation and OOD-dev only (300 attacks, so a few points of difference is noise):

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

Round one improved recall, but its validation guard on hard-benign text had only <!--v:val_hb_old-->19<!--/v--> examples, and on the <!--v:hb_v1_n-->60<!--/v-->-item hard-benign test set the round-one model blocked <!--v:r1_v1_fpr-->8.3%<!--/v--> of benign prompts (<!--v:r1_v1_fp-->5<!--/v--> of <!--v:hb_v1_n-->60<!--/v-->; with templated near-duplicates removed, <!--v:r1_dedup_fp-->3<!--/v--> of <!--v:hb_v1_distinct_n-->30<!--/v--> distinct items). I rejected that model as the default.

**Round two: fix the guard, then re-select.**

- **A real hard-benign validation set.** I wrote <!--v:val_hb_new-->132<!--/v--> hand-written benign prompts that talk about, quote or mention injection (security questions, documentation and tutorial text, quoted attack strings inside analysis, classroom and policy text, code comments, support tickets, translation and summarisation requests that contain attack phrases as data, and ordinary uses of trigger words such as "bypass the cache"). Together with the 19 older ones the validation hard-benign set has <!--v:val_hb_total-->151<!--/v--> items. A separate <!--v:hn_train_n-->115<!--/v-->-item set of the same kind went into training as hard negatives (repeated <!--v:hn_repeat-->4<!--/v--> times in training). No item is a near-duplicate (word-set similarity of 0.8 or more) of an item in another of these sets (`tests/test_frozen_v2.py` checks this).
- **A rule fixed in advance.** The block threshold is the lowest threshold whose validation false-positive rate is at or below <!--v:cap_hb-->2%<!--/v--> on hard-benign text and <!--v:cap_dolly-->0.5%<!--/v--> on everyday benign text (Dolly validation). Among models, the one with the best OOD-dev recall at that threshold is the default. Presets `strict`, `balanced` (this rule) and `permissive` are in the thresholds file and selectable with `SENTINEL_PRESET`.
- **Fresh, frozen test sets.** Hard-benign v2 (<!--v:hb_v2_n-->91<!--/v--> items) and plain attacks v2 (<!--v:att_v2_n-->30<!--/v--> items) were written and frozen (SHA-256 in `data/hand_written/FROZEN_V2.json`, checked by a test) before any round-two model was trained or run, and evaluated once at the end. I also report v1 with its templated near-duplicates removed (<!--v:hb_v1_n-->60<!--/v--> items collapse to <!--v:hb_v1_distinct_n-->30<!--/v--> distinct ones).
- **A rules gap, found from the plain-attack drop.** Round one did not block <!--v:plain_r1_missed-->4<!--/v--> of the <!--v:att_v1_n-->26<!--/v--> plain attacks (<!--v:plain_r1_tp-->22<!--/v--> blocked, <!--v:plain_r1-->84.6%<!--/v-->; the first model blocked <!--v:plain_first_tp-->25<!--/v-->, <!--v:plain_first-->96.2%<!--/v-->): a "repeat the words above" leak, a "two answers, a normal one and a jailbroken one" request, "stop being X, your new job is to ...", and "the previous rules were a test, the real rule is ...". Each is an ordinary override or leak that the rules layer should catch whatever the classifier thinks, so I fixed the patterns, not the strings: a new `LEK-005`, `OVR-007` and `OVR-008`, and `JBK-003` raised to high severity, each with positive and negative tests. Because those 26 items informed the fixes they are no longer a clean number; plain attacks v2 is.

Selection among the round-two candidates (validation and OOD-dev only, nothing else consulted):

<!-- BEGIN:ablation -->
| Model (round two, same training data) | Train rows | Epochs run | Val PR-AUC | OOD-dev PR-AUC | Balanced block threshold | OOD-dev recall at it | OOD-dev FPR | Val hard-benign FPR | Val everyday FPR | OOD-dev recall at 1% / 2% / 5% hard-benign val FPR | Selected |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DeBERTa-v3-xsmall classifier | 13730 | 5 | 0.9950 | 0.9416 | 0.975 | 52.3% | 1.0% | 2.0% (n=151) | 0.0% | 51% / 52% / 67% | yes |
| MiniLM-L6 classifier | 13730 | 5 | 0.9950 | 0.9225 | 0.978 | 34.0% | 0.0% | 0.7% (n=151) | 0.3% | 38% / 39% / 50% |  |
<!-- END:ablation -->

The first model, round one as published, and round two, on the same current test splits ("not run" means that model was never scored on that set; round one was scored on the new sets afterwards with its published thresholds and the current rules, using `scripts/score_snapshot.py`):

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

**Honest reading.** Round two fixed what round one broke. Hard-benign false blocks went from <!--v:r1_v2_fpr-->16.5%<!--/v--> (<!--v:r1_v2_fp-->15<!--/v--> of <!--v:hb_v2_n-->91<!--/v-->) on the frozen v2 set for the round-one model to <!--v:r2_v2_fpr-->1.1%<!--/v--> (<!--v:r2_v2_fp-->1<!--/v--> of <!--v:hb_v2_n-->91<!--/v-->), out-of-distribution recall did not give back its round-one gain and rose on deepset, and the plain attacks the rules were missing are caught. The gains are measured on small sets, so read the intervals: v2 hard-benign has <!--v:hb_v2_n-->91<!--/v--> items and plain attacks v2 has <!--v:att_v2_n-->30<!--/v-->. Hard-benign v2 and v1 are written by the same person who wrote the validation and training hard negatives, so a shared style is likely; they are not independent of my taste. Recall at this operating point is still about half of the attacks that other datasets contain; counting a flag as a catch raises it to <!--v:deepset_flag-->72%<!--/v--> on deepset and <!--v:spml_flag-->70%<!--/v--> on SPML, but flagged prompts still reach the model.

### Operating curve

Each model's thresholds at <!--v:levels-->1%, 2% and 5%<!--/v--> false-positive rate on the validation hard-benign set, and what they do on every test set (classifier score only; the full pipeline also lets high-severity rules block, which is why its recall in the headline table is higher):

<!-- BEGIN:operating -->
| Model | Val hard-benign FPR | Threshold | Recall deepset | Recall SPML test | Recall in-dist | Recall plain v2 | Recall obfuscated | Recall indirect (synth.) | FPR hard v2 | FPR hard v1 | FPR v1 distinct | FPR everyday |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DeBERTa-v3-xsmall classifier (default) | 1% | 0.977 | 43% | 51% | 94% | 93% | 100% | 47% | 1.1% (1/91) | 0.0% (0/60) | 0.0% (0/30) | 0.0% (0/992) |
|  | 2% | 0.975 | 43% | 54% | 94% | 97% | 100% | 47% | 1.1% (1/91) | 0.0% (0/60) | 0.0% (0/30) | 0.0% (0/992) |
|  | 5% | 0.619 | 61% | 67% | 98% | 97% | 100% | 73% | 3.3% (3/91) | 10.0% (6/60) | 10.0% (3/30) | 1.0% (10/992) |
| MiniLM-L6 classifier | 1% | 0.969 | 42% | 39% | 94% | 90% | 100% | 75% | 4.4% (4/91) | 3.3% (2/60) | 3.3% (1/30) | 0.6% (6/992) |
|  | 2% | 0.961 | 46% | 40% | 94% | 93% | 100% | 78% | 5.5% (5/91) | 5.0% (3/60) | 6.7% (2/30) | 0.6% (6/992) |
|  | 5% | 0.696 | 58% | 49% | 96% | 93% | 100% | 88% | 8.8% (8/91) | 8.3% (5/60) | 10.0% (3/30) | 1.4% (14/992) |
| TF-IDF + logistic regression | 1% | 0.905 | 15% | 9% | 86% | 73% | 96% | 32% | 3.3% (3/91) | 0.0% (0/60) | 0.0% (0/30) | 0.0% (0/992) |
|  | 2% | 0.863 | 18% | 11% | 89% | 80% | 98% | 37% | 5.5% (5/91) | 5.0% (3/60) | 6.7% (2/30) | 0.0% (0/992) |
|  | 5% | 0.822 | 21% | 13% | 90% | 83% | 98% | 47% | 6.6% (6/91) | 8.3% (5/60) | 10.0% (3/30) | 0.2% (2/992) |
<!-- END:operating -->

## Multilingual

<!-- BEGIN:language -->
| deepset subset | n | attacks | Recall (Sentinel) | FPR (Sentinel) | Recall (classifier only) |
|---|---|---|---|---|---|
| EN | 336 | 164 | 54.9% | 0.6% | 43.3% |
| DE | 233 | 85 | 44.7% | 1.4% | 35.3% |
<!-- END:language -->

## Sanity checks against shortcuts

<!-- BEGIN:shortcuts -->
- Length-only logistic regression, ROC-AUC: indist 0.61, deepset 0.81, spml 0.99 (0.50 is chance).
- TF-IDF trained on shuffled labels, ROC-AUC: indist 0.54, deepset 0.53 (should be near 0.50).
<!-- END:shortcuts -->

## Thresholds

<!-- BEGIN:thresholds -->
Chosen on the validation split only. Rule, fixed before the round-two models were trained: the block threshold is the lowest threshold whose validation false-positive rate is within the caps below on hard-benign text (n=151) and on everyday benign text; the flag threshold uses looser caps. `balanced` is the default; select another with the `SENTINEL_PRESET` environment variable or `Sentinel.load(preset=...)`.

| Preset | Block caps (hard-benign / everyday val FPR) | Flag caps | Block threshold | Flag threshold | Rules may block alone |
|---|---|---|---|---|---|
| strict | 1% / 0.5% | 5% / 2% | 0.977 | 0.619 | True |
| balanced (default) | 2% / 0.5% | 10% / 2% | 0.975 | 0.346 | True |
| permissive | 5% / 1% | 20% / 3% | 0.948 | 0.123 | True |
<!-- END:thresholds -->

## Latency

<!-- BEGIN:latency -->
| Path | p50 (ms) | p95 (ms) |
|---|---|---|
| Rules only | 0.2 | 1.7 |
| Classifier, one prompt at a time | 37.6 | 70.0 |
| Full Sentinel, one prompt | 37.4 | 94.0 |
| TF-IDF + LR | 0.5 | 1.2 |

CPU, classifier in batches of 64: 66.7 ms per prompt. CPU figures: 3 torch threads, float32, system-wide CPU utilisation 5% just before the run. Busy machines inflate them: treat as an upper-bound ballpark unless the load is low.

GPU (cuda, float32) for comparison: classifier 14.1 ms p50 / 19.1 ms p95 per prompt, full Sentinel 14.5 / 31.2 ms, batches of 64: 2.1 ms per prompt.
<!-- END:latency -->

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
- Training rows: 13385 de-duplicated rows plus 115 hard-benign rows repeated 3 extra times (4 copies in total) gives 13730 training rows.
- Split sizes after de-duplication: train 13385 (7966 attacks), train_base 5864 (3112 attacks), train_aug 7445 (4329 attacks), train_ext 10861 (6109 attacks), val 1737 (621 attacks), test_indist 1187 (562 attacks), test_deepset 660 (261 attacks), test_spml 597 (300 attacks), test_spml_dev 599 (300 attacks), test_hard_benign 60 (0 attacks), test_hard_benign_v2 91 (0 attacks), test_attacks_v2 30 (30 attacks), test_attacks 26 (26 attacks), test_obfuscated 53 (47 attacks), test_dolly_benign 992 (0 attacks), test_indirect 80 (60 attacks), test_hard_benign_dedup 30 (0 attacks).
<!-- END:training -->

## Errors

<!-- BEGIN:errors -->
Across the reported test sets (OOD-dev and the de-duplicated v1 subset excluded), Sentinel blocked 16 benign prompts and let 174 attacks through without even a flag. Up to 60 examples of each are stored in `docs/data/eval.json` under `errors` (16 and 60 stored).
<!-- END:errors -->
