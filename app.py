            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Checklist Maintenance")
                st.download_button(
                    label="📄 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Checklist_{rec['id']}.pdf",
                    mime="application/pdf"
                )

    # === Calibration ===
    elif menu == "Calibration":
        st.header("Calibration Report")
        if user['role'] in ['admin', 'operator']:
            with st.form("calibration_form", clear_on_submit=True):
                col1, col2 = st.columns([3, 1])
                date = col1.date_input("Tanggal Kalibrasi", value=datetime.today())
                instrument = col1.text_input("Nama Alat / Instrumen")
                procedure = st.text_area("Prosedur Kalibrasi")
                result = col2.selectbox("Hasil", ["OK", "NG", "Perlu Adjustment"])
                remarks = st.text_area("Keterangan Tambahan")

                if st.form_submit_button("💾 Simpan Data Kalibrasi", use_container_width=True):
                    if save_calibration(user['id'], date, instrument, procedure, result, remarks):
                        st.rerun()

        st.subheader("📋 Daftar Kalibrasi")
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
                    sel_approve = col1.selectbox("Pilih ID untuk Approve", [""] + pending_df['id'].astype(str).tolist(), key="approve_calib")
                    
                    if sel_approve:
                        st.markdown("---")
                        preview_data = pending_df[pending_df['id'] == int(sel_approve)].iloc[0]
                        st.write("**Preview Data:**")
                        col_a, col_b = st.columns(2)
                        col_a.write(f"**Instrument:** {preview_data['instrument']}")
                        col_b.write(f"**Result:** {preview_data['result']}")
                        st.write(f"**Procedure:** {preview_data['procedure']}")
                        st.write(f"**Remarks:** {preview_data['remarks']}")
                        
                        st.markdown("#### ✍️ Tanda Tangan untuk Approval")
                        if user.get('signature'):
                            st.success("✅ Menggunakan tanda tangan tersimpan dari profile")
                            try:
                                sig_bytes = user['signature']
                                if isinstance(sig_bytes, bytes) and len(sig_bytes) > 0:
                                    st.image(sig_bytes, width=200, caption="Preview Tanda Tangan Tersimpan")
                            except:
                                pass

                            use_saved = st.checkbox("Gunakan tanda tangan tersimpan", value=True, key="use_saved_sig_calib")
                            if not use_saved:
                                new_signature = st.file_uploader("Upload tanda tangan baru", type=['png', 'jpg', 'jpeg'], key="new_sig_calib")
                                signature_to_use = new_signature.read() if new_signature else None
                            else:
                                signature_to_use = user['signature']
                        else:
                            st.warning("⚠️ Anda belum upload tanda tangan di Profile. Silakan upload tanda tangan untuk approval.")
                            signature_upload = st.file_uploader("Upload Tanda Tangan", type=['png', 'jpg', 'jpeg'], key="sig_calib")
                            signature_to_use = signature_upload.read() if signature_upload else None

                        if signature_to_use and col2.button("✅ Approve", key="btn_approve_calib"):
                            if isinstance(signature_to_use, bytes) and len(signature_to_use) > 0:
                                if approve_calibration(int(sel_approve), user['fullname'], signature_to_use):
                                    st.success(f"✅ Calibration ID {sel_approve} berhasil di-approve dengan tanda tangan!")
                                    st.rerun()
                            else:
                                st.error("❌ Data tanda tangan tidak valid!")
                        elif not signature_to_use and col2.button("✅ Approve", key="btn_approve_calib_no_sig"):
                            st.error("❌ Harap upload tanda tangan terlebih dahulu!")
                else:
                    st.info("✅ Semua data kalibrasi sudah di-approve")

            # Download PDF Calibration
            st.markdown("---")
            sel = st.selectbox("Pilih ID untuk download PDF", [""] + df['id'].astype(str).tolist(), key="pdf_calib")
            if sel:
                rec = df[df['id'] == int(sel)].iloc[0].to_dict()
                pdf_bytes = generate_pdf(rec, "Calibration Report")
                st.download_button(
                    label="📄 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Calibration_{rec['id']}.pdf",
                    mime="application/pdf"
                )

    # === Admin Dashboard ===
    elif menu == "Admin Dashboard" and user['role'] == 'admin':
        st.header("👨‍💼 Admin Dashboard")
        st.subheader("📦 Semua Data Checklist")
        df_check = get_checklists()
        st.dataframe(df_check[['id', 'date', 'machine', 'item', 'condition', 'approval_status']], use_container_width=True, hide_index=True)
        
        st.subheader("📏 Semua Data Calibration")
        df_calib = get_calibrations()
        st.dataframe(df_calib[['id', 'date', 'instrument', 'result', 'approval_status']], use_container_width=True, hide_index=True)

        st.markdown("### ⚙️ Pengaturan User")
        conn = get_conn()
        users_df = pd.read_sql("SELECT id, username, fullname, role, created_at FROM users", conn)
        conn.close()
        st.dataframe(users_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("➕ Tambah User Baru")
        with st.form("add_user_form"):
            new_username = st.text_input("Username")
            new_fullname = st.text_input("Full Name")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["admin", "manager", "operator"])
            if st.form_submit_button("💾 Tambah User"):
                try:
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO users (username, password_hash, fullname, role, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (new_username, hash_password(new_password), new_fullname, new_role, datetime.now(pytz.timezone('Asia/Singapore')).isoformat()))
                    conn.commit()
                    conn.close()
                    st.success("✅ User baru berhasil ditambahkan!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ Username sudah digunakan.")
    
    # Tombol logout
    st.markdown("---")
    if st.button("🚪 Logout"):
        st.session_state['auth'] = False
        st.session_state['user'] = None
        st.rerun()


# ---------------------------
# RUN APP
# ---------------------------
if __name__ == "__main__":
    main()
