# PDF Gate FIXED — Recheck fail-closed patch

## Fixed
- Recheck now counts `UNABLE TO VERIFY` separately from `PROBLEM`.
- `Gate: CLEAR` is possible only when the result set is non-empty and both counts are zero.
- `PROBLEM -> UNABLE TO VERIFY` is no longer reported as resolved.
- Invoice/support documents are tagged by their upload role, so a corrected invoice does not depend on having the word `invoice` in its filename.
- Attachment filenames normalize separator/extension differences (`completion-report` matches `Completion_Report.pdf`).
- Browser messages identify Invoice vs Supporting PDF extraction.

## Regression coverage
- `0 problems + unresolved evidence -> Gate: NOT CLEAR`
- corrected invoice PDF + supporting PDF -> `0 problems / 0 unable to verify -> Gate: CLEAR`
- corrected invoice renamed without `invoice` in the filename still verifies by explicit input role.

## Included PDF fixtures
- `test_pdfs/ACME_Billing_Guide.pdf`
- `test_pdfs/Invoice_4021_BAD.pdf`
- `test_pdfs/Invoice_4021_FIXED.pdf`
- `test_pdfs/Completion_Report.pdf`
