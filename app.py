import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client

# -------------------- Page --------------------
st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")
st.title("Njangi Admin Dashboard")

# -------------------- Secrets --------------------
def get_secret(key: str) -> str | None:
    try:
        return st.secrets.get(key)
    except Exception:
        return os.getenv(key)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_ANON_KEY in Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# -------------------- Helpers --------------------
def to_df(resp):
    return pd.DataFrame(resp.data or [])

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    st.code(str(e))

def safe_select_table(c, table: str, order_col: str | None = None, desc: bool = True, limit: int = 500):
    q = c.table(table).select("*")
    if order_col:
        q = q.order(order_col, desc=desc)
    if limit:
        q = q.limit(limit)
    return q.execute()

# -------------------- Login --------------------
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Admin Login")

    if st.session_state.session is None:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.session = res.session
                st.rerun()
            except Exception as e:
                show_api_error(e, "Login failed")
    else:
        u = st.session_state.session.user
        st.success(f"Logged in: {u.email}")
        if st.button("Logout", use_container_width=True):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = authed_client()
auth_uid = st.session_state.session.user.id
st.caption(f"auth.uid(): {auth_uid}")

# Optional admin check (won't stop app if RLS blocks)
try:
    prof = client.table("profiles").select("id,role,approved").eq("id", auth_uid).single().execute().data
    if prof and prof.get("approved") is False:
        st.error("Your account is not approved yet (profiles.approved = false).")
        st.stop()
    if prof and prof.get("role") != "admin":
        st.warning("Your role is not admin (profiles.role != 'admin'). Inserts may fail by RLS.")
except Exception:
    st.warning("Could not read profiles (RLS). Continuing.")

# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Rotation", "Contributions", "Foundation", "JSON Inserter"])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("All Njangi Members (member_registry)")
    try:
        members = client.table("member_registry").select("*").order("legacy_member_id").execute()
        st.dataframe(to_df(members), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load member_registry")

# ===================== ROTATION =====================
with tabs[1]:
    st.subheader("Rotation State (app_state)")
    try:
        state = client.table("app_state").select("*").execute()
        st.dataframe(to_df(state), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load app_state")

# ===================== CONTRIBUTIONS (FIXED) =====================
with tabs[2]:
    st.subheader("Contributions (contributions_legacy)")

    try:
        contribs = safe_select_table(client, "contributions_legacy", order_col="created_at", desc=True, limit=500)
        st.dataframe(to_df(contribs), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### Insert a Contribution (legacy)")
    st.caption("Columns: member_id (int), amount (int), kind (text), session_id (uuid optional).")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        c_member_id = st.number_input("member_id (1–17)", min_value=1, max_value=17, step=1, value=1, key="c_member")
    with c2:
        c_amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
    with c3:
        c_kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
    with c4:
        c_session_id = st.text_input("session_id (uuid, optional)", value="", key="c_session")

    if st.button("Insert Contribution (legacy)", use_container_width=True, key="btn_ins_contrib"):
        payload = {
            "member_id": int(c_member_id),
            "amount": int(c_amount),
            "kind": str(c_kind),
        }
        if c_session_id.strip():
            payload["session_id"] = c_session_id.strip()
        # If your table/RLS requires user_id, uncomment:
        # payload["user_id"] = auth_uid

        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Inserted contribution.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS or invalid data)")

# ===================== FOUNDATION (FIXED) =====================
with tabs[3]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        foundation = safe_select_table(client, "foundation_payments_legacy", order_col="id", desc=True, limit=500)
        st.dataframe(to_df(foundation), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment (legacy)")
    st.caption("Columns: member_id (bigint), amount_paid, amount_pending, status, date_paid, notes, converted_to_loan.")

    f1, f2, f3 = st.columns(3)
    with f1:
        f_member_id = st.number_input("member_id (1–17)", min_value=1, max_value=17, step=1, value=1, key="f_member")
    with f2:
        f_amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="f_paid")
    with f3:
        f_amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="f_pending")

    f4, f5, f6 = st.columns(3)
    with f4:
        f_status = st.selectbox("status", ["paid", "pending", "converted"], index=0, key="f_status")
    with f5:
        f_date_paid = st.date_input("date_paid", key="f_date")
    with f6:
        f_converted = st.selectbox("converted_to_loan", [False, True], index=0, key="f_conv")

    f_notes = st.text_input("notes (optional)", value="", key="f_notes")

    if st.button("Insert Foundation Payment (legacy)", use_container_width=True, key="btn_ins_found"):
        payload = {
            "member_id": int(f_member_id),
            "amount_paid": float(f_amount_paid),
            "amount_pending": float(f_amount_pending),
            "status": str(f_status),
            "date_paid": f"{f_date_paid}T00:00:00Z",
            "converted_to_loan": bool(f_converted),
        }
        if f_notes.strip():
            payload["notes"] = f_notes.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Inserted foundation payment.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS or invalid data)")

# ===================== JSON INSERTER =====================
with tabs[4]:
    st.subheader("Universal Insert / Update (JSON)")
    st.caption("Use this when you want to insert/update any table with exact column names.")

    mode = st.radio("Mode", ["INSERT", "UPDATE"], horizontal=True)
    table_name = st.text_input("Table name", value="contributions_legacy")

    if mode == "INSERT":
        payload_text = st.text_area("JSON payload", value=json.dumps({"member_id": 1, "amount": 500, "kind": "contribution"}, indent=2), height=200)
        if st.button("Run INSERT", use_container_width=True):
            try:
                payload = json.loads(payload_text)
                client.table(table_name).insert(payload).execute()
                st.success("Insert complete.")
            except Exception as e:
                show_api_error(e, "Insert failed")
    else:
        filter_col = st.text_input("Filter column", value="id")
        filter_val = st.text_input("Filter value", value="1")
        payload_text = st.text_area("JSON payload", value=json.dumps({"status": "paid"}, indent=2), height=200)
        if st.button("Run UPDATE", use_container_width=True):
            try:
                payload = json.loads(payload_text)
                client.table(table_name).update(payload).eq(filter_col, filter_val).execute()
                st.success("Update complete.")
            except Exception as e:
                show_api_error(e, "Update failed")
