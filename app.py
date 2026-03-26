"""
╔══════════════════════════════════════════════════════════╗
║  Checkgate — Streamlit App  (v3)                         ║
║                                                          ║
║  HOW CHECK-IN WORKS (no camera needed in browser):       ║
║  Each badge QR encodes a URL → your phone scanner app    ║
║  reads it → browser opens → check-in recorded instantly. ║
║                                                          ║
║  Tabs:                                                   ║
║    🎴 Card Generator  — upload CSV → PDF badges + QRs    ║
║    📋 Check-In        — URL auto-checkin + paste/manual  ║
║    📊 Attendance      — live dashboard + CSV export      ║
║    ⚙  Settings        — key, event, import participants  ║
╚══════════════════════════════════════════════════════════╝

Run locally:
  pip install -r requirements.txt
  streamlit run app.py

Deploy free (Streamlit Cloud):
  1. Push app.py + requirements.txt to a GitHub repo
  2. share.streamlit.io -> New app -> connect repo -> Deploy
  3. Share the URL, scan a badge QR, phone opens it, checked in
"""

import csv
import hashlib
import hmac as hmac_lib
import io
import json
import textwrap
import urllib.parse
import zipfile
from datetime import datetime

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

# ── Page config ──────────────────────────────────────────
st.set_page_config(
    page_title="Checkgate", page_icon="✦",
    layout="wide", initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,400&family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1.6rem;padding-bottom:2rem;}

.cg-hdr{background:linear-gradient(135deg,#16130f 0%,#2a2010 100%);border-radius:14px;
  padding:20px 28px;margin-bottom:22px;border:1px solid rgba(184,131,42,.25);
  display:flex;align-items:center;justify-content:space-between;}
.cg-logo{font-family:'Playfair Display',serif;font-size:24px;color:#faf8f4;}
.cg-logo em{color:#d4a855;font-style:italic;}
.cg-sub{font-size:11px;color:#9a8a78;letter-spacing:.1em;text-transform:uppercase;margin-top:3px;}

.stat-card{background:#1a2020;border:1px solid rgba(255,255,255,.08);border-radius:12px;
  padding:16px 20px;text-align:center;margin-bottom:4px;}
.stat-val{font-family:'DM Mono',monospace;font-size:34px;font-weight:500;line-height:1;}
.stat-lbl{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#546860;margin-top:4px;}
.sv-green{color:#36d97e;} .sv-amber{color:#f0b020;} .sv-blue{color:#60a5fa;}

.flash-ok {background:#0d2b1a;border:1px solid #1e6b3e;border-radius:12px;padding:16px 22px;margin:8px 0;}
.flash-dup{background:#2b2200;border:1px solid #6b5000;border-radius:12px;padding:16px 22px;margin:8px 0;}
.flash-err{background:#2b0d0d;border:1px solid #6b1e1e;border-radius:12px;padding:16px 22px;margin:8px 0;}
.flash-hd{display:flex;align-items:center;justify-content:space-between;}
.flash-nm{font-family:'Playfair Display',serif;font-size:20px;color:#faf8f4;}
.flash-sb{font-size:12px;color:#9aada0;margin-top:4px;}
.chip{border-radius:20px;padding:3px 11px;font-size:10px;font-weight:700;letter-spacing:.06em;}
.chip-ok {background:#36d97e;color:#06180c;}
.chip-dup{background:#f0b020;color:#180f00;}
.chip-err{background:#ff5f5f;color:#180606;}

.info-box{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.25);
  border-radius:10px;padding:14px 18px;font-size:13px;color:#93c5fd;line-height:1.7;}
.warn-box{background:rgba(240,176,32,.08);border:1px solid rgba(240,176,32,.25);
  border-radius:10px;padding:14px 18px;font-size:13px;color:#fcd34d;line-height:1.7;}
.ok-box  {background:rgba(54,217,126,.08);border:1px solid rgba(54,217,126,.25);
  border-radius:10px;padding:14px 18px;font-size:13px;color:#36d97e;line-height:1.7;}

.step-box{background:#1a2020;border:1px solid rgba(255,255,255,.08);
  border-radius:12px;padding:18px 22px;margin-bottom:12px;}
.step-num{display:inline-flex;align-items:center;justify-content:center;
  width:24px;height:24px;border-radius:50%;background:#b8832a;color:white;
  font-size:12px;font-weight:700;margin-right:8px;flex-shrink:0;}
.step-title{font-size:15px;font-weight:600;color:#faf8f4;}
.step-desc{font-size:12px;color:#9aada0;margin-top:6px;line-height:1.6;}

button[data-baseweb="tab"]{font-family:'DM Sans',sans-serif!important;
  font-size:14px!important;font-weight:500!important;}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────
def _init():
    for k, v in {
        "secret_key": "", "event_name": "Annual Event 2025",
        "app_url": "", "participants": {}, "checkins": {},
        "generated_cards": [], "last_result": None,
        "auto_checked": set(),
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()

# ── HMAC helpers ──────────────────────────────────────────
def hmac_sign(secret, msg):
    return hmac_lib.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

def make_sig(pid, name, email, event, secret):
    raw = json.dumps({"id":pid,"name":name,"email":email,"event":event},
                     separators=(",",":"), ensure_ascii=False)
    return hmac_sign(secret, raw)[:16]

def build_qr_url(pid, name, email, event, secret, base_url):
    sig    = make_sig(pid, name, email, event, secret)
    params = urllib.parse.urlencode({"id":pid,"name":name,"event":event,"sig":sig})
    return f"{base_url.rstrip('/')}/?{params}"

def build_qr_json(pid, name, email, event, secret):
    sig = make_sig(pid, name, email, event, secret)
    return json.dumps({"id":pid,"name":name,"event":event,"sig":sig},
                      separators=(",",":"), ensure_ascii=False)

def verify(pid, name, event, sig):
    secret = st.session_state.secret_key
    if not secret:
        return False
    email  = st.session_state.participants.get(pid, {}).get("email", "")
    return any(
        hmac_sign(secret, json.dumps({"id":pid,"name":name,"email":e,"event":event},
                                     separators=(",",":")))[:16] == sig
        for e in ([email, ""] if email else [""])
    )

# ── Check-in logic ────────────────────────────────────────
def do_checkin(pid, name, event, method="qr"):
    if pid in st.session_state.checkins:
        return "duplicate"
    p = st.session_state.participants.get(pid, {})
    st.session_state.checkins[pid] = {
        "id": pid, "name": p.get("name", name),
        "role": p.get("role",""), "org": p.get("org",""), "email": p.get("email",""),
        "event": event or st.session_state.event_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "method": method,
    }
    return "ok"

def process_raw(raw, method):
    raw = raw.strip()
    pid = name = event = sig = ""
    if raw.startswith("http"):
        try:
            qs    = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            pid   = qs.get("id",[""])[0]
            name  = qs.get("name",[""])[0]
            event = qs.get("event",[""])[0]
            sig   = qs.get("sig",[""])[0]
        except Exception:
            return {"ok":False,"reason":"Could not parse URL"}
    else:
        try:
            p     = json.loads(raw)
            pid   = p.get("id",""); name = p.get("name","")
            event = p.get("event",""); sig = p.get("sig","")
        except Exception:
            return {"ok":False,"reason":"Not a Checkgate QR — expected a URL or JSON"}

    if not all([pid, name, sig]):
        return {"ok":False,"reason":"QR is missing required fields"}
    if not st.session_state.secret_key:
        return {"ok":False,"reason":"No secret key — go to ⚙ Settings"}
    if not verify(pid, name, event, sig):
        return {"ok":False,"reason":"Signature invalid — wrong key or tampered QR"}

    status = do_checkin(pid, name, event, method=method)
    p = st.session_state.participants.get(pid, {})
    return {"ok":True,"status":status,"id":pid,
            "name":p.get("name",name),"role":p.get("role",""),"org":p.get("org","")}

# ── QR image ─────────────────────────────────────────────
def make_qr_image(data, size=200):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=1)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="#16130f", back_color="white")
    return img.resize((size,size), Image.LANCZOS)

# ── PDF card ─────────────────────────────────────────────
CARD_W, CARD_H = 148*mm, 105*mm
C_GOLD   = colors.HexColor("#b8832a")
C_FOREST = colors.HexColor("#3d7259")
C_PAPER  = colors.HexColor("#faf8f4")
C_PAPER2 = colors.HexColor("#f0ebe0")
C_INK3   = colors.HexColor("#8a7a6e")

def draw_card(c, p, event_name):
    w, h = CARD_W, CARD_H
    c.setFillColor(colors.white)
    c.roundRect(0,0,w,h,radius=3*mm,fill=1,stroke=0)
    bw = 7
    c.setFillColor(C_GOLD)
    c.roundRect(0,0,bw,h,radius=2*mm,fill=1,stroke=0)
    c.rect(bw//2,0,bw//2,h,fill=1,stroke=0)
    qcw = 42*mm; qx = w-qcw
    c.setFillColor(C_PAPER); c.rect(qx,0,qcw,h,fill=1,stroke=0)
    c.setStrokeColor(C_PAPER2); c.setLineWidth(0.5); c.line(qx,3*mm,qx,h-3*mm)
    mx = bw+4*mm
    c.setFillColor(C_GOLD); c.setFont("Helvetica",6.5)
    c.drawString(mx,h-10*mm,event_name.upper())
    name = p.get("name",""); fsz = 20 if len(name)<=20 else 16
    c.setFillColor(colors.HexColor("#16130f")); c.setFont("Helvetica-Bold",fsz)
    y = h-20*mm
    for line in textwrap.wrap(name,22)[:2]:
        c.drawString(mx,y,line); y -= fsz+3
    role = p.get("role","")
    if role:
        c.setFillColor(C_FOREST); c.setFont("Helvetica",9)
        c.drawString(mx,y-2,role[:42]); y -= 13
    org = p.get("org","")
    if org:
        c.setFillColor(C_INK3); c.setFont("Helvetica",8)
        c.drawString(mx,y-2,org[:44])
    c.setStrokeColor(C_GOLD); c.setLineWidth(1.5); c.line(mx,12*mm,mx+18*mm,12*mm)
    pid = p.get("id","")
    c.setFillColor(C_PAPER2); c.roundRect(mx,5*mm,28*mm,5.5*mm,radius=2*mm,fill=1,stroke=0)
    c.setFillColor(C_INK3); c.setFont("Helvetica",7)
    c.drawString(mx+2*mm,6.5*mm,f"ID · {pid}")
    qr_data = p.get("_qr_data","")
    if qr_data:
        qi = make_qr_image(qr_data,size=180)
        buf = io.BytesIO(); qi.save(buf,format="PNG"); buf.seek(0)
        qs = 32*mm; qcx = qx+(qcw-qs)/2; qcy = (h-qs)/2+3*mm; pad = 2*mm
        c.setFillColor(colors.white)
        c.roundRect(qcx-pad,qcy-pad,qs+2*pad,qs+2*pad,radius=2*mm,fill=1,stroke=0)
        c.drawImage(ImageReader(buf),qcx,qcy,width=qs,height=qs)
    c.setFillColor(C_INK3); c.setFont("Helvetica",6)
    lbl = "SCAN TO CHECK IN"; lw = c.stringWidth(lbl,"Helvetica",6)
    c.drawString(qx+(qcw-lw)/2,6*mm,lbl)
    c.setFillColor(C_GOLD); c.setFillAlpha(0.05)
    c.circle(w,h,20*mm,fill=1,stroke=0); c.setFillAlpha(1.0)

def make_pdf(p, event_name):
    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=landscape((CARD_W,CARD_H)))
    draw_card(c,p,event_name); c.showPage(); c.save()
    buf.seek(0); return buf.read()

# ── CSV helpers ───────────────────────────────────────────
AUTO = {
    "name":  ["name","full","participant","attendee"],
    "email": ["email","mail"],
    "role":  ["role","title","position","job"],
    "org":   ["org","company","affil","institution"],
    "badge": ["badge","id","number","num","ref","ticket"],
}
def detect(headers, field):
    for h in headers:
        if any(k in h.lower() for k in AUTO.get(field,[])):
            return h
    return None

def load_csv(f):
    df   = pd.read_csv(f, dtype=str, keep_default_na=False)
    hdrs = list(df.columns)
    return df.to_dict(orient="records"), {fld:detect(hdrs,fld) for fld in AUTO}

def checkins_csv_bytes():
    rows = list(st.session_state.checkins.values())
    if not rows: return b""
    fields = ["id","name","role","org","email","event","time","method"]
    buf = io.StringIO()
    w   = csv.DictWriter(buf,fieldnames=fields,extrasaction="ignore")
    w.writeheader(); w.writerows(rows)
    return buf.getvalue().encode()

def participants_json_bytes():
    return json.dumps({
        "event": st.session_state.event_name,
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "participants": list(st.session_state.participants.values()),
    }, indent=2, ensure_ascii=False).encode()

def build_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for card in st.session_state.generated_cards:
            zf.writestr(f"cards/{card['pid']}-{card['name'].replace(' ','_')}.pdf",
                        card["pdf_bytes"])
        zf.writestr("participants.json", participants_json_bytes().decode())
    buf.seek(0); return buf.read()

# ── Auto check-in from URL params ────────────────────────
params   = st.query_params
auto_pid = params.get("id","")

if auto_pid and auto_pid not in st.session_state.auto_checked:
    auto_name  = params.get("name","")
    auto_event = params.get("event","")
    auto_sig   = params.get("sig","")
    st.session_state.auto_checked.add(auto_pid)

    if st.session_state.secret_key:
        if verify(auto_pid, auto_name, auto_event, auto_sig):
            status = do_checkin(auto_pid, auto_name, auto_event, method="qr-scan")
            p      = st.session_state.participants.get(auto_pid, {})
            st.session_state.last_result = {
                "type": status,
                "name": p.get("name", auto_name),
                "sub":  " · ".join(filter(None,[p.get("role",""),p.get("org","")])) or auto_pid,
            }
        else:
            st.session_state.last_result = {
                "type":"err","name":"Invalid QR",
                "sub":"Signature mismatch — wrong key or tampered code",
            }
    else:
        st.session_state["_pending"] = {
            "pid":auto_pid,"name":auto_name,"event":auto_event,"sig":auto_sig
        }

# ── Header ────────────────────────────────────────────────
inn   = len(st.session_state.checkins)
total = len(st.session_state.participants)
st.markdown(f"""
<div class="cg-hdr">
  <div>
    <div class="cg-logo">Check<em>gate</em></div>
    <div class="cg-sub">Event Check-In · HMAC-SHA256</div>
  </div>
  <div style="display:flex;gap:16px;align-items:center;">
    <div style="text-align:right">
      <div style="font-family:'DM Mono',monospace;font-size:24px;color:#36d97e;font-weight:500">{inn}</div>
      <div style="font-size:10px;color:#546860;text-transform:uppercase;letter-spacing:.08em">Checked in</div>
    </div>
    <div style="width:1px;height:32px;background:rgba(255,255,255,.1)"></div>
    <div style="text-align:right">
      <div style="font-family:'DM Mono',monospace;font-size:24px;color:#e4ece6;font-weight:500">{total or "–"}</div>
      <div style="font-size:10px;color:#546860;text-transform:uppercase;letter-spacing:.08em">Total</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────
tab_gen, tab_scan, tab_attend, tab_settings = st.tabs([
    "🎴  Card Generator", "📋  Check-In", "📊  Attendance", "⚙  Settings",
])

# ════════════════════════════════════════════════════
# TAB 1 — CARD GENERATOR
# ════════════════════════════════════════════════════
with tab_gen:
    st.markdown("### Generate participant badge cards")
    g1, g2 = st.columns(2)
    with g1:
        gen_event = st.text_input("Event name", value=st.session_state.event_name, key="g_event")
        st.session_state.event_name = gen_event
        gen_key = st.text_input("Secret signing key", type="password",
                                value=st.session_state.secret_key,
                                placeholder="e.g. summit-2025-secret", key="g_key")
        st.session_state.secret_key = gen_key
    with g2:
        gen_url = st.text_input("Your Streamlit app URL",
                                value=st.session_state.app_url,
                                placeholder="https://yourname-checkgate.streamlit.app",
                                key="g_url",
                                help="QR codes will encode this URL. Leave blank for JSON QR codes.")
        st.session_state.app_url = gen_url
        id_prefix = st.text_input("Badge ID prefix", value="P", max_chars=4, key="g_pfx")
        id_start  = st.number_input("Starting number", min_value=1, value=1, key="g_start")

    if gen_url.strip():
        st.markdown('<div class="ok-box">✓ <strong>URL mode:</strong> Phone scanner opens the app URL and check-in happens automatically.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-box">ℹ <strong>JSON mode:</strong> No URL set — paste QR text in the Check-In tab. Set your app URL above for fully automatic check-in.</div>', unsafe_allow_html=True)

    st.markdown("---")
    uploaded = st.file_uploader("Upload participants CSV", type=["csv"])
    st.download_button("⬇ Download sample CSV",
        "name,email,role,organisation,badge_id\n"
        "Alice Martin,alice@example.com,Lead Engineer,Acumen Labs,\n"
        "Bob Chen,bob@example.com,Product Manager,Nexus Corp,\n"
        "Clara Osei,clara@example.com,UX Designer,Studio Volta,\n",
        file_name="participants-template.csv", mime="text/csv")

    if uploaded:
        rows, cm = load_csv(uploaded)
        st.success(f"✓ {len(rows)} participants loaded")
        with st.expander("Preview & column mapping"):
            st.dataframe(pd.DataFrame(rows).head(5), use_container_width=True)
            st.dataframe(pd.DataFrame([{"Field":k,"Maps to":v or "*(not found)*"}
                                        for k,v in cm.items()]),
                         use_container_width=True, hide_index=True)

        if not cm["name"]:
            st.error("No name column found.")
        elif not gen_key:
            st.warning("Enter a secret key above.")
        else:
            if st.button("⚡ Generate all cards", type="primary", use_container_width=True):
                prog = st.progress(0, text="Generating…")
                cards_out = []; parts_out = {}
                for i, row in enumerate(rows):
                    name  = (row.get(cm["name"],"") or "").strip()
                    email = (row.get(cm["email"],"") or "").strip() if cm["email"] else ""
                    role  = (row.get(cm["role"],"")  or "").strip() if cm["role"]  else ""
                    org   = (row.get(cm["org"],"")   or "").strip() if cm["org"]   else ""
                    pid   = (row.get(cm["badge"],"") or "").strip() if cm["badge"] else ""
                    if not pid:
                        pid = f"{id_prefix.upper()}{str(int(id_start)+i).zfill(4)}"
                    if not name: continue
                    qr_data = (build_qr_url(pid,name,email,gen_event,gen_key,gen_url.strip())
                               if gen_url.strip()
                               else build_qr_json(pid,name,email,gen_event,gen_key))
                    p_dict = {"id":pid,"name":name,"email":email,"role":role,"org":org,"_qr_data":qr_data}
                    cards_out.append({"pid":pid,"name":name,"pdf_bytes":make_pdf(p_dict,gen_event)})
                    parts_out[pid] = {"id":pid,"name":name,"email":email,"role":role,"org":org}
                    prog.progress((i+1)/len(rows), text=f"Generated {i+1}/{len(rows)} — {name}")
                st.session_state.generated_cards = cards_out
                st.session_state.participants     = parts_out
                prog.empty()
                st.success(f"✓ {len(cards_out)} cards generated!")

    if st.session_state.generated_cards:
        st.markdown("---")
        st.markdown("#### Download")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button("⬇ All cards + participants.json (ZIP)", build_zip(),
                               file_name=f"checkgate-{datetime.now().strftime('%Y%m%d')}.zip",
                               mime="application/zip", use_container_width=True, type="primary")
        with d2:
            st.download_button("⬇ participants.json", participants_json_bytes(),
                               file_name="participants.json", mime="application/json",
                               use_container_width=True)
        st.markdown("#### Individual cards")
        cols = st.columns(3)
        for i, card in enumerate(st.session_state.generated_cards):
            with cols[i % 3]:
                st.download_button(f"⬇ {card['pid']} — {card['name']}", card["pdf_bytes"],
                                   file_name=f"{card['pid']}-{card['name'].replace(' ','_')}.pdf",
                                   mime="application/pdf", use_container_width=True)

# ════════════════════════════════════════════════════
# TAB 2 — CHECK-IN
# ════════════════════════════════════════════════════
with tab_scan:
    if not st.session_state.secret_key:
        st.markdown('<div class="warn-box">⚠ Set your secret key in ⚙ Settings before checking people in.</div>', unsafe_allow_html=True)
        st.markdown("")

    # Show last result
    r = st.session_state.last_result
    if r:
        rtype = r["type"]
        css   = "ok" if rtype=="ok" else ("dup" if rtype=="duplicate" else "err")
        icons  = {"ok":"✓","duplicate":"⚠","err":"✕"}
        labels = {"ok":"CHECKED IN","duplicate":"ALREADY IN","err":"INVALID"}
        chips  = {"ok":"chip-ok","duplicate":"chip-dup","err":"chip-err"}
        st.markdown(
            f'<div class="flash-{css}"><div class="flash-hd">'
            f'<div class="flash-nm">{icons.get(rtype,"?")} {r["name"]}</div>'
            f'<span class="chip {chips.get(rtype,"chip-err")}">{labels.get(rtype,"")}</span>'
            f'</div><div class="flash-sb">{r["sub"]}</div></div>',
            unsafe_allow_html=True)
        st.markdown("")

    sc1, sc2 = st.columns([1.1, 1])

    with sc1:
        st.markdown("#### How to check people in")
        st.markdown("""
<div class="step-box"><div style="display:flex;align-items:flex-start;gap:8px">
  <span class="step-num">1</span>
  <div><div class="step-title">Print the badge cards</div>
  <div class="step-desc">Generate cards in 🎴 Card Generator. Each card has a signed QR code.</div></div>
</div></div>

<div class="step-box"><div style="display:flex;align-items:flex-start;gap:8px">
  <span class="step-num">2</span>
  <div><div class="step-title">Keep this page open at the door</div>
  <div class="step-desc">Open this on a laptop or tablet at the entrance. Every scan shows up here live.</div></div>
</div></div>

<div class="step-box"><div style="display:flex;align-items:flex-start;gap:8px">
  <span class="step-num">3</span>
  <div><div class="step-title">Scan badge QR with your phone Scanner app</div>
  <div class="step-desc">
    Use your phone's <strong>Camera app</strong> (iPhone) or <strong>Google Lens / Samsung Camera</strong> (Android) — any QR scanner works.<br><br>
    <strong>URL mode (recommended):</strong> Scanner opens the app in the browser → check-in is logged instantly on this screen. Done.<br><br>
    <strong>JSON mode:</strong> Scanner copies the text → paste it in the field on the right → click Check In.
  </div></div>
</div></div>
""", unsafe_allow_html=True)

        st.markdown('<div class="info-box">📱 <strong>Best scanner apps that work:</strong><br>'
                    '• iPhone — <strong>built-in Camera app</strong> (just point at QR) or Control Centre scanner<br>'
                    '• Android — <strong>Google Lens</strong>, Samsung Camera, or any QR app<br>'
                    '• Any app that opens URLs automatically will trigger the check-in with zero extra steps</div>',
                    unsafe_allow_html=True)

    with sc2:
        st.markdown("#### Paste / manual check-in")
        st.markdown("For JSON-mode QRs, or to check in someone by name/ID:")

        paste_val = st.text_area(
            "Paste QR text, URL, or type a name / badge ID",
            height=110,
            placeholder=(
                'Paste QR text here, e.g.:\n'
                '{"id":"P0001","name":"Alice","sig":"abc123..."}\n\n'
                'Or type a name:  Alice Martin\n'
                'Or a badge ID:   P0001'
            ),
            key="paste_input",
            label_visibility="collapsed",
        )

        if st.button("✓ Check In", type="primary", use_container_width=True):
            q = paste_val.strip()
            if q:
                if q.startswith("{") or q.startswith("http"):
                    res = process_raw(q, "paste")
                    if res["ok"]:
                        st.session_state.last_result = {
                            "type": res["status"], "name": res["name"],
                            "sub": " · ".join(filter(None,[res.get("role",""),res.get("org","")])) or res["id"],
                        }
                    else:
                        st.session_state.last_result = {"type":"err","name":"Invalid QR","sub":res["reason"]}
                else:
                    q_lo  = q.lower()
                    found = next((p for p in st.session_state.participants.values()
                                  if p["id"].lower()==q_lo or q_lo in p["name"].lower()), None)
                    if found:
                        status = do_checkin(found["id"],found["name"],
                                            st.session_state.event_name,"manual")
                        st.session_state.last_result = {
                            "type": status, "name": found["name"],
                            "sub": " · ".join(filter(None,[found.get("role",""),found.get("org","")])) or found["id"],
                        }
                    else:
                        wid = f"W-{int(datetime.now().timestamp())}"
                        do_checkin(wid,q,st.session_state.event_name,"walk-in")
                        st.session_state.last_result = {"type":"ok","name":q,"sub":"Walk-in registered"}
                st.rerun()

        st.markdown("---")
        st.markdown("#### Recent arrivals")
        recent = sorted(st.session_state.checkins.values(),
                        key=lambda x: x["time"], reverse=True)[:10]
        if recent:
            for e in recent:
                meta = " · ".join(filter(None,[e.get("role",""),e.get("org","")]))
                meta_html = (f'<span style="font-size:11px;color:#546860;margin-left:8px">{meta}</span>'
                             if meta else "")
                name_str = e["name"]
                time_str = e["time"][11:16]
                method_str = e.get("method","")
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:7px 0;border-bottom:1px solid rgba(255,255,255,.06);">'
                    f'<div><span style="font-weight:500;color:#e4ece6">{name_str}</span>'
                    f'{meta_html}'
                    f'</div><div style="display:flex;align-items:center;gap:8px">'
                    f'<span style="font-size:10px;color:#546860">{method_str}</span>'
                    f'<span style="font-family:monospace;font-size:12px;color:#36d97e">{time_str}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#546860;font-size:13px;padding:12px 0">No check-ins yet</div>',
                        unsafe_allow_html=True)

# ════════════════════════════════════════════════════
# TAB 3 — ATTENDANCE
# ════════════════════════════════════════════════════
with tab_attend:
    inn   = len(st.session_state.checkins)
    total = len(st.session_state.participants)
    pend  = max(total-inn,0)
    pct   = f"{inn*100//total}%" if total else "–"

    a1,a2,a3,a4 = st.columns(4)
    for col,val,lbl,cls in [(a1,inn,"Checked In","sv-green"),(a2,total or "–","Expected",""),
                             (a3,pend,"Pending","sv-amber"),(a4,pct,"Rate","sv-blue")]:
        with col:
            st.markdown(f'<div class="stat-card"><div class="stat-val {cls}">{val}</div>'
                        f'<div class="stat-lbl">{lbl}</div></div>', unsafe_allow_html=True)
    st.markdown("")

    fs,ff = st.columns([3,1])
    with fs: search = st.text_input("Search","",placeholder="Name, ID, role…",
                                     label_visibility="hidden",key="a_search")
    with ff: filt   = st.selectbox("Filter",["All","Checked in","Pending"],
                                    label_visibility="hidden",key="a_filt")

    rows_all = []
    for p in st.session_state.participants.values():
        ci = st.session_state.checkins.get(p["id"])
        rows_all.append({"✓":"✓" if ci else "","ID":p["id"],"Name":p["name"],
                          "Role":p.get("role",""),"Org":p.get("org",""),
                          "Time":ci["time"][11:16] if ci else "","Method":ci.get("method","") if ci else ""})
    for pid,ci in st.session_state.checkins.items():
        if pid not in st.session_state.participants:
            rows_all.append({"✓":"✓","ID":pid,"Name":ci["name"],"Role":ci.get("role",""),
                              "Org":ci.get("org",""),"Time":ci["time"][11:16],"Method":ci.get("method","")})

    if filt=="Checked in": rows_all=[r for r in rows_all if r["✓"]]
    elif filt=="Pending":  rows_all=[r for r in rows_all if not r["✓"]]
    if search:
        q=search.lower(); rows_all=[r for r in rows_all if any(q in str(v).lower() for v in r.values())]
    rows_all.sort(key=lambda r:(not r["✓"],r["Name"]))

    if rows_all:
        st.dataframe(pd.DataFrame(rows_all), use_container_width=True, hide_index=True,
                     column_config={"✓":st.column_config.TextColumn("✓",width=40),
                                    "Time":st.column_config.TextColumn("Time",width=70),
                                    "Method":st.column_config.TextColumn("Method",width=90)})
    else:
        st.info("No data yet.")

    st.markdown("")
    e1,e2,e3 = st.columns(3)
    with e1:
        st.download_button("⬇ Export CSV", checkins_csv_bytes() or b"id,name\n",
                           file_name=f"checkins-{datetime.now().strftime('%Y%m%d-%H%M')}.csv",
                           mime="text/csv", use_container_width=True)
    with e2:
        st.download_button("⬇ Export JSON",
                           json.dumps({"event":st.session_state.event_name,
                                       "checkins":list(st.session_state.checkins.values())},
                                      indent=2).encode(),
                           file_name=f"checkins-{datetime.now().strftime('%Y%m%d-%H%M')}.json",
                           mime="application/json", use_container_width=True)
    with e3:
        if st.button("🗑 Clear check-ins", use_container_width=True):
            if st.session_state.get("_confirm_clear"):
                st.session_state.checkins={}; st.session_state["_confirm_clear"]=False; st.rerun()
            else:
                st.session_state["_confirm_clear"]=True
                st.warning("Click again to confirm.")

# ════════════════════════════════════════════════════
# TAB 4 — SETTINGS
# ════════════════════════════════════════════════════
with tab_settings:
    st.markdown("### Settings")
    s1,s2 = st.columns(2)
    with s1:
        st.markdown("#### Event & security")
        new_event = st.text_input("Event name", value=st.session_state.event_name, key="s_event")
        st.session_state.event_name = new_event
        new_key = st.text_input("Secret signing key", type="password",
                                value=st.session_state.secret_key,
                                placeholder="Must match key used in card generator", key="s_key")
        st.session_state.secret_key = new_key
        new_url = st.text_input("App URL", value=st.session_state.app_url,
                                placeholder="https://yourapp.streamlit.app", key="s_url")
        st.session_state.app_url = new_url
        st.caption("🔒 Key is session-only — never written to disk or sent anywhere.")

        # Process any pending check-in (arrived before key was set)
        pending = st.session_state.get("_pending")
        if pending and new_key:
            if verify(pending["pid"],pending["name"],pending["event"],pending["sig"]):
                status = do_checkin(pending["pid"],pending["name"],pending["event"],"qr-scan")
                p = st.session_state.participants.get(pending["pid"],{})
                st.session_state.last_result = {
                    "type":status,"name":p.get("name",pending["name"]),
                    "sub":" · ".join(filter(None,[p.get("role",""),p.get("org","")])) or pending["pid"],
                }
                del st.session_state["_pending"]
                st.success(f"✓ Pending check-in processed: {pending['name']}")

    with s2:
        st.markdown("#### Import participants")
        st.markdown("Upload `participants.json` (from Card Generator) or a CSV to pre-populate the attendance list.")
        imp_json = st.file_uploader("participants.json", type=["json"], key="s_json")
        if imp_json:
            try:
                data  = json.load(imp_json)
                items = data if isinstance(data,list) else data.get("participants",[])
                st.session_state.participants = {
                    p.get("id","??"): {k:p.get(k,"") for k in ["id","name","email","role","org"]}
                    for p in items if p.get("id")}
                st.success(f"✓ {len(st.session_state.participants)} participants loaded")
            except Exception as ex:
                st.error(f"Could not parse JSON: {ex}")

        imp_csv = st.file_uploader("Or import CSV", type=["csv"], key="s_csv")
        if imp_csv:
            rows,cm = load_csv(imp_csv)
            if cm["name"]:
                st.session_state.participants={}
                for i,row in enumerate(rows):
                    pid=(row.get(cm["badge"],"") or f"P{str(i+1).zfill(4)}").strip()
                    st.session_state.participants[pid]={
                        "id":pid,"name":row.get(cm["name"],""),
                        "email":row.get(cm["email"],"") if cm["email"] else "",
                        "role": row.get(cm["role"],"")  if cm["role"]  else "",
                        "org":  row.get(cm["org"],"")   if cm["org"]   else "",
                    }
                st.success(f"✓ {len(st.session_state.participants)} participants loaded")

    st.markdown("---")
    st.markdown("#### Streamlit Cloud deployment (free)")
    st.markdown("""
1. Create a free **[GitHub](https://github.com)** account and make a new repo
2. Upload `app.py` and `requirements.txt` to the repo
3. Go to **[share.streamlit.io](https://share.streamlit.io)** → *New app* → connect repo → Deploy
4. Copy your app URL (e.g. `https://alice-checkgate.streamlit.app`)
5. Paste it into **App URL** in Settings, then regenerate your cards
6. Every badge QR now encodes that URL — phone scans it → browser opens → checked in automatically
    """)
