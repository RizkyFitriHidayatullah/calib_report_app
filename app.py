import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import io
from fpdf import FPDF
from datetime import datetime

# ---------------------------
# CONFIG
# ---------------------------
DB_PATH = "maintenance_app.db"
st.set_page_config(page_title="Maintenance & Calibration System", layout="wide")

# ---------------------------
# UTIL: BOOTSTRAP INJECTION
# ---------------------------
def inject_bootstrap():
    bootstrap_cdn = """
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"
     integrity="sha384-..." crossorigin="anonymous">
    <style>
    /* small style tweaks to harmonize streamlit and bootstrap */
    .stButton>button {border-radius: .5rem;}
    .card {padding:1rem; border-radius: .7rem; box-shadow: 0 2px 6px rgba(0,0,0,0.08)}
    .form-label {font-weight:600}
    .small-muted {font-size:0.9rem; color:#6c757d}
    </style>
    """
    st.markdown(bootstrap_cdn, unsafe_allow_html=True)

# ---------------------------
# UTIL: DB
# ---------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        fullname TEXT,
        created_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS checklist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        machine TEXT,
        shift TEXT,
        item TEXT,
        condition TEXT,
        note TEXT,
        created_at TEXT
    )
    """)
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
    )
    """)
    conn.commit()
    conn.close()

# ---------------------------
# UTIL: AUTH
# ---------------------------
SALT = "maintenance_system_salt_2025"  # demo salt

def hash_password(password: str) -> str:
    return hashlib.sha256((password + SALT).encode('utf-8')).hexdigest()

def create_user(username, password, fullname=""):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, fullname, created_at) VALUES (?, ?, ?, ?)",
                  (username, hash_password(password), fullname, datetime.utcnow().isoformat()))
        conn.commit()
        return True, "User created"
    except sqlite3.IntegrityError:
        return False, "Username sudah dipakai"
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, password_hash, fullname FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, "User tidak ditemukan", None
    user_id, pw_hash, fullname = row
    if pw_hash == hash_password(password):
        return True, "Login berhasil", {"id": user_id, "username": username, "fullname": fullname}
    else:
        return False, "Password salah", None

# ---------------------------
# UTIL: DB save/read functions
# ---------------------------
def save_checklist(user_id, date, machine, shift, item, condition, note):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO checklist (user_id, date, machine, shift, item, condition, note, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, date, machine, shift, item, condition, note, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def save_calibration(user_id, date, instrument, procedure, result, remarks):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO calibration (user_id, date, instrument, procedure, result, remarks, created_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (user_id, date, instrument, procedure, result, remarks, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_checklists(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("SELECT * FROM checklist WHERE user_id=? ORDER BY date DESC, id DESC", (user_id,))
    else:
        c.execute("SELECT * FROM checklist ORDER BY date DESC, id DESC")
    rows = c.fetchall()
    conn.close()
    cols = ["id","user_id","date","machine","shift","item","condition","note","created_at"]
    return pd.DataFrame(rows, columns=cols)

def get_calibrations(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    if user_id:
        c.execute("SELECT * FROM calibration WHERE user_id=? ORDER BY date DESC, id DESC", (user_id,))
    else:
        c.execute("SELECT * FROM calibration ORDER BY date DESC, id DESC")
    rows = c.fetchall()
    conn.close()
    cols = ["id","user_id","date","instrument","procedure","result","remarks","created_at"]
    return pd.DataFrame(rows, columns=cols)

# ---------------------------
# UTIL: PDF generation
# ---------------------------
def generate_checklist_pdf(record: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, "Checklist Maintenance Harian", ln=True, align="C")
    pdf.ln(4)
    for k, v in record.items():
        pdf.set_font("Arial", style='B', size=11)
        pdf.cell(50, 8, f"{k}:", border=0)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, str(v))
    return pdf.output(dest='S').encode('latin-1')

def generate_calibration_pdf(record: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, "Calibration Report", ln=True, align="C")
    pdf.ln(4)
    for k, v in record.items():
        pdf.set_font("Arial", style='B', size=11)
        pdf.cell(50, 8, f"{k}:", border=0)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, str(v))
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------
# UI: Authentication pages
# ---------------------------
def auth_ui():
    st.sidebar.title("Akun")
    menu = st.sidebar.radio("Menu", ["Login", "Sign up", "About"])
    if menu == "About":
        st.sidebar.write("Aplikasi demo: Checklist Maintenance & Calibration\nDibuat dengan Streamlit + SQLite.\nGunakan untuk kebutuhan internal.")
    elif menu == "Sign up":
        st.sidebar.subheader("Buat akun baru")
        new_user = st.sidebar.text_input("Username")
        new_fullname = st.sidebar.text_input("Nama lengkap (opsional)")
        new_pass = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Daftar"):
            if not new_user or not new_pass:
                st.sidebar.error("Isi username dan password")
            else:
                ok, msg = create_user(new_user, new_pass, new_fullname)
                if ok:
                    st.sidebar.success("Akun berhasil dibuat. Silakan login.")
                else:
                    st.sidebar.error(msg)
    elif menu == "Login":
        st.sidebar.subheader("Masuk")
        username = st.sidebar.text_input("Username", key="login_user")
        password = st.sidebar.text_input("Password", type="password", key="login_pw")
        if st.sidebar.button("Login"):
            ok, msg, user = verify_user(username, password)
            if ok:
                st.session_state['auth'] = True
                st.session_state['user'] = user
                st.sidebar.success(msg)
            else:
                st.sidebar.error(msg)

# ---------------------------
# UI: Main app pages (protected)
# ---------------------------
def checklist_form(user):
    st.header("Checklist Maintenance Harian")
    st.markdown("Isi checklist harian untuk mesin/line Anda. Data akan disimpan di database dan dapat diekspor ke PDF.")
    with st.form("checklist_form", clear_on_submit=True):
        col1, col2 = st.columns([2,1])
        date = col1.date_input("Tanggal", value=datetime.today())
        machine = col1.selectbox("Machine / Area", ["Papper Machine 1", "Papper Machine 2", "Boiler", "WWTP","Balling Press", "Conveyor A", "Conveyor B", "Compressor", "Other"])
        shift = col2.selectbox("Shift", ["Pagi", "Siang", "Malam"])
        item = st.selectbox("Item yang diperiksa", ["Motor", "Belt", "Bearing", "Oil Level", "Sensor", "Other"])
        condition = st.selectbox("Condition", ["Good", "Minor", "Bad"])
        note = st.text_area("Keterangan / Temuan", help="Tulis detail temuan atau tindakan perbaikan singkat.")
        submitted = st.form_submit_button("Simpan Checklist")
        if submitted:
            save_checklist(user['id'], str(date), machine, shift, item, condition, note)
            st.success("Checklist tersimpan.")
    # show recent entries
    st.subheader("Daftar Checklist (terbaru)")
    df = get_checklists(user_id=user['id'])
    if not df.empty:
        st.dataframe(df[['id','date','machine','shift','item','condition','note','created_at']])
        sel = st.selectbox("Pilih ID untuk export PDF (kosong = tidak ada)", [""] + df['id'].astype(str).tolist())
        if sel:
            rec = df[df['id']==int(sel)].iloc[0].to_dict()
            pdf_bytes = generate_checklist_pdf(rec)
            st.download_button("Download PDF Checklist", data=pdf_bytes, file_name=f"checklist_{sel}.pdf", mime="application/pdf")
    else:
        st.info("Belum ada checklist.")

def calibration_form(user):
    st.header("Calibration Report")
    st.markdown("Form laporan kalibrasi instrumen.")
    with st.form("cal_form", clear_on_submit=True):
        date = st.date_input("Tanggal Kalibrasi", value=datetime.today(), key="cal_date")
        instrument = st.selectbox("Instrument", ["Multimeter", "Pressure Gauge", "Thermometer", "Flow Meter", "Other"])
        procedure = st.text_area("Prosedur Singkat", "Tuliskan prosedur kalibrasi yang dilakukan")
        result = st.selectbox("Hasil", ["Pass", "Fail", "Adjust"])
        remarks = st.text_area("Catatan / Rekomendasi")
        submit = st.form_submit_button("Simpan Calibration Report")
        if submit:
            save_calibration(user['id'], str(date), instrument, procedure, result, remarks)
            st.success("Calibration report tersimpan.")
    st.subheader("Daftar Calibration (terbaru)")
    df = get_calibrations(user_id=user['id'])
    if not df.empty:
        st.dataframe(df[['id','date','instrument','procedure','result','remarks','created_at']])
        sel = st.selectbox("Pilih ID untuk export PDF (kosong = tidak ada)", [""] + df['id'].astype(str).tolist(), key="cal_sel")
        if sel:
            rec = df[df['id']==int(sel)].iloc[0].to_dict()
            pdf_bytes = generate_calibration_pdf(rec)
            st.download_button("Download PDF Calibration", data=pdf_bytes, file_name=f"calibration_{sel}.pdf", mime="application/pdf")
    else:
        st.info("Belum ada calibration report.")

def admin_dashboard():
    st.header("Admin Dashboard")
    st.markdown("Tabel semua data (admin hanya).")
    st.subheader("Checklist Semua Pengguna")
    st.dataframe(get_checklists())
    st.subheader("Calibration Semua Pengguna")
    st.dataframe(get_calibrations())

# ---------------------------
# MAIN
# ---------------------------
def main():
    inject_bootstrap()
    init_db()

    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
        st.session_state['user'] = None

    auth_ui()

    st.markdown("<div class='card'>"
                "<h2>Maintenance & Calibration System</h2>"
                "<p class='small-muted'>Aplikasi sederhana untuk mencatat checklist harian dan laporan kalibrasi. Gunakan fitur kiri untuk login / registrasi.</p>"
                "</div>", unsafe_allow_html=True)

    if st.session_state['auth']:
        user = st.session_state['user']
        st.sidebar.success(f"Hi, {user.get('fullname') or user.get('username')}")
        page = st.sidebar.radio("Aplikasi", ["Checklist Maintenance", "Calibration Report", "Account", "Admin (if you are admin)"])
        if page == "Checklist Maintenance":
            checklist_form(user)
        elif page == "Calibration Report":
            calibration_form(user)
        elif page == "Account":
            st.subheader("Profil")
            st.write(f"Username: {user['username']}")
            st.write(f"Nama: {user.get('fullname') or '-'}")
            if st.button("Logout"):
                st.session_state['auth'] = False
                st.session_state['user'] = None
                st.experimental_rerun()
        elif page == "Admin (if you are admin)":
            # simple check: username == "admin" to show admin dashboard; adjust as needed
            if user['username'] == "admin":
                admin_dashboard()
            else:
                st.warning("Hanya admin yang dapat melihat halaman ini.")
    else:
        st.info("Silakan login atau registrasi melalui panel di kiri untuk mulai menggunakan aplikasi.")

if __name__ == "__main__":
    main()
