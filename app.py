import streamlit as st
import sqlite3
from datetime import datetime
from fpdf import FPDF
import hashlib
import pandas as pd
from io import BytesIO

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
    
    # DROP existing tables if they have wrong structure (TEMPORARY FIX)
    # Uncomment these 3 lines ONLY ONCE to reset database, then comment them again
    # c.execute("DROP TABLE IF EXISTS checklist")
    # c.execute("DROP TABLE IF EXISTS calibration")
    # conn.commit()
    
    # Users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        fullname TEXT,
        role TEXT,
        created_at TEXT
    )""")
    
    # Checklist table
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
    
    # AUTO-MIGRATE: Add image columns if not exist
    try:
        c.execute("ALTER TABLE checklist ADD COLUMN image_before BLOB")
        c.execute("ALTER TABLE checklist ADD COLUMN image_after BLOB")
        conn.commit()
    except sqlite3.OperationalError:
        # Columns already exist
        pass
    
    # Calibration table
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

    # Add default users if not exist
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
        
        # Convert images to binary if provided
        img_before_binary = image_before.read() if image_before else None
        img_after_binary = image_after.read() if image_after else None
        
        c.execute("""
            INSERT INTO checklist (user_id, date, machine, sub_area, shift, item, condition, note, image_before, image_after, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, date_str, machine, sub_area, shift, item, condition, note, img_before_binary, img_after_binary, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        st.success(f"✅ Data berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan checklist: {e}")
        return False

def save_calibration(user_id, date, instrument, procedure, result, remarks):
    try:
        conn = get_conn()
        c = conn.cursor()
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
        c.execute("""
            INSERT INTO calibration (user_id, date, instrument, procedure, result, remarks, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, date_str, instrument, procedure, result, remarks, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        st.success(f"✅ Data berhasil disimpan!")
        return True
    except Exception as e:
        st.error(f"❌ Error menyimpan calibration: {e}")
        return False

def get_checklists(user_id=None):
    conn = get_conn()
    c = conn.cursor()
    
    # Check if image columns exist
    c.execute("PRAGMA table_info(checklist)")
    columns_info = c.fetchall()
    has_images = any(col[1] in ['image_before', 'image_after'] for col in columns_info)
    
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
    
    if has_images:
        cols = ["id", "user_id", "date", "machine", "sub_area", "shift", "item", "condition", "note", "image_before", "image_after", "created_at", "input_by"]
    else:
        cols = ["id", "user_id", "date", "machine", "sub_area", "shift", "item", "condition", "note", "created_at", "input_by"]
    
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
# PDF GENERATOR
# ---------------------------
def generate_pdf(record, title):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, title, ln=True, align="C")
    pdf.ln(5)
    for key, value in record.items():
        pdf.set_font("Arial", style='B', size=11)
        pdf.cell(40, 8, f"{key.capitalize()}:", 0)
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 8, str(value))
    return pdf.output(dest='S').encode('latin-1')

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

    # LOGIN
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

    # MENU
    user = st.session_state['user']
    st.success(f"Halo, {user['fullname']} ({user['role']})")
    menu = st.radio("Pilih Menu", ["Checklist", "Calibration"] + (["Admin Dashboard"] if user['role'] == "admin" else []), horizontal=True)

    # CHECKLIST
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
            # Display dengan column yang benar + input_by untuk manager/admin
            if user['role'] in ['admin', 'manager']:
                display_df = df[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note', 'input_by']].copy()
            else:
                display_df = df[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note']].copy()
            
            # Add indicator if images exist
            if 'image_before' in df.columns and 'image_after' in df.columns:
                display_df['has_images'] = df.apply(lambda row: '📷' if row['image_before'] or row['image_after'] else '', axis=1)
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # View images
            sel = st.selectbox("Pilih ID untuk melihat detail/gambar", [""] + df['id'].astype(str).tolist())
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0]
                
                with st.expander("📸 Lihat Gambar Before & After", expanded=True):
                    col_view1, col_view2 = st.columns(2)
                    
                    if rec['image_before'] and isinstance(rec['image_before'], bytes):
                        col_view1.markdown("**Before:**")
                        col_view1.image(BytesIO(rec['image_before']), use_container_width=True)
                    else:
                        col_view1.info("Tidak ada foto Before")
                    
                    if rec['image_after'] and isinstance(rec['image_after'], bytes):
                        col_view2.markdown("**After:**")
                        col_view2.image(BytesIO(rec['image_after']), use_container_width=True)
                    else:
                        col_view2.info("Tidak ada foto After")
            
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist())
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Checklist Maintenance")
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"checklist_{sel}.pdf", mime="application/pdf")
        else:
            st.info("Belum ada data checklist.")

    # CALIBRATION
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
            if user['role'] in ['admin', 'manager']:
                display_df = df[['id', 'date', 'instrument', 'procedure', 'result', 'remarks', 'input_by']].copy()
            else:
                display_df = df[['id', 'date', 'instrument', 'procedure', 'result', 'remarks']].copy()
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="cal_sel")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Calibration Report")
                st.download_button("📄 Download PDF", data=pdf_bytes, file_name=f"calibration_{sel}.pdf", mime="application/pdf")
        else:
            st.info("Belum ada data calibration.")

    # ADMIN DASHBOARD
    elif menu == "Admin Dashboard":
        st.header("Admin Dashboard")
        st.subheader("Checklist Semua Pengguna")
        df_check = get_checklists()
        if not df_check.empty:
            st.dataframe(df_check[['id', 'date', 'machine', 'sub_area', 'shift', 'item', 'condition', 'note', 'input_by']], use_container_width=True)
        else:
            st.info("Belum ada data.")
            
        st.subheader("Calibration Semua Pengguna")
        df_cal = get_calibrations()
        if not df_cal.empty:
            st.dataframe(df_cal[['id', 'date', 'instrument', 'procedure', 'result', 'remarks', 'input_by']], use_container_width=True)
        else:
            st.info("Belum ada data.")

    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()

if __name__ == "__main__":
    main()