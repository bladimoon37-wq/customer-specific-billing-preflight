from app import *
from demo import GUIDE,BAD,FIXED,REPORT
p=RuleParser(); rules=p.draft(GUIDE,"guide.txt")
assert len(rules)==7
for r in rules:r.user_confirmed=True
eng=PreflightEngine(); before=eng.run(rules,[DocumentParser.parse_text("invoice.txt",BAD)])
assert any(x.status=="PROBLEM" and "PO" in x.rule for x in before)
assert any(x.status=="PROBLEM" and "Max Total" in x.rule for x in before)
assert any(x.status=="PROBLEM" and "Invoice within" in x.rule for x in before)
assert any(x.status=="PROBLEM" and "Required Attachment" in x.rule for x in before)
assert any(x.status=="UNABLE TO VERIFY" and "Signature" in x.rule for x in before)
after=eng.run(rules,[DocumentParser.parse_text("invoice.txt",FIXED),DocumentParser.parse_text("completion-report.txt",REPORT)])
c=compare(before,after)
assert c["after_problems"]==0, c
assert c["after_unable"]==0, c
assert c["gate"]=="CLEAR", c
assert c["before_problems"]>=4, c
# unconfirmed rules never silently pass
r=p.draft("PO Number: P1","g.txt")[0]
f=eng.run([r],[DocumentParser.parse_text("invoice.txt","PO Number: P1")])[0]
assert f.status=="UNABLE TO VERIFY"
# arithmetic mismatch
ar=eng.run([], [DocumentParser.parse_text("invoice.txt","Qty: 2\nUnit Price: 10\nSubtotal: 30\nTax: 0\nTotal: 30")])
assert ar[-1].status=="PROBLEM"
print("V0 SYNTHETIC TESTS PASS")

# regression: zero PROBLEM with unresolved evidence must remain NOT CLEAR
partial=eng.run(rules,[DocumentParser.parse_text("completion-report.txt",REPORT,role="invoice"),DocumentParser.parse_text("completion-report.txt",REPORT,role="support")])
pc=compare(before,partial)
assert pc["after_problems"]==0, pc
assert pc["after_unable"]>0, pc
assert pc["gate"]=="NOT CLEAR", pc
