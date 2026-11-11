# Dataset card

Source: https://huggingface.co/datasets/Console-AI/IT-helpdesk-synthetic-tickets

Publisher dataset ID: Console-AI/IT-helpdesk-synthetic-tickets. Declared license recorded at acquisition: mit. Revision: 165693849d955c6da4c00bc8be8e541afec0514e. Retrieved: 2026-11-10T13:32:25.031392+00:00. Raw bytes: 263690; raw rows: 500; SHA-256: 27ffa4446d557278a8e1922b8f639fb9d104c13676c18927793e52e3f45c0151.

This is a synthetic IT-helpdesk dataset. The blueprint originally proposed a larger different source; the project deliberately selected this small dataset for learning and local resource limits. The source manifest is data/metadata/source.json. Preserve its license attribution when sharing the dataset; no new project-code license is inferred from the dataset license.

Preparation retained 409 rows and excluded 91: 88 unsupported-category records and 3 unsupported-priority records after category filtering. Original retained labels were preserved. The exclusion CSV and reports/data_preparation.json record this decision.

| Category | Retained rows |
| --- | --- |
| Network | 66 |
| Software | 230 |
| Account | 71 |
| Security | 42 |

| Priority | Retained rows |
| --- | --- |
| Medium | 227 |
| High | 182 |

Model inputs are subject and description. Requester email, source ID/timestamps, labels and split metadata are not model features. Serving normalizes whitespace and redacts email strings. Metadata is preserved for provenance, not used to fabricate chronological evaluation.

Seed 42 grouped splitting retained 247/81/81 train/validation/test rows. Similarity grouping used description token-set Jaccard >=0.85; exact IDs and detected groups are disjoint. The source is small, imbalanced and synthetic, and the similarity detector cannot identify every semantic paraphrase. Account and Security test supports are only 14 and 9. Human-created demonstrations and load-check records are not independent test data.

Frozen test data was evaluated after parameter/policy selection; see final_test_evaluation.json. Approved feedback snapshots are separate from raw observations. The retraining demonstration used synthetic_demo labels and was blocked from quality promotion.
