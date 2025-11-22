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

    # Check if old calibration table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='calibration'")
    table_exists = c.fetchone()
    
    if table_exists:
        # Check if old structure (get column names)
        c.execute("PRAGMA table_info(calibration)")
        columns = [col[1] for col in c.fetchall()]
        
        # If old structure detected (doesn't have doc_no), migrate
        if 'doc_no' not in columns:
            # Rename old table
            c.execute("ALTER TABLE calibration RENAME TO calibration_old")
            
            # Create new table
            c.execute("""
            CREATE TABLE calibration(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                doc_no TEXT,
                date TEXT,
                name TEXT,
                environmental_temp TEXT,
                humidity TEXT,
                equipment_name TEXT,
                id_number TEXT,
                function_loc TEXT,
                plant TEXT,
                description TEXT,
                service_name TEXT,
                input TEXT,
                output TEXT,
                manufacturer TEXT,
                model TEXT,
                serial_no TEXT,
                range_in TEXT,
                range_out TEXT,
                pressure_cal TEXT,
                calibrators TEXT,
                result_data TEXT,
                created_at TEXT,
                approved_by TEXT,
                approved_at TEXT,
                approval_status TEXT DEFAULT 'Pending',
                signature BLOB
            )""")
            
            # Migrate old data if any
            try:
                c.execute("""
                    INSERT INTO calibration (
                        id, user_id, date, equipment_name, created_at, 
                        approved_by, approved_at, approval_status, signature
                    )
                    SELECT 
                        id, user_id, date, 
                        COALESCE(instrument, 'Unknown'), 
                        created_at,
                        approved_by, approved_at, approval_status, signature
                    FROM calibration_old
                """)
            except:
                pass
            
            # Drop old table
            c.execute("DROP TABLE IF EXISTS calibration_old")
    else:
        # Create new table from scratch
        c.execute("""
        CREATE TABLE calibration(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            doc_no TEXT,
            date TEXT,
            name TEXT,
            environmental_temp TEXT,
            humidity TEXT,
            equipment_name TEXT,
            id_number TEXT,
            function_loc TEXT,
            plant TEXT,
            description TEXT,
            service_name TEXT,
            input TEXT,
            output TEXT,
            manufacturer TEXT,
            model TEXT,
            serial_no TEXT,
            range_in TEXT,
            range_out TEXT,
            pressure_cal TEXT,
            calibrators TEXT,
            result_data TEXT,
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

    # Update existing records
    try:
        c.execute("UPDATE checklist SET approval_status = 'Pending' WHERE approval_status IS NULL")
        c.execute("UPDATE calibration SET approval_status = 'Pending' WHERE approval_status IS NULL")
    except:
        pass

    default_users = [
        ("Admin", "admin123", "Admin", "admin"),
        ("Farid", "farid123", "Farid", "manager"),
        ("Tisna", "tisna123", "Tisna", "operator"),
        ("supervisor", "supervisor123", "Supervisor", "manager"),
        ("Rizky", "rizky176565", "Rizky/176565", "operator"),
        ("Apuy", "apuy123", "Apuy", "operator"),
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

def save_calibration(user_id, calibration_data):
    """Save detailed calibration report"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Add missing columns if they don't exist
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN location TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN interval_cal TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN reject_error_value TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN reject_error_span TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN status_as_found TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN status_as_left TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN next_cal_date TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN calibration_node TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN calibration_by_name TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN calibration_by_date TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN approved_by_name TEXT")
        except:
            pass
        try:
            c.execute("ALTER TABLE calibration ADD COLUMN approved_by_date TEXT")
        except:
            pass
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            INSERT INTO calibration (
                user_id, doc_no, date, name, environmental_temp, humidity,
                equipment_name, id_number, function_loc, plant, description, service_name, location,
                input, output, manufacturer, model, serial_no, range_in, range_out,
                interval_cal, calibrators, result_data, created_at,
                reject_error_value, reject_error_span, status_as_found, status_as_left,
                next_cal_date, calibration_node, calibration_by_name, calibration_by_date,
                approved_by_name, approved_by_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            calibration_data.get('doc_no'),
            calibration_data.get('date'),
            calibration_data.get('name'),
            calibration_data.get('environmental_temp'),
            calibration_data.get('humidity'),
            calibration_data.get('equipment_name'),
            calibration_data.get('id_number'),
            calibration_data.get('function_loc'),
            calibration_data.get('plant'),
            calibration_data.get('description'),
            calibration_data.get('service_name'),
            calibration_data.get('location'),
            calibration_data.get('input'),
            calibration_data.get('output'),
            calibration_data.get('manufacturer'),
            calibration_data.get('model'),
            calibration_data.get('serial_no'),
            calibration_data.get('range_in'),
            calibration_data.get('range_out'),
            calibration_data.get('interval_cal'),
            calibration_data.get('calibrators'),
            json.dumps(calibration_data.get('result_data', [])),
            now.isoformat(),
            calibration_data.get('reject_error_value'),
            calibration_data.get('reject_error_span'),
            calibration_data.get('status_as_found'),
            calibration_data.get('status_as_left'),
            calibration_data.get('next_cal_date'),
            calibration_data.get('calibration_node'),
            calibration_data.get('calibration_by_name'),
            calibration_data.get('calibration_by_date'),
            calibration_data.get('approved_by_name'),
            calibration_data.get('approved_by_date')
        ))
        
        conn.commit()
        conn.close()
        st.success("✅ Calibration report berhasil disimpan!")
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
    
    # First, check which columns exist
    c.execute("PRAGMA table_info(calibration)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    # Build SELECT clause dynamically based on existing columns
    select_parts = []
    
    # Always available base columns
    base_required = ['id', 'user_id', 'created_at']
    for col in base_required:
        if col in existing_columns:
            select_parts.append(f"c.{col}")
        else:
            select_parts.append(f"NULL as {col}")
    
    # Optional columns with fallback
    optional_columns = {
        'doc_no': '',
        'date': '',
        'name': '',
        'equipment_name': '',
        'model': '',
        'serial_no': '',
        'environmental_temp': '',
        'humidity': '',
        'id_number': '',
        'function_loc': '',
        'plant': '',
        'description': '',
        'service_name': '',
        'location': '',
        'input': '',
        'output': '',
        'manufacturer': '',
        'range_in': '',
        'range_out': '',
        'interval_cal': '',
        'calibrators': '',
        'result_data': '[]',
        'approved_by': '',
        'approved_at': '',
        'approval_status': 'Pending',
        'signature': None,
        'reject_error_value': '',
        'reject_error_span': '',
        'status_as_found': '',
        'status_as_left': '',
        'next_cal_date': '',
        'calibration_node': '',
        'calibration_by_name': '',
        'calibration_by_date': '',
        'approved_by_name': '',
        'approved_by_date': ''
    }
    
    for col, default in optional_columns.items():
        if col in existing_columns:
            if default == 'Pending':
                select_parts.append(f"COALESCE(c.{col}, '{default}') as {col}")
            elif default is None:
                select_parts.append(f"c.{col}")
            else:
                select_parts.append(f"COALESCE(c.{col}, '{default}') as {col}")
        else:
            if default is None:
                select_parts.append(f"NULL as {col}")
            else:
                select_parts.append(f"'{default}' as {col}")
    
    # Add user fullname
    select_parts.append("COALESCE(u.fullname, '') as input_by")
    
    select_clause = ", ".join(select_parts)
    
    if user_id:
        query = f"""
            SELECT {select_clause}
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            WHERE c.user_id = ? 
            ORDER BY c.id DESC
        """
        c.execute(query, (user_id,))
    else:
        query = f"""
            SELECT {select_clause}
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.id DESC
        """
        c.execute(query)
    
    rows = c.fetchall()
    conn.close()
    
    # Column names in order
    cols = ["id", "user_id", "created_at", "doc_no", "date", "name", "equipment_name", "model", "serial_no",
            "environmental_temp", "humidity", "id_number", "function_loc", "plant",
            "description", "service_name", "location", "input", "output", "manufacturer",
            "range_in", "range_out", "interval_cal", "calibrators", "result_data",
            "approved_by", "approved_at", "approval_status", "signature",
            "reject_error_value", "reject_error_span", "status_as_found", "status_as_left",
            "next_cal_date", "calibration_node", "calibration_by_name", "calibration_by_date",
            "approved_by_name", "approved_by_date", "input_by"]
    
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
def generate_pdf_wrapping_rewinder(df_records, date, shift, user_name):
    """Generate PDF khusus untuk WRAPPING & REWINDER dengan semua 11 part dalam satu halaman"""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, "PREVENTIVE MAINTENANCE CHECKLIST PM1 - WRAPPING & REWINDER", ln=True, align="C")
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

def generate_calibration_pdf(record):
    """Generate detailed calibration PDF matching the screenshot format"""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "CALIBRATION REPORT", ln=True, align="C")
    pdf.ln(5)
    
    # Basic Info Section
    pdf.set_font("Arial", "", 9)
    pdf.set_fill_color(173, 216, 230)  # Light blue
    
    # Doc No
    pdf.cell(40, 6, "Doc. No", border=1)
    pdf.cell(60, 6, str(record.get('doc_no', '')), border=1, fill=True)
    pdf.ln()
    
    # Date
    pdf.cell(40, 6, "Date", border=1)
    pdf.cell(60, 6, str(record.get('date', '')), border=1, fill=True)
    pdf.ln()
    
    # Name
    pdf.cell(40, 6, "Name", border=1)
    pdf.cell(60, 6, str(record.get('name', '')), border=1, fill=True)
    pdf.ln()
    
    # Environmental Temp
    pdf.cell(40, 6, "Environmental Temperature", border=1)
    pdf.cell(60, 6, str(record.get('environmental_temp', '')), border=1, fill=True)
    pdf.ln()
    
    # Humidity
    pdf.cell(40, 6, "Humidity", border=1)
    pdf.cell(60, 6, str(record.get('humidity', '')), border=1, fill=True)
    pdf.ln(5)
    
    # Name of Equipment Section
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "Name of Equipment:", ln=True)
    pdf.set_font("Arial", "", 9)
    
    # Equipment details in table
    pdf.cell(40, 6, "Tag ID", border=1)
    pdf.cell(50, 6, str(record.get('id_number', '')), border=1, fill=True)
    pdf.cell(40, 6, "Manufacturer", border=1)
    pdf.cell(60, 6, str(record.get('manufacturer', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Function Loc", border=1)
    pdf.cell(50, 6, str(record.get('function_loc', '')), border=1, fill=True)
    pdf.cell(40, 6, "Model", border=1)
    pdf.cell(60, 6, str(record.get('model', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Plant", border=1)
    pdf.cell(50, 6, str(record.get('plant', '')), border=1, fill=True)
    pdf.cell(40, 6, "Serial No", border=1)
    pdf.cell(60, 6, str(record.get('serial_no', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Description", border=1)
    pdf.cell(50, 6, str(record.get('description', ''))[:30], border=1, fill=True)
    pdf.cell(40, 6, "Range In", border=1)
    pdf.cell(60, 6, str(record.get('range_in', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Device Name", border=1)
    pdf.cell(50, 6, str(record.get('service_name', ''))[:30], border=1, fill=True)
    pdf.cell(40, 6, "Range Out", border=1)
    pdf.cell(60, 6, str(record.get('range_out', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Location", border=1)
    pdf.cell(50, 6, str(record.get('location', '')), border=1, fill=True)
    pdf.cell(40, 6, "Interval Cal", border=1)
    pdf.cell(60, 6, str(record.get('interval_cal', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Input", border=1)
    pdf.cell(50, 6, str(record.get('input', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Output", border=1)
    pdf.cell(50, 6, str(record.get('output', '')), border=1, fill=True)
    pdf.ln(5)
    
    # Calibrators Section
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "Calibrators:", ln=True)
    pdf.set_font("Arial", "", 9)
    
    calibrators = str(record.get('calibrators', '')).split('\n')
    for cal in calibrators:
        if cal.strip():
            pdf.cell(10, 5, chr(149), border=0)  # Bullet point
            pdf.multi_cell(0, 5, cal.strip())
    pdf.ln(3)
    
    # Result Section - Table
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "Result:", ln=True)
    pdf.ln(2)
    
    # Table headers
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(200, 200, 200)
    
    col_widths = [15, 25, 25, 25, 25, 30, 30]
    headers = ["%", "Nominal\nBar", "Nominal\nOutput", "A.s Found", "A.s Left", "A.s Found Error", "A.s Left Error"]
    
    # Multi-line headers
    for i, h in enumerate(headers):
        lines = h.split('\n')
        if len(lines) > 1:
            pdf.cell(col_widths[i], 3, lines[0], border=1, align='C', fill=True)
        else:
            pdf.cell(col_widths[i], 6, h, border=1, align='C', fill=True)
    pdf.ln()
    
    # Second line of headers
    for i, h in enumerate(headers):
        lines = h.split('\n')
        if len(lines) > 1:
            pdf.cell(col_widths[i], 3, lines[1], border=1, align='C', fill=True)
        else:
            pdf.cell(col_widths[i], 0, '', border=0)
    pdf.ln()
    
    # Unit row
    pdf.set_font("Arial", "I", 7)
    units = ["", "Bar", "mA", "mA", "mA", "% of span", "% of span"]
    for i, unit in enumerate(units):
        pdf.cell(col_widths[i], 4, unit, border=1, align='C', fill=True)
    pdf.ln()
    
    # Data rows
    pdf.set_font("Arial", "", 8)
    pdf.set_fill_color(173, 216, 230)  # Light blue for data cells
    
    try:
        result_data = json.loads(record.get('result_data', '[]'))
        if not result_data:
            result_data = []
    except:
        result_data = []
    
    # If no data, create empty rows
    if not result_data:
        for _ in range(10):
            for w in col_widths:
                pdf.cell(w, 5, "", border=1, fill=True)
            pdf.ln()
    else:
        for row in result_data:
            pdf.cell(col_widths[0], 5, str(row.get('percent', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[1], 5, str(row.get('nominal_bar', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[2], 5, str(row.get('nominal_output', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[3], 5, str(row.get('as_found', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[4], 5, str(row.get('as_left', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[5], 5, str(row.get('found_error', '')), border=1, align='C', fill=True)
            pdf.cell(col_widths[6], 5, str(row.get('left_error', '')), border=1, align='C', fill=True)
            pdf.ln()
    
    pdf.ln(3)
    
    # Additional Information Section
    pdf.set_font("Arial", "", 9)
    pdf.set_fill_color(173, 216, 230)
    
    # Reject if Error
    pdf.cell(40, 6, "Reject if Error >", border=1)
    pdf.cell(30, 6, str(record.get('reject_error_value', '1.00')), border=1, fill=True)
    pdf.cell(30, 6, str(record.get('reject_error_span', '% of Span')), border=1, fill=True)
    pdf.ln()
    
    # Status As Found / As Left
    pdf.cell(40, 6, "Status: As Found", border=1)
    pdf.cell(30, 6, str(record.get('status_as_found', '')), border=1, fill=True)
    pdf.cell(40, 6, "Status: As Left", border=1)
    pdf.cell(30, 6, str(record.get('status_as_left', '')), border=1, fill=True)
    pdf.ln()
    
    # Next Calibration Date
    pdf.cell(40, 6, "Next Calibration Date", border=1)
    pdf.cell(60, 6, str(record.get('next_cal_date', '')), border=1, fill=True)
    pdf.ln()
    
    # Calibration Node
    pdf.cell(40, 6, "Calibration Node", border=1)
    pdf.cell(60, 6, str(record.get('calibration_node', '')), border=1, fill=True)
    pdf.ln(5)
    
    # Calibration By & Approved By Section
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, "Calibration & Approval Details:", ln=True)
    pdf.set_font("Arial", "", 9)
    
    # Calibration By
    pdf.cell(40, 6, "Calibration By", border=1)
    cal_by_name = str(record.get('calibration_by_name', ''))
    cal_by_date = str(record.get('calibration_by_date', ''))
    cal_by_text = f"{cal_by_name}" if cal_by_name else ""
    pdf.cell(60, 6, cal_by_text, border=1, fill=True)
    pdf.cell(20, 6, "Date:", border=1)
    pdf.cell(40, 6, cal_by_date, border=1, fill=True)
    pdf.ln()
    
    # Approved By (from additional fields, not manager approval)
    pdf.cell(40, 6, "Approved by", border=1)
    appr_by_name = str(record.get('approved_by_name', ''))
    appr_by_date = str(record.get('approved_by_date', ''))
    appr_by_text = f"{appr_by_name}" if appr_by_name else ""
    pdf.cell(60, 6, appr_by_text, border=1, fill=True)
    pdf.cell(20, 6, "Date:", border=1)
    pdf.cell(40, 6, appr_by_date, border=1, fill=True)
    pdf.ln(8)
    
    # Manager Approval Section (if approved via system)
    if record.get('approval_status') == 'Approved':
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(0, 6, "MANAGER APPROVAL SECTION", ln=True, align='C')
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
        pdf.cell(95, 8, f"Reviewed & Approved by: {approved_by}", border=1, align='L')
        pdf.cell(95, 8, f"Date: {approved_at}", border=1, align='L')
        pdf.ln(10)
        
        # Signature
        signature_data = record.get("signature")
        if signature_data and isinstance(signature_data, bytes) and len(signature_data) > 0:
            pdf.set_font("Arial", "B", 9)
            pdf.cell(40, 6, "Signature:", border=0, align='L')
            pdf.ln(8)
            
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as tmp:
                    tmp.write(signature_data)
                    tmp.flush()
                    current_x = pdf.get_x()
                    current_y = pdf.get_y()
                    pdf.image(tmp.name, x=current_x + 10, y=current_y, w=60, h=25)
                    pdf.ln(28)
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
                
                if is_wrapping_rewinder:
                    st.markdown("### 📋 Checklist - WRAPPING & REWINDER")
                    st.info("Centang ✓ jika OK, kosongkan jika ada masalah")
                    
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
                    # Cek apakah ada WRAPPING & REWINDER
                    wrapping_pending = pending_df[(pending_df['machine'] == 'Papper Machine 1') & (pending_df['sub_area'] == 'WRAPPING & REWINDER')]
                    
                    if not wrapping_pending.empty:
                        st.markdown("#### 🔧 Batch Approval - WRAPPING & REWINDER")
                        st.info("Approve semua checklist untuk satu shift sekaligus")
                        
                        # Group by date and shift
                        unique_sessions = wrapping_pending.groupby(['date', 'shift']).size().reset_index()[['date', 'shift']]
                        
                        # Mobile-friendly layout
                        session_options = [""] + [f"{row['date']} - Shift {row['shift']}" for _, row in unique_sessions.iterrows()]
                        sel_session = st.selectbox("📅 Pilih Tanggal & Shift", session_options, key="approve_session")
                        
                        if sel_session:
                            selected_date, selected_shift = sel_session.split(" - Shift ")
                            session_df = wrapping_pending[(wrapping_pending['date'] == selected_date) & (wrapping_pending['shift'] == selected_shift)]
                            
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
                    non_wrapping_pending = pending_df[~((pending_df['machine'] == 'Papper Machine 1') & (pending_df['sub_area'] == 'WRAPPING & REWINDER'))]
                    
                    if not non_wrapping_pending.empty:
                        sel_approve = st.selectbox("Pilih ID", [""] + non_wrapping_pending['id'].astype(str).tolist(), key="approve_individual")
                        
                        if sel_approve:
                            preview_data = non_wrapping_pending[non_wrapping_pending['id'] == int(sel_approve)].iloc[0]
                            
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
            
            # Filter untuk WRAPPING & REWINDER
            wrapping_df = df[(df['machine'] == 'Papper Machine 1') & (df['sub_area'] == 'WRAPPING & REWINDER')]
            
            if not wrapping_df.empty:
                # Group by date and shift
                unique_sessions = wrapping_df.groupby(['date', 'shift']).size().reset_index()[['date', 'shift']]
                
                st.markdown("#### 🔧 WRAPPING & REWINDER (All Parts in One PDF)")
                session_options = [""] + [f"{row['date']} - Shift {row['shift']}" for _, row in unique_sessions.iterrows()]
                sel_session = st.selectbox("Pilih Tanggal & Shift", session_options, key="pdf_wrapping")
                
                if sel_session:
                    selected_date, selected_shift = sel_session.split(" - Shift ")
                    session_df = wrapping_df[(wrapping_df['date'] == selected_date) & (wrapping_df['shift'] == selected_shift)]
                    
                    if not session_df.empty:
                        first_rec = session_df.iloc[0]
                        pdf_bytes = generate_pdf_wrapping_rewinder(
                            session_df, 
                            selected_date, 
                            selected_shift,
                            first_rec.get('input_by', 'N/A')
                        )
                        st.download_button(
                            "📄 Download PDF - WRAPPING & REWINDER", 
                            data=pdf_bytes, 
                            file_name=f"wrapping_rewinder_{selected_date}_{selected_shift}.pdf", 
                            mime="application/pdf"
                        )
            
            # Download individual checklist
            st.markdown("#### 📋 Individual Checklist PDF")
            non_wrapping_df = df[~((df['machine'] == 'Papper Machine 1') & (df['sub_area'] == 'WRAPPING & REWINDER'))]
            
            if not non_wrapping_df.empty:
                sel = st.selectbox("Pilih ID untuk download", [""] + non_wrapping_df['id'].astype(str).tolist(), key="pdf_individual")
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
        st.header("📊 Calibration Report")
        
        if user['role'] == "admin":
            st.subheader("📝 Input Calibration Report")
            
            # Get historical data for autocomplete
            df_history = get_calibrations()
            
            # Helper function to get unique history
            def get_history_list(df, column, limit=20):
                if df.empty:
                    return []
                values = df[column].dropna().unique().tolist()
                # Filter empty strings and sort by most recent (reverse)
                values = [str(x).strip() for x in values if x and str(x).strip()]
                return sorted(list(set(values)))[:limit]
            
            with st.form("calibration_form", clear_on_submit=True):
                st.markdown("#### 📋 Basic Information")
                col1, col2 = st.columns(2)
                
                # Get histories
                doc_no_history = get_history_list(df_history, 'doc_no', 20)
                name_history = get_history_list(df_history, 'name', 20)
                temp_history = get_history_list(df_history, 'environmental_temp', 10)
                humid_history = get_history_list(df_history, 'humidity', 10)
                
                # Use markdown for datalist suggestion (HTML5 datalist)
                st.markdown(f"""
                <style>
                    .stTextInput input {{
                        background-color: grey;
                    }}
                </style>
                """, unsafe_allow_html=True)
                
                # Doc No with autocomplete
                doc_no = col1.text_input(
                    "Doc. No", 
                    placeholder="e.g., CAL-2025-001",
                    help=f"💡 Previous: {', '.join(doc_no_history[:3])}" if doc_no_history else None
                )
                
                date = col1.date_input("Date", value=datetime.today())
                
                # Name with autocomplete
                name = col1.text_input(
                    "Name", 
                    placeholder="Rotary Pump",
                    help=f"💡 Previous: {', '.join(name_history[:3])}" if name_history else None
                )
                
                # Environmental Temp with autocomplete
                environmental_temp = col2.text_input(
                    "Environmental Temperature", 
                    placeholder="e.g., +25 degC",
                    help=f"💡 Previous: {', '.join(temp_history[:3])}" if temp_history else None
                )
                
                # Humidity with autocomplete
                humidity = col2.text_input(
                    "Humidity", 
                    placeholder="e.g., ~55%",
                    help=f"💡 Previous: {', '.join(humid_history[:3])}" if humid_history else None
                )
                
                st.markdown("---")
                st.markdown("#### ⚙️ Equipment Details")
                
                col1, col2 = st.columns(2)
                
                # Get equipment histories
                tag_history = get_history_list(df_history, 'id_number', 20)
                func_history = get_history_list(df_history, 'function_loc', 20)
                plant_history = get_history_list(df_history, 'plant', 10)
                loc_history = get_history_list(df_history, 'location', 20)
                input_history = get_history_list(df_history, 'input', 10)
                output_history = get_history_list(df_history, 'output', 10)
                mfg_history = get_history_list(df_history, 'manufacturer', 20)
                model_history = get_history_list(df_history, 'model', 20)
                sn_history = get_history_list(df_history, 'serial_no', 20)
                range_in_history = get_history_list(df_history, 'range_in', 10)
                range_out_history = get_history_list(df_history, 'range_out', 10)
                interval_history = get_history_list(df_history, 'interval_cal', 10)
                
                # Tag ID with autocomplete
                tag_id = col1.text_input(
                    "Tag ID", 
                    placeholder="e.g., PT/1",
                    help=f"💡 Previous: {', '.join(tag_history[:3])}" if tag_history else None
                )
                
                # Function Loc with autocomplete
                function_loc = col1.text_input(
                    "Function Loc", 
                    placeholder="e.g., PM1",
                    help=f"💡 Previous: {', '.join(func_history[:3])}" if func_history else None
                )
                
                # Plant with autocomplete
                plant = col1.text_input(
                    "Plant", 
                    placeholder="e.g., 1",
                    help=f"💡 Previous: {', '.join(plant_history[:3])}" if plant_history else None
                )
                
                description = col1.text_area("Description", placeholder="Pressure outlet col DDK - pressure 70 (DUMP 107)")
                device_name = col1.text_area("Device Name", placeholder="Pressure transmitter - pressure Hx (DUMP 107)")
                
                # Location with autocomplete
                location = col1.text_input(
                    "Location", 
                    placeholder="e.g., Field Area A",
                    help=f"💡 Previous: {', '.join(loc_history[:3])}" if loc_history else None
                )
                
                # Input with autocomplete
                input_type = col1.text_input(
                    "Input", 
                    placeholder="e.g., Pressure",
                    help=f"💡 Previous: {', '.join(input_history[:3])}" if input_history else None
                )
                
                # Output with autocomplete
                output_type = col1.text_input(
                    "Output", 
                    placeholder="e.g., 4-20 mA",
                    help=f"💡 Previous: {', '.join(output_history[:3])}" if output_history else None
                )
                
                # Manufacturer with autocomplete
                manufacturer = col2.text_input(
                    "Manufacturer", 
                    placeholder="e.g., Keller",
                    help=f"💡 Previous: {', '.join(mfg_history[:3])}" if mfg_history else None
                )
                
                # Model with autocomplete
                model = col2.text_input(
                    "Model", 
                    placeholder="e.g., -",
                    help=f"💡 Previous: {', '.join(model_history[:3])}" if model_history else None
                )
                
                # Serial No with autocomplete
                serial_no = col2.text_input(
                    "Serial No", 
                    placeholder="e.g., -",
                    help=f"💡 Previous: {', '.join(sn_history[:3])}" if sn_history else None
                )
                
                # Range In with autocomplete
                range_in = col2.text_input(
                    "Range In", 
                    placeholder="e.g., 0 to 10 bar",
                    help=f"💡 Previous: {', '.join(range_in_history[:3])}" if range_in_history else None
                )
                
                # Range Out with autocomplete
                range_out = col2.text_input(
                    "Range Out", 
                    placeholder="e.g., 4 to 20 mA",
                    help=f"💡 Previous: {', '.join(range_out_history[:3])}" if range_out_history else None
                )
                
                # Interval Cal with autocomplete
                interval_cal = col2.text_input(
                    "Interval Cal", 
                    placeholder="e.g., 6 months",
                    help=f"💡 Previous: {', '.join(interval_history[:3])}" if interval_history else None
                )
                
                st.markdown("---")
                st.markdown("#### 🔧 Calibrators")
                calibrators = st.text_area("Calibrators (one per line)", 
                                          placeholder="IET3000 Digital Multimeter Cert No. ...\nFluke Digital Multimeter Cert No. ...",
                                          height=100)
                
                st.markdown("---")
                st.markdown("#### 📊 Result Data")
                st.info("Masukkan data hasil kalibrasi. Biarkan kosong jika tidak ada data.")
                
                # Initialize result data in session state
                if 'cal_result_rows' not in st.session_state:
                    st.session_state.cal_result_rows = [
                        {"percent": "0", "nominal_bar": "0", "nominal_output": "4.00"},
                        {"percent": "25", "nominal_bar": "2.5", "nominal_output": "8.00"},
                        {"percent": "50", "nominal_bar": "5", "nominal_output": "12.00"},
                        {"percent": "75", "nominal_bar": "7.5", "nominal_output": "16.00"},
                        {"percent": "100", "nominal_bar": "10", "nominal_output": "20.00"},
                        {"percent": "75", "nominal_bar": "7.5", "nominal_output": "16.00"},
                        {"percent": "50", "nominal_bar": "5", "nominal_output": "12.00"},
                        {"percent": "25", "nominal_bar": "2.5", "nominal_output": "8.00"},
                        {"percent": "0", "nominal_bar": "0", "nominal_output": "4.00"}
                    ]
                
                # Display result table with editable fields
                st.markdown("**Tabel Hasil Kalibrasi:**")
                
                result_data = []
                for idx, row_data in enumerate(st.session_state.cal_result_rows):
                    col_p, col_nb, col_no, col_af, col_al, col_fe, col_le = st.columns([1, 1.5, 1.5, 1.5, 1.5, 2, 2])
                    
                    with col_p:
                        if idx == 0:
                            st.markdown("**%**")
                        st.text_input(f"pct_{idx}", value=row_data.get('percent', ''), label_visibility="collapsed", key=f"percent_{idx}")
                    
                    with col_nb:
                        if idx == 0:
                            st.markdown("**Nominal Input**")
                        st.text_input(f"nb_{idx}", value=row_data.get('nominal_bar', ''), label_visibility="collapsed", key=f"nom_bar_{idx}")
                    
                    with col_no:
                        if idx == 0:
                            st.markdown("**Nominal Output**")
                        st.text_input(f"no_{idx}", value=row_data.get('nominal_output', ''), label_visibility="collapsed", key=f"nom_out_{idx}")
                    
                    with col_af:
                        if idx == 0:
                            st.markdown("**A.s Found (mA)**")
                        st.number_input(f"af_{idx}", value=0.0, format="%.2f", label_visibility="collapsed", key=f"as_found_{idx}")
                    
                    with col_al:
                        if idx == 0:
                            st.markdown("**A.s Left (mA)**")
                        st.number_input(f"al_{idx}", value=0.0, format="%.2f", label_visibility="collapsed", key=f"as_left_{idx}")
                    
                    with col_fe:
                        if idx == 0:
                            st.markdown("**A.s Found Error (%)**")
                        st.number_input(f"fe_{idx}", value=0.0, format="%.2f", label_visibility="collapsed", key=f"found_err_{idx}")
                    
                    with col_le:
                        if idx == 0:
                            st.markdown("**A.s Left Error (%)**")
                        st.number_input(f"le_{idx}", value=0.0, format="%.2f", label_visibility="collapsed", key=f"left_err_{idx}")
                    
                    # Collect data
                    result_data.append({
                        "percent": st.session_state.get(f"percent_{idx}", row_data.get('percent', '')),
                        "nominal_bar": st.session_state.get(f"nom_bar_{idx}", row_data.get('nominal_bar', '')),
                        "nominal_output": st.session_state.get(f"nom_out_{idx}", row_data.get('nominal_output', '')),
                        "as_found": st.session_state.get(f"as_found_{idx}", 0.0),
                        "as_left": st.session_state.get(f"as_left_{idx}", 0.0),
                        "found_error": st.session_state.get(f"found_err_{idx}", 0.0),
                        "left_error": st.session_state.get(f"left_err_{idx}", 0.0)
                    })
                
                st.markdown("---")
                st.markdown("#### 📊 Additional Information")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    reject_error_value = st.text_input("Reject if Error >", placeholder="e.g., 1.00", value="1.00")
                    status_as_found = st.selectbox("Status: As Found", ["", "Pass", "Fail", "Adjust"])
                
                with col2:
                    reject_error_span = st.text_input("% of Span", placeholder="e.g., % of Span")
                    status_as_left = st.selectbox("Status: As Left", ["", "Pass", "Fail", "Adjust"])
                
                with col3:
                    next_cal_date = st.date_input("Next Calibration Date", value=None)
                    calibration_node = st.text_input("Calibration Node", placeholder="e.g., Node information")
                
                st.markdown("---")
                st.markdown("#### ✍️ Calibration & Approval Details")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    calibration_by_name = st.text_input("Calibration By (Name)", placeholder=user['fullname'], value=user['fullname'])
                    calibration_by_date = st.date_input("Calibration Date", value=datetime.today())
                
                with col2:
                    approved_by_name = st.text_input("Approved by (Name)", placeholder="e.g., Farid Vitra Baskara")
                    approved_by_date = st.date_input("Approved Date", value=None)
                
                st.markdown("---")
                
                # Submit button
                if st.form_submit_button("💾 Simpan Calibration Report", use_container_width=True):
                    calibration_data = {
                        'doc_no': doc_no,
                        'date': date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date),
                        'name': name,
                        'environmental_temp': environmental_temp,
                        'humidity': humidity,
                        'equipment_name': name,
                        'id_number': tag_id,
                        'function_loc': function_loc,
                        'plant': plant,
                        'description': description,
                        'service_name': device_name,
                        'location': location,
                        'input': input_type,
                        'output': output_type,
                        'manufacturer': manufacturer,
                        'model': model,
                        'serial_no': serial_no,
                        'range_in': range_in,
                        'range_out': range_out,
                        'interval_cal': interval_cal,
                        'calibrators': calibrators,
                        'result_data': result_data,
                        'reject_error_value': reject_error_value,
                        'reject_error_span': reject_error_span,
                        'status_as_found': status_as_found,
                        'status_as_left': status_as_left,
                        'next_cal_date': next_cal_date.strftime("%Y-%m-%d") if next_cal_date else '',
                        'calibration_node': calibration_node,
                        'calibration_by_name': calibration_by_name,
                        'calibration_by_date': calibration_by_date.strftime("%Y-%m-%d") if hasattr(calibration_by_date, 'strftime') else str(calibration_by_date),
                        'approved_by_name': approved_by_name,
                        'approved_by_date': approved_by_date.strftime("%Y-%m-%d") if approved_by_date else ''
                    }
                    
                    if save_calibration(user['id'], calibration_data):
                        # Clear form
                        if 'cal_result_rows' in st.session_state:
                            del st.session_state.cal_result_rows
                        st.rerun()
        
        # Display existing calibration reports
        st.markdown("---")
        st.subheader("📋 Daftar Calibration Reports")
        
        df = get_calibrations() if user['role'] in ['admin', 'manager'] else get_calibrations(user_id=user['id'])
        
        if not df.empty:
            st.info(f"Total: {len(df)} calibration reports")
            
            # Compact display
            display_df = df[['id', 'doc_no', 'date', 'name', 'equipment_name', 'model', 'approval_status']]
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            
            # Approval section for Manager
            if user['role'] == 'manager':
                st.markdown("### ✅ Approval Calibration")
                pending_df = df[df['approval_status'] == 'Pending']
                
                if not pending_df.empty:
                    sel_approve = st.selectbox("Pilih ID untuk Approve", [""] + pending_df['id'].astype(str).tolist(), key="approve_calibration")
                    
                    if sel_approve:
                        st.markdown("---")
                        preview_data = pending_df[pending_df['id'] == int(sel_approve)].iloc[0]
                        
                        with st.expander("📋 Preview Data", expanded=True):
                            col1, col2, col3 = st.columns(3)
                            col1.write(f"**Doc No:** {preview_data['doc_no']}")
                            col2.write(f"**Equipment:** {preview_data['equipment_name']}")
                            col3.write(f"**Date:** {preview_data['date']}")
                        
                        st.markdown("#### ✍️ Tanda Tangan")
                        
                        if user.get('signature'):
                            st.success("✅ Tanda tangan tersimpan")
                            
                            with st.expander("👁️ Preview Tanda Tangan", expanded=False):
                                try:
                                    sig_bytes = user['signature']
                                    if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                        st.image(sig_bytes, width=150)
                                except:
                                    pass
                            
                            use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_cal")
                            
                            if not use_saved:
                                new_signature = st.file_uploader("Upload baru", type=['png', 'jpg', 'jpeg'], key="new_sig_cal")
                                signature_to_use = new_signature.read() if new_signature else None
                            else:
                                signature_to_use = user['signature']
                        else:
                            st.warning("⚠️ Upload tanda tangan di Profile")
                            signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_cal")
                            signature_to_use = signature_upload.read() if signature_upload else None
                        
                        if signature_to_use:
                            if st.button("✅ Approve", key="btn_approve_calibration", use_container_width=True):
                                if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                    if approve_calibration(int(sel_approve), user['fullname'], signature_to_use):
                                        st.success(f"✅ Calibration ID {sel_approve} berhasil di-approve!")
                                        st.rerun()
                                else:
                                    st.error("❌ Data tanda tangan tidak valid!")
                        else:
                            st.button("✅ Approve (Upload signature dulu)", disabled=True, use_container_width=True)
                else:
                    st.info("✅ Semua calibration sudah di-approve")
            
            # Download PDF
            st.markdown("---")
            st.subheader("📄 Download PDF Report")
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="pdf_cal")
            
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_calibration_pdf(rec)
                st.download_button(
                    "📄 Download Calibration PDF", 
                    data=pdf_bytes, 
                    file_name=f"calibration_{rec.get('doc_no', sel)}.pdf", 
                    mime="application/pdf",
                    use_container_width=True
                )
        else:
            st.info("Belum ada calibration report.")

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
            st.dataframe(df_cal[['id', 'doc_no', 'date', 'name', 'equipment_name', 'model', 'approval_status']], use_container_width=True)

    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()

if __name__ == "__main__":
    main()