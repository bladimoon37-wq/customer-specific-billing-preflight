from app import *
GUIDE='''Customer: ACME Facilities\nPO Number: PO-1831\nWO Number: WO-118\nSite ID: STORE-104\nRequired Attachment: completion-report\nMax Total: 750.00\nInvoice within 30 days of service\nSignature Required: yes'''
BAD='''Invoice: 4021\nPO Number: PO-1837\nWO Number: WO-118\nSite ID: STORE-104\nService Date: 2026-09-01\nInvoice Date: 2026-10-05\nQty: 2\nUnit Price: 400\nSubtotal: 800\nTax: 50\nTotal: 850'''
FIXED='''Invoice: 4021\nPO Number: PO-1831\nWO Number: WO-118\nSite ID: STORE-104\nService Date: 2026-09-10\nInvoice Date: 2026-10-05\nQty: 2\nUnit Price: 350\nSubtotal: 700\nTax: 50\nTotal: 750'''
REPORT='''Completion Report\nWO Number: WO-118\nSignature: J. Smith'''
p=RuleParser(); rules=p.draft(GUIDE,"ACME Billing Guide.txt")
for r in rules:r.user_confirmed=True
eng=PreflightEngine()
b=eng.run(rules,[DocumentParser.parse_text("invoice-4021.txt",BAD)])
a=eng.run(rules,[DocumentParser.parse_text("invoice-4021.txt",FIXED),DocumentParser.parse_text("completion-report.txt",REPORT)])
print(json.dumps({"rules":[asdict(x) for x in rules],"before":[asdict(x) for x in b],"after":[asdict(x) for x in a],"comparison":compare(b,a)},indent=2,ensure_ascii=False))
