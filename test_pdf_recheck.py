from pathlib import Path
from app import PDFParser, RuleParser, PreflightEngine, compare

ROOT = Path(__file__).resolve().parent
PDFS = ROOT / "test_pdfs"


def load_pdf(filename: str, role: str | None = None):
    data = (PDFS / filename).read_bytes()
    return PDFParser.parse_document(filename, data, role=role)


if __name__ == "__main__":
    guide = PDFParser.extract_bytes(
        "ACME_Billing_Guide.pdf", (PDFS / "ACME_Billing_Guide.pdf").read_bytes()
    )
    rules = RuleParser().draft(guide["text"], "ACME_Billing_Guide.pdf")
    assert len(rules) == 7, [(r.rule_type, r.expected) for r in rules]
    for r in rules:
        r.user_confirmed = True

    engine = PreflightEngine()

    # Initial bad package: the invoice has 3 rule violations while the supporting
    # report is present and signed.
    before = engine.run(
        rules,
        [
            load_pdf("Invoice_4021_BAD.pdf", role="invoice"),
            load_pdf("Completion_Report.pdf", role="support"),
        ],
    )
    assert sum(f.status == "PROBLEM" for f in before) == 3, [
        (f.status, f.rule, f.observed) for f in before
    ]
    assert sum(f.status == "UNABLE TO VERIFY" for f in before) == 0, [
        (f.status, f.rule, f.observed) for f in before
    ]

    # Regression: 0 problems must NOT be treated as success when verification
    # is incomplete. A completion report placed in the invoice slot has no
    # invoice identifiers/totals/dates, so the result is NOT CLEAR.
    incomplete_after = engine.run(
        rules,
        [
            load_pdf("Completion_Report.pdf", role="invoice"),
            load_pdf("Completion_Report.pdf", role="support"),
        ],
    )
    incomplete = compare(before, incomplete_after)
    assert incomplete["after_problems"] == 0, incomplete
    assert incomplete["after_unable"] > 0, incomplete
    assert incomplete["gate"] == "NOT CLEAR", incomplete
    assert not incomplete["gate_clear"], incomplete
    assert incomplete["resolved"] == [], incomplete

    # Happy path: corrected invoice PDF + supporting PDF must each be parsed,
    # all rules verified, and only then may the gate be CLEAR.
    after = engine.run(
        rules,
        [
            load_pdf("Invoice_4021_FIXED.pdf", role="invoice"),
            load_pdf("Completion_Report.pdf", role="support"),
        ],
    )
    result = compare(before, after)
    assert result["after_problems"] == 0, result
    assert result["after_unable"] == 0, result
    assert result["gate"] == "CLEAR", result
    assert result["gate_clear"], result

    # Explicit role must work even when the filename itself does not contain
    # the word "invoice".
    renamed = PDFParser.parse_document(
        "corrected_4021.pdf",
        (PDFS / "Invoice_4021_FIXED.pdf").read_bytes(),
        role="invoice",
    )
    renamed_after = engine.run(
        rules,
        [renamed, load_pdf("Completion_Report.pdf", role="support")],
    )
    renamed_result = compare(before, renamed_after)
    assert renamed_result["gate"] == "CLEAR", renamed_result

    print("RECHECK SUMMARY REGRESSION PASS")
    print(
        "PDF RECHECK PACKAGE PASS:"
        f" after {result['after_problems']} problems /"
        f" {result['after_unable']} unable to verify"
    )
    print(f"Gate: {result['gate']}")
