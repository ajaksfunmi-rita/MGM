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
#  SESSION STATE — FIXED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def init_session_state():
    """Initialize session state with safe defaults"""
    defaults = {
        "secret_key": "",
        "event_name": "Annual Event 2025",
        "participants": {},
        "checkins": {},
        "generated_cards": [],
        "last_scan_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# Call this safely
try:
    init_session_state()
except AttributeError:
    # Fallback if st.session_state is not available
    pass

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
    secret = st.session_state.get("secret_key", "")
    participants = st.session_state.get("participants", {})
    try:
        payload = json.loads(qr_text)
    except Exception:
        return {"ok": False, "reason": "Not a valid Checkgate QR code"}

    pid = payload.get("id", "")
    name = payload.get("name", "")
    event = payload.get("event", "")
    sig_reported = payload.get("sig", "")

    if not secret:
        return {"ok": False, "reason": "Secret key not set — go to Settings"}

    p = participants.get(pid)
    if not p:
        return {"ok": False, "reason": f"ID {pid} not in participant list"}

    email = p.get("email", "")
    sig_input = json.dumps(
        {"id": pid, "name": name, "email": email, "event": event},
        separators=(",", ":"), ensure_ascii=False
    )
    sig_computed = hmac_sign(secret, sig_input)[:16]

    if sig_computed != sig_reported:
        return {"ok": False, "reason": "QR code signature verification failed — tampering detected"}

    return {
        "ok": True,
        "id": pid,
        "name": name,
        "role": p.get("role", ""),
        "org": p.get("org", ""),
        "email": email,
    }

def parse_participants_csv(uploader):
    """Parse CSV file and auto-detect column names"""
    try:
        df = pd.read_csv(uploader, dtype=str)
    except Exception as e:
        st.error(f"Could not parse CSV: {e}")
        return [], {}

    col_map = {
        "name": None,
        "email": None,
        "role": None,
        "org": None,
        "badge": None,
    }

    cols_lower = {c.lower().strip(): c for c in df.columns}
    for key in col_map:
        for variant in [key, f"{key}_*", f"*{key}", f"*{key}*"]:
            if variant.replace("*", "") == key:
                for col, col_l in cols_lower.items():
                    if key in col.lower():
                        col_map[key] = col_l
                        break
            if col_map[key]:
                break

    rows = df.to_dict("records")
    return rows, col_map

def generate_card_pdf(pid, name, email, role, org, photo_url, qr_pil, template_a4=True):
    """Generate a single PDF card with QR code and participant details"""
    buf = io.BytesIO()
    if template_a4:
        w, h = 210 * mm, 297 * mm
    else:
        w, h = 105 * mm, 148 * mm

    c = rl_canvas.Canvas(buf, pagesize=(w, h))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(15 * mm, h - 30 * mm, name)

    if role:
        c.setFont("Helvetica", 10)
        c.drawString(15 * mm, h - 38 * mm, f"Role: {role}")
    if org:
        c.setFont("Helvetica", 10)
        c.drawString(15 * mm, h - 45 * mm, f"Org: {org}")

    qr_img = ImageReader(qr_pil)
    qr_size = 40 * mm
    c.drawImage(qr_img, w - qr_size - 10 * mm, h - qr_size - 20 * mm, width=qr_size, height=qr_size)

    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 20 * mm, f"ID: {pid}")

    c.save()
    buf.seek(0)
    return buf.getvalue()

def export_checkins_csv():
    """Export checkins to CSV bytes"""
    if not st.session_state.get("checkins"):
        return None
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "name", "role", "org", "email", "event", "time", "method"])
    writer.writeheader()
    for ci in st.session_state.checkins.values():
        writer.writerow(ci)
    return buf.getvalue().encode()

def do_checkin(p_info, method="qr"):
    """Record a check-in"""
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    pid = p_info.get("id", "??")
    if pid in st.session_state.checkins:
        st.session_state.last_scan_result = {
            "type": "duplicate",
            "name": p_info.get("name", "Unknown"),
            "sub": "Already checked in"
        }
    else:
        st.session_state.checkins[pid] = {
            "id": pid,
            "name": p_info.get("name", ""),
            "role": p_info.get("role", ""),
            "org": p_info.get("org", ""),
            "email": p_info.get("email", ""),
            "event": st.session_state.get("event_name", ""),
            "time": now,
            "method": method,
        }
        st.session_state.last_scan_result = {
            "type": "ok",
            "name": p_info.get("name", "Unknown"),
            "sub": f"{p_info.get('role', '')} • {p_info.get('org', '')}".strip(" •")
        }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Header
st.markdown("""
<div class="cg-header">
    <div>
        <div class="cg-logo">Check<em>gate</em></div>
        <div class="cg-tagline">Event attendance management</div>
    </div>
    <div class="cg-badge">Ready</div>
</div>
""", unsafe_allow_html=True)

# Tabs
tab_gen, tab_scan, tab_attend, tab_settings = st.tabs(
    ["🎴 Card Generator", "📷 Scanner", "📋 Attendance", "⚙ Settings"]
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 1 — CARD GENERATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_gen:
    st.markdown("### Generate signed participant badge cards")
    st.markdown("Upload a CSV with participant data. Each person gets a static QR code signed with your secret key.")

    col_csv, col_key = st.columns(2)
    with col_csv:
        csv_file = st.file_uploader("Upload CSV", type=["csv"], key="gen_csv")
    with col_key:
        secret = st.text_input("Secret key", type="password", placeholder="e.g., mysecret123", key="gen_key")

    if csv_file and secret:
        rows, colmap = parse_participants_csv(csv_file)
        if not colmap.get("name"):
            st.error("CSV must have a 'name' column")
        else:
            st.success(f"✓ Found {len(rows)} participants")

            col_event, col_prefix, col_start = st.columns(3)
            with col_event:
                event = st.text_input("Event name", value=st.session_state.get("event_name", ""), key="gen_event")
            with col_prefix:
                prefix = st.text_input("Badge ID prefix", value="P", key="gen_prefix", max_chars=10)
            with col_start:
                start_num = st.number_input("Starting number", value=1, min_value=1, key="gen_start")

            if st.button("Generate Cards", use_container_width=True, key="gen_btn"):
                progress = st.progress(0)
                status = st.status("Generating...", expanded=True)

                cards_data = []
                participants_list = []

                for idx, row in enumerate(rows):
                    name = row.get(colmap["name"], f"Participant {idx+1}")
                    email = row.get(colmap.get("email"), "") if colmap.get("email") else ""
                    role = row.get(colmap.get("role"), "") if colmap.get("role") else ""
                    org = row.get(colmap.get("org"), "") if colmap.get("org") else ""
                    photo_url = row.get(colmap.get("photo"), "") if colmap.get("photo") else ""

                    pid = f"{prefix}{str(idx + start_num).zfill(4)}"
                    qr_payload = build_qr_payload(pid, name, email, event or "Event", secret)

                    # Generate QR
                    qr = qrcode.QRCode(version=1, box_size=10, border=2)
                    qr.add_data(qr_payload)
                    qr.make(fit=True)
                    qr_pil = qr.make_image(fill_color="black", back_color="white")

                    # Generate PDF
                    pdf_bytes = generate_card_pdf(pid, name, email, role, org, photo_url, qr_pil)

                    cards_data.append({"pid": pid, "name": name, "pdf": pdf_bytes})
                    participants_list.append({
                        "id": pid,
                        "name": name,
                        "email": email,
                        "role": role,
                        "org": org,
                    })

                    progress.progress((idx + 1) / len(rows))

                # Save to session
                st.session_state.generated_cards = cards_data
                st.session_state.participants = {p["id"]: p for p in participants_list}

                status.update(label=f"✓ Generated {len(cards_data)} cards", state="complete")
                st.success("Cards ready for download!")

                # Download individual PDFs
                st.markdown("#### Individual PDFs")
                cols = st.columns(3)
                for i, card in enumerate(cards_data[:12]):
                    with cols[i % 3]:
                        st.download_button(
                            label=f"📥 {card['name'][:15]}",
                            data=card["pdf"],
                            file_name=f"{card['pid']}-{card['name'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{i}",
                            use_container_width=True
                        )

                if len(cards_data) > 12:
                    st.info(f"Showing first 12 of {len(cards_data)} cards. Scroll to see more.")

                # ZIP download
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for card in cards_data:
                        zf.writestr(f"{card['pid']}-{card['name'].replace(' ', '_')}.pdf", card["pdf"])
                    zf.writestr("participants.json", json.dumps(participants_list, indent=2))

                zip_buf.seek(0)
                st.download_button(
                    "📦 Download all as ZIP",
                    zip_buf.getvalue(),
                    file_name=f"cards-{datetime.now().strftime('%Y%m%d-%H%M')}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 2 — SCANNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_scan:
    st.markdown("### 📷 Live QR Scanner")
    st.markdown("**Choose your scanning method below:**")

    # Initialize QR scan result in session
    if "scanned_qr" not in st.session_state:
        st.session_state.scanned_qr = None

    scanner_mode = st.radio("Scanning Method", 
                           ["📱 Phone Camera (Recommended)", "🔤 Manual ID Entry"],
                           horizontal=True, label_visibility="collapsed")

    if scanner_mode == "📱 Phone Camera (Recommended)":
        st.markdown("#### 📱 Phone Camera Scanner")
        st.markdown('<div class="info-box">✨ Tap "Start Scanner" and point your phone at the badge QR code. Works best in bright light.</div>', unsafe_allow_html=True)
        
        # HTML5 Camera Scanner with improved jsQR integration
        camera_html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
                    background: #0a0a0a; 
                    color: #fff;
                    padding: 0;
                }
                .scanner-container {
                    max-width: 100%;
                    margin: 0 auto;
                    padding: 16px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    min-height: 100vh;
                }
                .scanner-box {
                    position: relative;
                    width: 100%;
                    max-width: 400px;
                    aspect-ratio: 1;
                    background: #000;
                    border-radius: 12px;
                    overflow: hidden;
                    border: 2px solid #36d97e;
                    box-shadow: 0 0 20px rgba(54, 217, 126, 0.3);
                }
                #video {
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                    display: block;
                }
                #canvas { display: none; }
                .scanner-overlay {
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    width: 70%;
                    height: 70%;
                    border: 3px solid rgba(54, 217, 126, 0.5);
                    border-radius: 12px;
                    pointer-events: none;
                    box-shadow: inset 0 0 0 9999px rgba(0, 0, 0, 0.3);
                }
                .scanner-corners {
                    position: absolute;
                    width: 40px;
                    height: 40px;
                    border: 3px solid #36d97e;
                }
                .corner-tl { top: 10%; left: 10%; border-right: none; border-bottom: none; border-radius: 8px 0 0 0; }
                .corner-tr { top: 10%; right: 10%; border-left: none; border-bottom: none; border-radius: 0 8px 0 0; }
                .corner-bl { bottom: 10%; left: 10%; border-right: none; border-top: none; border-radius: 0 0 0 8px; }
                .corner-br { bottom: 10%; right: 10%; border-left: none; border-top: none; border-radius: 0 0 8px 0; }
                .controls {
                    margin-top: 20px;
                    width: 100%;
                    max-width: 400px;
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    justify-content: center;
                }
                button {
                    flex: 1;
                    min-width: 120px;
                    padding: 12px 20px;
                    font-size: 14px;
                    font-weight: 600;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.3s;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                #startBtn {
                    background: #36d97e;
                    color: #000;
                }
                #startBtn:hover { background: #2eb66f; box-shadow: 0 4px 12px rgba(54, 217, 126, 0.4); }
                #stopBtn {
                    background: #ff5f5f;
                    color: #fff;
                }
                #stopBtn:hover { background: #ff4444; }
                #stopBtn:disabled { opacity: 0.5; cursor: not-allowed; }
                .status {
                    margin-top: 16px;
                    padding: 12px 16px;
                    border-radius: 8px;
                    font-size: 13px;
                    text-align: center;
                    min-height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .status-idle { background: rgba(96, 165, 250, 0.1); color: #60a5fa; }
                .status-scanning { background: rgba(54, 217, 126, 0.1); color: #36d97e; animation: pulse 1.5s infinite; }
                .status-success { background: rgba(54, 217, 126, 0.2); color: #36d97e; }
                .status-error { background: rgba(255, 95, 95, 0.2); color: #ff5f5f; }
                @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
                .hint { font-size: 12px; color: #888; margin-top: 12px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="scanner-container">
                <div class="scanner-box">
                    <video id="video" playsinline></video>
                    <canvas id="canvas"></canvas>
                    <div class="scanner-overlay">
                        <div class="scanner-corners corner-tl"></div>
                        <div class="scanner-corners corner-tr"></div>
                        <div class="scanner-corners corner-bl"></div>
                        <div class="scanner-corners corner-br"></div>
                    </div>
                </div>
                <div class="controls">
                    <button id="startBtn" onclick="startCamera()">🎥 Start Scanner</button>
                    <button id="stopBtn" onclick="stopCamera()" disabled>⏹️ Stop</button>
                </div>
                <div class="status status-idle" id="status">Ready to scan</div>
                <div class="hint">📱 Allow camera access when prompted • Hold QR code in frame</div>
            </div>

            <script src="https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js"></script>
            <script>
                const video = document.getElementById('video');
                const canvas = document.getElementById('canvas');
                const statusDiv = document.getElementById('status');
                const startBtn = document.getElementById('startBtn');
                const stopBtn = document.getElementById('stopBtn');
                
                let ctx = canvas.getContext('2d', { willReadFrequently: true });
                let scanning = false;
                let lastScanned = null;

                async function startCamera() {
                    try {
                        statusDiv.textContent = '📹 Requesting camera access...';
                        statusDiv.className = 'status status-scanning';
                        
                        const stream = await navigator.mediaDevices.getUserMedia({
                            video: {
                                facingMode: 'environment',
                                width: { ideal: 1280 },
                                height: { ideal: 720 }
                            },
                            audio: false
                        });
                        
                        video.srcObject = stream;
                        video.setAttribute('playsinline', 'true');
                        video.onloadedmetadata = () => {
                            video.play().then(() => {
                                scanning = true;
                                startBtn.disabled = true;
                                stopBtn.disabled = false;
                                statusDiv.textContent = '✓ Scanning... Point at QR code';
                                statusDiv.className = 'status status-scanning';
                                scanFrame();
                            });
                        };
                    } catch (err) {
                        statusDiv.textContent = '❌ Camera access denied. Use manual entry below.';
                        statusDiv.className = 'status status-error';
                        console.error('Camera error:', err);
                    }
                }

                function stopCamera() {
                    scanning = false;
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                    
                    if (video.srcObject) {
                        video.srcObject.getTracks().forEach(track => track.stop());
                        video.srcObject = null;
                    }
                    statusDiv.textContent = 'Scanner stopped';
                    statusDiv.className = 'status status-idle';
                }

                function scanFrame() {
                    if (!scanning) return;

                    try {
                        if (video.readyState === video.HAVE_ENOUGH_DATA) {
                            canvas.width = video.videoWidth;
                            canvas.height = video.videoHeight;
                            
                            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                            
                            const code = jsQR(imageData.data, imageData.width, imageData.height, {
                                inversionAttempts: 'dontInvert'
                            });
                            
                            if (code) {
                                const qrData = code.data;
                                if (qrData !== lastScanned) {
                                    lastScanned = qrData;
                                    statusDiv.textContent = '✓ QR detected! Sending to app...';
                                    statusDiv.className = 'status status-success';
                                    
                                    // Send data to Streamlit via postMessage
                                    window.parent.postMessage({ 
                                        type: 'streamlit:setComponentValue', 
                                        value: qrData 
                                    }, '*');
                                    
                                    stopCamera();
                                    return;
                                }
                            }
                        }
                    } catch (err) {
                        console.error('Scan error:', err);
                    }

                    requestAnimationFrame(scanFrame);
                }

                // Ensure we clean up on page unload
                window.addEventListener('beforeunload', stopCamera);
            </script>
        </body>
        </html>
        """

        # Display the scanner
        try:
            import streamlit.components.v1 as components
            scanned_value = components.html(camera_html, height=700)
            
            # Process scanned QR code
            if scanned_value:
                st.session_state.scanned_qr = scanned_value
                st.rerun()
        except Exception as e:
            st.warning(f"⚠️ Camera component unavailable: {e}")
            st.info("Use the Manual ID Entry method below instead.")

    else:  # Manual ID Entry mode
        st.markdown("#### 🔤 Manual ID Entry")
        st.markdown("Enter the participant ID directly (e.g., P0001)")
        
        manual_pid = st.text_input(
            "Participant ID", 
            placeholder="e.g., P0001", 
            key="manual_pid_input",
            label_visibility="collapsed"
        )
        
        if st.button("✓ Check in", use_container_width=True, key="manual_checkin_btn"):
            if not manual_pid:
                st.error("Please enter a participant ID")
            elif manual_pid in st.session_state.get("participants", {}):
                p = st.session_state.participants[manual_pid]
                do_checkin(p, method="manual")
                st.session_state.last_scan_result = {
                    "type": "ok",
                    "name": p.get("name", "Unknown"),
                    "sub": f"{p.get('role', '')} • {p.get('org', '')}".strip(" •")
                }
                st.rerun()
            else:
                st.error(f"❌ ID '{manual_pid}' not found in participant list")
                st.session_state.last_scan_result = {
                    "type": "error",
                    "name": "Not Found",
                    "sub": "ID not in participant database"
                }

    st.markdown("---")
    
    # Result display
    result = st.session_state.get("last_scan_result")
    if result:
        if result["type"] == "ok":
            st.markdown(f'<div class="flash-ok"><div class="flash-name">✓ {result["name"]}</div>'
                       f'<div class="flash-sub">Successfully checked in • {result["sub"]}</div></div>', 
                       unsafe_allow_html=True)
        elif result["type"] == "duplicate":
            st.markdown(f'<div class="flash-dup"><div class="flash-name">⚠ {result["name"]}</div>'
                       f'<div class="flash-sub">{result["sub"]}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="flash-err"><div class="flash-name">✗ Error</div>'
                       f'<div class="flash-sub">{result["sub"]}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 🔢 Recent check-ins")
    recent = sorted(st.session_state.get("checkins", {}).values(),
                    key=lambda x: x["time"], reverse=True)[:10]
    if recent:
        for entry in recent:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06);">'
                f'<div><span style="font-weight:600;color:#e4ece6;">{entry["name"]}</span>'
                f'<br><span style="font-size:12px;color:#888;">{entry.get("role","") + " • " + entry.get("org","")}</span></div>'
                f'<span style="font-family:monospace;font-size:12px;color:#36d97e;text-align:right;">{entry["time"][11:16]}<br>{entry.get("method","")}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
    else:
        st.info("No check-ins yet. Start scanning QR codes or use manual entry.")

    st.markdown("---")
    st.markdown("#### 🔢 Recent check-ins")
    recent = sorted(st.session_state.get("checkins", {}).values(),
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 3 — ATTENDANCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_attend:
    inn = len(st.session_state.get("checkins", {}))
    total = len(st.session_state.get("participants", {}))
    pend = max(total - inn, 0)
    pct = f"{inn*100//total}%" if total else "–"

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
    for p in st.session_state.get("participants", {}).values():
        ci = st.session_state.get("checkins", {}).get(p["id"])
        all_rows.append({
            "Status":   "✓ In" if ci else "Pending",
            "ID":       p["id"],
            "Name":     p["name"],
            "Role":     p.get("role", ""),
            "Org":      p.get("org",  ""),
            "Time":     ci["time"][11:16] if ci else "",
            "Method":   ci.get("method","") if ci else "",
        })

    for pid, ci in st.session_state.get("checkins", {}).items():
        if pid not in st.session_state.get("participants", {}):
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
            "event": st.session_state.get("event_name", ""),
            "exportedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "checkins": list(st.session_state.get("checkins", {}).values()),
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TAB 4 — SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_settings:
    st.markdown("### Settings")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_event = st.text_input("Event name", value=st.session_state.get("event_name", ""), key="s_event")
        st.session_state.event_name = new_event

        new_key = st.text_input(
            "Secret signing key", type="password",
            value=st.session_state.get("secret_key", ""),
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
                data = json.load(imp_json)
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
