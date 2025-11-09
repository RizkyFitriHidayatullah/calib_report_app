import streamlit as st
import sqlite3
from datetime import datetime
import pytz
from fpdf import FPDF
import hashlib
import pandas as pd
import tempfile
import json

DB_PATH = "maintenance_app.db"
st.set_page_config(page_title="Maintenance System", layout="wide")
st.markdown("""<style>[data-testid="stToolbar"]{visibility:hidden!important;}[data-testid="stDecoration"]{visibility:hidden!important;}
#MainMenu{visibility:hidden!important;}footer{visibility:hidden!important;}
@media(max-width:768px){.stDataFrame{font-size:0.75rem!important;}h1{font-size:1.5rem!important;}}</style>""", unsafe_allow_html=True)

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, 
                 password_hash TEXT, fullname TEXT, role TEXT, created_at TEXT, signature BLOB)""")
    c.execute("""CREATE TABLE IF NOT EXISTS checklist(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                 date TEXT, machine TEXT, sub_area TEXT, shift TEXT, item TEXT, condition TEXT, note TEXT, 
                 image_before BLOB, image_after BLOB, created_at TEXT, approved_by TEXT, approved_at TEXT,
                 approval_status TEXT DEFAULT 'Pending', signature BLOB, details TEXT)""")
    for col in ["signature", "approved_by", "approved_at", "approval_status", "details"]:
        try:
            c.execute(f"ALTER TABLE checklist ADD COLUMN {col} {'TEXT DEFAULT \"Pending\"' if col=='approval_status' else 'BLOB' if col=='signature' else 'TEXT'}")
        except: pass
    users = [("Admin","admin123","Admin","admin"),("Farid","farid123","Farid","manager"),("Tisna","tisna123","Tisna","operator")]
    for u,p,f,r in users:
        try: c.execute("INSERT INTO users(username,password_hash,fullname,role,created_at)VALUES(?,?,?,?,?)",
                      (u,hashlib.sha256((p+'salt2025').encode()).hexdigest(),f,r,datetime.now(pytz.timezone('Asia/Singapore')).isoformat()))
        except: pass
    conn.commit()
    conn.close()

def verify_user(username, password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id,username,fullname,role,password_hash,signature FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row and row[4] == hashlib.sha256((password+'salt2025').encode()).hexdigest():
        return True, {"id":row[0],"username":row[1],"fullname":row[2],"role":row[3],"signature":row[5]}
    return False, None

def save_signature(uid, sig):
    try:
        conn = get_conn()
        conn.execute("UPDATE users SET signature=? WHERE id=?", (sig, uid))
        conn.commit()
        conn.close()
        return True
    except: return False

def save_checklist_batch(uid, date, machine, sub_area, shift, data, img_b=None, img_a=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        ds = date.strftime("%Y-%m-%d") if hasattr(date,'strftime') else str(date)
        ib = img_b.read() if img_b else None
        ia = img_a.read() if img_a else None
        now = datetime.now(pytz.timezone('Asia/Singapore'))
        for item in data:
            c.execute("""INSERT INTO checklist(user_id,date,machine,sub_area,shift,item,condition,note,image_before,
                      image_after,created_at,details)VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (uid,ds,machine,sub_area,shift,item['item'],item['condition'],item['note'],ib,ia,now.isoformat(),json.dumps(item.get('details'))))
        conn.commit()
        conn.close()
        st.success(f"✅ {len(data)} item saved!")
        return True
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return False

def get_checklists(uid=None):
    conn = get_conn()
    c = conn.cursor()
    q = """SELECT c.id,c.user_id,c.date,c.machine,c.sub_area,c.shift,c.item,c.condition,c.note,c.image_before,
           c.image_after,c.created_at,COALESCE(c.approved_by,'')as approved_by,COALESCE(c.approved_at,'')as approved_at,
           COALESCE(c.approval_status,'Pending')as approval_status,c.signature,c.details,u.fullname as input_by 
           FROM checklist c LEFT JOIN users u ON c.user_id=u.id"""
    c.execute(q + (" WHERE c.user_id=?" if uid else "") + " ORDER BY c.date DESC,c.id DESC", (uid,) if uid else ())
    rows = c.fetchall()
    conn.close()
    cols = ["id","user_id","date","machine","sub_area","shift","item","condition","note","image_before","image_after",
            "created_at","approved_by","approved_at","approval_status","signature","details","input_by"]
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

def approve_batch(ids, mgr, sig):
    try:
        conn = get_conn()
        c = conn.cursor()
        now = datetime.now(pytz.timezone('Asia/Singapore'))
        for i in ids:
            c.execute("UPDATE checklist SET approval_status='Approved',approved_by=?,approved_at=?,signature=? WHERE id=?",
                     (mgr,now.isoformat(),sig,i))
        conn.commit()
        conn.close()
        return True
    except: return False

def gen_pdf_wrapping(df, date, shift, user):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Arial","B",14)
    pdf.cell(0,8,"PM1 - WRAPPING & REWINDER",ln=True,align="C")
    pdf.ln(3)
    pdf.set_font("Arial","",9)
    pdf.cell(60,6,f"Date: {date}",border=0)
    pdf.cell(60,6,f"Shift: {shift}",border=0)
    pdf.cell(60,6,f"By: {user}",border=0)
    pdf.ln(8)
    hdr = ["No","Unit","Pneu","Hydr","Press","Conn","Sens","Pump","Pack","Disp","Acc","Note"]
    cw = [10,30,21,21,21,21,21,21,21,21,21,48]
    pdf.set_font("Arial","B",7)
    pdf.set_fill_color(200,200,200)
    for i,h in enumerate(hdr):
        pdf.cell(cw[i],6,h,border=1,align='C',fill=True)
    pdf.ln()
    pdf.set_font("Arial","",6)
    for idx,(_, rec) in enumerate(df.iterrows(),1):
        det = json.loads(rec.get('details','{}')) if rec.get('details') else {}
        gs = lambda k: "OK" if det.get(k,"OK")=="OK" else "NG"
        vals = [str(idx),rec.get('item','')[:35],gs('pneumatic_cylinder'),gs('hydraulic_cylinder'),gs('pressure_gauge'),
                gs('connector'),gs('sensor'),gs('pumps'),gs('packing_seal'),gs('display'),gs('accuracy'),str(rec.get('note',''))[:60]]
        for i,v in enumerate(vals):
            if 2<=i<=10 and v=="NG":
                pdf.set_fill_color(255,200,200)
                pdf.cell(cw[i],5,v,border=1,align='C',fill=True)
                pdf.set_fill_color(255,255,255)
            else:
                pdf.cell(cw[i],5,v,border=1,align='L' if i in[1,11]else'C')
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Arial","I",7)
    pdf.cell(0,4,"Legend: OK=Good | NG=Issue",align='L')
    if len(df)>0 and df.iloc[0].get('approval_status')=='Approved':
        pdf.ln(8)
        pdf.set_font("Arial","B",9)
        pdf.cell(0,6,"APPROVAL",ln=True,align='C')
        a = df.iloc[0]
        pdf.set_font("Arial","",8)
        pdf.cell(70,6,f"By: {a.get('approved_by','N/A')}",border=1)
        pdf.cell(70,6,f"Date: {a.get('approved_at','N/A')}",border=1)
        pdf.ln(8)
        if a.get("signature"):
            try:
                with tempfile.NamedTemporaryFile(delete=False,suffix=".png",mode='wb')as tmp:
                    tmp.write(a["signature"])
                    tmp.flush()
                    pdf.image(tmp.name,x=pdf.get_x()+5,y=pdf.get_y(),w=50,h=20)
            except: pass
    return pdf.output(dest="S").encode("latin-1",errors="ignore")

def gen_pdf_pope(df, date, shift, user):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Arial","B",14)
    pdf.cell(0,8,"PM1 - POPE REEL & KUSTER",ln=True,align="C")
    pdf.ln(3)
    pdf.set_font("Arial","",9)
    pdf.cell(60,6,f"Date: {date}",border=0)
    pdf.cell(60,6,f"Shift: {shift}",border=0)
    pdf.cell(60,6,f"By: {user}",border=0)
    pdf.ln(8)
    hdr = ["No","Unit","Pneu","Hydr","Press","Conn","Sens","Pump","Pack","Disp","Acc","Note"]
    cw = [10,35,20,20,20,20,20,20,20,20,20,52]
    pdf.set_font("Arial","B",7)
    pdf.set_fill_color(200,200,200)
    for i,h in enumerate(hdr):
        pdf.cell(cw[i],6,h,border=1,align='C',fill=True)
    pdf.ln()
    pdf.set_font("Arial","",6)
    for idx,(_, rec) in enumerate(df.iterrows(),1):
        det = json.loads(rec.get('details','{}')) if rec.get('details') else {}
        gs = lambda k: "OK" if det.get(k,"OK")=="OK" else "NG"
        vals = [str(idx),rec.get('item','')[:40],gs('pneumatic_cylinder'),gs('hydraulic_cylinder'),gs('pressure_gauge'),
                gs('connector'),gs('sensor'),gs('pumps'),gs('packing_seal'),gs('display'),gs('accuracy'),str(rec.get('note',''))[:65]]
        for i,v in enumerate(vals):
            if 2<=i<=10 and v=="NG":
                pdf.set_fill_color(255,200,200)
                pdf.cell(cw[i],5,v,border=1,align='C',fill=True)
                pdf.set_fill_color(255,255,255)
            else:
                pdf.cell(cw[i],5,v,border=1,align='L' if i in[1,11]else'C')
        pdf.ln()
    pdf.ln(5)
    pdf.set_font("Arial","I",7)
    pdf.cell(0,4,"Legend: OK=Good | NG=Issue",align='L')
    if len(df)>0 and df.iloc[0].get('approval_status')=='Approved':
        pdf.ln(8)
        pdf.set_font("Arial","B",9)
        pdf.cell(0,6,"APPROVAL",ln=True,align='C')
        a = df.iloc[0]
        pdf.set_font("Arial","",8)
        pdf.cell(70,6,f"By: {a.get('approved_by','N/A')}",border=1)
        pdf.cell(70,6,f"Date: {a.get('approved_at','N/A')}",border=1)
        pdf.ln(8)
        if a.get("signature"):
            try:
                with tempfile.NamedTemporaryFile(delete=False,suffix=".png",mode='wb')as tmp:
                    tmp.write(a["signature"])
                    tmp.flush()
                    pdf.image(tmp.name,x=pdf.get_x()+5,y=pdf.get_y(),w=50,h=20)
            except: pass
    return pdf.output(dest="S").encode("latin-1",errors="ignore")

def main():
    init_db()
    if 'auth' not in st.session_state:
        st.session_state['auth'] = False
        st.session_state['user'] = None

    st.title("🔧 Maintenance System")
    
    if not st.session_state['auth']:
        conn = get_conn()
        users = pd.read_sql("SELECT username FROM users", conn)['username'].tolist()
        conn.close()
        st.subheader("🔐 Login")
        with st.form("login"):
            u = st.selectbox("Username", users)
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                ok, user = verify_user(u, p)
                if ok:
                    st.session_state['auth'] = True
                    st.session_state['user'] = user
                    st.rerun()
                else:
                    st.error("❌ Login failed")
        st.stop()

    user = st.session_state['user']
    st.success(f"👋 {user['fullname']} ({user['role']})")
    
    menu = st.radio("Menu", ["Checklist", "Profile"] if user['role']=='manager' else ["Checklist"], horizontal=True)

    if menu == "Profile" and user['role']=='manager':
        st.header("👤 Profile")
        st.write(f"**Name:** {user['fullname']}")
        st.subheader("✍️ Signature Upload")
        sig = st.file_uploader("Upload signature (PNG/JPG)", type=['png','jpg','jpeg'])
        if sig:
            st.image(sig, width=200)
            if st.button("💾 Save"):
                if save_signature(user['id'], sig.read()):
                    st.success("✅ Saved!")
                    st.rerun()

    elif menu == "Checklist":
        st.header("📋 Maintenance Checklist")
        
        # FORM INPUT - OUTSIDE THE IF BLOCK SO IT'S ALWAYS VISIBLE
        if user['role'] in ['admin','operator']:
            with st.form("form", clear_on_submit=True):
                c1, c2 = st.columns([3,1])
                date = c1.date_input("Date", datetime.today())
                machine = c1.selectbox("Machine", ["Papper Machine 1","Papper Machine 2","Boiler"])
                
                # Sub area options
                opts = {
                    "Papper Machine 1": ["WRAPPING & REWINDER", "POPE REEL & KUSTER", "DRYER GROUP 1 & 2", "PRESS 1, 2 & 3"],
                    "Papper Machine 2": ["Wire Section", "Press Section"],
                    "Boiler": ["Feed Pump", "Burner"]
                }
                sub = c1.selectbox("Sub Area", opts.get(machine, ["N/A"]))
                shift = c2.selectbox("Shift", ["Pagi","Siang","Malam"])
                
                # DEBUG INFO
                st.info(f"🔍 Debug: Machine='{machine}' | Sub Area='{sub}'")
                
                # Check conditions
                is_wrapping = (machine == "Papper Machine 1" and sub == "WRAPPING & REWINDER")
                is_pope = (machine == "Papper Machine 1" and sub == "POPE REEL & KUSTER")
                
                st.info(f"🔍 Is Wrapping: {is_wrapping} | Is Pope: {is_pope}")
                
                # WRAPPING & REWINDER FORM
                if is_wrapping:
                    st.markdown("### 📋 WRAPPING & REWINDER (11 Parts)")
                    st.success("✅ Form WRAPPING & REWINDER aktif!")
                    parts = ["P1-Upender","P2-Winder Platform","P3-Winder Rope Feed","P4-Drive Stretcher","P5-Blade",
                            "P6-Blade Roll","P7-Belt Stretcher","P8-Drive Lock","P9-Brake","P10-Power Pack","P11-Paper Care"]
                    if 'tbl' not in st.session_state:
                        st.session_state.tbl = {}
                    
                    for idx, p in enumerate(parts):
                        with st.expander(f"**{p}**"):
                            c1,c2,c3 = st.columns(3)
                            with c1:
                                st.markdown("**Mechanical**")
                                pn=st.checkbox("Pneumatic",True,key=f"w_p{idx}")
                                hy=st.checkbox("Hydraulic",True,key=f"w_h{idx}")
                                pr=st.checkbox("Pressure",True,key=f"w_r{idx}")
                            with c2:
                                st.markdown("**Electrical**")
                                co=st.checkbox("Connector",True,key=f"w_c{idx}")
                                se=st.checkbox("Sensor",True,key=f"w_s{idx}")
                                di=st.checkbox("Display",True,key=f"w_d{idx}")
                            with c3:
                                st.markdown("**Others**")
                                pu=st.checkbox("Pumps",True,key=f"w_u{idx}")
                                pa=st.checkbox("Packing",True,key=f"w_a{idx}")
                                ac=st.checkbox("Accuracy",True,key=f"w_y{idx}")
                            nt=st.text_input("Note",key=f"w_n{idx}")
                            if pn and hy and pr and co and se and pu and pa and di and ac:
                                st.success("✅ OK")
                            else:
                                st.warning("⚠️ Issue")
                            st.session_state.tbl[p]={'pneumatic':pn,'hydraulic':hy,'pressure':pr,'connector':co,
                                                     'sensor':se,'pumps':pu,'packing':pa,'display':di,'accuracy':ac,'note':nt}
                    
                    st.markdown("#### 📷 Images")
                    c1,c2=st.columns(2)
                    ib=c1.file_uploader("Before",type=['png','jpg'],key="wr_b")
                    ia=c2.file_uploader("After",type=['png','jpg'],key="wr_a")
                    
                    if st.form_submit_button("💾 Save All", use_container_width=True):
                        data=[]
                        for pt,d in st.session_state.tbl.items():
                            ok=all([d['pneumatic'],d['hydraulic'],d['pressure'],d['connector'],d['sensor'],
                                   d['pumps'],d['packing'],d['display'],d['accuracy']])
                            det={f"{k}_cylinder" if k in['pneumatic','hydraulic']else f"{k}_gauge" if k=='pressure'else 
                                f"{k}_seal" if k=='packing'else k:"OK" if d[k]else"NG" for k in d if k!='note'}
                            data.append({'item':pt,'condition':"Good"if ok else"Minor",'note':d['note'],'details':det})
                        if save_checklist_batch(user['id'],date,machine,sub,shift,data,ib,ia):
                            st.session_state.tbl={}
                            st.rerun()
                
                # POPE REEL & KUSTER FORM
                elif is_pope:
                    st.markdown("### 📋 POPE REEL & KUSTER (10 Parts)")
                    st.success("✅ Form POPE REEL & KUSTER aktif!")
                    parts = [
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
                    
                    if 'tbl_pope' not in st.session_state:
                        st.session_state.tbl_pope = {}
                    
                    for idx, p in enumerate(parts):
                        with st.expander(f"**{p}**", expanded=False):
                            st.markdown(f"##### {p}")
                            c1,c2,c3 = st.columns(3)
                            with c1:
                                st.markdown("**Mechanical**")
                                pn=st.checkbox("Pneumatic",True,key=f"pope_p{idx}")
                                hy=st.checkbox("Hydraulic",True,key=f"pope_h{idx}")
                                pr=st.checkbox("Pressure",True,key=f"pope_r{idx}")
                            with c2:
                                st.markdown("**Electrical**")
                                co=st.checkbox("Connector",True,key=f"pope_c{idx}")
                                se=st.checkbox("Sensor",True,key=f"pope_s{idx}")
                                di=st.checkbox("Display",True,key=f"pope_d{idx}")
                            with c3:
                                st.markdown("**Others**")
                                pu=st.checkbox("Pumps",True,key=f"pope_u{idx}")
                                pa=st.checkbox("Packing",True,key=f"pope_a{idx}")
                                ac=st.checkbox("Accuracy",True,key=f"pope_y{idx}")
                            nt=st.text_input("Note",key=f"pope_n{idx}", placeholder="Catatan untuk part ini...")
                            
                            # Status indicator
                            if pn and hy and pr and co and se and pu and pa and di and ac:
                                st.success("✅ Semua komponen OK")
                            else:
                                st.warning("⚠️ Ada komponen yang perlu perhatian")
                            
                            st.session_state.tbl_pope[p]={'pneumatic':pn,'hydraulic':hy,'pressure':pr,'connector':co,
                                                          'sensor':se,'pumps':pu,'packing':pa,'display':di,'accuracy':ac,'note':nt}
                    
                    st.markdown("---")
                    st.markdown("#### 📷 Upload Gambar (Opsional)")
                    c1,c2=st.columns(2)
                    ib=c1.file_uploader("Foto Before",type=['png','jpg','jpeg'],key="pope_before")
                    ia=c2.file_uploader("Foto After",type=['png','jpg','jpeg'],key="pope_after")
                    
                    if st.form_submit_button("💾 Simpan Semua Checklist POPE REEL", use_container_width=True):
                        data=[]
                        for pt,d in st.session_state.tbl_pope.items():
                            ok=all([d['pneumatic'],d['hydraulic'],d['pressure'],d['connector'],d['sensor'],
                                   d['pumps'],d['packing'],d['display'],d['accuracy']])
                            det={f"{k}_cylinder" if k in['pneumatic','hydraulic']else f"{k}_gauge" if k=='pressure'else 
                                f"{k}_seal" if k=='packing'else k:"OK" if d[k]else"NG" for k in d if k!='note'}
                            data.append({'item':pt,'condition':"Good"if ok else"Minor",'note':d['note'],'details':det})
                        if save_checklist_batch(user['id'],date,machine,sub,shift,data,ib,ia):
                            st.session_state.tbl_pope={}
                            st.rerun()
                
                # OTHER AREAS - STANDARD FORM
                else:
                    st.markdown("### 📋 Standard Checklist Form")
                    st.info("Untuk area lain, gunakan form standard")
                    if st.form_submit_button("💾 Save", use_container_width=True):
                        st.warning("Form standard - belum diimplementasi")

        # RECORDS SECTION
        st.markdown("---")
        st.subheader("📊 Records")
        df = get_checklists() if user['role']=='manager' else get_checklists(user['id'])
        
        if not df.empty:
            st.dataframe(df[['id','date','machine','sub_area','shift','item','condition','approval_status']], 
                        use_container_width=True, hide_index=True)
            
            # APPROVAL SECTION FOR MANAGER
            if user['role']=='manager':
                st.markdown("### ✅ Approval")
                pend = df[df['approval_status']=='Pending']
                if not pend.empty:
                    spec = pend[(pend['machine']=='Papper Machine 1')&
                               ((pend['sub_area']=='WRAPPING & REWINDER')|(pend['sub_area']=='POPE REEL & KUSTER'))]
                    if not spec.empty:
                        st.markdown("#### 🔧 Batch Approval")
                        sess = spec.groupby(['sub_area','date','shift']).size().reset_index()[['sub_area','date','shift']]
                        opts = [""]+[f"{r['sub_area']}-{r['date']}-{r['shift']}" for _,r in sess.iterrows()]
                        sel = st.selectbox("Select Session", opts)
                        if sel:
                            parts = sel.split("-")
                            area_sel, date_sel, shift_sel = parts[0], parts[1], parts[2]
                            sdf = spec[(spec['sub_area']==area_sel)&(spec['date']==date_sel)&(spec['shift']==shift_sel)]
                            st.success(f"✅ {len(sdf)} items to approve")
                            sig = user.get('signature')
                            if sig and st.button("✅ Approve All", use_container_width=True):
                                if approve_batch(sdf['id'].tolist(), user['fullname'], sig):
                                    st.success("✅ Approved!")
                                    st.rerun()
            
            # PDF DOWNLOAD SECTION
            st.markdown("---")
            st.subheader("📄 Download PDF")
            wr = df[(df['machine']=='Papper Machine 1')&(df['sub_area']=='WRAPPING & REWINDER')]
            pr = df[(df['machine']=='Papper Machine 1')&(df['sub_area']=='POPE REEL & KUSTER')]
            
            if not wr.empty or not pr.empty:
                spec = pd.concat([wr,pr])
                sess = spec.groupby(['sub_area','date','shift']).size().reset_index()[['sub_area','date','shift']]
                opts = [""]+[f"{r['sub_area']}-{r['date']}-{r['shift']}" for _,r in sess.iterrows()]
                sel = st.selectbox("Select for PDF", opts, key="pdf")
                if sel:
                    parts = sel.split("-")
                    area_sel, date_sel, shift_sel = parts[0], parts[1], parts[2]
                    sdf = spec[(spec['sub_area']==area_sel)&(spec['date']==date_sel)&(spec['shift']==shift_sel)]
                    if not sdf.empty:
                        rec = sdf.iloc[0]
                        if area_sel == "WRAPPING & REWINDER":
                            pdf = gen_pdf_wrapping(sdf, date_sel, shift_sel, rec.get('input_by','N/A'))
                            fname = f"wrapping_{date_sel}_{shift_sel}.pdf"
                        else:
                            pdf = gen_pdf_pope(sdf, date_sel, shift_sel, rec.get('input_by','N/A'))
                            fname = f"pope_{date_sel}_{shift_sel}.pdf"
                        st.download_button(f"📄 Download - {area_sel}", pdf, fname, "application/pdf")
        else:
            st.info("📭 No records yet")

    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()

if __name__ == "__main__":
    main()