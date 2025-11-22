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
            
            .stSelectbox, .stTextInput, .stTextArea, .stNumberInput {
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

def save_calibration(user_id, calibration_data):
    """Save detailed calibration report"""
    try:
        conn = get_conn()
        c = conn.cursor()
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            INSERT INTO calibration (
                user_id, doc_no, date, name, environmental_temp, humidity,
                equipment_name, id_number, function_loc, plant, description, service_name,
                input, output, manufacturer, model, serial_no, range_in, range_out,
                pressure_cal, calibrators, result_data, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            calibration_data.get('input'),
            calibration_data.get('output'),
            calibration_data.get('manufacturer'),
            calibration_data.get('model'),
            calibration_data.get('serial_no'),
            calibration_data.get('range_in'),
            calibration_data.get('range_out'),
            calibration_data.get('pressure_cal'),
            calibration_data.get('calibrators'),
            json.dumps(calibration_data.get('result_data', [])),
            now.isoformat()
        ))
        
        conn.commit()
        conn.close()
        st.success("✅ Calibration report berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan calibration: {e}")
        return False

def get_calibrations(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("""
            SELECT c.id, c.user_id, c.doc_no, c.date, c.name, c.equipment_name, c.model, c.serial_no,
                   c.environmental_temp, c.humidity, c.id_number, c.function_loc, c.plant, 
                   c.description, c.service_name, c.input, c.output, c.manufacturer,
                   c.range_in, c.range_out, c.pressure_cal, c.calibrators, c.result_data,
                   c.created_at,
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
            SELECT c.id, c.user_id, c.doc_no, c.date, c.name, c.equipment_name, c.model, c.serial_no,
                   c.environmental_temp, c.humidity, c.id_number, c.function_loc, c.plant,
                   c.description, c.service_name, c.input, c.output, c.manufacturer,
                   c.range_in, c.range_out, c.pressure_cal, c.calibrators, c.result_data,
                   c.created_at,
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
    cols = ["id", "user_id", "doc_no", "date", "name", "equipment_name", "model", "serial_no",
            "environmental_temp", "humidity", "id_number", "function_loc", "plant",
            "description", "service_name", "input", "output", "manufacturer",
            "range_in", "range_out", "pressure_cal", "calibrators", "result_data",
            "created_at", "approved_by", "approved_at", "approval_status", "signature", "input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

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
# PDF GENERATOR FOR CALIBRATION
# ---------------------------
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
    pdf.cell(40, 6, "", border=0)
    pdf.cell(50, 6, "", border=0)
    pdf.ln()
    
    # Date
    pdf.cell(40, 6, "Date", border=1)
    pdf.cell(60, 6, str(record.get('date', '')), border=1, fill=True)
    pdf.cell(40, 6, "Kolej Bekasi-cuwang", border=1)
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
    pdf.cell(40, 6, "Id PT/A21A", border=1)
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
    
    pdf.cell(40, 6, "Service Name", border=1)
    pdf.cell(50, 6, str(record.get('service_name', ''))[:30], border=1, fill=True)
    pdf.cell(40, 6, "Range Out", border=1)
    pdf.cell(60, 6, str(record.get('range_out', '')), border=1, fill=True)
    pdf.ln()
    
    pdf.cell(40, 6, "Input", border=1)
    pdf.cell(50, 6, str(record.get('input', '')), border=1, fill=True)
    pdf.cell(40, 6, "Pressure Cal", border=1)
    pdf.cell(60, 6, str(record.get('pressure_cal', '')), border=1, fill=True)
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
    
    # Approval Section
    if record.get('approval_status') == 'Approved':
        pdf.ln(10)
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
        pdf.cell(95, 8, f"Approved by: {approved_by}", border=1, align='L')
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
# MAIN APP (Simplified - Only Calibration part shown)
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
    
    # Show Calibration menu
    st.header("📊 Calibration Report")
    
    if user['role'] == "admin":
        st.subheader("📝 Input Calibration Report")
        
        with st.form("calibration_form", clear_on_submit=True):
            st.markdown("#### 📋 Basic Information")
            col1, col2 = st.columns(2)
            
            doc_no = col1.text_input("Doc. No", placeholder="e.g., CAL-2025-001")
            date = col1.date_input("Date", value=datetime.today())
            name = col1.text_input("Name", placeholder="Rotary Pump")
            environmental_temp = col2.text_input("Environmental Temperature", placeholder="e.g., +25 degC")
            humidity = col2.text_input("Humidity", placeholder="e.g., ~55%")
            
            st.markdown("---")
            st.markdown("#### ⚙️ Equipment Details")
            
            col1, col2 = st.columns(2)
            
            id_number = col1.text_input("Id (PT/A21A)", placeholder="e.g., PT/1")
            function_loc = col1.text_input("Function Loc", placeholder="e.g., PM1")
            plant = col1.text_input("Plant", placeholder="e.g., 1")
            description = col1.text_area("Description", placeholder="Pressure outlet col DDK - pressure 70 (DUMP 107)")
            service_name = col1.text_area("Service Name", placeholder="Pressure transmitter - pressure Hx (DUMP 107)")
            input_type = col1.text_input("Input", placeholder="e.g., Pressure")
            output_type = col1.text_input("Output", placeholder="e.g., 4-20 mA")
            
            manufacturer = col2.text_input("Manufacturer", placeholder="e.g., Keller")
            model = col2.text_input("Model", placeholder="e.g., -")
            serial_no = col2.text_input("Serial No", placeholder="e.g., -")
            range_in = col2.text_input("Range In", placeholder="e.g., 0 to 10 bar")
            range_out = col2.text_input("Range Out", placeholder="e.g., 4 to 20 mA")
            pressure_cal = col2.text_input("Pressure Cal", placeholder="e.g., Min / Max")
            
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
                        st.markdown("**Nominal Bar**")
                    st.text_input(f"nb_{idx}", value=row_data.get('nominal_bar', ''), label_visibility="collapsed", key=f"nom_bar_{idx}")
                
                with col_no:
                    if idx == 0:
                        st.markdown("**Nominal Output (mA)**")
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
            
            # Submit button
            if st.form_submit_button("💾 Simpan Calibration Report", use_container_width=True):
                calibration_data = {
                    'doc_no': doc_no,
                    'date': date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date),
                    'name': name,
                    'environmental_temp': environmental_temp,
                    'humidity': humidity,
                    'equipment_name': name,
                    'id_number': id_number,
                    'function_loc': function_loc,
                    'plant': plant,
                    'description': description,
                    'service_name': service_name,
                    'input': input_type,
                    'output': output_type,
                    'manufacturer': manufacturer,
                    'model': model,
                    'serial_no': serial_no,
                    'range_in': range_in,
                    'range_out': range_out,
                    'pressure_cal': pressure_cal,
                    'calibrators': calibrators,
                    'result_data': result_data
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
    
    # Logout button
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()

if __name__ == "__main__":
    main()