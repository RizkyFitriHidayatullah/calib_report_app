import streamlit as st
import sqlite3
from datetime import datetime
from fpdf import FPDF
import hashlib
import pandas as pd

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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
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
        shift TEXT,
        item TEXT,
        condition TEXT,
        note TEXT,
        created_at TEXT
    )""")
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
    # Default users
    default_users = [
        ("admin","admin123","Admin","admin"),
        ("manager","manager123","Manager","manager"),
        ("operator","operator123","Operator","operator")
    ]
    for username,password,fullname,role in default_users:
        try:
            c.execute("INSERT INTO users (username,password_hash,fullname,role,created_at) VALUES (?,?,?,?,?)",
                      (username, hashlib.sha256((password+'salt2025').encode()).hexdigest(), fullname, role, datetime.utcnow().isoformat()))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256((password+'salt2025').encode()).hexdigest()

def verify_user(username,password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,username,fullname,role,password_hash FROM users WHERE username=?",(username,))
    row = c.fetchone()
    conn.close()
    if row and row[4]==hash_password(password):
        return True, {"id":row[0],"username":row[1],"fullname":row[2],"role":row[3]}
    return False, None

def save_checklist(user_id,date,machine,shift,item,condition,note):
    conn=get_conn()
    c=conn.cursor()
    c.execute("""INSERT INTO checklist (user_id,date,machine,shift,item,condition,note,created_at)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (user_id,str(date),machine,shift,item,condition,note,datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def save_calibration(user_id,date,instrument,procedure,result,remarks):
    conn=get_conn()
    c=conn.cursor()
    c.execute("""INSERT INTO calibration (user_id,date,instrument,procedure,result,remarks,created_at)
                 VALUES (?,?,?,?,?,?,?)""",
              (user_id,str(date),instrument,procedure,result,remarks,datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_checklists(user_id=None):
    conn=get_conn()
    c=conn.cursor()
    if user_id:
        c.execute("SELECT * FROM checklist WHERE user_id=? ORDER BY date DESC,id DESC",(user_id,))
    else:
        c.execute("SELECT * FROM checklist ORDER BY date DESC,id DESC")
    rows=c.fetchall()
    conn.close()
    cols=["id","user_id","date","machine","shift","item","condition","note","created_at"]
    return pd.DataFrame(rows,columns=cols)

def get_calibrations(user_id=None):
    conn=get_conn()
    c=conn.cursor()
    if user_id:
        c.execute("SELECT * FROM calibration WHERE user_id=? ORDER BY date DESC,id DESC",(user_id,))
    else:
        c.execute("SELECT * FROM calibration ORDER BY date DESC,id DESC")
    rows=c.fetchall()
    conn.close()
    cols=["id","user_id","date","instrument","procedure","result","remarks","created_at"]
    return pd.DataFrame(rows,columns=cols)

# ---------------------------
# PDF GENERATOR
# ---------------------------
def generate_pdf(record,title):
    pdf=FPDF()
    pdf.add_page()
    pdf.set_font("Arial",size=12)
    pdf.cell(0,8,title,ln=True,align="C")
    pdf.ln(4)
    for k,v in record.items():
        pdf.set_font("Arial",style='B',size=11)
        pdf.cell(50,8,f"{k}:",border=0)
        pdf.set_font("Arial",size=11)
        pdf.multi_cell(0,8,str(v))
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------
# MAIN APP
# ---------------------------
def main():
    inject_bootstrap()
    init_db()

    if 'auth' not in st.session_state:
        st.session_state['auth']=False
        st.session_state['user']=None

    st.markdown("<div class='card'><h2>Maintenance & Calibration System</h2>"
                "<p class='small-muted'>Gunakan akun yang sudah ditentukan.</p></div>",unsafe_allow_html=True)

    # ---------------- LOGIN FORM ----------------
    if not st.session_state['auth']:
        conn = get_conn()
        usernames = pd.read_sql("SELECT username FROM users", conn)['username'].tolist()
        conn.close()

        st.subheader("🔐 Login")
        selected_user = st.selectbox("Pilih Username", usernames)
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            ok,user=verify_user(selected_user,password)
            if ok:
                st.session_state['auth']=True
                st.session_state['user']=user
                st.success(f"Login berhasil sebagai {user['role'].capitalize()}")
                st.rerun()   # ✅ diganti dari experimental_rerun
            else:
                st.error("Login gagal. Password salah.")
        st.info("Silakan login menggunakan akun yang sudah ditentukan.")
        return  # Hentikan eksekusi di sini jika belum login

    # ---------------- MAIN MENU ----------------
    user = st.session_state['user']
    st.success(f"Halo, {user.get('fullname') or user.get('username')} ({user['role']})")
    menu = st.radio("Pilih Menu", ["Checklist", "Calibration"] + (["Admin Dashboard"] if user['role']=="admin" else []))

    # -------- Checklist --------
    if menu=="Checklist":
        st.header("Checklist Maintenance Harian")
        if user['role'] in ['admin','operator']:
            with st.form("checklist_form",clear_on_submit=True):
                col1,col2=st.columns([2,1])
                date=col1.date_input("Tanggal",value=datetime.today())
                machine=col1.selectbox("Machine / Area", ["Balling Press","Conveyor A","Conveyor B","Compressor","Other"])
                shift=col2.selectbox("Shift",["Pagi","Siang","Malam"])
                item=st.selectbox("Item yang diperiksa",["Motor","Belt","Bearing","Oil Level","Sensor","Other"])
                condition=st.selectbox("Condition",["Good","Minor","Bad"])
                note=st.text_area("Keterangan / Temuan")
                submitted=st.form_submit_button("Simpan Checklist")
                if submitted:
                    save_checklist(user['id'],str(date),machine,shift,item,condition,note)
                    st.success("Checklist tersimpan.")

        st.subheader("Daftar Checklist")
        if user['role'] in ['admin','manager']:
            df=get_checklists()
        else:
            df=get_checklists(user_id=user['id'])

        if not df.empty:
            st.dataframe(df[['id','date','machine','shift','item','condition','note']])
            sel=st.selectbox("Pilih ID untuk download PDF",[""]+df['id'].astype(str).tolist())
            if sel:
                rec=df[df['id']==int(sel)].iloc[0].to_dict()
                pdf_bytes=generate_pdf(rec,"Checklist Maintenance")
                st.download_button("Download PDF",data=pdf_bytes,file_name=f"checklist_{sel}.pdf",mime="application/pdf")
        else:
            st.info("Belum ada data.")

    # -------- Calibration --------
    if menu=="Calibration":
        st.header("Calibration Report")
        if user['role']=='admin':
            with st.form("cal_form",clear_on_submit=True):
                date=st.date_input("Tanggal Kalibrasi",value=datetime.today(),key="cal_date")
                instrument=st.selectbox("Instrument",["Multimeter","Pressure Gauge","Thermometer","Flow Meter","Other"])
                procedure=st.text_area("Prosedur Singkat")
                result=st.selectbox("Hasil",["Pass","Fail","Adjust"])
                remarks=st.text_area("Catatan / Rekomendasi")
                submit=st.form_submit_button("Simpan Calibration Report")
                if submit:
                    save_calibration(user['id'],str(date),instrument,procedure,result,remarks)
                    st.success("Calibration report tersimpan.")

        st.subheader("Daftar Calibration")
        if user['role'] in ['admin','manager']:
            df=get_calibrations()
        else:
            df=get_calibrations(user_id=user['id'])

        if not df.empty:
            st.dataframe(df[['id','date','instrument','procedure','result','remarks']])
            sel=st.selectbox("Pilih ID untuk download PDF",[""]+df['id'].astype(str).tolist(),key="cal_sel")
            if sel:
                rec=df[df['id']==int(sel)].iloc[0].to_dict()
                pdf_bytes=generate_pdf(rec,"Calibration Report")
                st.download_button("Download PDF",data=pdf_bytes,file_name=f"calibration_{sel}.pdf",mime="application/pdf")
        else:
            st.info("Belum ada data.")

    # -------- Admin Dashboard --------
    if menu=="Admin Dashboard":
        st.header("Admin Dashboard")
        st.subheader("Checklist Semua Pengguna")
        st.dataframe(get_checklists())
        st.subheader("Calibration Semua Pengguna")
        st.dataframe(get_calibrations())

    # -------- Logout --------
    if st.button("Logout"):
        st.session_state['auth']=False
        st.session_state['user']=None
        st.rerun()   # ✅ diganti dari experimental_rerun

if __name__=="__main__":
    main()


