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

def safe_select_autosort(c, table: str, limit=400):
    for col in ["created_at", "issued_at", "updated_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def load_member_registry(c):
    """
    member_registry columns (you showed):
      legacy_member_id (int), full_name (text), phone (text), is_active (bool), created_at (timestamptz)
    """
    resp = c.table("member_registry").select("legacy_member_id,full_name,is_active,phone,created_at").order("legacy_member_id").execute()
    rows = resp.data or []
    df = pd.DataFrame(rows)

    labels = []
    label_to_legacy = {}
    label_to_name = {}

    for r in rows:
        mid = int(r.get("legacy_member_id"))
        name = (r.get("full_name") or f"Member {mid}").strip()
        active = r.get("is_active", True)
        tag = "" if active in (None, True) else " (inactive)"
        label = f"{mid} — {name}{tag}"
        labels.append(label)
        label_to_legacy[label] = mid
        label_to_name[label] = name

    if not labels:
        labels = ["No members found"]
        label_to_legacy = {"No members found": 0}
        label_to_name = {"No members found": ""}

    return labels, label_to_legacy, label_to_name, df

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

# -------------------- Load Members --------------------
member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Contributions (Legacy)", "Foundation (Legacy)", "Loans (Legacy)", "JSON Inserter"])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("member_registry")
    st.dataframe(df_registry, use_container_width=True)

# ===================== CONTRIBUTIONS (LEGACY) =====================
with tabs[1]:
    st.subheader("contributions_legacy")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy", limit=500)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### Insert Contribution (legacy)")

    mem_label = st.selectbox("Member", member_labels, key="c_member_label")
    legacy_id = label_to_legacy_id.get(mem_label, 0)
    st.caption(f"member_id (legacy): **{legacy_id}**")

    amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
    kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
    session_id = st.text_input("session_id (uuid optional)", value="", key="c_session_id")

    if st.button("Insert Contribution", use_container_width=True, key="btn_c_insert"):
        payload = {"member_id": int(legacy_id), "amount": int(amount), "kind": str(kind)}
        if session_id.strip():
            payload["session_id"] = session_id.strip()
        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Contribution inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Contribution insert failed (RLS or invalid data)")

# ===================== FOUNDATION (LEGACY) =====================
with tabs[2]:
    st.subheader("foundation_payments_legacy")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy", limit=500)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment (legacy)")

    mem_label_f = st.selectbox("Member", member_labels, key="f_member_label")
    legacy_id_f = label_to_legacy_id.get(mem_label_f, 0)
    st.caption(f"member_id (legacy): **{legacy_id_f}**")

    amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="f_paid")
    amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="f_pending")
    status = st.selectbox("status", ["paid", "pending", "converted"], index=0, key="f_status")
    date_paid = st.date_input("date_paid", key="f_date_paid")
    converted_to_loan = st.selectbox("converted_to_loan", [False, True], index=0, key="f_conv")
    notes_f = st.text_input("notes (optional)", value="", key="f_notes")

    if st.button("Insert Foundation Payment", use_container_width=True, key="btn_f_insert"):
        payload = {
            "member_id": int(legacy_id_f),
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": str(status),
            "date_paid": f"{date_paid}T00:00:00Z",
            "converted_to_loan": bool(converted_to_loan),
        }
        if notes_f.strip():
            payload["notes"] = notes_f.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Foundation payment inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Foundation insert failed (RLS or invalid data)")

# ===================== LOANS (LEGACY) =====================
with tabs[3]:
    st.subheader("loans_legacy")

    try:
        st.dataframe(to_df(client.table("loans_legacy").select("*").order("created_at", desc=True).limit(300).execute()), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loans_legacy")

    st.divider()
    st.markdown("### Insert Loan (loans_legacy)")

    borrower_label = st.selectbox("Borrower", member_labels, key="loan_borrower_label")
    borrower_member_id = int(label_to_legacy_id.get(borrower_label, 0))
    borrower_name = label_to_name.get(borrower_label, "")

    surety_label = st.selectbox("Surety", member_labels, key="loan_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input("principal", min_value=500.0, step=500.0, value=500.0, key="loan_principal")
    interest_cycle_days = st.number_input("interest_cycle_days", min_value=1, value=26, step=1, key="loan_cycle_days")
    status = st.selectbox("status", ["active", "pending", "closed", "paid"], index=0, key="loan_status")

    # Njangi rule: 5% interest upfront
    interest = float(principal) * 0.05
    total_due = float(principal) + interest

    st.caption(f"Interest (5%): {interest}")
    st.caption(f"Total Due: {total_due}")

    if st.button("Insert Loan", use_container_width=True, key="btn_insert_loan"):
        # Optional eligibility check (if RPC exists & matches legacy bigint)
        try:
            elig = client.rpc("borrow_eligibility", {
                "p_borrower_id": borrower_member_id,
                "p_surety_id": surety_member_id,
                "p_requested": float(principal),
            }).execute().data
            if elig and isinstance(elig, list) and elig[0].get("eligible") is False:
                st.error(f"Not eligible: {elig[0].get('reason')}")
                st.stop()
        except Exception:
            # If RPC not available or blocked by RLS, we still allow admin insert
            pass

        now_iso = pd.Timestamp.utcnow().isoformat()
        payload = {
            "member_id": borrower_member_id,                 # nullable, but ok
            "borrower_member_id": borrower_member_id,        # NOT NULL
            "surety_member_id": surety_member_id,            # NOT NULL
            "borrower_name": borrower_name,                  # optional
            "surety_name": surety_name,                      # optional
            "principal": float(principal),                   # NOT NULL
            "interest": float(interest),                     # NOT NULL
            "total_due": float(total_due),                   # NOT NULL
            "principal_current": float(principal),           # optional
            "unpaid_interest": float(interest),              # optional
            "total_interest_generated": float(interest),      # optional
            "total_interest_accumulated": 0.0,               # NOT NULL
            "interest_cycle_days": int(interest_cycle_days),  # NOT NULL
            "last_interest_at": now_iso,                      # optional
            "last_interest_date": now_iso,                    # optional
            "issued_at": now_iso,                             # NOT NULL
            "created_at": now_iso,                            # NOT NULL
            "status": str(status),                            # NOT NULL
        }

        try:
            client.table("loans_legacy").insert(payload).execute()
            st.success("Loan inserted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (RLS or constraint/column mismatch)")

# ===================== JSON INSERTER =====================
with tabs[4]:
    st.subheader("Universal JSON Inserter")

    table = st.text_input("table", value="contributions_legacy", key="json_table")
    payload_text = st.text_area(
        "payload (json)",
        value='{"member_id": 1, "amount": 500, "kind": "contribution"}',
        height=220,
        key="json_payload",
    )

    if st.button("Run Insert", use_container_width=True, key="btn_json_insert"):
        try:
            payload = json.loads(payload_text)
            client.table(table).insert(payload).execute()
            st.success("Insert OK")
        except Exception as e:
            show_api_error(e, "Insert failed")
