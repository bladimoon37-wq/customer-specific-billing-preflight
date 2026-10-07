from io import BytesIO
from app import PDFParser, PDFExtractionError, RuleParser, PreflightEngine
try:
    from reportlab.pdfgen import canvas
except ImportError:
    canvas=None

def make_pdf(lines):
    if canvas is None: return None
    b=BytesIO(); c=canvas.Canvas(b); y=800
    for line in lines:
        c.drawString(60,y,line); y-=18
    c.save(); return b.getvalue()

if __name__=='__main__':
    if canvas is None:
        print('SKIP: reportlab unavailable for synthetic PDF fixture')
    else:
        guide=make_pdf(['PO Number: PO-1831','WO Number: WO-118','Site ID: STORE-104','Max Total: 750.00','Invoice within 30 days of service'])
        ex=PDFParser.extract_bytes('guide.pdf',guide)
        rules=RuleParser().draft(ex['text'],'guide.pdf')
        assert len(rules)==5, [(r.rule_type,r.expected) for r in rules]
        for r in rules: r.user_confirmed=True
        inv=make_pdf(['Invoice: 4021','PO Number: PO-1837','WO Number: WO-118','Site ID: STORE-104','Service Date: 2026-09-01','Invoice Date: 2026-10-05','Qty: 2','Unit Price: 400','Subtotal: 800','Tax: 50','Total: 850'])
        doc=PDFParser.parse_document('invoice.pdf',inv)
        findings=PreflightEngine().run(rules,[doc])
        assert any(f.status=='PROBLEM' and 'PO Number' in f.rule for f in findings)
        assert any(f.status=='PROBLEM' and 'Max Total' in f.rule for f in findings)
        print('PDF V0 TESTS PASS')
