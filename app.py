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
# UTIL: BOOTSTRAP
# ---------------------------
def inject_bootstrap():
    st.markdown("""
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .stButton>button {border-radius: .5rem;}
        .card {padding:1.5rem; border-radius:.7rem; box-shadow:0 2px 6px rgba(0,0,0,0.08); margin-top:1rem;}
        .form-label {font-weight:600;}
        .small-muted {font-size:0.9rem;color:#6c757d;}
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
        signature BLOB
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
        ("operator", "operator123", "Operator", "operator")
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

def save_checklist(user_id, date, machine, sub_area, shift, item, condition, note, image_before=None, image_after=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        img_before_binary = image_before.read() if image_before else None
        img_after_binary = image_after.read() if image_after else None
        
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        c.execute("""
            INSERT INTO checklist (user_id, date, machine, sub_area, shift, item, condition, note, image_before, image_after, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, date_str, machine, sub_area, shift, item, condition, note, img_before_binary, img_after_binary, now.isoformat()))
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
                   u.fullname as input_by
            FROM checklist c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.date DESC, c.id DESC
        """)
    rows = c.fetchall()
    conn.close()
    cols = ["id", "user_id", "date", "machine", "sub_area", "shift", "item", "condition", "note", "image_before", "image_after", "created_at", "approved_by", "approved_at", "approval_status", "signature", "input_by"]
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

def approve_checklist(checklist_id, manager_name, signature_data):
    try:
        conn = get_conn()
        c = conn.cursor()
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        # Debug: print info
        print(f"Approving checklist {checklist_id}")
        print(f"Signature data type: {type(signature_data)}")
        print(f"Signature data length: {len(signature_data) if signature_data else 0}")
        
        c.execute("""
            UPDATE checklist 
            SET approval_status = 'Approved', approved_by = ?, approved_at = ?, signature = ?
            WHERE id = ?
        """, (manager_name, now.isoformat(), signature_data, checklist_id))
        
        # Verify signature was saved
        c.execute("SELECT signature FROM checklist WHERE id = ?", (checklist_id,))
        result = c.fetchone()
        if result and result[0]:
            print(f"Signature saved successfully. Size: {len(result[0])} bytes")
        else:
            print("WARNING: Signature not saved!")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in approve_checklist: {e}")
        st.error(f"❌ Error approve: {e}")
        return False

def approve_calibration(calibration_id, manager_name, signature_data):
    try:
        conn = get_conn()
        c = conn.cursor()
        singapore_tz = pytz.timezone('Asia/Singapore')
        now = datetime.now(singapore_tz)
        
        # Debug: print info
        print(f"Approving calibration {calibration_id}")
        print(f"Signature data type: {type(signature_data)}")
        print(f"Signature data length: {len(signature_data) if signature_data else 0}")
        
        c.execute("""
            UPDATE calibration 
            SET approval_status = 'Approved', approved_by = ?, approved_at = ?, signature = ?
            WHERE id = ?
        """, (manager_name, now.isoformat(), signature_data, calibration_id))
        
        # Verify signature was saved
        c.execute("SELECT signature FROM calibration WHERE id = ?", (calibration_id,))
        result = c.fetchone()
        if result and result[0]:
            print(f"Signature saved successfully. Size: {len(result[0])} bytes")
        else:
            print("WARNING: Signature not saved!")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error in approve_calibration: {e}")
        st.error(f"❌ Error approve: {e}")
        return False

# ---------------------------
# PDF GENERATOR
# ---------------------------
def generate_pdf(record, title):
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

    # Approval Section dengan Tanda Tangan
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
        
        # Box untuk approval info
        pdf.set_font("Arial", "", 9)
        x_pos = pdf.get_x()
        y_pos = pdf.get_y()
        
        # Info boxes
        pdf.cell(70, 8, f"Approved by: {approved_by}", border=1, align='L')
        pdf.cell(70, 8, f"Date: {approved_at}", border=1, align='L')
        pdf.ln(10)
        
        # Tanda tangan jika ada
        signature_data = record.get("signature")
        pdf.set_font("Arial", "B", 9)
        pdf.cell(40, 6, "Signature:", border=0, align='L')
        pdf.ln(8)
        
        signature_displayed = False
        
        if signature_data:
            try:
                # Convert ke bytes jika perlu
                if not isinstance(signature_data, bytes):
                    signature_data = bytes(signature_data)
                
                if len(signature_data) > 0:
                    # Simpan signature ke temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", mode='wb') as tmp:
                        tmp.write(signature_data)
                        tmp.flush()
                        tmp_path = tmp.name
                    
                    # Tambahkan gambar signature
                    current_x = pdf.get_x()
                    current_y = pdf.get_y()
                    
                    try:
                        pdf.image(tmp_path, x=current_x + 10, y=current_y, w=60, h=25)
                        signature_displayed = True
                        pdf.ln(28)
                        
                        # Garis bawah signature
                        pdf.set_draw_color(0, 0, 0)
                        pdf.line(current_x + 10, current_y + 25, current_x + 70, current_y + 25)
                    except Exception as img_err:
                        print(f"Error displaying image: {img_err}")
                        
            except Exception as e:
                print(f"Error processing signature: {e}")
        
        if not signature_displayed:
            pdf.set_font("Arial", "I", 8)
            pdf.cell(0, 6, "[No digital signature available]", align='L')
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
        return pdf.output(dest="S").encode("latin-1")
    except UnicodeEncodeError:
        return pdf.output(dest="S").encode("latin-1", errors="ignore")

# ---------------------------
# SIGNATURE PAD COMPONENT
# ---------------------------
def signature_pad():
    """HTML Canvas untuk tanda tangan"""
    signature_html = """
    <div style="border: 2px solid #ddd; border-radius: 8px; padding: 10px; background: white;">
        <p style="margin: 5px 0; font-weight: bold;">✍️ Tanda Tangan Digital:</p>
        <canvas id="signatureCanvas" width="400" height="150" style="border: 1px solid #999; cursor: crosshair; background: white;"></canvas>
        <br>
        <button onclick="clearSignature()" style="margin-top: 10px; padding: 8px 15px; background: #ff4b4b; color: white; border: none; border-radius: 5px; cursor: pointer;">🗑️ Clear</button>
        <input type="hidden" id="signatureData" name="signatureData">
    </div>

    <script>
        const canvas = document.getElementById('signatureCanvas');
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        canvas.addEventListener('mousedown', startDrawing);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', stopDrawing);
        canvas.addEventListener('mouseout', stopDrawing);

        // Touch support
        canvas.addEventListener('touchstart', handleTouch);
        canvas.addEventListener('touchmove', handleTouchMove);
        canvas.addEventListener('touchend', stopDrawing);

        function startDrawing(e) {
            isDrawing = true;
            [lastX, lastY] = [e.offsetX, e.offsetY];
        }

        function draw(e) {
            if (!isDrawing) return;
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(e.offsetX, e.offsetY);
            ctx.stroke();
            [lastX, lastY] = [e.offsetX, e.offsetY];
            
            // Save signature as base64
            document.getElementById('signatureData').value = canvas.toDataURL('image/png');
        }

        function stopDrawing() {
            isDrawing = false;
        }

        function handleTouch(e) {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            lastX = touch.clientX - rect.left;
            lastY = touch.clientY - rect.top;
            isDrawing = true;
        }

        function handleTouchMove(e) {
            if (!isDrawing) return;
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            const x = touch.clientX - rect.left;
            const y = touch.clientY - rect.top;
            
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(x, y);
            ctx.stroke();
            lastX = x;
            lastY = y;
            
            document.getElementById('signatureData').value = canvas.toDataURL('image/png');
        }

        function clearSignature() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            document.getElementById('signatureData').value = '';
        }
    </script>
    """
    return signature_html

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
    
    # Menu dengan Profile untuk Manager
    if user['role'] == 'manager':
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration", "Profile"], horizontal=True)
    elif user['role'] == 'admin':
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration", "Admin Dashboard"], horizontal=True)
    else:
        menu = st.radio("Pilih Menu", ["Checklist", "Calibration"], horizontal=True)

    # === Profile Menu (untuk upload signature) ===
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
                    "Papper Machine 1": ["Wire Section", "Press Section", "Dryer Section", "Calendar", "Reel"],
                    "Papper Machine 2": ["Wire Section", "Press Section", "Dryer Section", "Calendar", "Reel"],
                    "Boiler": ["Feed Pump", "Burner", "Economizer", "Air Fan", "Water Softener"],
                    "WWTP": ["Blower", "Screening", "Clarifier", "Sludge Pump", "Equalization Tank"],
                    "Other": ["Workshop", "Office", "Warehouse"]
                }
                sub_area = col1.selectbox("Sub Area", sub_area_options.get(machine, ["N/A"]))
                shift = col2.selectbox("Shift", ["Pagi", "Siang", "Malam"])
                item = col1.selectbox("Item yang diperiksa", ["Motor", "Pump", "Bearing", "Belt", "Gearbox", "Oil Level", "Sensor", "Other"])
                condition = col1.selectbox("Condition", ["Good", "Minor", "Bad"])
                note = st.text_area("Keterangan / Temuan")
                st.markdown("#### 📷 Upload Gambar (Opsional)")
                col_img1, col_img2 = st.columns(2)
                image_before = col_img1.file_uploader("Foto Before", type=['png', 'jpg', 'jpeg'], key="before")
                image_after = col_img2.file_uploader("Foto After", type=['png', 'jpg', 'jpeg'], key="after")

                if st.form_submit_button("💾 Simpan Checklist", use_container_width=True):
                    if save_checklist(user['id'], date, machine, sub_area, shift, item, condition, note, image_before, image_after):
                        st.rerun()

        st.subheader("📋 Daftar Checklist")
        df = get_checklists() if user['role'] in ['admin', 'manager'] else get_checklists(user_id=user['id'])
        if not df.empty:
            display_df = df[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note', 'approval_status']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Fitur Approval untuk Manager
            if user['role'] == 'manager':
                st.markdown("### ✅ Approval Checklist")
                pending_df = df[df['approval_status'] == 'Pending']
                if not pending_df.empty:
                    col1, col2 = st.columns([3, 1])
                    sel_approve = col1.selectbox("Pilih ID untuk Approve", [""] + pending_df['id'].astype(str).tolist(), key="approve_checklist")
                    
                    if sel_approve:
                        st.markdown("---")
                        # Preview data yang akan di-approve
                        preview_data = pending_df[pending_df['id'] == int(sel_approve)].iloc[0]
                        st.write("**Preview Data:**")
                        col_a, col_b, col_c = st.columns(3)
                        col_a.write(f"**Machine:** {preview_data['machine']}")
                        col_b.write(f"**Item:** {preview_data['item']}")
                        col_c.write(f"**Condition:** {preview_data['condition']}")
                        
                        # Upload tanda tangan untuk approval
                        st.markdown("#### ✍️ Tanda Tangan untuk Approval")
                        
                        if user.get('signature'):
                            st.success("✅ Menggunakan tanda tangan tersimpan dari profile")
                            
                            # Preview signature tersimpan
                            try:
                                sig_bytes = user['signature']
                                if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                    st.image(sig_bytes, width=200, caption="Preview Tanda Tangan Tersimpan")
                            except:
                                pass
                            
                            use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_check")
                            
                            if not use_saved:
                                new_signature = st.file_uploader("Upload tanda tangan baru", type=['png', 'jpg', 'jpeg'], key="new_sig_check")
                                signature_to_use = new_signature.read() if new_signature else None
                            else:
                                signature_to_use = user['signature']
                        else:
                            st.warning("⚠️ Anda belum upload tanda tangan di Profile. Silakan upload tanda tangan untuk approval.")
                            signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_check")
                            signature_to_use = signature_upload.read() if signature_upload else None
                        
                        if signature_to_use and col2.button("✅ Approve", key="btn_approve_checklist"):
                            # Debug: cek apakah signature ada
                            if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                if approve_checklist(int(sel_approve), user['fullname'], signature_to_use):
                                    st.success(f"✅ Checklist ID {sel_approve} berhasil di-approve dengan tanda tangan!")
                                    st.rerun()
                            else:
                                st.error("❌ Data tanda tangan tidak valid!")
                        elif not signature_to_use and col2.button("✅ Approve", key="btn_approve_checklist_no_sig"):
                            st.error("❌ Harap upload tanda tangan terlebih dahulu!")
                else:
                    st.info("✅ Semua checklist sudah di-approve")
            
            # Download PDF
            st.markdown("---")
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="pdf_checklist")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                
                # Debug info untuk melihat apakah signature ada
                if rec.get('approval_status') == 'Approved':
                    sig_data = rec.get('signature')
                    if sig_data and isinstance(sig_data, bytes) and len(sig_data) > 0:
                        st.success(f"✅ Data ini memiliki tanda tangan (Size: {len(sig_data)} bytes)")
                        # Show preview
                        try:
                            st.image(sig_data, width=200, caption="Preview Tanda Tangan di Database")
                        except:
                            st.info("Signature ada tapi tidak bisa di-preview")
                    else:
                        st.warning("⚠️ Data ini sudah di-approve tapi tidak ada tanda tangan.")
                        st.info(f"Debug: signature type = {type(sig_data)}, value = {sig_data}")
                
                pdf_bytes = generate_pdf(rec, "Checklist Maintenance")
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"checklist_{sel}.pdf", mime="application/pdf")
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
            
            # Fitur Approval untuk Manager
            if user['role'] == 'manager':
                st.markdown("### ✅ Approval Calibration")
                pending_df = df[df['approval_status'] == 'Pending']
                if not pending_df.empty:
                    col1, col2 = st.columns([3, 1])
                    sel_approve = col1.selectbox("Pilih ID untuk Approve", [""] + pending_df['id'].astype(str).tolist(), key="approve_calibration")
                    
                    if sel_approve:
                        st.markdown("---")
                        # Preview data yang akan di-approve
                        preview_data = pending_df[pending_df['id'] == int(sel_approve)].iloc[0]
                        st.write("**Preview Data:**")
                        col_a, col_b, col_c = st.columns(3)
                        col_a.write(f"**Instrument:** {preview_data['instrument']}")
                        col_b.write(f"**Result:** {preview_data['result']}")
                        col_c.write(f"**Date:** {preview_data['date']}")
                        
                        # Upload tanda tangan untuk approval
                        st.markdown("#### ✍️ Tanda Tangan untuk Approval")
                        
                        if user.get('signature'):
                            st.success("✅ Menggunakan tanda tangan tersimpan dari profile")
                            
                            # Preview signature tersimpan
                            try:
                                sig_bytes = user['signature']
                                if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                    st.image(sig_bytes, width=200, caption="Preview Tanda Tangan Tersimpan")
                            except:
                                pass
                            
                            use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_cal")
                            
                            if not use_saved:
                                new_signature = st.file_uploader("Upload tanda tangan baru", type=['png', 'jpg', 'jpeg'], key="new_sig_cal")
                                signature_to_use = new_signature.read() if new_signature else None
                            else:
                                signature_to_use = user['signature']
                        else:
                            st.warning("⚠️ Anda belum upload tanda tangan di Profile. Silakan upload tanda tangan untuk approval.")
                            signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_cal")
                            signature_to_use = signature_upload.read() if signature_upload else None
                        
                        if signature_to_use and col2.button("✅ Approve", key="btn_approve_calibration"):
                            # Debug: cek apakah signature ada
                            if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                if approve_calibration(int(sel_approve), user['fullname'], signature_to_use):
                                    st.success(f"✅ Calibration ID {sel_approve} berhasil di-approve dengan tanda tangan!")
                                    st.rerun()
                            else:
                                st.error("❌ Data tanda tangan tidak valid!")
                        elif not signature_to_use and col2.button("✅ Approve", key="btn_approve_calibration_no_sig"):
                            st.error("❌ Harap upload tanda tangan terlebih dahulu!")
                else:
                    st.info("✅ Semua calibration sudah di-approve")
            
            # Download PDF
            st.markdown("---")
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="pdf_cal")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                
                # Debug info untuk melihat apakah signature ada
                if rec.get('approval_status') == 'Approved':
                    sig_data = rec.get('signature')
                    if sig_data and isinstance(sig_data, bytes) and len(sig_data) > 0:
                        st.success(f"✅ Data ini memiliki tanda tangan (Size: {len(sig_data)} bytes)")
                        # Show preview
                        try:
                            st.image(sig_data, width=200, caption="Preview Tanda Tangan di Database")
                        except:
                            st.info("Signature ada tapi tidak bisa di-preview")
                    else:
                        st.warning("⚠️ Data ini sudah di-approve tapi tidak ada tanda tangan.")
                        st.info(f"Debug: signature type = {type(sig_data)}, value = {sig_data}")
                
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