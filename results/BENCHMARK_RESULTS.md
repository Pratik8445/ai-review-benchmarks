# Benchmark Results & Denominator Report

## 1. Provider-by-Case Coverage Matrix

| Provider | Case 01 | Case 02 | Case 03 | Case 04 | Case 05 | Case 06 | Case 07 | Case 08 | Completed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **proofline** | CAUGHT (TP) (+1 valid_extra) | CAUGHT (TP) (+1 valid_extra) | CAUGHT (TP) | MISSED (FN) + 2 FP | UNATTEMPTED | MISSED (FN) + 1 FP | NOISE (2 FP) | UNATTEMPTED | 6/8 |
| **coderabbit** | CAUGHT (TP) [non-blind] | CAUGHT (TP) [non-blind] | CAUGHT (TP) [non-blind] | CAUGHT (TP) [non-blind] | CAUGHT (TP) | CAUGHT (TP) [non-blind] | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | 6/8 |
| **greptile** | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | REQUESTED_NO_RESPONSE | 0/8 |
| **copilot** | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | 0/8 |

## 2. Accuracy & Denominator Summary (Completed Reviews Only)

| Provider | Completed Pairs | Strictly Isolated Pairs | Defects Caught (Recall) | Finding Precision (Strict) | Valid Extra Operational Warnings | Clean Control Pass Rate |
| --- | --- | --- | --- | --- | --- | --- |
| **proofline** | 6/8 | 6/6 | 3/5 (60.0%) | 3/8 (37.5%) | 2 | 0/1 |
| **coderabbit** | 6/8 | 1/6 | 6/6 (100.0%) | 6/6 (100.0%) | 0 | N/A |
| **greptile** | 0/8 | 0/0 | N/A | N/A (0 findings) | 0 | N/A |
| **copilot** | 0/8 | 0/0 | N/A | N/A (0 findings) | 0 | N/A |
