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
        created_at TEXT
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
        created_at TEXT
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
        created_at TEXT
    )""")

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
            """, (username, hashlib.sha256((password+'salt2025').encode()).hexdigest(), fullname, role, datetime.utcnow().isoformat()))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256((password+'salt2025').encode()).hexdigest()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, fullname, role, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and row[4] == hash_password(password):
        return True, {"id": row[0], "username": row[1], "fullname": row[2], "role": row[3]}
    return False, None

def save_checklist(user_id, date, machine, sub_area, shift, item, condition, note, image_before=None, image_after=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        img_before_binary = image_before.read() if image_before else None
        img_after_binary = image_after.read() if image_after else None
        
        # Gunakan waktu Singapore (UTC+8)
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
        
        # Gunakan waktu Singapore (UTC+8)
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
            SELECT c.*, u.fullname 
            FROM checklist c 
            LEFT JOIN users u ON c.user_id = u.id 
            WHERE c.user_id=? 
            ORDER BY c.date DESC, c.id DESC
        """, (user_id,))
    else:
        c.execute("""
            SELECT c.*, u.fullname 
            FROM checklist c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.date DESC, c.id DESC
        """)
    rows = c.fetchall()
    conn.close()
    cols = ["id", "user_id", "date", "machine", "sub_area", "shift", "item", "condition", "note", "image_before", "image_after", "created_at", "input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def get_calibrations(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("""
            SELECT c.*, u.fullname 
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            WHERE c.user_id=? 
            ORDER BY c.date DESC, c.id DESC
        """, (user_id,))
    else:
        c.execute("""
            SELECT c.*, u.fullname 
            FROM calibration c 
            LEFT JOIN users u ON c.user_id = u.id 
            ORDER BY c.date DESC, c.id DESC
        """)
    rows = c.fetchall()
    conn.close()
    cols = ["id", "user_id", "date", "instrument", "procedure", "result", "remarks", "created_at", "input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

# ---------------------------
# PDF GENERATOR (LANDSCAPE, DIPERBAIKI)
# ---------------------------
def generate_pdf(record, title):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()

    # Judul
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 12, title, ln=True, align="C")
    pdf.ln(8)

    # Header Tabel - DISESUAIKAN LEBAR KOLOM
    if title == "Checklist Maintenance":
        headers = ["Id", "User", "Date & Time", "Machine", "Sub Area", "Shift", "Item", "Condition", "Note"]
        col_widths = [10, 23, 32, 40, 30, 16, 26, 22, 68]  # Total = 267mm
    else:  # Calibration
        headers = ["Id", "User", "Date & Time", "Instrument", "Procedure", "Result", "Remarks"]
        col_widths = [10, 23, 32, 38, 80, 20, 64]  # Total = 267mm

    # Header dengan background
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(220, 220, 220)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, align='C', fill=True)
    pdf.ln()

    # Isi Tabel
    pdf.set_font("Arial", "", 8)
    
    # Format datetime dari created_at
    created_at = record.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            datetime_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            datetime_str = str(record.get("date", ""))
    else:
        datetime_str = str(record.get("date", ""))
    
    # Ambil username
    user_name = str(record.get("input_by", ""))[:18]
    
    if title == "Checklist Maintenance":
        values = [
            str(record.get("id", "")),
            user_name,
            datetime_str,
            str(record.get("machine", ""))[:32],
            str(record.get("sub_area", ""))[:22],
            str(record.get("shift", "")),
            str(record.get("item", ""))[:18],
            str(record.get("condition", "")),
            str(record.get("note", ""))[:140]
        ]
    else:  # Calibration
        values = [
            str(record.get("id", "")),
            user_name,
            datetime_str,
            str(record.get("instrument", ""))[:28],
            str(record.get("procedure", ""))[:150],
            str(record.get("result", "")),
            str(record.get("remarks", ""))[:130]
        ]
    
    # Hitung tinggi baris yang dibutuhkan
    max_lines = 1
    for i, val in enumerate(values):
        chars_per_line = int(col_widths[i] / 2.3)
        lines_needed = max(1, (len(val) // chars_per_line) + 1)
        max_lines = max(max_lines, lines_needed)
    
    row_height = max(8, min(max_lines * 4, 25))
    
    # Print cells dengan multi_cell
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    
    for i, val in enumerate(values):
        pdf.set_xy(x_start + sum(col_widths[:i]), y_start)
        pdf.multi_cell(col_widths[i], 4, val, border=1, align='L')
    
    pdf.set_xy(x_start, y_start + row_height)
    pdf.ln(8)

    # Gambar Before–After (khusus checklist)
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

    return pdf.output(dest="S").encode("latin-1")

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
    menu = st.radio("Pilih Menu", ["Checklist", "Calibration"] + (["Admin Dashboard"] if user['role'] == "admin" else []), horizontal=True)

    # === Checklist ===
    if menu == "Checklist":
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
            display_df = df[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist())
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
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
            display_df = df[['id', 'date', 'instrument', 'procedure', 'result', 'remarks']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="cal_sel")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Calibration Report")
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"calibration_{sel}.pdf", mime="application/pdf")
        else:
            st.info("Belum ada data calibration.")

    # === Admin Dashboard ===
    elif menu == "Admin Dashboard":
        st.header("Admin Dashboard")
        st.subheader("Checklist Semua Pengguna")
        df_check = get_checklists()
        st.dataframe(df_check[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note']], use_container_width=True)

        st.subheader("Calibration Semua Pengguna")
        df_cal = get_calibrations()
        st.dataframe(df_cal[['id', 'date', 'instrument', 'procedure', 'result', 'remarks']], use_container_width=True)

    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()


if __name__ == "__main__":
    main()