from __future__ import annotations
import html, io, os, threading, time, uuid
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from app import RuleParser, DocumentParser, PDFParser, PDFExtractionError, PreflightEngine, compare

HOST=os.getenv('HOST','0.0.0.0'); PORT=int(os.getenv('PORT','8765'))
MAX_UPLOAD_BYTES=int(os.getenv('MAX_UPLOAD_BYTES', str(12*1024*1024)))
SESSIONS={}
SESSIONS_LOCK=threading.Lock()
SESSION_TTL=2*60*60

def _prune_sessions():
    now=time.time()
    with SESSIONS_LOCK:
        stale=[k for k,v in SESSIONS.items() if now-v.get('_ts',now)>SESSION_TTL]
        for k in stale: SESSIONS.pop(k,None)

def _session(handler):
    _prune_sessions()
    cookie=handler.headers.get('Cookie','')
    sid=None
    for item in cookie.split(';'):
        item=item.strip()
        if item.startswith('bp_session='):
            sid=item.split('=',1)[1].strip()
            break
    if not sid or sid not in SESSIONS:
        sid=uuid.uuid4().hex
        with SESSIONS_LOCK:
            SESSIONS[sid]={'rules':[], 'before':[], 'after':[], '_ts':time.time()}
        handler._new_session_cookie=f'bp_session={sid}; Path=/; HttpOnly; SameSite=Lax'
    state=SESSIONS[sid]
    state['_ts']=time.time()
    return state

def esc(v): return html.escape(str(v or ''))
def page(body,msg=''):
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Billing Preflight V0</title><style>
*{{box-sizing:border-box}}body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f6f8fb;color:#111827;margin:0;line-height:1.5}}main{{max-width:1180px;margin:34px auto;padding:0 22px 48px}}h1{{font-size:32px;line-height:1.2;margin:0 0 6px;color:#0f172a;letter-spacing:-.4px}}h2{{font-size:21px;color:#0f172a;margin:0 0 16px}}label{{display:block;font-weight:700;color:#24324a;margin:4px 0 6px}}.card{{background:#fff;border:1px solid #d7e0ea;border-radius:14px;padding:22px;margin:18px 0;box-shadow:0 2px 8px rgba(15,23,42,.05)}}textarea,input{{width:100%;padding:12px 13px;border:1.5px solid #aebdcd;border-radius:8px;background:#fff;color:#111827;font-size:15px;outline:none}}textarea{{min-height:145px;resize:vertical}}textarea:focus,input:focus{{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.13)}}button{{padding:12px 18px;background:#155eef;color:#fff;border:0;border-radius:8px;font-size:15px;font-weight:800;cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,.08)}}button:hover{{background:#0b4ed1}}a{{color:#0b57d0;font-weight:700;text-decoration:none}}a:hover{{text-decoration:underline}}table{{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;border:1px solid #d8e0e8;border-radius:10px;overflow:hidden}}th{{background:#172033;color:#fff;font-size:13px;letter-spacing:.15px;padding:12px 11px;text-align:left;vertical-align:top;border-bottom:1px solid #172033}}td{{text-align:left;vertical-align:top;border-bottom:1px solid #e5eaf0;padding:12px 11px;color:#253247}}tr:nth-child(even) td{{background:#f8fafc}}tr:last-child td{{border-bottom:0}}tr:hover td{{background:#f1f5f9}}.problem,.ok,.unable{{font-weight:800}}td.problem,td.ok,td.unable{{width:128px}}td.problem{{color:#991b1b;background:#fff7f7}}td.ok{{color:#166534;background:#f3fff7}}td.unable{{color:#92400e;background:#fffaf0}}.status-badge{{display:inline-block;padding:5px 8px;border-radius:999px;font-size:12px;font-weight:900;line-height:1.15;border:1px solid currentColor}}.status-badge.problem{{color:#991b1b;background:#fee2e2}}.status-badge.ok{{color:#166534;background:#dcfce7}}.status-badge.unable{{color:#92400e;background:#fef3c7}}.gate-badge{{display:inline-block;padding:7px 12px;border-radius:999px;font-weight:900;border:1px solid currentColor}}.muted{{color:#607086}}.warn{{background:#fff9e8;border-color:#e6b94e}}.summary-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:10px 0 16px}}.summary-box{{border:1px solid #d8e0e8;border-radius:10px;padding:13px 14px;background:#f8fafc}}.summary-box small{{display:block;color:#607086;font-weight:700;margin-bottom:3px}}.summary-box strong{{font-size:18px;color:#111827}}.gate-clear{{background:#edfdf3;border-color:#86d7a0}}.gate-blocked{{background:#fff1f2;border-color:#f3a6ad}}@media(max-width:800px){{main{{padding:0 12px 30px}}h1{{font-size:26px}}.card{{padding:16px}}.summary-grid{{grid-template-columns:1fr}}table{{font-size:12px;display:block;overflow-x:auto;white-space:nowrap}}th,td{{padding:10px 8px}}}}
</style></head><body><main><h1>Customer-Specific Billing Preflight — V0</h1><p class="muted">PDF/Text preflight checker. No portal integration. No approval guarantee. Uploaded documents are processed in memory and are not intentionally persisted by this app.</p>{('<div class="card">'+esc(msg)+'</div>') if msg else ''}{body}</main></body></html>'''

def findings_table(findings):
    rows=''
    for f in findings:
        cls='problem' if f.status=='PROBLEM' else ('ok' if f.status=='NO PROBLEM FOUND' else 'unable')
        rows+=f'<tr><td class="{cls}"><span class="status-badge {cls}">{esc(f.status)}</span></td><td><b>{esc(f.rule)}</b></td><td>{esc(f.expected)}</td><td>{esc(f.observed)}</td><td>{esc(f.evidence_document)} — {esc(f.evidence_location)}</td><td>{esc(f.explanation)}<br><b>Fix:</b> {esc(f.suggested_fix_location)}</td></tr>'
    return '<table><tr><th>Status</th><th>Rule</th><th>Expected</th><th>Observed</th><th>Evidence</th><th>Explanation / Fix</th></tr>'+rows+'</table>'

HOME='''<div class="card"><h2>1. Billing Guide → Rule Draft</h2><form method="post" action="/draft" enctype="multipart/form-data"><label>Customer name</label><input name="customer" value="ACME Facilities"><br><br><label>Billing Guide PDF (optional)</label><input type="file" name="guide_pdf" accept="application/pdf,.pdf"><p class="muted">Text-based PDFs only. Image/scanned PDFs are not OCR'd and will be reported as UNABLE TO VERIFY.</p><label>Or Billing Guide text</label><textarea name="guide">Customer: ACME Facilities\nPO Number: PO-1831\nWO Number: WO-118\nSite ID: STORE-104\nRequired Attachment: completion-report\nMax Total: 750.00\nInvoice within 30 days of service\nSignature Required: yes</textarea><br><button>Draft rules</button></form></div>'''

def multipart(handler):
    ctype=handler.headers.get('Content-Type','')
    if 'multipart/form-data' not in ctype:
        n=int(handler.headers.get('Content-Length','0')); return {k:v[0] for k,v in parse_qs(handler.rfile.read(n).decode()).items()},{}
    raw=(f'Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n').encode()+handler.rfile.read(int(handler.headers.get('Content-Length','0')))
    msg=BytesParser(policy=default).parsebytes(raw); fields={}; files={}
    for part in msg.iter_parts():
        name=part.get_param('name',header='content-disposition'); filename=part.get_filename(); payload=part.get_payload(decode=True) or b''
        if filename: files[name]=(filename,payload)
        elif name: fields[name]=payload.decode(part.get_content_charset() or 'utf-8',errors='replace')
    return fields,files

def pdf_or_text(files, file_key, fields, text_key, default_name, role=None, label='PDF'):
    if file_key in files and files[file_key][1]:
        name,data=files[file_key]
        if not name.lower().endswith('.pdf'): raise PDFExtractionError('Only PDF is accepted in this upload field.')
        return PDFParser.parse_document(name,data,role=role), f'{label} extracted: {name}'
    text=fields.get(text_key,'')
    return DocumentParser.parse_text(default_name,text,role=role), f'{label} text input used.'

class H(BaseHTTPRequestHandler):
    def send_html(self,s,code=200):
        b=s.encode(); self.send_response(code); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.send_header('Referrer-Policy','no-referrer');
        if getattr(self,'_new_session_cookie',None): self.send_header('Set-Cookie',self._new_session_cookie)
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path=='/healthz':
            b=b'ok'; self.send_response(200); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(b))); self.end_headers(); return self.wfile.write(b)
        self.state=_session(self)
        return self.send_html(page(HOME)) if self.path=='/' else self.send_html(page('<div class="card">Not found</div>'),404)
    def do_POST(self):
        self.state=_session(self)
        try:
            n=int(self.headers.get('Content-Length','0') or 0)
            if n>MAX_UPLOAD_BYTES: return self.send_html(page(HOME,'Upload too large.'),413)
            d,files=multipart(self)
        except Exception as e: return self.send_html(page(HOME,f'Input error: {e}'),400)
        if self.path=='/draft':
            try:
                if 'guide_pdf' in files and files['guide_pdf'][1]:
                    name,data=files['guide_pdf']; ex=PDFParser.extract_bytes(name,data); guide=ex['text']; src=name; note=f'PDF extracted: {name} ({ex["readable_pages"]}/{ex["page_count"]} readable pages).'
                else: guide=d.get('guide',''); src='billing-guide.txt'; note='Text Billing Guide used.'
            except PDFExtractionError as e:
                return self.send_html(page(HOME,f'UNABLE TO VERIFY — Billing Guide PDF: {e}'))
            rules=RuleParser().draft(guide,src); self.state['rules']=rules
            rows=''.join(f'<tr><td>{esc(r.rule_id)}</td><td>{esc(r.rule_type)}</td><td><input name="expected_{i}" value="{esc(r.expected)}"></td><td>{esc(r.source_document)} — {esc(r.source_location)}</td><td><input type="checkbox" name="confirm_{i}" checked></td></tr>' for i,r in enumerate(rules))
            body=f'<div class="card"><h2>2. Confirm / edit rules</h2><form method="post" action="/confirm"><table><tr><th>ID</th><th>Type</th><th>Expected</th><th>Source</th><th>Confirm</th></tr>{rows}</table><br><button>Confirm rules</button></form></div>'
            return self.send_html(page(body,f'{note} {len(rules)} rule drafts created. Review before use.'))
        if self.path=='/confirm':
            for i,r in enumerate(self.state['rules']):
                raw=d.get(f'expected_{i}',r.expected)
                if r.rule_type=='MAX_DAYS_AFTER_SERVICE':
                    try: raw=int(raw)
                    except: pass
                elif r.rule_type=='SIGNATURE_REQUIRED': raw=str(raw).lower() in ('true','yes','1','required')
                r.expected=raw; r.user_confirmed=(d.get(f'confirm_{i}')=='on')
            sample='''Invoice: 4021\nPO Number: PO-1837\nWO Number: WO-118\nSite ID: STORE-104\nService Date: 2026-09-01\nInvoice Date: 2026-10-05\nQty: 2\nUnit Price: 400\nSubtotal: 800\nTax: 50\nTotal: 850'''
            body=f'''<div class="card"><h2>3. Preflight package</h2><form method="post" action="/preflight" enctype="multipart/form-data"><label>Invoice PDF (optional)</label><input type="file" name="invoice_pdf" accept="application/pdf,.pdf"><p class="muted">If a PDF is selected it is used instead of the text box.</p><label>Or Invoice text</label><textarea name="invoice">{esc(sample)}</textarea><br><label>Supporting PDF (optional)</label><input type="file" name="support_pdf" accept="application/pdf,.pdf"><br><br><label>Or supporting document filename</label><input name="support_name" placeholder="completion-report.txt"><br><br><label>Supporting document text</label><textarea name="support" placeholder="Completion Report&#10;WO Number: WO-118&#10;Signature: J. Smith"></textarea><br><button>Run preflight</button></form></div>'''
            return self.send_html(page(body,'Rules confirmed.'))
        if self.path in ('/preflight','/recheck'):
            try:
                docs=[]; notes=[]
                inv,note=pdf_or_text(files,'invoice_pdf',d,'invoice','invoice.txt',role='invoice',label='Invoice'); docs.append(inv); notes.append(note)
                if 'support_pdf' in files and files['support_pdf'][1]:
                    name,data=files['support_pdf']; docs.append(PDFParser.parse_document(name,data,role='support')); notes.append(f'Supporting PDF extracted: {name}')
                elif d.get('support_name') or d.get('support'):
                    docs.append(DocumentParser.parse_text(d.get('support_name') or 'support.txt',d.get('support',''),role='support'))
            except PDFExtractionError as e:
                body='<div class="card warn"><h2>UNABLE TO VERIFY</h2><p>'+esc(e)+'</p><p>No PASS/NO PROBLEM result was inferred from unreadable PDF content.</p></div><div class="card"><a href="/">Start over</a></div>'
                return self.send_html(page(body))
            if self.path=='/preflight':
                self.state['before']=PreflightEngine().run(self.state['rules'],docs)
                corrected='''Invoice: 4021\nPO Number: PO-1831\nWO Number: WO-118\nSite ID: STORE-104\nService Date: 2026-09-01\nInvoice Date: 2026-09-20\nQty: 2\nUnit Price: 300\nSubtotal: 600\nTax: 40\nTotal: 640'''
                corrected_support='''Completion Report\nWO Number: WO-118\nSite ID: STORE-104\nSignature: J. Smith'''
                body=f'''<div class="card"><h2>4. Findings</h2>{findings_table(self.state['before'])}</div><div class="card"><h2>5. Correct and recheck</h2><form method="post" action="/recheck" enctype="multipart/form-data"><label>Corrected invoice PDF (optional)</label><input type="file" name="invoice_pdf" accept="application/pdf,.pdf"><br><br><label>Or corrected invoice text</label><textarea name="invoice">{esc(corrected)}</textarea><br><label>Corrected supporting PDF (optional)</label><input type="file" name="support_pdf" accept="application/pdf,.pdf"><br><br><label>Or supporting document filename</label><input name="support_name" value="completion-report.txt"><br><br><label>Supporting document text</label><textarea name="support">{esc(corrected_support)}</textarea><br><button>Recheck corrected package</button></form></div>'''
                return self.send_html(page(body,' '.join(notes)))
            self.state['after']=PreflightEngine().run(self.state['rules'],docs); c=compare(self.state['before'],self.state['after'])
            gate_cls='ok' if c['gate_clear'] else 'problem'
            problem_names=', '.join(c['remaining_problems']) or 'None'
            unable_names=', '.join(c['unable_rules']) or 'None'
            gate_box='gate-clear' if c['gate_clear'] else 'gate-blocked'
            body=f'''<div class="card"><h2>6. Recheck — Before / After</h2>
            <div class="summary-grid">
              <div class="summary-box"><small>BEFORE</small><strong>{c['before_problems']} problems / {c['before_unable']} unable</strong></div>
              <div class="summary-box"><small>AFTER</small><strong>{c['after_problems']} problems / {c['after_unable']} unable</strong></div>
              <div class="summary-box {gate_box}"><small>GATE</small><span class="gate-badge {gate_cls}">{c['gate']}</span></div>
            </div>
            <p><b>Resolved:</b> {esc(', '.join(c['resolved']) or 'None')}<br>
            <b>Remaining problems:</b> {esc(problem_names)}<br>
            <b>Unable to verify:</b> {esc(unable_names)}</p></div>
            <div class="card">{findings_table(self.state['after'])}</div><div class="card"><a href="/">Start over</a></div>'''
            return self.send_html(page(body,' '.join(notes)))
        return self.send_html(page('<div class="card">Not found</div>'),404)
    def log_message(self,*args): pass

if __name__=='__main__':
    print(f'Billing Preflight V0 listening on {HOST}:{PORT}')
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()
