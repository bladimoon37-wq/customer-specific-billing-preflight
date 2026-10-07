from __future__ import annotations
import json, re, csv, io
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

STATUSES = {"PROBLEM", "NO PROBLEM FOUND", "UNABLE TO VERIFY"}

@dataclass
class Rule:
    rule_id: str
    rule_type: str
    description: str
    expected: Any
    source_document: str
    source_location: str
    rule_set_version: str = "v1"
    effective_date: str = ""
    user_confirmed: bool = False

@dataclass
class Finding:
    finding_id: str
    status: str
    rule: str
    expected: Any
    observed: Any
    evidence_document: str
    evidence_location: str
    explanation: str
    suggested_fix_location: str
    verification_state: str


def norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()

def doc_key(s: Any) -> str:
    """Normalize attachment labels/filenames without guessing document content."""
    raw=str(s or "").lower()
    # Ignore a final file extension and separator style differences such as
    # completion-report vs Completion_Report.pdf.
    raw=re.sub(r"\.[a-z0-9]{1,8}$", "", raw)
    return re.sub(r"[^a-z0-9]+", "", raw)

def money(v: Any):
    try: return Decimal(str(v).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, AttributeError): return None

def iso(v: str):
    try: return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception: return None

class RuleParser:
    """Deterministic V0 draft parser for a small, explicit billing-guide syntax."""
    PATTERNS = [
        ("PO_REQUIRED", r"(?:po|purchase order)\s*(?:number)?\s*[:=]\s*([A-Za-z0-9_-]+)"),
        ("WO_REQUIRED", r"(?:wo|work order)\s*(?:number)?\s*[:=]\s*([A-Za-z0-9_-]+)"),
        ("SITE_REQUIRED", r"(?:site|location)\s*(?:id)?\s*[:=]\s*([A-Za-z0-9_-]+)"),
        ("MAX_TOTAL", r"(?:max(?:imum)? total|cap|not exceed)\s*[:=$ ]+([0-9,.]+)"),
        ("REQUIRED_ATTACHMENT", r"required attachment\s*[:=]\s*(.+)"),
        ("SIGNATURE_REQUIRED", r"signature required\s*[:=]\s*(yes|true|required)"),
        ("MAX_DAYS_AFTER_SERVICE", r"invoice within\s*([0-9]+)\s*days"),
    ]
    def draft(self, text: str, source_document="billing-guide.txt") -> list[Rule]:
        out=[]; rid=1
        for ln, line in enumerate(text.splitlines(), 1):
            for typ, pat in self.PATTERNS:
                m=re.search(pat, line, re.I)
                if m:
                    val=m.group(1).strip()
                    if typ in {"SIGNATURE_REQUIRED"}: val=True
                    elif typ in {"MAX_DAYS_AFTER_SERVICE"}: val=int(val)
                    elif typ == "MAX_TOTAL": val=str(money(val))
                    out.append(Rule(f"R{rid:03}", typ, norm(line), val, source_document, f"line {ln}")); rid+=1
        return out

class DocumentParser:
    @staticmethod
    def parse_text(name: str, text: str, role: str | None = None) -> dict:
        fields={}
        pats={
            "po": r"(?:po|purchase order)\s*(?:number)?\s*[:=#-]\s*([A-Za-z0-9_-]+)",
            "wo": r"(?:wo|work order)\s*(?:number)?\s*[:=#-]\s*([A-Za-z0-9_-]+)",
            "site": r"(?:site|location)\s*(?:id)?\s*[:=#-]\s*([A-Za-z0-9_-]+)",
            "service_date": r"service date\s*[:=]\s*(\d{4}-\d{2}-\d{2})",
            "invoice_date": r"invoice date\s*[:=]\s*(\d{4}-\d{2}-\d{2})",
            "qty": r"qty\s*[:=]\s*([0-9.]+)",
            "unit_price": r"unit price\s*[:=$ ]+([0-9,.]+)",
            "subtotal": r"subtotal\s*[:=$ ]+([0-9,.]+)",
            "tax": r"tax\s*[:=$ ]+([0-9,.]+)",
            "total": r"(?m)^(?:invoice )?total\s*[:=$ ]+([0-9,.]+)\s*$",
            "signature": r"signature\s*[:=]\s*(.+)",
        }
        for k,p in pats.items():
            m=re.search(p,text,re.I); fields[k]=m.group(1).strip() if m else None
        return {"name":name,"text":text,"fields":fields,"role":role}

class PDFExtractionError(Exception):
    pass

class PDFParser:
    @staticmethod
    def extract_bytes(name: str, data: bytes) -> dict:
        """Extract text from a text-based PDF. Never OCRs or guesses unreadable pages."""
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise PDFExtractionError("pypdf is not installed. Run: python -m pip install pypdf") from e
        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as e:
            raise PDFExtractionError(f"PDF could not be opened: {e}") from e
        pages=[]
        for i, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append({"page": i, "text": text.strip()})
        readable=[p for p in pages if p["text"]]
        if not readable:
            raise PDFExtractionError("No readable text was extracted. Scanned/image-only PDFs are UNABLE TO VERIFY in V0.")
        joined="\n".join(p["text"] for p in readable)
        return {"name": name, "text": joined, "pages": pages, "readable_pages": len(readable), "page_count": len(pages)}

    @staticmethod
    def parse_document(name: str, data: bytes, role: str | None = None) -> dict:
        extracted=PDFParser.extract_bytes(name,data)
        doc=DocumentParser.parse_text(name, extracted["text"], role=role)
        doc["pages"]=extracted["pages"]
        doc["page_count"]=extracted["page_count"]
        doc["readable_pages"]=extracted["readable_pages"]
        return doc

class PreflightEngine:
    def run(self, rules: list[Rule], docs: list[dict]) -> list[Finding]:
        findings=[]
        # Prefer the explicit upload/input role. Filename matching remains as a
        # backwards-compatible fallback for direct engine callers.
        invoice=next((d for d in docs if d.get("role")=="invoice"), None)
        if invoice is None:
            invoice=next((d for d in docs if "invoice" in d["name"].lower()), None)
        def f(rule, status, obs, doc, loc, exp, msg, fix):
            findings.append(Finding(f"F{len(findings)+1:03}",status,rule.description,exp,obs,doc,loc,msg,fix,"verified" if status!="UNABLE TO VERIFY" else "insufficient evidence"))
        for r in rules:
            if not r.user_confirmed:
                f(r,"UNABLE TO VERIFY",None,r.source_document,r.source_location,r.expected,"Rule has not been confirmed by the user.","Confirm or edit this rule."); continue
            if r.rule_type in {"PO_REQUIRED","WO_REQUIRED","SITE_REQUIRED"}:
                key={"PO_REQUIRED":"po","WO_REQUIRED":"wo","SITE_REQUIRED":"site"}[r.rule_type]
                if not invoice or not invoice["fields"].get(key): f(r,"UNABLE TO VERIFY",None,invoice["name"] if invoice else "Invoice",key,r.expected,"Required identifier could not be read.",f"Verify {key.upper()} on the invoice.")
                else:
                    obs=invoice["fields"][key]; st="NO PROBLEM FOUND" if norm(obs).upper()==norm(r.expected).upper() else "PROBLEM"
                    f(r,st,obs,invoice["name"],key,r.expected,"Identifier matches the confirmed rule." if st!="PROBLEM" else "Identifier does not match the confirmed customer rule.",f"Verify {key.upper()} reference on the invoice.")
            elif r.rule_type=="REQUIRED_ATTACHMENT":
                expected_key=doc_key(r.expected)
                hit=next((d for d in docs if expected_key and expected_key in doc_key(d["name"])),None)
                f(r,"NO PROBLEM FOUND" if hit else "PROBLEM",hit["name"] if hit else "missing","package","file list",r.expected,"Required attachment is present." if hit else "Required attachment is missing.","Add the required supporting document.")
            elif r.rule_type=="MAX_TOTAL":
                obs=money(invoice["fields"].get("total")) if invoice else None; exp=money(r.expected)
                if obs is None or exp is None: f(r,"UNABLE TO VERIFY",None,invoice["name"] if invoice else "Invoice","total",r.expected,"Total or cap could not be read.","Verify invoice total and approved cap.")
                else: f(r,"PROBLEM" if obs>exp else "NO PROBLEM FOUND",str(obs),invoice["name"],"total",str(exp),"Invoice total exceeds the confirmed cap." if obs>exp else "Invoice total is within the confirmed cap.","Verify approved amount or invoice total.")
            elif r.rule_type=="MAX_DAYS_AFTER_SERVICE":
                sd=iso(invoice["fields"].get("service_date") or "") if invoice else None; idt=iso(invoice["fields"].get("invoice_date") or "") if invoice else None
                if not sd or not idt: f(r,"UNABLE TO VERIFY",None,invoice["name"] if invoice else "Invoice","dates",r.expected,"Required dates could not be read.","Verify service and invoice dates.")
                else:
                    days=(idt-sd).days; st="PROBLEM" if days<0 or days>int(r.expected) else "NO PROBLEM FOUND"
                    f(r,st,days,invoice["name"],"service_date/invoice_date",r.expected,"Invoice timing violates the confirmed rule." if st=="PROBLEM" else "Invoice timing is within the confirmed rule.","Verify invoice date.")
            elif r.rule_type=="SIGNATURE_REQUIRED":
                report=next((d for d in docs if d.get("role")=="support"),None)
                if report is None:
                    report=next((d for d in docs if "report" in d["name"].lower()),None)
                sig=report and norm(report["fields"].get("signature"))
                st="NO PROBLEM FOUND" if sig else "UNABLE TO VERIFY"
                f(r,st,sig or None,report["name"] if report else "Completion Report","signature",True,"A signature field is present." if sig else "A readable signature value was not provided; V0 does not authenticate signatures.","Verify the completion report signature manually.")
        # arithmetic is independent when fields are available
        if invoice:
            q=money(invoice["fields"].get("qty")); u=money(invoice["fields"].get("unit_price")); sub=money(invoice["fields"].get("subtotal")); tax=money(invoice["fields"].get("tax")); total=money(invoice["fields"].get("total"))
            if all(x is not None for x in (q,u,sub,tax,total)):
                calc=q*u; expected_total=sub+tax
                status="NO PROBLEM FOUND" if calc==sub and expected_total==total else "PROBLEM"
                findings.append(Finding(f"F{len(findings)+1:03}",status,"Arithmetic consistency",f"subtotal={calc}; total={expected_total}",f"subtotal={sub}; total={total}",invoice["name"],"qty/unit_price/subtotal/tax/total","Arithmetic is consistent." if status!="PROBLEM" else "Invoice arithmetic is inconsistent.","Verify line arithmetic and totals.","verified"))
        return findings


def compare(before:list[Finding], after:list[Finding]):
    b={x.rule:x for x in before}; a={x.rule:x for x in after}
    # A problem is resolved only when the same check is positively verified.
    # PROBLEM -> UNABLE TO VERIFY is not a resolution.
    resolved=[
        k for k,v in b.items()
        if v.status=="PROBLEM" and k in a and a[k].status=="NO PROBLEM FOUND"
    ]
    remaining_problems=[x.rule for x in after if x.status=="PROBLEM"]
    unable_rules=[x.rule for x in after if x.status=="UNABLE TO VERIFY"]
    before_problems=sum(x.status=="PROBLEM" for x in before)
    before_unable=sum(x.status=="UNABLE TO VERIFY" for x in before)
    after_problems=len(remaining_problems)
    after_unable=len(unable_rules)
    # Fail closed: only a non-empty result set with every finding positively
    # verified may be presented as CLEAR.
    gate_clear=bool(after) and after_problems==0 and after_unable==0
    return {
        "before_problems": before_problems,
        "before_unable": before_unable,
        "after_problems": after_problems,
        "after_unable": after_unable,
        "resolved": resolved,
        "remaining": remaining_problems,  # backwards compatibility
        "remaining_problems": remaining_problems,
        "unable_rules": unable_rules,
        "gate_clear": gate_clear,
        "gate": "CLEAR" if gate_clear else "NOT CLEAR",
    }

def save_json(path, data): Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
