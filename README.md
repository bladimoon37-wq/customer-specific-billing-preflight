# Customer-Specific Billing Preflight — V0 Small Bet

Local deterministic prototype for one customer rule set and one invoice package.

## V0 implemented
- Billing-guide text → rule draft with source line
- Explicit user confirmation gate
- PO / WO / Site checks
- Required attachment check
- Billing-date rule
- Total cap check
- Arithmetic check
- Signature presence check with conservative `UNABLE TO VERIFY`
- Evidence/fix fields
- Corrected-package recheck and before/after comparison
- Synthetic acceptance test

## Deliberately not implemented
Portal integrations, ERP/accounting integrations, submission bots, payment chasing, dashboards, auth/teams, automatic customer learning, signature authentication, or generalized document AI.

PDF parsing is intentionally limited to text-based PDFs through `pypdf`. Unreadable/unavailable evidence remains `UNABLE TO VERIFY`.

## Run
```bash
python test_v0.py
python demo.py
```

## Minimal browser UI
```bash
python web_ui.py
```
Opens a local-only browser workflow at `http://127.0.0.1:8765`:
Billing Guide → Rule Draft → Confirm/Edit → Preflight → Evidence → Correct → Recheck → Before/After.

The UI accepts either text input or text-based PDF uploads. Scanned/image-only PDFs remain out of scope for V0 and must not silently pass.

## PDF gate
This build adds local text-based PDF extraction with `pypdf` for Billing Guides, invoices, and one supporting document. No upload leaves the local machine/server process.

Install once:
```bash
python -m pip install -r requirements.txt
```

Run PDF regression test:
```bash
python test_pdf_v0.py
```

Scanned/image-only or otherwise unreadable PDFs are deliberately not OCR'd in V0. They return `UNABLE TO VERIFY`; the tool must not infer a clean result from unreadable evidence.

## Recheck fail-closed gate
A corrected package is shown as `Gate: CLEAR` only when both conditions are true:

```text
Problems: 0
Unable to verify: 0
```

`PROBLEM -> UNABLE TO VERIFY` is not counted as resolved. The browser summary shows both counts and the gate state.

Run the PDF recheck regression:
```bash
python test_pdf_recheck.py
```

Manual PDF fixtures are under `test_pdfs/`, including a corrected invoice for the final browser recheck.

## Manual browser acceptance path
Use the included `test_pdfs/` fixtures:

1. Billing Guide: `ACME_Billing_Guide.pdf`
2. Initial package: `Invoice_4021_BAD.pdf` + `Completion_Report.pdf`
3. Corrected package: `Invoice_4021_FIXED.pdf` + `Completion_Report.pdf`
4. Final expected summary: `After: 0 problems / 0 unable to verify` and `Gate: CLEAR`

Negative regression: putting `Completion_Report.pdf` in the corrected invoice slot produces zero `PROBLEM` findings but unresolved evidence, so the gate must remain `NOT CLEAR`.
