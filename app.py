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
    if not labels:
        labels = ["No members found"]
        mapping = {"No members found": 0}
    return labels, mapping, pd.DataFrame(rows)

def infer_table_columns_from_sample(c, table: str):
    """
    Returns a set of columns from one existing row.
    If table empty or select blocked, returns empty set.
    """
    try:
        sample_resp = c.table(table).select("*").limit(1).execute()
        rows = sample_resp.data or []
        if not rows:
            return set()
        return set(rows[0].keys())
    except Exception:
        return set()

def pick(cols: set, *names):
    for n in names:
        if n in cols:
            return n
    return None

# -------------------- Login --------------------
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Admin Login")

    if st.session_state.session is None:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", use_container_width=True, key="btn_login"):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.session = res.session
                st.rerun()
            except Exception as e:
                show_api_error(e, "Login failed")
    else:
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True, key="btn_logout"):
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
    st.subheader("Contributions (contributions_legacy)")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### Insert Contribution")

    m_label = st.selectbox("Member", member_choices, key="c_member_select")
    member_id = member_map.get(m_label, 0)

    amount = st.number_input("Amount", step=500, min_value=0, value=500, key="c_amount")
    kind = st.selectbox("Kind", ["contribution", "paid", "other"], key="c_kind")
    session_id = st.text_input("Session ID (optional)", key="c_session_id")

    if st.button("Insert Contribution", key="btn_insert_contrib"):
        payload = {"member_id": int(member_id), "amount": int(amount), "kind": str(kind)}
        if session_id.strip():
            payload["session_id"] = session_id.strip()

        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Contribution inserted")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS or invalid data)")

# ===================== FOUNDATION =====================
with tabs[2]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment")

    f_label = st.selectbox("Member", member_choices, key="f_member_select")
    f_member_id = member_map.get(f_label, 0)

    amount_paid = st.number_input("Amount Paid", step=500.0, min_value=0.0, value=500.0, key="f_amount_paid")
    amount_pending = st.number_input("Amount Pending", step=500.0, min_value=0.0, value=0.0, key="f_amount_pending")
    status = st.selectbox("Status", ["paid", "pending", "converted"], key="f_status")
    date_paid = st.date_input("Date Paid", key="f_date_paid")
    converted = st.selectbox("Converted to Loan", [False, True], key="f_converted")
    notes = st.text_input("Notes (optional)", key="f_notes")

    if st.button("Insert Foundation Payment", key="btn_insert_foundation"):
        payload = {
            "member_id": int(f_member_id),
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": str(status),
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
            show_api_error(e, "Insert failed (RLS or invalid data)")

# ===================== LOANS =====================
with tabs[3]:
    st.subheader("Loans (Surety Qualification + Insert)")

    LOANS_TABLE = "loans_legacy"  # change to "loans" if needed

    try:
        st.dataframe(to_df(safe_select_autosort(client, LOANS_TABLE, limit=200)), use_container_width=True)
    except Exception as e:
        show_api_error(e, f"Could not load {LOANS_TABLE}")

    st.divider()
    st.markdown("### Create Loan")

    borrower_label = st.selectbox("Borrower", member_choices, key="loan_borrower_select")
    borrower_id = member_map.get(borrower_label, 0)

    surety_label = st.selectbox("Surety (optional)", ["(none)"] + member_choices, key="loan_surety_select")
    surety_id = None if surety_label == "(none)" else member_map.get(surety_label, 0)

    requested = st.number_input("Requested Amount", step=500.0, min_value=0.0, value=500.0, key="loan_requested")

    st.markdown("### Check Eligibility (borrow_eligibility)")
    elig_cache_key = "elig_result"
    if elig_cache_key not in st.session_state:
        st.session_state[elig_cache_key] = None

    if st.button("Check Eligibility", key="btn_check_eligibility"):
        try:
            s_id = surety_id if surety_id else borrower_id
            res = client.rpc(
                "borrow_eligibility",
                {"p_borrower_id": int(borrower_id), "p_surety_id": int(s_id), "p_requested": float(requested)},
            ).execute()
            rows = res.data or []
            st.session_state[elig_cache_key] = rows[0] if rows else None
            if st.session_state[elig_cache_key]:
                st.success(f"Eligible: {st.session_state[elig_cache_key].get('eligible')} — {st.session_state[elig_cache_key].get('reason')}")
                st.json(st.session_state[elig_cache_key])
            else:
                st.warning("No eligibility rows returned.")
        except Exception as e:
            show_api_error(e, "Eligibility check failed")

    status = st.selectbox("Loan Status", ["active", "pending", "closed", "paid"], key="loan_status_select")
    loan_notes = st.text_input("Loan Notes (optional)", key="loan_notes")

    st.markdown("### Insert Loan (uses your actual loans_legacy columns)")
    cols = infer_table_columns_from_sample(client, LOANS_TABLE)

    if not cols:
        st.warning(
            f"Cannot infer columns for {LOANS_TABLE} (table empty or SELECT blocked by RLS). "
            "Use JSON Inserter after checking loans_legacy columns in SQL."
        )
        st.code("SQL: SELECT column_name, data_type FROM information_schema.columns WHERE table_name='loans_legacy';")

    if st.button("Insert Loan", key="btn_insert_loan"):
        elig = st.session_state.get(elig_cache_key)
        if elig is not None and not bool(elig.get("eligible")):
            st.error(f"Not eligible: {elig.get('reason')}")
            st.stop()

        if borrower_id <= 0 or requested <= 0:
            st.error("Select valid borrower and amount.")
            st.stop()

        # Map common loan column names (only set ones that exist)
        borrower_col = pick(cols, "borrower_member_id", "borrower_id", "member_id")
        surety_col = pick(cols, "surety_id", "surety_member_id", "guarantor_id")
        principal_col = pick(cols, "principal", "loan_amount", "amount", "requested_amount")
        status_col = pick(cols, "status", "loan_status")
        notes_col = pick(cols, "notes", "note", "remark")
        issued_col = pick(cols, "issued_at", "created_at", "date_issued", "start_date")

        if not borrower_col:
            st.error(f"loans table has no borrower column I recognize. Columns: {sorted(list(cols))}")
            st.stop()

        payload = {borrower_col: int(borrower_id)}

        if surety_col and surety_id is not None:
            payload[surety_col] = int(surety_id)

        if principal_col:
            payload[principal_col] = float(requested)

        if status_col:
            payload[status_col] = str(status)

        if notes_col and loan_notes.strip():
            payload[notes_col] = loan_notes.strip()

        # If issued column is NOT NULL, set it
        if issued_col:
            payload[issued_col] = pd.Timestamp.utcnow().isoformat()

        try:
            client.table(LOANS_TABLE).insert(payload).execute()
            st.success("Loan inserted")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (RLS or column mismatch)")

# ===================== JSON INSERTER =====================
with tabs[4]:
    st.subheader("Universal JSON Inserter")

    table = st.text_input("Table name", value="contributions_legacy", key="json_table")
    payload_text = st.text_area("JSON payload", height=200, key="json_payload")

    if st.button("Run Insert", key="btn_json_insert"):
        try:
            payload = json.loads(payload_text)
            client.table(table).insert(payload).execute()
            st.success("Insert successful")
        except Exception as e:
            show_api_error(e, "Insert failed")
