import streamlit as st
import sqlite3
from datetime import datetime
import pytz
from fpdf import FPDF
import hashlib
import pandas as pd
from io import BytesIO
from PIL import Image
import tempfile
import base64
import json

# ---------------------------
# CONFIG
# ---------------------------
DB_PATH = "maintenance_app.db"
st.set_page_config(page_title="Maintenance & Calibration System", layout="wide")

# ---------------------------
# HILANGKAN TOOLBAR STREAMLIT
# ---------------------------
hide_streamlit_style = """
    <style>
        [data-testid="stToolbar"] {visibility: hidden !important;}
        [data-testid="stDecoration"] {visibility: hidden !important;}
        [data-testid="stStatusWidget"] {visibility: hidden !important;}
        #MainMenu {visibility: hidden !important;}
        footer {visibility: hidden !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ---------------------------
# UTIL: BOOTSTRAP & MOBILE RESPONSIVE
# ---------------------------
def inject_bootstrap():
    st.markdown("""
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .stButton>button {border-radius: .5rem;}
        .card {padding:1.5rem; border-radius:.7rem; box-shadow:0 2px 6px rgba(0,0,0,0.08); margin-top:1rem;}
        .form-label {font-weight:600;}
        .small-muted {font-size:0.9rem;color:#6c757d;}
        
        /* Mobile Responsive Styles */
        @media (max-width: 768px) {
            .stDataFrame {
                font-size: 0.75rem !important;
                overflow-x: auto !important;
            }
            
            .stSelectbox, .stTextInput, .stTextArea {
                font-size: 0.9rem !important;
            }
            
            .card {
                padding: 0.8rem !important;
            }
            
            h1 {
                font-size: 1.5rem !important;
            }
            
            h2 {
                font-size: 1.3rem !important;
            }
            
            h3 {
                font-size: 1.1rem !important;
            }
            
            h4 {
                font-size: 1rem !important;
            }
            
            /* Compact table for checklist */
            .checklist-mobile {
                font-size: 0.7rem !important;
            }
            
            /* Better spacing for mobile */
            .stMarkdown {
                margin-bottom: 0.5rem !important;
            }
            
            /* Checkbox labels */
            .stCheckbox label {
                font-size: 0.8rem !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# DB FUNCTIONS
# ---------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        fullname TEXT,
        role TEXT,
        created_at TEXT,
        signature BLOB
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS checklist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        machine TEXT,
        sub_area TEXT,
        shift TEXT,
        item TEXT,
        condition TEXT,
        note TEXT,
        image_before BLOB,
        image_after BLOB,
        created_at TEXT,
        approved_by TEXT,
        approved_at TEXT,
        approval_status TEXT DEFAULT 'Pending',
        signature BLOB,
        details TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS calibration(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        instrument TEXT,
        procedure TEXT,
        result TEXT,
        remarks TEXT,
        created_at TEXT,
        approved_by TEXT,
        approved_at TEXT,
        approval_status TEXT DEFAULT 'Pending',
        signature BLOB
    )""")

    # Tambahkan kolom baru jika belum ada
    try:
        c.execute("ALTER TABLE users ADD COLUMN signature BLOB")
    except:
        pass
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN approved_by TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN approved_at TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN approval_status TEXT DEFAULT 'Pending'")
    except:
        pass
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN signature BLOB")
    except:
        pass
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN details TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE calibration ADD COLUMN approved_by TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE calibration ADD COLUMN approved_at TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE calibration ADD COLUMN approval_status TEXT DEFAULT 'Pending'")
    except:
        pass
    try:
        c.execute("ALTER TABLE calibration ADD COLUMN signature BLOB")
    except:
        pass

    # Update existing records
    try:
        c.execute("UPDATE checklist SET approval_status = 'Pending' WHERE approval_status IS NULL")
        c.execute("UPDATE calibration SET approval_status = 'Pending' WHERE approval_status IS NULL")
    except:
        pass

    default_users = [
        ("admin", "admin123", "Admin", "admin"),
        ("manager", "manager123", "Manager", "manager"),
        ("operator", "operator123", "Operator", "operator"),
        ("supervisor", "supervisor123", "Supervisor", "manager"),
    ]
    for username, password, fullname, role in default_users:
        try:
            c.execute("""
                INSERT INTO users (username, password_hash, fullname, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (username, hashlib.sha256((password+'salt2025').encode()).hexdigest(), fullname, role, datetime.now(pytz.timezone('Asia/Singapore')).isoformat()))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256((password+'salt2025').encode()).hexdigest()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, fullname, role, password_hash, signature FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and row[4] == hash_password(password):
        return True, {"id": row[0], "username": row[1], "fullname": row[2], "role": row[3], "signature": row[5]}
    return False, None

def save_signature(user_id, signature_data):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET signature = ? WHERE id = ?", (signature_data, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error saving signature: {e}")
        return False

def save_checklist_batch(user_id, date, machine, sub_area, shift, checklist_data, image_before=None, image_after=None):
    """Save multiple checklist items at once"""
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        img_before_binary = image_before.read() if image_before else None
        img_after_binary = image_after.read() if image_after else None
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        # Insert each item
        for item_data in checklist_data:
            details_json = json.dumps(item_data['details']) if item_data.get('details') else None
            
            c.execute("""
                INSERT INTO checklist (user_id, date, machine, sub_area, shift, item, condition, note, image_before, image_after, created_at, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, date_str, machine, sub_area, shift, 
                  item_data['item'], item_data['condition'], item_data['note'], 
                  img_before_binary, img_after_binary, now.isoformat(), details_json))
        
        conn.commit()
        conn.close()
        st.success(f"✅ {len(checklist_data)} item berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan checklist: {e}")
        return False

def save_checklist(user_id, date, machine, sub_area, shift, item, condition, note, image_before=None, image_after=None, details=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        img_before_binary = image_before.read() if image_before else None
        img_after_binary = image_after.read() if image_after else None
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        details_json = json.dumps(details) if details else None
        
        c.execute("""
            INSERT INTO checklist (user_id, date, machine, sub_area, shift, item, condition, note, image_before, image_after, created_at, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, date_str, machine, sub_area, shift, item, condition, note, img_before_binary, img_after_binary, now.isoformat(), details_json))
        conn.commit()
        conn.close()
        st.success("✅ Data berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan checklist: {e}")
        return False

def save_calibration(user_id, date, instrument, procedure, result, remarks):
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            INSERT INTO calibration (user_id, date, instrument, procedure, result, remarks, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, date_str, instrument, procedure, result, remarks, now.isoformat()))
        conn.commit()
        conn.close()
        st.success("✅ Data berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan calibration: {e}")
        return False

def get_checklists(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("""
            SELECT c.id, c.user_id, c.date, c.machine, c.sub_area, c.shift, c.item, c.condition, c.note, 
                   c.image_before, c.image_after, c.created_at, 
                   COALESCE(c.approved_by, '') as approved_by, 
                   COALESCE(c.approved_at, '') as approved_at, 
                   COALESCE(c.approval_status, 'Pending') as approval_status,
                   c.signature,
                   c.details,
                   u.fullname as input_by
            FROM checklist c 
            LEFT JOIN users u ON c.user_id = u.id 
            WHERE c.user_id=? 
            ORDER BY c.date DESC, c.id DESC
        """, (user_id,))
    else:
        c.execute("""
            SELECT c.id, c.user_id, c.date, c.machine, c.sub_area, c.shift, c.item, c.condition, c.note, 
                   c.image_before, c.image_after, c.created_at, 
                   COALESCE(c.approved_by, '') as approved_by, 
                   COALESCE(c.approved_at, '') as approved_at, 
                   COALESCE(c.approval_status, 'Pending') as approval_status,
                   c.signature,
                   c.details,
                   u.fullname as input_by
            FROM checklist c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.date DESC, c.id DESC
        """)
    rows = c.fetchall()
    conn.close()
    cols = ["id", "user_id", "date", "machine", "sub_area", "shift", "item", "condition", "note", "image_before", "image_after", "created_at", "approved_by", "approved_at", "approval_status", "signature", "details", "input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def get_calibrations(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("""
            SELECT c.id, c.user_id, c.date, c.instrument, c.procedure, c.result, c.remarks, c.created_at,
                   COALESCE(c.approved_by, '') as approved_by, 
                   COALESCE(c.approved_at, '') as approved_at, 
                   COALESCE(c.approval_status, 'Pending') as approval_status,
                   c.signature,
                   u.fullname as input_by
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            WHERE c.user_id=? 
            ORDER BY c.date DESC, c.id DESC
        """, (user_id,))
    else:
        c.execute("""
            SELECT c.id, c.user_id, c.date, c.instrument, c.procedure, c.result, c.remarks, c.created_at,
                   COALESCE(c.approved_by, '') as approved_by, 
                   COALESCE(c.approved_at, '') as approved_at, 
                   COALESCE(c.approval_status, 'Pending') as approval_status,
                   c.signature,
                   u.fullname as input_by
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.date DESC, c.id DESC
        """)
    rows = c.fetchall()
    conn.close()
    cols = ["id", "user_id", "date", "instrument", "procedure", "result", "remarks", "created_at", "approved_by", "approved_at", "approval_status", "signature", "input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def approve_checklist_batch(checklist_ids, manager_name, signature_data):
    """Approve multiple checklist items at once"""
    try:
        conn = get_conn()
        c = conn.cursor()
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        for checklist_id in checklist_ids:
            c.execute("""
                UPDATE checklist 
                SET approval_status = 'Approved', approved_by = ?, approved_at = ?, signature = ?
                WHERE id = ?
            """, (manager_name, now.isoformat(), signature_data, checklist_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"❌ Error approve batch: {e}")
        return False

def approve_checklist(checklist_id, manager_name, signature_data):
    try:
        conn = get_conn()
        c = conn.cursor()
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            UPDATE checklist 
            SET approval_status = 'Approved', approved_by = ?, approved_at = ?, signature = ?
            WHERE id = ?
        """, (manager_name, now.isoformat(), signature_data, checklist_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"❌ Error approve: {e}")
        return False

def approve_calibration(calibration_id, manager_name, signature_data):
    try:
        conn = get_conn()
        c = conn.cursor()
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            UPDATE calibration 
            SET approval_status = 'Approved', approved_by = ?, approved_at = ?, signature = ?
            WHERE id = ?
        """, (manager_name, now.isoformat(), signature_data, calibration_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"❌ Error approve: {e}")
        return False

# ---------------------------
# PDF GENERATOR
# ---------------------------
def generate_pdf_pope_reel(df_records, date, shift, user_name):
    """Generate PDF khusus untuk POPE REEL & KUSTER dengan semua 10 part dalam satu halaman"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "PREVENTIVE MAINTENANCE CHECKLIST PM1 - POPE REEL & KUSTER", ln=True, align="C")
    pdf.ln(3)
    
    # Info
    pdf.set_font("Arial", "", 9)
    pdf.cell(60, 6, f"Date: {date}", border=0)
    pdf.cell(60, 6, f"Shift: {shift}", border=0)
    pdf.cell(60, 6, f"Input and prepared by: {user_name}", border=0)
    pdf.ln(8)
    
    # Header Tabel
    headers = ["No", "Unit - Position", "Pneumatic", "Hydraulic", "Pressure", "Connector", "Sensor", "Pump", "Packing", "Display", "Accuracy", "Note"]
    col_widths = [10, 30, 21, 21, 21, 21, 21, 21, 21, 21, 21, 48]
    
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(200, 200, 200)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align='C', fill=True)
    pdf.ln()
    
    # Isi Tabel
    pdf.set_font("Arial", "", 6)
    for idx, (_, record) in enumerate(df_records.iterrows(), 1):
        details_str = record.get('details', '{}')
        try:
            details = json.loads(details_str) if details_str else {}
        except:
            details = {}
        
        # Status symbols
        def get_status(key):
            status = details.get(key, "OK")
            return "OK" if status == "OK" else "NG"
        
        values = [
            str(idx),
            record.get('item', '')[:35],
            get_status('pneumatic_cylinder'),
            get_status('hydraulic_cylinder'),
            get_status('pressure_gauge'),
            get_status('connector'),
            get_status('sensor'),
            get_status('pumps'),
            get_status('packing_seal'),
            get_status('display'),
            get_status('accuracy'),
            str(record.get('note', ''))[:60]
        ]
        
        # Warna untuk OK/NG
        for i, val in enumerate(values):
            if i >= 2 and i <= 10:  # Kolom check
                if val == "NG":
                    pdf.set_fill_color(255, 200, 200)  # Merah muda
                    pdf.cell(col_widths[i], 5, val, border=1, align='C', fill=True)
                    pdf.set_fill_color(255, 255, 255)
                else:
                    pdf.cell(col_widths[i], 5, val, border=1, align='C')
            else:
                pdf.cell(col_widths[i], 5, val, border=1, align='L' if i in [1, 11] else 'C')
        pdf.ln()
    
    # Legend
    pdf.ln(5)
    pdf.set_font("Arial", "I", 7)
    pdf.cell(0, 4, "Legend: OK = Kondisi Baik | NG = Ada Masalah (Background Merah)", align='L')
    
    # Approval Section
    if len(df_records) > 0:
        first_record = df_records.iloc[0]
        if first_record.get('approval_status') == 'Approved':
            pdf.ln(8)
            pdf.set_font("Arial", "B", 9)
            pdf.cell(0, 6, "APPROVAL SECTION", ln=True, align='C')
            pdf.ln(2)
            
            approved_by = str(first_record.get('approved_by', 'N/A'))
            approved_at_raw = first_record.get('approved_at', 'N/A')
            
            if approved_at_raw and approved_at_raw != 'N/A':
                try:
                    dt = datetime.fromisoformat(approved_at_raw)
                    approved_at = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    approved_at = str(approved_at_raw)
            else:
                approved_at = 'N/A'
            
            pdf.set_font("Arial", "", 8)
            pdf.cell(70, 6, f"Approved and Reviewed by chief manager : {approved_by}", border=1)
            pdf.cell(70, 6, f"Date: {approved_at}", border=1)
            pdf.ln(8)
            
            # Signature
            signature_data = first_record.get("signature")
            if signature_data and isinstance(signature_data, bytes) and len(signature_data) > 0:
                pdf.set_font("Arial", "B", 8)
                pdf.cell(30, 5, "Signature:", border=0)
                pdf.ln(6)
                
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as tmp:
                        tmp.write(signature_data)
                        tmp.flush()
                        current_x = pdf.get_x()
                        current_y = pdf.get_y()
                        pdf.image(tmp.name, x=current_x + 5, y=current_y, w=50, h=20)
                        pdf.ln(22)
                except:
                    pass
    
    try:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")
    except:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")

def generate_pdf_wrapping_rewinder(df_records, date, shift, user_name):
    """Generate PDF khusus untuk WRAPPING & REWINDER dengan semua 11 part dalam satu halaman"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "CHECKLIST MAINTENANCE - WRAPPING & REWINDER", ln=True, align="C")
    pdf.ln(3)
    
    # Info
    pdf.set_font("Arial", "", 9)
    pdf.cell(60, 6, f"Date: {date}", border=0)
    pdf.cell(60, 6, f"Shift: {shift}", border=0)
    pdf.cell(60, 6, f"Input by: {user_name}", border=0)
    pdf.ln(8)
    
    # Header Tabel
    headers = ["No", "Part", "Pneu", "Hydr", "Press", "Conn", "Sens", "Pump", "Pack", "Disp", "Accu", "Note"]
    col_widths = [10, 45, 10, 10, 10, 10, 10, 10, 10, 10, 10, 82]
    
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(200, 200, 200)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 6, h, border=1, align='C', fill=True)
    pdf.ln()
    
    # Isi Tabel
    pdf.set_font("Arial", "", 6)
    for idx, (_, record) in enumerate(df_records.iterrows(), 1):
        details_str = record.get('details', '{}')
        try:
            details = json.loads(details_str) if details_str else {}
        except:
            details = {}
        
        # Status symbols
        def get_status(key):
            status = details.get(key, "OK")
            return "OK" if status == "OK" else "NG"
        
        values = [
            str(idx),
            record.get('item', '')[:35],
            get_status('pneumatic_cylinder'),
            get_status('hydraulic_cylinder'),
            get_status('pressure_gauge'),
            get_status('connector'),
            get_status('sensor'),
            get_status('pumps'),
            get_status('packing_seal'),
            get_status('display'),
            get_status('accuracy'),
            str(record.get('note', ''))[:60]
        ]
        
        # Warna untuk OK/NG
        for i, val in enumerate(values):
            if i >= 2 and i <= 10:  # Kolom check
                if val == "NG":
                    pdf.set_fill_color(255, 200, 200)  # Merah muda
                    pdf.cell(col_widths[i], 5, val, border=1, align='C', fill=True)
                    pdf.set_fill_color(255, 255, 255)
                else:
                    pdf.cell(col_widths[i], 5, val, border=1, align='C')
            else:
                pdf.cell(col_widths[i], 5, val, border=1, align='L' if i in [1, 11] else 'C')
        pdf.ln()
    
    # Legend
    pdf.ln(5)
    pdf.set_font("Arial", "I", 7)
    pdf.cell(0, 4, "Legend: OK = Kondisi Baik | NG = Ada Masalah (Background Merah)", align='L')
    
    # Approval Section
    if len(df_records) > 0:
        first_record = df_records.iloc[0]
        if first_record.get('approval_status') == 'Approved':
            pdf.ln(8)
            pdf.set_font("Arial", "B", 9)
            pdf.cell(0, 6, "APPROVAL SECTION", ln=True, align='C')
            pdf.ln(2)
            
            approved_by = str(first_record.get('approved_by', 'N/A'))
            approved_at_raw = first_record.get('approved_at', 'N/A')
            
            if approved_at_raw and approved_at_raw != 'N/A':
                try:
                    dt = datetime.fromisoformat(approved_at_raw)
                    approved_at = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    approved_at = str(approved_at_raw)
            else:
                approved_at = 'N/A'
            
            pdf.set_font("Arial", "", 8)
            pdf.cell(60, 6, f"Approved by: {approved_by}", border=1)
            pdf.cell(60, 6, f"Date: {approved_at}", border=1)
            pdf.ln(8)
            
            # Signature
            signature_data = first_record.get("signature")
            if signature_data and isinstance(signature_data, bytes) and len(signature_data) > 0:
                pdf.set_font("Arial", "B", 8)
                pdf.cell(30, 5, "Signature:", border=0)
                pdf.ln(6)
                
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as tmp:
                        tmp.write(signature_data)
                        tmp.flush()
                        current_x = pdf.get_x()
                        current_y = pdf.get_y()
                        pdf.image(tmp.name, x=current_x + 5, y=current_y, w=50, h=20)
                        pdf.ln(22)
                except:
                    pass
    
    try:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")
    except:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")

def generate_pdf(record, title):
    """PDF generator untuk checklist biasa"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    # Judul
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.ln(8)

    # Header Tabel
    if title == "Checklist Maintenance":
        headers = ["Id", "User", "Date & Time", "Machine", "Sub Area", "Shift", "Item", "Condition", "Note", "Status"]
        col_widths = [10, 20, 30, 37, 28, 15, 24, 20, 60, 23]
    else:
        headers = ["Id", "User", "Date & Time", "Instrument", "Procedure", "Result", "Remarks", "Status"]
        col_widths = [10, 20, 30, 35, 70, 20, 60, 22]

    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align='C', fill=True)
    pdf.ln()

    # Isi Tabel
    pdf.set_font("Arial", "", 8)
    
    created_at = record.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            datetime_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            datetime_str = str(record.get("date", ""))
    else:
        datetime_str = str(record.get("date", ""))
    
    user_name = str(record.get("input_by", ""))[:18]
    approval_status = str(record.get("approval_status", "Pending"))
    
    if title == "Checklist Maintenance":
        values = [
            str(record.get("id", "")),
            user_name,
            datetime_str,
            str(record.get("machine", ""))[:30],
            str(record.get("sub_area", ""))[:20],
            str(record.get("shift", "")),
            str(record.get("item", ""))[:16],
            str(record.get("condition", "")),
            str(record.get("note", ""))[:120],
            approval_status
        ]
    else:
        values = [
            str(record.get("id", "")),
            user_name,
            datetime_str,
            str(record.get("instrument", ""))[:26],
            str(record.get("procedure", ""))[:130],
            str(record.get("result", "")),
            str(record.get("remarks", ""))[:110],
            approval_status
        ]
    
    max_lines = 1
    for i, val in enumerate(values):
        chars_per_line = int(col_widths[i] / 2.3)
        lines_needed = max(1, (len(val) // chars_per_line) + 1)
        max_lines = max(max_lines, lines_needed)
    
    row_height = max(8, min(max_lines * 4, 25))
    
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    
    for i, val in enumerate(values):
        pdf.set_xy(x_start + sum(col_widths[:i]), y_start)
        pdf.multi_cell(col_widths[i], 4, val, border=1, align='L')
    
    pdf.set_xy(x_start, y_start + row_height)
    pdf.ln(8)

    # Approval Section
    if record.get("approval_status") == "Approved":
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 6, "APPROVAL SECTION", ln=True, align='C')
        pdf.ln(3)
        
        approved_by = str(record.get('approved_by', 'N/A'))
        approved_at_raw = record.get('approved_at', 'N/A')
        
        if approved_at_raw and approved_at_raw != 'N/A':
            try:
                dt = datetime.fromisoformat(approved_at_raw)
                approved_at = dt.strftime("%Y-%m-%d %H:%M")
            except:
                approved_at = str(approved_at_raw)
        else:
            approved_at = 'N/A'
        
        pdf.set_font("Arial", "", 9)
        pdf.cell(70, 8, f"Approved by: {approved_by}", border=1, align='L')
        pdf.cell(70, 8, f"Date: {approved_at}", border=1, align='L')
        pdf.ln(10)
        
        # Signature
        signature_data = record.get("signature")
        pdf.set_font("Arial", "B", 9)
        pdf.cell(40, 6, "Signature:", border=0, align='L')
        pdf.ln(8)
        
        if signature_data and isinstance(signature_data, bytes) and len(signature_data) > 0:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as tmp:
                    tmp.write(signature_data)
                    tmp.flush()
                    current_x = pdf.get_x()
                    current_y = pdf.get_y()
                    pdf.image(tmp.name, x=current_x + 10, y=current_y, w=60, h=25)
                    pdf.ln(28)
                    pdf.set_draw_color(0, 0, 0)
                    pdf.line(current_x + 10, current_y + 25, current_x + 70, current_y + 25)
            except:
                pdf.set_font("Arial", "I", 8)
                pdf.cell(0, 6, "[Signature not available]", align='L')
                pdf.ln()
        else:
            pdf.set_font("Arial", "I", 8)
            pdf.cell(0, 6, "[No digital signature]", align='L')
            pdf.ln()
        
        pdf.ln(5)

    # Gambar Before-After
    if title == "Checklist Maintenance" and (record.get("image_before") or record.get("image_after")):
        pdf.ln(3)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 8, "Before vs After", ln=True, align="C")
        pdf.ln(4)

        img_w, img_h = 90, 70
        y_pos = pdf.get_y()

        if record.get("image_before"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(record["image_before"])
                    tmp.flush()
                    pdf.image(tmp.name, x=30, y=y_pos, w=img_w, h=img_h)
                    pdf.set_font("Arial", "B", 10)
                    pdf.text(x=65, y=y_pos + img_h + 4, txt="Before")
            except:
                pass

        if record.get("image_after"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(record["image_after"])
                    tmp.flush()
                    pdf.image(tmp.name, x=150, y=y_pos, w=img_w, h=img_h)
                    pdf.set_font("Arial", "B", 10)
                    pdf.text(x=185, y=y_pos + img_h + 4, txt="After")
            except:
                pass

    try:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")
    except:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")

# ---------------------------
# MAIN APP
# ---------------------------
def main():
    inject_bootstrap()
    init_db()

    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
        st.session_state['user'] = None

    st.markdown("<div class='card'><h2>Maintenance & Calibration System</h2><p class='small-muted'>Gunakan akun yang sudah ditentukan.</p></div>", unsafe_allow_html=True)

    if not st.session_state['auth']:
        conn = get_conn()
        usernames = pd.read_sql("SELECT username FROM users", conn)['username'].tolist()
        conn.close()

        st.subheader("🔐 Login")
        with st.form("login_form"):
            selected_user = st.selectbox("Pilih Username", usernames)
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)
            if submit:
                ok, user = verify_user(selected_user, password)
                if ok:
                    st.session_state['auth'] = True
                    st.session_state['user'] = user
                    st.success(f"Login berhasil sebagai {user['role'].capitalize()}")
                    st.rerun()
                else:
                    st.error("Login gagal. Password salah.")
        st.stop()

    user = st.session_state['user']
    st.success(f"Halo, {user['fullname']} ({user['role']})")
    
    # Menu
    if user['role'] == 'manager':
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration", "Profile"], horizontal=True)
    elif user['role'] == 'admin':
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration", "Admin Dashboard"], horizontal=True)
    else:
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration"], horizontal=True)

    # === Profile Menu ===
    if menu == "Profile" and user['role'] == 'manager':
        st.header("👤 Manager Profile")
        st.write(f"**Nama:** {user['fullname']}")
        st.write(f"**Username:** {user['username']}")
        st.write(f"**Role:** {user['role']}")
        
        st.markdown("---")
        st.subheader("✍️ Upload Tanda Tangan")
        st.info("Upload tanda tangan Anda untuk digunakan saat approval")
        
        signature_file = st.file_uploader("Upload gambar tanda tangan (PNG/JPG)", type=['png', 'jpg', 'jpeg'])
        
        if signature_file:
            st.image(signature_file, width=200, caption="Preview Tanda Tangan")
            if st.button("💾 Simpan Tanda Tangan"):
                sig_data = signature_file.read()
                if save_signature(user['id'], sig_data):
                    st.success("✅ Tanda tangan berhasil disimpan!")
                    st.session_state['user']['signature'] = sig_data
                    st.rerun()
        
        if user.get('signature'):
            st.success("✅ Anda sudah memiliki tanda tangan tersimpan")

    # === Checklist ===
    elif menu == "Checklist":
        st.header("Checklist Maintenance Harian")
        if user['role'] in ['admin', 'operator']:
            with st.form("checklist_form", clear_on_submit=True):
                col1, col2 = st.columns([3, 1])
                date = col1.date_input("Tanggal", value=datetime.today())
                machine = col1.selectbox("Machine / Area", ["Papper Machine 1", "Papper Machine 2", "Boiler", "WWTP", "Other"])
                
                sub_area_options = {
                    "Papper Machine 1": [
                        "WRAPPING & REWINDER",
                        "POPE REEL & KUSTER",
                        "DRYER GROUP 1 & 2",
                        "DRYER GROUP 3, 4 & 5",
                        "DRYER GROUP 6 & 7",
                        "PRESS 1, 2 & 3",
                        "WIRE AREA",
                        "STOCK PREPARATION AREA"
                    ],
                    "Papper Machine 2": ["Wire Section", "Press Section", "Dryer Section", "Calendar", "Reel"],
                    "Boiler": ["Feed Pump", "Burner", "Economizer", "Air Fan", "Water Softener"],
                    "WWTP": ["Blower", "Screening", "Clarifier", "Sludge Pump", "Equalization Tank"],
                    "Other": ["Workshop", "Office", "Warehouse"]
                }
                sub_area = col1.selectbox("Sub Area", sub_area_options.get(machine, ["N/A"]))
                shift = col2.selectbox("Shift", ["Pagi", "Siang", "Malam"])
                
                is_wrapping_rewinder = (machine == "Papper Machine 1" and sub_area == "WRAPPING & REWINDER")
                is_pope_reel = (machine == "Papper Machine 1" and sub_area == "POPE REEL & KUSTER")
                
                if is_wrapping_rewinder or is_pope_reel:
                    # Tentukan parts list berdasarkan area
                    if is_wrapping_rewinder:
                        area_title = "WRAPPING & REWINDER"
                        parts_list = [
                            "P1 - Upender",
                            "P2 - Winder Platform",
                            "P3 - Winder Rope Feed",
                            "P4 - Winder Drive Stretcher",
                            "P5 - Winder Blade",
                            "P6 - Winder Blade Roll",
                            "P7 - Winder Belt Stretcher",
                            "P8 - Winder Drive Lock",
                            "P9 - Winder Brake",
                            "P10 - Power Pack Unit",
                            "P11 - Paper Care"
                        ]
                    else:  # POPE REEL & KUSTER
                        area_title = "POPE REEL & KUSTER"
                        parts_list = [
                            "P1 - Power Pack Unit",
                            "P2 - Primary Arm Hydraulic",
                            "P3 - Secondary Arm Hydraulic",
                            "P4 - Pneumatic Clamping",
                            "P5 - Pneumatic Stopper Reel",
                            "P6 - Air Clutch",
                            "P7 - Pneumatic Brake",
                            "P8 - Kuster",
                            "P9 - PV COM",
                            "P10 - Seml Scan (0-Frame)"
                        ]
                    
                    st.markdown(f"### 📋 Checklist - {area_title}")
                    st.info("Centang ✓ jika OK, kosongkan jika ada masalah")
                    
                    if 'checklist_table' not in st.session_state:
                        st.session_state.checklist_table = {}
                    
                    # Mobile-friendly layout
                    for idx, part in enumerate(parts_list):
                        with st.expander(f"**{part}**", expanded=False):
                            st.markdown(f"##### {part}")
                            
                            # Compact layout untuk mobile
                            col_check1, col_check2, col_check3 = st.columns(3)
                            
                            with col_check1:
                                st.markdown("**Mechanical:**")
                                pneumatic = st.checkbox("Pneumatic", value=True, key=f"pn_{idx}")
                                hydraulic = st.checkbox("Hydraulic", value=True, key=f"hy_{idx}")
                                pressure = st.checkbox("Pressure", value=True, key=f"pr_{idx}")
                            
                            with col_check2:
                                st.markdown("**Electrical:**")
                                connector = st.checkbox("Connector", value=True, key=f"co_{idx}")
                                sensor = st.checkbox("Sensor", value=True, key=f"se_{idx}")
                                display = st.checkbox("Display", value=True, key=f"di_{idx}")
                            
                            with col_check3:
                                st.markdown("**Others:**")
                                pumps = st.checkbox("Pumps", value=True, key=f"pu_{idx}")
                                packing = st.checkbox("Packing", value=True, key=f"pa_{idx}")
                                accuracy = st.checkbox("Accuracy", value=True, key=f"ac_{idx}")
                            
                            note_part = st.text_input("📝 Note", key=f"note_{idx}", placeholder="Catatan untuk part ini...")
                            
                            # Status indicator
                            all_ok = pneumatic and hydraulic and pressure and connector and sensor and pumps and packing and display and accuracy
                            if all_ok:
                                st.success("✅ Semua komponen OK")
                            else:
                                st.warning("⚠️ Ada komponen yang perlu perhatian")
                            
                            st.session_state.checklist_table[part] = {
                                'pneumatic': pneumatic,
                                'hydraulic': hydraulic,
                                'pressure': pressure,
                                'connector': connector,
                                'sensor': sensor,
                                'pumps': pumps,
                                'packing': packing,
                                'display': display,
                                'accuracy': accuracy,
                                'note': note_part
                            }
                    
                    st.markdown("---")
                    st.markdown("#### 📷 Upload Gambar (Opsional)")
                    col_img1, col_img2 = st.columns(2)
                    image_before = col_img1.file_uploader("Foto Before", type=['png', 'jpg', 'jpeg'], key="before")
                    image_after = col_img2.file_uploader("Foto After", type=['png', 'jpg', 'jpeg'], key="after")
                    
                    if st.form_submit_button("💾 Simpan Semua Checklist", use_container_width=True):
                        checklist_data = []
                        for part, data in st.session_state.checklist_table.items():
                            all_ok = all([data['pneumatic'], data['hydraulic'], data['pressure'], 
                                        data['connector'], data['sensor'], data['pumps'], 
                                        data['packing'], data['display'], data['accuracy']])
                            condition = "Good" if all_ok else "Minor"
                            
                            details = {
                                "pneumatic_cylinder": "OK" if data['pneumatic'] else "NG",
                                "hydraulic_cylinder": "OK" if data['hydraulic'] else "NG",
                                "pressure_gauge": "OK" if data['pressure'] else "NG",
                                "connector": "OK" if data['connector'] else "NG",
                                "sensor": "OK" if data['sensor'] else "NG",
                                "pumps": "OK" if data['pumps'] else "NG",
                                "packing_seal": "OK" if data['packing'] else "NG",
                                "display": "OK" if data['display'] else "NG",
                                "accuracy": "OK" if data['accuracy'] else "NG"
                            }
                            
                            checklist_data.append({
                                'item': part,
                                'condition': condition,
                                'note': data['note'],
                                'details': details
                            })
                        
                        if save_checklist_batch(user['id'], date, machine, sub_area, shift, checklist_data, image_before, image_after):
                            st.session_state.checklist_table = {}
                            st.rerun()
                
                else:
                    item_options = {
                        "Papper Machine 1": {"default": ["Motor", "Pump", "Bearing", "Belt", "Gearbox", "Oil Level", "Sensor", "Other"]},
                        "Papper Machine 2": {"default": ["Motor", "Pump", "Bearing", "Belt", "Gearbox", "Oil Level", "Sensor", "Other"]},
                        "Boiler": {"default": ["Motor", "Pump", "Bearing", "Belt", "Valve", "Pressure Gauge", "Temperature Sensor", "Other"]},
                        "WWTP": {"default": ["Motor", "Pump", "Bearing", "Belt", "Valve", "Sensor", "Other"]},
                        "Other": {"default": ["Motor", "Pump", "Bearing", "Belt", "Gearbox", "Oil Level", "Sensor", "Other"]}
                    }
                    
                    item_list = item_options.get(machine, {}).get("default", ["Motor", "Pump", "Bearing", "Belt", "Gearbox", "Oil Level", "Sensor", "Other"])
                    item = col1.selectbox("Item yang diperiksa", item_list)
                    condition = col1.selectbox("Condition", ["Good", "Minor", "Bad"])
                    note = st.text_area("Keterangan / Temuan")
                    
                    st.markdown("#### 📷 Upload Gambar (Opsional)")
                    col_img1, col_img2 = st.columns(2)
                    image_before = col_img1.file_uploader("Foto Before", type=['png', 'jpg', 'jpeg'], key="before")
                    image_after = col_img2.file_uploader("Foto After", type=['png', 'jpg', 'jpeg'], key="after")

                    if st.form_submit_button("💾 Simpan Checklist", use_container_width=True):
                        if save_checklist(user['id'], date, machine, sub_area, shift, item, condition, note, image_before, image_after, None):
                            st.rerun()

        st.subheader("📋 Daftar Checklist")
        df = get_checklists() if user['role'] in ['admin', 'manager'] else get_checklists(user_id=user['id'])
        if not df.empty:
            # Tampilan mobile-friendly
            st.info(f"Total: {len(df)} checklist")
            
            # Compact display untuk mobile
            display_df = df[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'approval_status']]
            
            # Make dataframe scrollable on mobile
            st.markdown('<div class="checklist-mobile">', unsafe_allow_html=True)
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Approval untuk Manager
            if user['role'] == 'manager':
                st.markdown("### ✅ Approval Checklist")
                pending_df = df[df['approval_status'] == 'Pending']
                
                if not pending_df.empty:
                    # Cek apakah ada WRAPPING & REWINDER atau POPE REEL & KUSTER
                    wrapping_pending = pending_df[(pending_df['machine'] == 'Papper Machine 1') & (pending_df['sub_area'] == 'WRAPPING & REWINDER')]
                    pope_pending = pending_df[(pending_df['machine'] == 'Papper Machine 1') & (pending_df['sub_area'] == 'POPE REEL & KUSTER')]
                    
                    # Gabungkan untuk batch approval
                    batch_pending = pd.concat([wrapping_pending, pope_pending])
                    
                    if not batch_pending.empty:
                        st.markdown("#### 🔧 Batch Approval - PM1 Detailed Checklist")
                        st.info("Approve semua checklist untuk satu shift sekaligus")
                        
                        # Group by sub_area, date and shift
                        unique_sessions = batch_pending.groupby(['sub_area', 'date', 'shift']).size().reset_index()[['sub_area', 'date', 'shift']]
                        
                        # Mobile-friendly layout
                        session_options = [""] + [f"{row['sub_area']} - {row['date']} - Shift {row['shift']}" for _, row in unique_sessions.iterrows()]
                        sel_session = st.selectbox("📅 Pilih Area, Tanggal & Shift", session_options, key="approve_session")
                        
                        if sel_session:
                            parts = sel_session.split(" - ")
                            selected_area = parts[0]
                            selected_date = parts[1]
                            selected_shift = parts[2].replace("Shift ", "")
                            
                            session_df = batch_pending[(batch_pending['sub_area'] == selected_area) & 
                                                       (batch_pending['date'] == selected_date) & 
                                                       (batch_pending['shift'] == selected_shift)]
                            
                            st.success(f"✅ Total {len(session_df)} items akan di-approve")
                            
                            # Compact preview untuk mobile
                            with st.expander("📋 Lihat Detail Items", expanded=False):
                                for _, row in session_df.iterrows():
                                    st.write(f"• **{row['item']}** - {row['condition']}")
                            
                            st.markdown("#### ✍️ Tanda Tangan")
                            
                            if user.get('signature'):
                                st.success("✅ Tanda tangan tersimpan")
                                
                                # Compact signature preview
                                with st.expander("👁️ Preview Tanda Tangan", expanded=False):
                                    try:
                                        sig_bytes = user['signature']
                                        if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                            st.image(sig_bytes, width=150)
                                    except:
                                        pass
                                
                                use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_batch")
                                
                                if not use_saved:
                                    new_signature = st.file_uploader("Upload baru", type=['png', 'jpg', 'jpeg'], key="new_sig_batch")
                                    signature_to_use = new_signature.read() if new_signature else None
                                else:
                                    signature_to_use = user['signature']
                            else:
                                st.warning("⚠️ Upload tanda tangan di Profile")
                                signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_batch")
                                signature_to_use = signature_upload.read() if signature_upload else None
                            
                            if signature_to_use:
                                if st.button("✅ Approve Semua", key="btn_approve_batch", use_container_width=True):
                                    if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                        checklist_ids = session_df['id'].tolist()
                                        if approve_checklist_batch(checklist_ids, user['fullname'], signature_to_use):
                                            st.success(f"✅ {len(checklist_ids)} checklist berhasil di-approve!")
                                            st.rerun()
                                    else:
                                        st.error("❌ Data tanda tangan tidak valid!")
                            else:
                                st.button("✅ Approve Semua (Upload signature dulu)", disabled=True, use_container_width=True)
                        
                        st.markdown("---")
                    
                    # Individual Approval untuk checklist lainnya
                    st.markdown("---")
                    st.markdown("#### 📋 Individual Approval")
                    detailed_areas = ['WRAPPING & REWINDER', 'POPE REEL & KUSTER']
                    non_batch_pending = pending_df[~((pending_df['machine'] == 'Papper Machine 1') & 
                                                     (pending_df['sub_area'].isin(detailed_areas)))]
                    
                    if not non_batch_pending.empty:
                        sel_approve = st.selectbox("Pilih ID", [""] + non_batch_pending['id'].astype(str).tolist(), key="approve_individual")
                        
                        if sel_approve:
                            preview_data = non_batch_pending[non_batch_pending['id'] == int(sel_approve)].iloc[0]
                            
                            # Compact preview untuk mobile
                            with st.expander("📋 Preview Data", expanded=True):
                                st.write(f"**Machine:** {preview_data['machine']}")
                                st.write(f"**Sub Area:** {preview_data['sub_area']}")
                                st.write(f"**Item:** {preview_data['item']}")
                                st.write(f"**Condition:** {preview_data['condition']}")
                            
                            st.markdown("#### ✍️ Tanda Tangan")
                            
                            if user.get('signature'):
                                st.success("✅ Tanda tangan tersimpan")
                                
                                with st.expander("👁️ Preview", expanded=False):
                                    try:
                                        sig_bytes = user['signature']
                                        if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                            st.image(sig_bytes, width=150)
                                    except:
                                        pass
                                
                                use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_ind")
                                
                                if not use_saved:
                                    new_signature = st.file_uploader("Upload baru", type=['png', 'jpg', 'jpeg'], key="new_sig_ind")
                                    signature_to_use = new_signature.read() if new_signature else None
                                else:
                                    signature_to_use = user['signature']
                            else:
                                st.warning("⚠️ Upload di Profile")
                                signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_ind")
                                signature_to_use = signature_upload.read() if signature_upload else None
                            
                            if signature_to_use:
                                if st.button("✅ Approve", key="btn_approve_individual", use_container_width=True):
                                    if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                        if approve_checklist(int(sel_approve), user['fullname'], signature_to_use):
                                            st.success(f"✅ Checklist ID {sel_approve} berhasil di-approve!")
                                            st.rerun()
                                    else:
                                        st.error("❌ Tanda tangan tidak valid!")
                            else:
                                st.button("✅ Approve (Upload signature dulu)", disabled=True, use_container_width=True)
                    else:
                        st.info("Tidak ada checklist individual yang perlu di-approve")
                else:
                    st.info("✅ Semua checklist sudah di-approve")
            
            # Download PDF
            st.markdown("---")
            st.subheader("📄 Download PDF Report")
            
            # Filter untuk detailed checklist areas (WRAPPING & REWINDER dan POPE REEL & KUSTER)
            detailed_areas = ['WRAPPING & REWINDER', 'POPE REEL & KUSTER']
            detailed_df = df[(df['machine'] == 'Papper Machine 1') & (df['sub_area'].isin(detailed_areas))]
            
            if not detailed_df.empty:
                # Group by sub_area, date and shift
                unique_sessions = detailed_df.groupby(['sub_area', 'date', 'shift']).size().reset_index()[['sub_area', 'date', 'shift']]
                
                st.markdown("#### 🔧 PM1 Detailed Checklist (All Parts in One PDF)")
                session_options = [""] + [f"{row['sub_area']} - {row['date']} - Shift {row['shift']}" for _, row in unique_sessions.iterrows()]
                sel_session = st.selectbox("Pilih Area, Tanggal & Shift", session_options, key="pdf_detailed")
                
                if sel_session:
                    parts = sel_session.split(" - ")
                    selected_area = parts[0]
                    selected_date = parts[1]
                    selected_shift = parts[2].replace("Shift ", "")
                    
                    session_df = detailed_df[(detailed_df['sub_area'] == selected_area) & 
                                            (detailed_df['date'] == selected_date) & 
                                            (detailed_df['shift'] == selected_shift)]
                    
                    if not session_df.empty:
                        first_rec = session_df.iloc[0]
                        
                        # Gunakan PDF generator yang sesuai
                        if selected_area == 'WRAPPING & REWINDER':
                            pdf_bytes = generate_pdf_wrapping_rewinder(
                                session_df, selected_date, selected_shift, first_rec.get('input_by', 'N/A')
                            )
                            filename = f"wrapping_rewinder_{selected_date}_{selected_shift}.pdf"
                        else:  # POPE REEL & KUSTER
                            pdf_bytes = generate_pdf_pope_reel(
                                session_df, selected_date, selected_shift, first_rec.get('input_by', 'N/A')
                            )
                            filename = f"pope_reel_kuster_{selected_date}_{selected_shift}.pdf"
                        
                        st.download_button(
                            f"📄 Download PDF - {selected_area}", 
                            data=pdf_bytes, 
                            file_name=filename, 
                            mime="application/pdf"
                        )
            
            # Download individual checklist
            st.markdown("#### 📋 Individual Checklist PDF")
            detailed_areas = ['WRAPPING & REWINDER', 'POPE REEL & KUSTER']
            non_detailed_df = df[~((df['machine'] == 'Papper Machine 1') & (df['sub_area'].isin(detailed_areas)))]
            
            if not non_detailed_df.empty:
                sel = st.selectbox("Pilih ID untuk download", [""] + non_detailed_df['id'].astype(str).tolist(), key="pdf_individual")
                if sel:
                    rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                    pdf_bytes = generate_pdf(rec, "Checklist Maintenance")
                    st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"checklist_{sel}.pdf", mime="application/pdf")
            else:
                st.info("Tidak ada checklist individual untuk di-download")
                
        else:
            st.info("Belum ada data checklist.")

    # === Calibration ===
    elif menu == "Calibration":
        st.header("Calibration Report")
        if user['role'] == "admin":
            with st.form("cal_form", clear_on_submit=True):
                date = st.date_input("Tanggal Kalibrasi", value=datetime.today())
                instrument = st.selectbox("Instrument", ["Multimeter", "Pressure Gauge", "Thermometer", "Flow Meter", "Other"])
                procedure = st.text_area("Prosedur Singkat")
                result = st.selectbox("Hasil", ["Pass", "Fail", "Adjust"])
                remarks = st.text_area("Catatan / Rekomendasi")
                if st.form_submit_button("💾 Simpan Calibration Report", use_container_width=True):
                    if save_calibration(user['id'], date, instrument, procedure, result, remarks):
                        st.rerun()

        st.subheader("📋 Daftar Calibration")
        df = get_calibrations() if user['role'] in ['admin', 'manager'] else get_calibrations(user_id=user['id'])
        if not df.empty:
            display_df = df[['id', 'date', 'instrument', 'procedure', 'result', 'remarks', 'approval_status']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Approval untuk Manager
            if user['role'] == 'manager':
                st.markdown("### ✅ Approval Calibration")
                pending_df = df[df['approval_status'] == 'Pending']
                if not pending_df.empty:
                    col1, col2 = st.columns([3, 1])
                    sel_approve = col1.selectbox("Pilih ID untuk Approve", [""] + pending_df['id'].astype(str).tolist(), key="approve_calibration")
                    
                    if sel_approve:
                        st.markdown("---")
                        preview_data = pending_df[pending_df['id'] == int(sel_approve)].iloc[0]
                        st.write("**Preview Data:**")
                        col_a, col_b, col_c = st.columns(3)
                        col_a.write(f"**Instrument:** {preview_data['instrument']}")
                        col_b.write(f"**Result:** {preview_data['result']}")
                        col_c.write(f"**Date:** {preview_data['date']}")
                        
                        st.markdown("#### ✍️ Tanda Tangan untuk Approval")
                        
                        if user.get('signature'):
                            st.success("✅ Menggunakan tanda tangan tersimpan")
                            try:
                                sig_bytes = user['signature']
                                if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                    st.image(sig_bytes, width=200, caption="Preview")
                            except:
                                pass
                            
                            use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_cal")
                            
                            if not use_saved:
                                new_signature = st.file_uploader("Upload baru", type=['png', 'jpg', 'jpeg'], key="new_sig_cal")
                                signature_to_use = new_signature.read() if new_signature else None
                            else:
                                signature_to_use = user['signature']
                        else:
                            st.warning("⚠️ Silakan upload tanda tangan di Profile")
                            signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_cal")
                            signature_to_use = signature_upload.read() if signature_upload else None
                        
                        if signature_to_use and col2.button("✅ Approve", key="btn_approve_calibration"):
                            if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                if approve_calibration(int(sel_approve), user['fullname'], signature_to_use):
                                    st.success(f"✅ Calibration ID {sel_approve} berhasil di-approve!")
                                    st.rerun()
                            else:
                                st.error("❌ Data tanda tangan tidak valid!")
                        elif not signature_to_use and col2.button("✅ Approve", key="btn_approve_calibration_no_sig"):
                            st.error("❌ Harap upload tanda tangan!")
                else:
                    st.info("✅ Semua calibration sudah di-approve")
            
            # Download PDF
            st.markdown("---")
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="pdf_cal")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Calibration Report")
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"calibration_{sel}.pdf", mime="application/pdf")
        else:
            st.info("Belum ada data calibration.")

    # === Admin Dashboard ===
    elif menu == "Admin Dashboard":
        st.header("Admin Dashboard")
        st.subheader("📋 Checklist Semua Pengguna")
        df_check = get_checklists()
        if not df_check.empty:
            st.dataframe(df_check[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note', 'approval_status']], use_container_width=True)

        st.subheader("📋 Calibration Semua Pengguna")
        df_cal = get_calibrations()
        if not df_cal.empty:
            st.dataframe(df_cal[['id', 'date', 'instrument', 'procedure', 'result', 'remarks', 'approval_status']], use_container_width=True)

    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()

if __name__ == "__main__":
    main()