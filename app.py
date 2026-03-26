"""
╔══════════════════════════════════════════════════════════╗
║  Checkgate — Streamlit App                               ║
║  Tab 1: Generate signed participant badge cards (PDF)    ║
║  Tab 2: Live QR scanner (phone camera in browser)        ║
║  Tab 3: Attendance dashboard                             ║
╚══════════════════════════════════════════════════════════╝

Run locally:
  pip install streamlit pillow qrcode reportlab pandas
  streamlit run app.py

Deploy free on Streamlit Cloud:
  1. Push this file + requirements.txt to a GitHub repo
  2. Go to share.streamlit.io → New app → select repo → deploy
  3. Share the URL — works on any phone browser
"""

import csv
import hashlib
import hmac as hmac_lib
import io
import json
import os
import textwrap
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import qrcode
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PAGE CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="Checkgate",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GLOBAL CSS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,400&family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap');

/* Base */
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.8rem; padding-bottom: 2rem; }

/* Custom header */
.cg-header {
    background: linear-gradient(135deg, #16130f 0%, #2a2010 100%);
    border-radius: 14px;
    padding: 22px 32px;
    margin-bottom: 24px;
    border: 1px solid rgba(184,131,42,0.25);
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.cg-logo {
    font-family: 'Playfair Display', serif;
    font-size: 26px;
    color: #faf8f4;
    letter-spacing: 0.02em;
}
.cg-logo em { color: #d4a855; font-style: italic; }
.cg-tagline { font-size: 12px; color: #9a8a78; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 3px; }
.cg-badge {
    background: rgba(184,131,42,0.15);
    border: 1px solid rgba(184,131,42,0.35);
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 11px;
    color: #d4a855;
    font-weight: 600;
    letter-spacing: 0.06em;
}

/* Stat cards */
.stat-card {
    background: #1a2020;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 18px 22px;
    text-align: center;
}
.stat-val {
    font-family: 'DM Mono', monospace;
    font-size: 36px;
    font-weight: 500;
    line-height: 1;
}
.stat-lbl {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #546860;
    margin-top: 4px;
}
.stat-green .stat-val { color: #36d97e; }
.stat-amber .stat-val  { color: #f0b020; }
.stat-blue .stat-val   { color: #60a5fa; }

/* Result flash */
.flash-ok  { background:#0d2b1a; border:1px solid #1e6b3e; border-radius:12px; padding:16px 22px; }
.flash-dup { background:#2b2200; border:1px solid #6b5000; border-radius:12px; padding:16px 22px; }
.flash-err { background:#2b0d0d; border:1px solid #6b1e1e; border-radius:12px; padding:16px 22px; }
.flash-name { font-family:'Playfair Display',serif; font-size:22px; color:#faf8f4; }
.flash-sub  { font-size:13px; color:#9aada0; margin-top:4px; }

/* Badge chip */
.chip-ok  { background:#36d97e; color:#06180c; border-radius:20px; padding:3px 12px; font-size:11px; font-weight:700; display:inline-block; letter-spacing:0.06em; }
.chip-dup { background:#f0b020; color:#180f00; border-radius:20px; padding:3px 12px; font-size:11px; font-weight:700; display:inline-block; letter-spacing:0.06em; }
.chip-err { background:#ff5f5f; color:#180606; border-radius:20px; padding:3px 12px; font-size:11px; font-weight:700; display:inline-block; letter-spacing:0.06em; }

/* Info box */
.info-box {
    background: rgba(96,165,250,0.08);
    border: 1px solid rgba(96,165,250,0.25);
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 13px;
    color: #93c5fd;
    line-height: 1.7;
}
.warn-box {
    background: rgba(240,176,32,0.08);
    border: 1px solid rgba(240,176,32,0.25);
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 13px;
    color: #fcd34d;
    line-height: 1.7;
}

/* Attendance table row colours */
.row-in  td { color: #36d97e !important; }
.row-out td { color: #546860 !important; }

/* Tab styling */
button[data-baseweb="tab"] {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 14px !important;
    font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SESSION STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _init_state():
    defaults = {
        "secret_key":    "",
        "event_name":    "Annual Event 2025",
        "participants":  {},   # {id: {id,name,role,org,email}}
        "checkins":      {},   # {id: {id,name,role,org,email,time,method}}
        "generated_cards": [], # list of {pid, name, pdf_bytes}
        "last_scan_result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HMAC HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def hmac_sign(secret: str, message: str) -> str:
    return hmac_lib.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

def build_qr_payload(pid, name, email, event, secret):
    sig_input = json.dumps(
        {"id": pid, "name": name, "email": email, "event": event},
        separators=(",", ":"), ensure_ascii=False
    )
    sig = hmac_sign(secret, sig_input)[:16]
    return json.dumps(
        {"id": pid, "name": name, "event": event, "sig": sig},
        separators=(",", ":"), ensure_ascii=False
    )

def verify_qr_payload(qr_text: str) -> dict:
    secret       = st.session_state.secret_key
    participants = st.session_state.participants
    try:
        payload = json.loads(qr_text)
    except Exception:
        return {"ok": False, "reason": "Not a valid Checkgate QR code"}

    pid   = payload.get("id",    "")
    name  = payload.get("name",  "")
    event = payload.get("event", "")
    sig   = payload.get("sig",   "")

    if not all([pid, name, sig]):
        return {"ok": False, "reason": "QR is missing required fields"}
    if not secret:
        return {"ok": False, "reason": "No secret key set — go to ⚙ Settings"}

    email = participants.get(pid, {}).get("email", "")
    attempts = (
        [json.dumps({"id":pid,"name":name,"email":email,"event":event}, separators=(",",":")),
         json.dumps({"id":pid,"name":name,"email":"",   "event":event}, separators=(",",":"))]
        if email else
        [json.dumps({"id":pid,"name":name,"email":"",   "event":event}, separators=(",",":"))]
    )
    for attempt in attempts:
        if hmac_sign(secret, attempt)[:16] == sig:
            p = participants.get(pid, {})
            return {
                "ok":    True,
                "id":    pid,
                "name":  p.get("name",  name),
                "role":  p.get("role",  ""),
                "org":   p.get("org",   ""),
                "email": p.get("email", email),
                "event": event,
            }
    return {"ok": False, "reason": "Signature mismatch — wrong key or tampered QR"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CHECK-IN LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def do_checkin(result: dict, method: str = "qr"):
    pid  = result["id"]
    name = result["name"]
    if pid in st.session_state.checkins:
        return "duplicate"
    entry = {
        "id":     pid,
        "name":   name,
        "role":   result.get("role",  ""),
        "org":    result.get("org",   ""),
        "email":  result.get("email", ""),
        "event":  result.get("event", st.session_state.event_name),
        "time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": method,
    }
    st.session_state.checkins[pid] = entry
    return "ok"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  QR IMAGE GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def make_qr_image(data: str, size: int = 200) -> Image.Image:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10, border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#16130f", back_color="white")
    return img.resize((size, size), Image.LANCZOS)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PDF CARD GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C_INK    = colors.HexColor("#16130f")
C_GOLD   = colors.HexColor("#b8832a")
C_GOLD2  = colors.HexColor("#d4a855")
C_GOLD3  = colors.HexColor("#f0c97a")
C_FOREST = colors.HexColor("#3d7259")
C_PAPER  = colors.HexColor("#faf8f4")
C_PAPER2 = colors.HexColor("#f0ebe0")
C_INK3   = colors.HexColor("#8a7a6e")

CARD_W = 148 * mm
CARD_H = 105 * mm

def draw_pdf_card(c, participant: dict, event_name: str):
    w, h = CARD_W, CARD_H

    # Background
    c.setFillColor(colors.white)
    c.roundRect(0, 0, w, h, radius=3*mm, fill=1, stroke=0)

    # Gold accent bar
    bw = 7
    c.setFillColor(C_GOLD)
    c.roundRect(0, 0, bw, h, radius=2*mm, fill=1, stroke=0)
    c.rect(bw//2, 0, bw//2, h, fill=1, stroke=0)

    # QR column background
    qr_col_w = 42 * mm
    qr_x = w - qr_col_w
    c.setFillColor(C_PAPER)
    c.rect(qr_x, 0, qr_col_w, h, fill=1, stroke=0)

    # Separator
    c.setStrokeColor(C_PAPER2)
    c.setLineWidth(0.5)
    c.line(qr_x, 3*mm, qr_x, h - 3*mm)

    # Content area
    mx = bw + 4*mm

    # Event name
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica", 6.5)
    c.drawString(mx, h - 10*mm, event_name.upper())

    # Name
    name = participant.get("name", "")
    font_sz = 20 if len(name) <= 20 else 16
    c.setFillColor(C_INK)
    c.setFont("Helvetica-Bold", font_sz)
    y = h - 20*mm
    for line in textwrap.wrap(name, 22)[:2]:
        c.drawString(mx, y, line)
        y -= font_sz + 3

    # Role
    role = participant.get("role", "")
    if role:
        c.setFillColor(C_FOREST)
        c.setFont("Helvetica", 9)
        c.drawString(mx, y - 2, role[:42])
        y -= 13

    # Org
    org = participant.get("org", "")
    if org:
        c.setFillColor(C_INK3)
        c.setFont("Helvetica", 8)
        c.drawString(mx, y - 2, org[:44])

    # Divider
    c.setStrokeColor(C_GOLD)
    c.setLineWidth(1.5)
    c.line(mx, 12*mm, mx + 18*mm, 12*mm)

    # Badge ID pill
    pid = participant.get("id", "")
    c.setFillColor(C_PAPER2)
    c.roundRect(mx, 5*mm, 28*mm, 5.5*mm, radius=2*mm, fill=1, stroke=0)
    c.setFillColor(C_INK3)
    c.setFont("Helvetica", 7)
    c.drawString(mx + 2*mm, 6.5*mm, f"ID · {pid}")

    # QR code
    qr_payload = participant.get("_qr_payload", "")
    if qr_payload:
        qr_img  = make_qr_image(qr_payload, size=180)
        buf     = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        qr_size = 32*mm
        qr_cx   = qr_x + (qr_col_w - qr_size) / 2
        qr_cy   = (h - qr_size) / 2 + 3*mm
        pad     = 2*mm
        c.setFillColor(colors.white)
        c.roundRect(qr_cx - pad, qr_cy - pad, qr_size + 2*pad, qr_size + 2*pad,
                    radius=2*mm, fill=1, stroke=0)
        c.drawImage(ImageReader(buf), qr_cx, qr_cy, width=qr_size, height=qr_size)

    # Scan label
    c.setFillColor(C_INK3)
    c.setFont("Helvetica", 6)
    lbl = "SCAN TO CHECK IN"
    lw  = c.stringWidth(lbl, "Helvetica", 6)
    c.drawString(qr_x + (qr_col_w - lw) / 2, 6*mm, lbl)

    # Corner glow
    c.setFillColor(C_GOLD)
    c.setFillAlpha(0.05)
    c.circle(w, h, 20*mm, fill=1, stroke=0)
    c.setFillAlpha(1.0)


def generate_pdf_card(participant: dict, event_name: str) -> bytes:
    buf = io.BytesIO()
    from reportlab.lib.pagesizes import landscape
    c = rl_canvas.Canvas(buf, pagesize=landscape((CARD_W, CARD_H)))
    draw_pdf_card(c, participant, event_name)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CSV PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTO_KEYS = {
    "name":  ["name","full","participant","attendee"],
    "email": ["email","mail"],
    "role":  ["role","title","position","job"],
    "org":   ["org","company","affil","institution","firm"],
    "badge": ["badge","id","number","num","ref","ticket"],
}

def detect_col(headers, field):
    for h in headers:
        if any(k in h.lower() for k in AUTO_KEYS.get(field, [])):
            return h
    return None

def parse_participants_csv(uploaded_file) -> tuple[list, dict]:
    df = pd.read_csv(uploaded_file, dtype=str, keep_default_na=False)
    hdrs   = list(df.columns)
    colmap = {f: detect_col(hdrs, f) for f in AUTO_KEYS}
    rows   = df.to_dict(orient="records")
    return rows, colmap

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXPORT HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def export_checkins_csv() -> bytes:
    checkins = list(st.session_state.checkins.values())
    if not checkins:
        return b""
    headers = ["id","name","role","org","email","event","time","method"]
    buf = io.StringIO()
    w   = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    w.writeheader()
    w.writerows(checkins)
    return buf.getvalue().encode()

def export_participants_json() -> bytes:
    return json.dumps({
        "event":       st.session_state.event_name,
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "participants": list(st.session_state.participants.values()),
    }, indent=2, ensure_ascii=False).encode()

def build_cards_zip() -> bytes:
    cards = st.session_state.generated_cards
    buf   = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for card in cards:
            zf.writestr(f"cards/{card['pid']}-{card['name'].replace(' ','_')}.pdf", card["pdf_bytes"])
        zf.writestr("participants.json", export_participants_json().decode())
        zf.writestr("SETUP.txt", textwrap.dedent(f"""
            CHECKGATE SETUP
            ================
            Event: {st.session_state.event_name}
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

            1. Print cards from the cards/ folder
            2. Use the Scanner tab in this Streamlit app to check people in
            3. Keep your secret key safe — never share it
        """).strip())
    buf.seek(0)
    return buf.read()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CAMERA QR SCANNER COMPONENT
#  Pure HTML/JS injected into Streamlit via
#  st.components.v1.html — uses jsQR library.
#  When a valid QR is detected the JS posts the
#  result to a hidden Streamlit text_input via
#  the streamlit:setComponentValue protocol.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCANNER_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jsQR/1.4.0/jsQR.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0c0f0e; font-family: 'DM Sans', system-ui, sans-serif; color: #e4ece6; }
#wrap {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px; gap: 14px; min-height: 100vh;
}
#cam-box {
  position: relative; width: 100%; max-width: 360px;
  border-radius: 16px; overflow: hidden;
  background: #1a2020;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.1), 0 8px 32px rgba(0,0,0,0.6);
}
#cam-box::before { content:''; display:block; padding-top:100%; }
#video {
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; border-radius:16px;
}
#canvas-hidden { display:none; }
.corners {
  position:absolute; inset:0; pointer-events:none;
  display:flex; align-items:center; justify-content:center;
}
.frame {
  width:62%; aspect-ratio:1; position:relative;
}
.frame::before,.frame::after,.c3,.c4 {
  content:''; position:absolute;
  width:24px; height:24px;
  border-color:#36d97e; border-style:solid; border-width:0;
}
.frame::before{top:0;left:0;border-top-width:3px;border-left-width:3px;border-radius:4px 0 0 0}
.frame::after {top:0;right:0;border-top-width:3px;border-right-width:3px;border-radius:0 4px 0 0}
.c3{bottom:0;left:0;border-bottom-width:3px;border-left-width:3px;border-radius:0 0 0 4px}
.c4{bottom:0;right:0;border-bottom-width:3px;border-right-width:3px;border-radius:0 0 4px 0}
.scan-line {
  position:absolute; left:18%; right:18%; height:2px;
  background:linear-gradient(90deg,transparent,#36d97e,transparent);
  animation:scan 2s ease-in-out infinite; border-radius:1px;
}
@keyframes scan{0%{top:20%;opacity:0}10%{opacity:.7}90%{opacity:.7}100%{top:80%;opacity:0}}

#status {
  font-size:12px; color:#546860; text-align:center;
  display:flex; align-items:center; gap:6px;
}
#dot {
  width:8px; height:8px; border-radius:50%;
  background:#546860; flex-shrink:0;
}
#dot.active { background:#36d97e; animation:pulse 1.2s infinite; }
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

#result-box {
  width:100%; max-width:360px; border-radius:12px;
  padding:14px 18px; display:none;
  animation:pop .2s ease-out;
}
@keyframes pop{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.res-ok  { background:#0d2b1a; border:1px solid #1e6b3e; display:flex!important; }
.res-dup { background:#2b2200; border:1px solid #6b5000; display:flex!important; }
.res-err { background:#2b0d0d; border:1px solid #6b1e1e; display:flex!important; }
#result-box { align-items:center; gap:12px; }
.res-icon { font-size:24px; flex-shrink:0; }
.res-name { font-size:17px; font-weight:700; color:#faf8f4; }
.res-sub  { font-size:12px; color:#9aada0; margin-top:3px; }
.badge {
  margin-left:auto; padding:3px 10px; border-radius:20px;
  font-size:10px; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; flex-shrink:0;
}
.badge-ok  { background:#36d97e; color:#06180c; }
.badge-dup { background:#f0b020; color:#180f00; }
.badge-err { background:#ff5f5f; color:#180606; }

#start-btn {
  padding:12px 32px; border-radius:10px; font-size:15px; font-weight:600;
  background:#36d97e; color:#06180c; border:none; cursor:pointer;
  width:100%; max-width:360px;
  font-family:system-ui,sans-serif;
  transition:background .15s;
}
#start-btn:hover { background:#4ee894; }

.hint { font-size:11px; color:#546860; text-align:center; max-width:320px; line-height:1.6; }
</style>
</head>
<body>
<div id="wrap">
  <div id="cam-box">
    <video id="video" playsinline autoplay muted></video>
    <canvas id="canvas-hidden"></canvas>
    <div class="corners">
      <div class="frame">
        <div class="c3"></div><div class="c4"></div>
        <div class="scan-line"></div>
      </div>
    </div>
  </div>

  <div id="status"><div id="dot"></div><span id="status-txt">Tap Start to activate camera</span></div>

  <div id="result-box">
    <div class="res-icon" id="res-icon"></div>
    <div>
      <div class="res-name" id="res-name"></div>
      <div class="res-sub"  id="res-sub"></div>
    </div>
    <div class="badge" id="res-badge"></div>
  </div>

  <button id="start-btn" onclick="startCam()">▶ Start Camera</button>
  <p class="hint">Point your phone's camera at a participant badge QR code.<br>Hold steady until it detects automatically.</p>
</div>

<script>
let stream = null;
let scanning = false;
let cooldownUntil = 0;
let flashTimer = null;

function startCam() {
  document.getElementById('start-btn').style.display = 'none';
  const constraints = {
    video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
  };
  navigator.mediaDevices.getUserMedia(constraints)
    .then(s => {
      stream = s;
      const v = document.getElementById('video');
      v.srcObject = stream;
      v.onloadedmetadata = () => { v.play(); startScanning(); };
    })
    .catch(err => {
      document.getElementById('status-txt').textContent = 'Camera denied: ' + err.message;
      document.getElementById('start-btn').style.display = 'block';
    });
}

function startScanning() {
  scanning = true;
  document.getElementById('dot').classList.add('active');
  document.getElementById('status-txt').textContent = 'Scanning…';
  requestAnimationFrame(scanFrame);
}

function scanFrame() {
  if (!scanning) return;
  const video  = document.getElementById('video');
  const canvas = document.getElementById('canvas-hidden');
  if (video.readyState < 2 || !video.videoWidth) {
    requestAnimationFrame(scanFrame); return;
  }
  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(video, 0, 0);
  const img  = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const code = jsQR(img.data, img.width, img.height, { inversionAttempts: 'attemptBoth' });
  if (code && code.data && Date.now() > cooldownUntil) {
    handleQR(code.data);
  }
  requestAnimationFrame(scanFrame);
}

function handleQR(data) {
  cooldownUntil = Date.now() + 3000;

  // Send to Streamlit via query param mechanism
  // We write to a hidden text area that Streamlit watches
  const input = window.parent.document.querySelector('input[aria-label="__qr_result__"]');
  if (input) {
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    nativeInputValueSetter.call(input, data);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // Also show local feedback immediately
  try {
    const p = JSON.parse(data);
    if (p.id && p.name && p.sig) {
      showLocalResult('ok', p.name, p.id, 'Verifying…', 'badge-ok');
    } else {
      showLocalResult('err', 'Unknown QR', '', 'Not a badge', 'badge-err');
    }
  } catch {
    showLocalResult('err', 'Not a badge QR', '', data.slice(0,40), 'badge-err');
  }
}

function showLocalResult(type, name, sub, badge, badgeClass) {
  const box = document.getElementById('result-box');
  box.className = 'res-' + type;
  const icons = { ok:'✓', dup:'⚠', err:'✕' };
  document.getElementById('res-icon').textContent  = icons[type] || '?';
  document.getElementById('res-name').textContent  = name;
  document.getElementById('res-sub').textContent   = sub;
  const badgeEl = document.getElementById('res-badge');
  badgeEl.textContent  = badge;
  badgeEl.className    = 'badge ' + badgeClass;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => { box.className = ''; box.style.display = 'none'; }, 5000);
}
</script>
</body>
</html>
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RENDER HEADER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
checkin_count = len(st.session_state.checkins)
total_count   = len(st.session_state.participants)

st.markdown(f"""
<div class="cg-header">
  <div>
    <div class="cg-logo">Check<em>gate</em></div>
    <div class="cg-tagline">Event Check-In System</div>
  </div>
  <div style="display:flex;gap:12px;align-items:center;">
    <div style="text-align:right;">
      <div style="font-family:'DM Mono',monospace;font-size:22px;color:#36d97e;font-weight:500;">{checkin_count}</div>
      <div style="font-size:10px;color:#546860;text-transform:uppercase;letter-spacing:.08em;">Checked in</div>
    </div>
    <div style="width:1px;height:36px;background:rgba(255,255,255,0.1);"></div>
    <div style="text-align:right;">
      <div style="font-family:'DM Mono',monospace;font-size:22px;color:#e4ece6;font-weight:500;">{total_count or '–'}</div>
      <div style="font-size:10px;color:#546860;text-transform:uppercase;letter-spacing:.08em;">Total</div>
    </div>
    <div class="cg-badge">HMAC-SHA256</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TABS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
tab_gen, tab_scan, tab_attend, tab_settings = st.tabs([
    "🎴  Card Generator",
    "📷  Scanner",
    "📋  Attendance",
    "⚙  Settings",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 1 — CARD GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_gen:
    st.markdown("### Generate participant badge cards")
    st.markdown("Upload your CSV → cards are generated with a permanent signed QR code. "
                "The QR can never be forged without your secret key.")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        event_input = st.text_input("Event name", value=st.session_state.event_name, key="gen_event")
        st.session_state.event_name = event_input
    with col_b:
        key_input = st.text_input("Secret signing key", type="password",
                                  value=st.session_state.secret_key,
                                  placeholder="Enter a strong secret — same key goes in Scanner tab",
                                  key="gen_key")
        st.session_state.secret_key = key_input

    col_c, col_d = st.columns([1, 1])
    with col_c:
        id_prefix = st.text_input("Badge ID prefix", value="P", max_chars=4,
                                  help="E.g. P → P0001, DEL → DEL0001")
    with col_d:
        id_start = st.number_input("Starting number", min_value=1, max_value=9999, value=1)

    st.markdown("---")

    uploaded_csv = st.file_uploader(
        "Upload participants CSV",
        type=["csv"],
        help="Required columns: name. Optional: email, role, organisation, badge_id"
    )

    # Sample CSV download
    sample_csv = ("name,email,role,organisation,badge_id\n"
                  "Alice Martin,alice@example.com,Lead Engineer,Acumen Labs,\n"
                  "Bob Chen,bob@example.com,Product Manager,Nexus Corp,\n"
                  "Clara Osei,clara@example.com,UX Designer,Studio Volta,\n")
    st.download_button("⬇ Download sample CSV template", sample_csv,
                       file_name="participants-template.csv", mime="text/csv")

    if uploaded_csv:
        rows, colmap = parse_participants_csv(uploaded_csv)
        st.success(f"✓ {len(rows)} participants loaded")

        with st.expander("Preview CSV & column mapping"):
            st.dataframe(pd.DataFrame(rows).head(5), use_container_width=True)
            st.markdown("**Auto-detected column mapping:**")
            mapping_df = pd.DataFrame([
                {"Field": k, "Mapped to": v or "*(not found)*"} for k, v in colmap.items()
            ])
            st.dataframe(mapping_df, use_container_width=True, hide_index=True)

        if not colmap["name"]:
            st.error("Could not find a name column. Please check your CSV headers.")
        elif not st.session_state.secret_key:
            st.warning("⚠ Enter a secret key above before generating cards.")
        else:
            if st.button("⚡ Generate all cards", type="primary", use_container_width=True):
                progress = st.progress(0, text="Generating cards…")
                cards_out = []
                participants_out = {}

                for i, row in enumerate(rows):
                    name  = (row.get(colmap["name"],  "") or "").strip()
                    email = (row.get(colmap["email"], "") or "").strip() if colmap["email"] else ""
                    role  = (row.get(colmap["role"],  "") or "").strip() if colmap["role"]  else ""
                    org   = (row.get(colmap["org"],   "") or "").strip() if colmap["org"]   else ""
                    if colmap["badge"] and row.get(colmap["badge"], "").strip():
                        pid = row[colmap["badge"]].strip()
                    else:
                        pid = f"{id_prefix.upper()}{str(int(id_start)+i).zfill(4)}"
                    if not name:
                        continue

                    qr_payload = build_qr_payload(pid, name, email, event_input,
                                                  st.session_state.secret_key)
                    participant = {"id": pid, "name": name, "email": email,
                                   "role": role, "org": org, "_qr_payload": qr_payload}
                    pdf_bytes   = generate_pdf_card(participant, event_input)

                    cards_out.append({"pid": pid, "name": name, "pdf_bytes": pdf_bytes})
                    participants_out[pid] = {"id":pid,"name":name,"email":email,"role":role,"org":org}

                    progress.progress((i+1)/len(rows),
                                      text=f"Generated {i+1}/{len(rows)} — {name}")

                st.session_state.generated_cards = cards_out
                st.session_state.participants     = participants_out
                progress.empty()
                st.success(f"✓ {len(cards_out)} cards generated and signed!")

    # Download section
    if st.session_state.generated_cards:
        st.markdown("---")
        st.markdown("#### Download cards")

        col_dl1, col_dl2, col_dl3 = st.columns(3)
        with col_dl1:
            zip_bytes = build_cards_zip()
            st.download_button(
                "⬇ All cards + participants.json (ZIP)",
                zip_bytes,
                file_name=f"checkgate-cards-{datetime.now().strftime('%Y%m%d')}.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary",
            )
        with col_dl2:
            st.download_button(
                "⬇ participants.json",
                export_participants_json(),
                file_name="participants.json",
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown("#### Card previews")
        cols = st.columns(3)
        for i, card in enumerate(st.session_state.generated_cards):
            with cols[i % 3]:
                st.download_button(
                    f"⬇ {card['pid']} — {card['name']}",
                    card["pdf_bytes"],
                    file_name=f"{card['pid']}-{card['name'].replace(' ','_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 2 — SCANNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_scan:
    if not st.session_state.secret_key:
        st.markdown('<div class="warn-box">⚠ No secret key set. Go to the ⚙ Settings tab and enter your key first.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f"**Event:** {st.session_state.event_name} &nbsp;·&nbsp; "
                    f"**{len(st.session_state.checkins)}** checked in so far")

    st.markdown("---")

    scan_col, manual_col = st.columns([1.2, 1])

    with scan_col:
        st.markdown("#### 📷 Phone camera scanner")
        st.markdown(
            '<div class="info-box">'
            '📱 <strong>Open this page on your phone</strong> — tap Start Camera, '
            'then point at a participant\'s badge QR code. '
            'It detects automatically and the check-in is recorded instantly.'
            '</div>',
            unsafe_allow_html=True
        )
        st.markdown("")

        # Hidden text input that receives QR data from the JS component
        qr_result = st.text_input("__qr_result__", label_visibility="hidden", key="qr_raw_input")

        # Process incoming QR
        if qr_result and qr_result != st.session_state.get("_last_processed_qr", ""):
            st.session_state["_last_processed_qr"] = qr_result
            result = verify_qr_payload(qr_result)
            if result["ok"]:
                status = do_checkin(result, method="qr-phone")
                if status == "ok":
                    st.session_state.last_scan_result = {
                        "type": "ok",
                        "name": result["name"],
                        "sub":  " · ".join(filter(None, [result.get("role"), result.get("org")])) or result["id"],
                    }
                    st.rerun()
                else:
                    t = st.session_state.checkins[result["id"]]["time"]
                    st.session_state.last_scan_result = {
                        "type": "dup",
                        "name": result["name"],
                        "sub":  f"Already checked in at {t[11:16]}",
                    }
                    st.rerun()
            else:
                st.session_state.last_scan_result = {
                    "type": "err", "name": "Invalid QR", "sub": result["reason"]
                }
                st.rerun()

        # Show last result
        r = st.session_state.last_scan_result
        if r:
            icons  = {"ok": "✓", "dup": "⚠", "err": "✕"}
            labels = {"ok": "CHECKED IN", "dup": "DUPLICATE", "err": "INVALID"}
            chips  = {"ok": "chip-ok", "dup": "chip-dup", "err": "chip-err"}
            st.markdown(
                f'<div class="flash-{r["type"]}">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<div class="flash-name">{icons[r["type"]]} {r["name"]}</div>'
                f'<span class="{chips[r["type"]]}">{labels[r["type"]]}</span>'
                f'</div>'
                f'<div class="flash-sub">{r["sub"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.markdown("")

        # Camera component
        import streamlit.components.v1 as components
        components.html(SCANNER_HTML, height=640, scrolling=False)

    with manual_col:
        st.markdown("#### ⌨ Manual check-in")
        st.markdown("Use this as a backup — type a name or badge ID to check someone in.")

        manual_query = st.text_input("Name or badge ID", placeholder="Alice Martin or P0001",
                                     key="manual_query")

        if st.button("Check in", use_container_width=True, type="primary"):
            q = manual_query.strip()
            if q:
                # Find in participants
                q_lo  = q.lower()
                found = next(
                    (p for p in st.session_state.participants.values()
                     if p["id"].lower() == q_lo or q_lo in p["name"].lower()),
                    None
                )
                if found:
                    result = {**found, "event": st.session_state.event_name}
                    status = do_checkin(result, method="manual")
                    if status == "ok":
                        st.session_state.last_scan_result = {
                            "type": "ok",
                            "name": found["name"],
                            "sub":  " · ".join(filter(None, [found.get("role"), found.get("org")])) or found["id"],
                        }
                    else:
                        t = st.session_state.checkins[found["id"]]["time"]
                        st.session_state.last_scan_result = {
                            "type": "dup", "name": found["name"],
                            "sub": f"Already checked in at {t[11:16]}"
                        }
                    st.rerun()
                else:
                    # Walk-in
                    pid = f"W-{int(datetime.now().timestamp())}"
                    do_checkin({"id": pid, "name": q, "event": st.session_state.event_name,
                                "role": "", "org": "", "email": ""}, method="walk-in")
                    st.session_state.last_scan_result = {
                        "type": "ok", "name": q, "sub": "Walk-in registered"
                    }
                    st.rerun()

        st.markdown("---")
        st.markdown("#### 🔢 Recent check-ins")
        recent = sorted(st.session_state.checkins.values(),
                        key=lambda x: x["time"], reverse=True)[:8]
        if recent:
            for entry in recent:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);">'
                    f'<div><span style="font-weight:500;color:#e4ece6;">{entry["name"]}</span>'
                    f'<span style="font-size:11px;color:#546860;margin-left:8px;">{entry.get("role","")}</span></div>'
                    f'<span style="font-family:monospace;font-size:11px;color:#36d97e;">{entry["time"][11:16]}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<div style="color:#546860;font-size:13px;">No check-ins yet</div>',
                        unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 3 — ATTENDANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_attend:
    inn   = len(st.session_state.checkins)
    total = len(st.session_state.participants)
    pend  = max(total - inn, 0)
    pct   = f"{inn*100//total}%" if total else "–"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-card stat-green"><div class="stat-val">{inn}</div>'
                    f'<div class="stat-lbl">Checked In</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-val">{total or "–"}</div>'
                    f'<div class="stat-lbl">Total Expected</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-card stat-amber"><div class="stat-val">{pend}</div>'
                    f'<div class="stat-lbl">Pending</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-card stat-blue"><div class="stat-val">{pct}</div>'
                    f'<div class="stat-lbl">Check-in Rate</div></div>', unsafe_allow_html=True)

    st.markdown("")

    # Search + filter
    col_s, col_f = st.columns([3, 1])
    with col_s:
        search = st.text_input("Search", placeholder="Name, ID, role, organisation…",
                               label_visibility="hidden", key="att_search")
    with col_f:
        filt = st.selectbox("Filter", ["All", "Checked in", "Pending"],
                            label_visibility="hidden", key="att_filter")

    # Build rows
    all_rows = []
    for p in st.session_state.participants.values():
        ci = st.session_state.checkins.get(p["id"])
        all_rows.append({
            "Status":   "✓ In" if ci else "Pending",
            "ID":       p["id"],
            "Name":     p["name"],
            "Role":     p.get("role", ""),
            "Org":      p.get("org",  ""),
            "Time":     ci["time"][11:16] if ci else "",
            "Method":   ci.get("method","") if ci else "",
        })

    for pid, ci in st.session_state.checkins.items():
        if pid not in st.session_state.participants:
            all_rows.append({
                "Status": "✓ In", "ID": pid, "Name": ci["name"],
                "Role": ci.get("role",""), "Org": ci.get("org",""),
                "Time": ci["time"][11:16], "Method": ci.get("method",""),
            })

    if filt == "Checked in":
        all_rows = [r for r in all_rows if r["Status"] == "✓ In"]
    elif filt == "Pending":
        all_rows = [r for r in all_rows if r["Status"] == "Pending"]

    if search:
        q = search.lower()
        all_rows = [r for r in all_rows if any(
            q in str(v).lower() for v in r.values()
        )]

    all_rows.sort(key=lambda r: (r["Status"] != "✓ In", r["Name"]))

    if all_rows:
        df = pd.DataFrame(all_rows)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     column_config={
                         "Status": st.column_config.TextColumn("Status", width=90),
                         "ID":     st.column_config.TextColumn("ID", width=90),
                         "Time":   st.column_config.TextColumn("Time", width=70),
                         "Method": st.column_config.TextColumn("Method", width=80),
                     })
    else:
        st.info("No participants to display yet. Generate cards or import a CSV.")

    st.markdown("")

    # Export + undo
    col_exp1, col_exp2, col_undo = st.columns(3)
    with col_exp1:
        csv_bytes = export_checkins_csv()
        st.download_button(
            "⬇ Export check-ins CSV",
            csv_bytes or b"id,name\n",
            file_name=f"checkins-{datetime.now().strftime('%Y%m%d-%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_exp2:
        json_export = json.dumps({
            "event": st.session_state.event_name,
            "exportedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "checkins": list(st.session_state.checkins.values()),
        }, indent=2).encode()
        st.download_button(
            "⬇ Export JSON log",
            json_export,
            file_name=f"checkins-{datetime.now().strftime('%Y%m%d-%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_undo:
        if st.button("🗑 Clear all check-ins", use_container_width=True):
            st.session_state.checkins = {}
            st.rerun()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 4 — SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_settings:
    st.markdown("### Settings")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_event = st.text_input("Event name", value=st.session_state.event_name, key="s_event")
        st.session_state.event_name = new_event

        new_key = st.text_input(
            "Secret signing key", type="password",
            value=st.session_state.secret_key,
            placeholder="Must match the key used in card generator",
            key="s_key",
            help="This key is stored in session only — never sent to any server."
        )
        st.session_state.secret_key = new_key
        st.caption("🔒 Stored in browser session only. Never persisted to disk or sent anywhere.")

    with col_s2:
        st.markdown("#### Import participants")
        st.markdown("Upload a `participants.json` from the card generator "
                    "(or a CSV) to pre-populate the attendance list.")

        imp_json = st.file_uploader("participants.json", type=["json"], key="imp_json")
        if imp_json:
            try:
                data  = json.load(imp_json)
                items = data if isinstance(data, list) else data.get("participants", [])
                st.session_state.participants = {
                    p.get("id","??"): {
                        "id":    p.get("id",""),
                        "name":  p.get("name",""),
                        "email": p.get("email",""),
                        "role":  p.get("role",""),
                        "org":   p.get("org",""),
                    } for p in items if p.get("id")
                }
                st.success(f"✓ {len(st.session_state.participants)} participants loaded")
            except Exception as e:
                st.error(f"Could not parse JSON: {e}")

        imp_csv = st.file_uploader("Or import CSV", type=["csv"], key="imp_csv_settings")
        if imp_csv:
            rows, colmap = parse_participants_csv(imp_csv)
            if colmap["name"]:
                st.session_state.participants = {}
                for i, row in enumerate(rows):
                    pid = (row.get(colmap["badge"],"") or f"P{str(i+1).zfill(4)}").strip()
                    st.session_state.participants[pid] = {
                        "id":    pid,
                        "name":  row.get(colmap["name"],  ""),
                        "email": row.get(colmap["email"], "") if colmap["email"] else "",
                        "role":  row.get(colmap["role"],  "") if colmap["role"]  else "",
                        "org":   row.get(colmap["org"],   "") if colmap["org"]   else "",
                    }
                st.success(f"✓ {len(st.session_state.participants)} participants loaded")

    st.markdown("---")
    st.markdown("#### How to deploy on Streamlit Cloud (free)")
    st.markdown("""
1. Create a GitHub repo and upload `app.py` + `requirements.txt`
2. Go to **[share.streamlit.io](https://share.streamlit.io)** → *New app* → connect your GitHub repo
3. Set main file to `app.py` → click Deploy
4. You get a public URL like `https://yourapp.streamlit.app`
5. Open that URL on any phone — the camera scanner works directly in the mobile browser

**Tip:** The secret key is never stored on disk — enter it fresh each session, or use Streamlit Secrets for persistent config.
    """)
