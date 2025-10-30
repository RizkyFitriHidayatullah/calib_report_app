import streamlit as st
import sqlite3
from datetime import datetime
from fpdf import FPDF
import hashlib
import pandas as pd
import os

# ---------------------------
# CONFIG
# ---------------------------
DB_PATH = os.path.join(os.getcwd(), "maintenance_app.db")
st.set_page_config(page_title="Maintenance & Calibration System", layout="wide")

# Hide Streamlit default UI elements
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
.stAppDeployButton {display: none;}
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
        .stButton>button {border-radius: .5rem; width:100%;}
        .card {padding:1rem; border-radius:.7rem; box-shadow:0 2px 6px rgba(0,0,0,0.08); margin-bottom:1rem;}
        .form-label {font-weight:600;}
        .small-muted {font-size:0.9rem;color:#6c757d;}
    </style>
    """, unsafe_allow_html=True)

# ---------------------------
# DB
# ---------------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        fullname TEXT,
        role TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS checklist(
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
    c.execute("""CREATE TABLE IF NOT EXISTS calibration(
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
        ("admin","admin123","Admin","admin"),
        ("manager","manager123","Manager","manager"),
        ("operator","operator123","Operator","operator")
    ]
    for username,password,fullname,role in default_users:
        c.execute("""
            INSERT OR IGNORE INTO users (username,password_hash,fullname,role,created_at)
            VALUES (?,?,?,?,?)
        """, (username, hashlib.sha256((password+"salt2025").encode()).hexdigest(), fullname, role, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256((password+"salt2025").encode()).hexdigest()

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
# PDF
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

    # --- RESPONSIVE LOGIN FORM ---
    if st.session_state['auth'] is False:
        st.markdown("<div class='card'><h3>Login</h3></div>", unsafe_allow_html=True)
        conn=get_conn()
        usernames=pd.read_sql("SELECT username FROM users",conn)['username'].tolist()
        conn.close()

        col1,col2 = st.columns([2,1])
        with col1:
            selected_user = st.selectbox("Username", usernames)
        with col2:
            password = st.text_input("Password", type="password")

        if st.button("Login"):
            ok,user=verify_user(selected_user,password)
            if ok:
                st.session_state['auth']=True
                st.session_state['user']=user
                st.success(f"Login berhasil sebagai {user['role'].capitalize()}")
            else:
                st.error("Login gagal. Password salah.")
        return  # stop render sampai login berhasil

    user = st.session_state['user']
    st.sidebar.success(f"Hi, {user.get('fullname') or user.get('username')} ({user['role']})")

    # --- MENU ---
    if user['role']=='admin':
        page=st.sidebar.radio("Menu",["Checklist","Calibration","Admin Dashboard"])
    elif user['role']=='manager':
        page=st.sidebar.radio("Menu",["Checklist","Calibration"])
    else:
        page=st.sidebar.radio("Menu",["Checklist"])

    # --- CHECKLIST ---
    if page=="Checklist":
        st.header("Checklist Maintenance Harian")
        if user['role'] in ['admin','operator']:
            with st.form("checklist_form",clear_on_submit=True):
                col1,col2=st.columns([1,1])
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
        df=get_checklists(user_id=None if user['role'] in ['admin','manager'] else user['id'])
        if not df.empty:
            st.dataframe(df[['id','date','machine','shift','item','condition','note']], width=0)
            sel=st.selectbox("Pilih ID untuk download PDF", [""]+df['id'].astype(str).tolist())
            if sel:
                rec=df[df['id']==int(sel)].iloc[0].to_dict()
                pdf_bytes=generate_pdf(rec,"Checklist Maintenance")
                st.download_button("Download PDF",data=pdf_bytes,file_name=f"checklist_{sel}.pdf",mime="application/pdf")
        else:
            st.info("Belum ada data.")

    # --- CALIBRATION ---
    if page=="Calibration":
        st.header("Calibration Report")
        if user['role']=='admin':
            with st.form("cal_form",clear_on_submit=True):
                col1,col2=st.columns([1,1])
                date=col1.date_input("Tanggal Kalibrasi",value=datetime.today(),key="cal_date")
                instrument=col1.selectbox("Instrument",["Multimeter","Pressure Gauge","Thermometer","Flow Meter","Other"])
                procedure=st.text_area("Prosedur Singkat")
                result=col2.selectbox("Hasil",["Pass","Fail","Adjust"])
                remarks=st.text_area("Catatan / Rekomendasi")
                submit=st.form_submit_button("Simpan Calibration Report")
                if submit:
                    save_calibration(user['id'],str(date),instrument,procedure,result,remarks)
                    st.success("Calibration report tersimpan.")

        st.subheader("Daftar Calibration")
        df=get_calibrations(user_id=None if user['role'] in ['admin','manager'] else None)
        if not df.empty:
            st.dataframe(df[['id','date','instrument','procedure','result','remarks']], width=0)
            sel=st.selectbox("Pilih ID untuk download PDF", [""]+df['id'].astype(str).tolist(), key="cal_sel")
            if sel:
                rec=df[df['id']==int(sel)].iloc[0].to_dict()
                pdf_bytes=generate_pdf(rec,"Calibration Report")
                st.download_button("Download PDF",data=pdf_bytes,file_name=f"calibration_{sel}.pdf",mime="application/pdf")
        else:
            st.info("Belum ada data.")

    # --- ADMIN DASHBOARD ---
    if page=="Admin Dashboard":
        st.header("Admin Dashboard")
        st.subheader("Checklist Semua Pengguna")
        st.dataframe(get_checklists(), width=0)
        st.subheader("Calibration Semua Pengguna")
        st.dataframe(get_calibrations(), width=0)

    # --- LOGOUT ---
    if st.sidebar.button("Logout"):
        st.session_state['auth']=False
        st.session_state['user']=None
        st.experimental_rerun()

if __name__=="__main__":
    main()
