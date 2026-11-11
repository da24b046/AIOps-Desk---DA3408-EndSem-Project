# Model card - candidate-001

## Intended use

Local educational decision support for IT-ticket category, priority and policy routing. The operator confirms the recommendation. The system does not diagnose root cause or perform remediation.

## Model and lineage

Separate balanced Logistic Regression pipelines use word TF-IDF (1-2 grams, max_features=5000, min_df=2), seed 42, max_iter=1000. Selected C is 2.0 for category and 0.5 for priority. Six bounded Ray trials selected settings using validation macro-F1; Ray parent run 43840ea679884553860e312d9dffea7b. Training uses 247 rows; validation/test use 81 each. The input is subject + description, not true category or priority.

The current serving capability is explanations-001 at artifacts/serving/candidate-001-explained. It contains the original candidate-001 fitted bytes, records their hashes and adds signed text explanations. Model version and policy remain candidate-001 / policy-001. See explained_model_package.json and the final evaluation plan for content hashes.

## Final held-out results

| Task | Accuracy | Macro-F1 | Majority macro-F1 |
| --- | --- | --- | --- |
| Category | 0.7778 | 0.7396 | 0.1811 |
| Priority | 0.8765 | 0.8742 | 0.3520 |

| Task / class | Test support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| category / Account | 14 | 0.6154 | 0.5714 | 0.5926 |
| category / Network | 12 | 0.8182 | 0.7500 | 0.7826 |
| category / Security | 9 | 0.8571 | 0.6667 | 0.7500 |
| category / Software | 46 | 0.8000 | 0.8696 | 0.8333 |
| priority / High | 37 | 0.9091 | 0.8108 | 0.8571 |
| priority / Medium | 44 | 0.8542 | 0.9318 | 0.8913 |

Category balanced accuracy 0.7144; priority balanced accuracy 0.8713. High-priority recall 0.8108. Log loss 0.6838 / 0.4892. Scores are not calibrated probabilities. Small synthetic class supports restrict interpretation.

The 0.60/0.60 review policy flags 58 of 81 tickets. The selected above-threshold subset has 23 rows, category accuracy 1.0000 and priority accuracy 0.8261; report this with its 28.4% coverage, never as whole-model accuracy.

## Explanations and known failure

Five signed TF-IDF contributions contrast the predicted class with the strongest alternative. They are associations in decision-score units. The intercept plus shown and omitted terms reconstruct the margin. Binary and multiclass numerical fixtures and 162 validation explanations were checked. The Wi-Fi example can predict Software rather than Network, with common terms influencing the result. An explanation makes that preference inspectable, not correct.

## Update and release policy

An approved synthetic category correction produced feedback-demo-001 trained on 248 category rows. Priority was copied unchanged. Validation macro-F1 did not improve. Promotion required operator_review feedback and >=0.001 improvement without accuracy regression; decision: keep_current_model. The separate switch/rollback exercise tested operations, not evidence of model improvement. No automatic retraining or deployment is enabled.

## Limitations

Synthetic source, limited vocabulary/domain, class imbalance, small held-out sample, no formal calibration/uncertainty estimates, no real-world outcome cohort and no protected-attribute fairness study. A changed input distribution is not proof of concept drift. Do not tune against the frozen test results. See limitations.md for system-wide scope.
