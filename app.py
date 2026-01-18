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

def safe_select_autosort(c, table: str, limit=500):
    for col in ["created_at", "issued_at", "updated_at", "date_paid"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def load_member_choices(c):
    resp = c.table("member_registry").select("legacy_member_id,full_name,is_active").order("legacy_member_id").execute()
    rows = resp.data or []

    labels = []
    mapping = {}
    for r in rows:
        mid = int(r["legacy_member_id"])
        name = r.get("full_name") or f"Member {mid}"
        tag = "" if r.get("is_active", True) else " (inactive)"
        label = f"{mid} — {name}{tag}"
        labels.append(label)
        mapping[label] = mid

    return labels, mapping, pd.DataFrame(rows)

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
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = authed_client()

# -------------------- Load Members --------------------
member_choices, member_map, df_members = load_member_choices(client)

# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Contributions", "Foundation", "Loans", "JSON Inserter"])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("Member Registry")
    st.dataframe(df_members, use_container_width=True)

# ===================== CONTRIBUTIONS =====================
with tabs[1]:
    st.subheader("Contributions (legacy)")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions")

    st.divider()
    st.markdown("### Insert Contribution")

    m_label = st.selectbox("Member", member_choices, key="c_member")
    member_id = member_map[m_label]

    amount = st.number_input("Amount", step=500, min_value=0, value=500)
    kind = st.selectbox("Kind", ["contribution", "paid", "other"])
    session_id = st.text_input("Session ID (optional)")

    if st.button("Insert Contribution"):
        payload = {"member_id": member_id, "amount": int(amount), "kind": kind}
        if session_id.strip():
            payload["session_id"] = session_id.strip()

        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Contribution inserted")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed")

# ===================== FOUNDATION =====================
with tabs[2]:
    st.subheader("Foundation Payments (legacy)")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation")

    st.divider()
    st.markdown("### Insert Foundation Payment")

    f_label = st.selectbox("Member", member_choices, key="f_member")
    member_id = member_map[f_label]

    amount_paid = st.number_input("Amount Paid", step=500.0, value=500.0)
    amount_pending = st.number_input("Amount Pending", step=500.0, value=0.0)
    status = st.selectbox("Status", ["paid", "pending", "converted"])
    date_paid = st.date_input("Date Paid")
    converted = st.selectbox("Converted to Loan", [False, True])
    notes = st.text_input("Notes")

    if st.button("Insert Foundation Payment"):
        payload = {
            "member_id": member_id,
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": status,
            "date_paid": f"{date_paid}T00:00:00Z",
            "converted_to_loan": bool(converted),
        }
        if notes.strip():
            payload["notes"] = notes.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Foundation payment inserted")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed")

# ===================== LOANS =====================
with tabs[3]:
    st.subheader("Loans")

    LOANS_TABLE = "loans_legacy"

    try:
        st.dataframe(to_df(safe_select_autosort(client, LOANS_TABLE)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loans")

    st.divider()
    st.markdown("### Create Loan")

    borrower_label = st.selectbox("Borrower", member_choices, key="loan_borrower")
    borrower_id = member_map[borrower_label]

    surety_label = st.selectbox("Surety (optional)", ["(none)"] + member_choices)
    surety_id = None if surety_label == "(none)" else member_map[surety_label]

    requested = st.number_input("Requested Amount", step=500.0, value=500.0)

    if st.button("Check Eligibility"):
        try:
            s_id = surety_id if surety_id else borrower_id
            res = client.rpc("borrow_eligibility", {
                "p_borrower_id": borrower_id,
                "p_surety_id": s_id,
                "p_requested": float(requested)
            }).execute()
            st.json(res.data)
        except Exception as e:
            show_api_error(e, "Eligibility check failed")

    status = st.selectbox("Loan Status", ["active", "pending", "closed"])
    notes = st.text_input("Notes")

    if st.button("Insert Loan"):
        try:
            payload = {
                "member_id": borrower_id,
                "surety_id": surety_id,
                "principal": float(requested),
                "status": status,
                "notes": notes
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            client.table(LOANS_TABLE).insert(payload).execute()
            st.success("Loan inserted")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed")

# ===================== JSON INSERTER =====================
with tabs[4]:
    st.subheader("Universal JSON Inserter")

    table = st.text_input("Table name", value="contributions_legacy")
    payload_text = st.text_area("JSON payload", height=200)

    if st.button("Run Insert"):
        try:
            payload = json.loads(payload_text)
            client.table(table).insert(payload).execute()
            st.success("Insert successful")
        except Exception as e:
            show_api_error(e, "Insert failed")
