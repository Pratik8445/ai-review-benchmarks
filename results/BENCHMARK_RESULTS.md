# Benchmark Results & Denominator Report

## 1. Provider-by-Case Coverage Matrix

| Provider | Case 01 | Case 02 | Case 03 | Case 04 | Case 05 | Case 06 | Case 07 | Case 08 | Completed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **proofline** | CAUGHT (TP) | CAUGHT (TP) | CAUGHT (TP) | MISSED (FN) + 2 FP | UNATTEMPTED | CAUGHT (TP) | NOISE (2 FP) | UNATTEMPTED | 6/8 |
| **coderabbit** | CAUGHT (TP) | CAUGHT (TP) | CAUGHT (TP) | CAUGHT (TP) | CAUGHT (TP) | CAUGHT (TP) | QUIET (TN) | QUIET (TN) | 8/8 |
| **greptile** | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | 0/8 |
| **copilot** | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | UNATTEMPTED | 0/8 |

## 2. Accuracy & Denominator Summary (Completed Reviews Only)

| Provider | Completed Pairs | Defects Caught (Recall) | Finding Precision | Clean Control Pass Rate |
| --- | --- | --- | --- | --- |
| **proofline** | 6/8 | 4/5 (80.0%) | 4/8 (50.0%) | 0/1 |
| **coderabbit** | 8/8 | 6/6 (100.0%) | 6/6 (100.0%) | 2/2 |
| **greptile** | 0/8 | N/A | N/A (0 findings) | N/A |
| **copilot** | 0/8 | N/A | N/A (0 findings) | N/A |
