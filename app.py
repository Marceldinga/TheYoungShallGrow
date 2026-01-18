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

def safe_select_autosort(c, table: str, limit=300):
    for col in ["created_at", "issued_at", "updated_at", "date_paid"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def load_registry_and_maps(c):
    """
    Returns:
      - legacy_labels: dropdown like "10 — Name"
      - legacy_label_to_legacy_id: label -> legacy_member_id (int)
      - legacy_label_to_uuid: label -> member_uuid (uuid string) (from member_map)
      - df_registry, df_map
    """
    reg = c.table("member_registry").select("legacy_member_id,full_name,is_active").order("legacy_member_id").execute().data or []
    df_reg = pd.DataFrame(reg)

    mp = c.table("member_map").select("legacy_member_id,member_id").order("legacy_member_id").execute().data or []
    df_map = pd.DataFrame(mp)

    # build lookup: legacy -> uuid
    legacy_to_uuid = {}
    for r in mp:
        legacy_to_uuid[int(r["legacy_member_id"])] = r["member_id"]

    labels = []
    label_to_legacy = {}
    label_to_uuid = {}

    for r in reg:
        mid = int(r["legacy_member_id"])
        name = r.get("full_name") or f"Member {mid}"
        active = r.get("is_active", True)
        tag = "" if active in (None, True) else " (inactive)"
        label = f"{mid} — {name}{tag}"
        labels.append(label)
        label_to_legacy[label] = mid
        label_to_uuid[label] = legacy_to_uuid.get(mid)  # may be None if mapping missing

    if not labels:
        labels = ["No members found"]
        label_to_legacy = {"No members found": 0}
        label_to_uuid = {"No members found": None}

    return labels, label_to_legacy, label_to_uuid, df_reg, df_map

def infer_cols(c, table: str):
    try:
        sample = c.table(table).select("*").limit(1).execute().data or []
        return set(sample[0].keys()) if sample else set()
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

# -------------------- Load registry + member_map --------------------
member_labels, label_to_legacy_id, label_to_uuid, df_registry, df_map = load_registry_and_maps(client)

# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Contributions (Legacy)", "Foundation (Legacy)", "Loans (New)", "JSON Inserter"])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("member_registry")
    st.dataframe(df_registry, use_container_width=True)
    st.subheader("member_map (legacy -> uuid)")
    st.dataframe(df_map, use_container_width=True)
    st.info("Loans use member_map.member_id (UUID). Legacy tables use legacy_member_id (int).")

# ===================== CONTRIBUTIONS (LEGACY) =====================
with tabs[1]:
    st.subheader("contributions_legacy")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### Insert Contribution (legacy)")

    mem_label = st.selectbox("Member", member_labels, key="c_member_label")
    legacy_id = label_to_legacy_id.get(mem_label, 0)

    amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
    kind = st.selectbox("kind", ["contribution", "paid", "other"], key="c_kind")
    session_id = st.text_input("session_id (uuid optional)", key="c_session_id")

    if st.button("Insert Contribution", key="btn_c_insert"):
        payload = {"member_id": int(legacy_id), "amount": int(amount), "kind": str(kind)}
        if session_id.strip():
            payload["session_id"] = session_id.strip()
        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed")

# ===================== FOUNDATION (LEGACY) =====================
with tabs[2]:
    st.subheader("foundation_payments_legacy")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy")), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment (legacy)")

    mem_label_f = st.selectbox("Member", member_labels, key="f_member_label")
    legacy_id_f = label_to_legacy_id.get(mem_label_f, 0)

    amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="f_paid")
    amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="f_pending")
    status = st.selectbox("status", ["paid", "pending", "converted"], key="f_status")
    date_paid = st.date_input("date_paid", key="f_date_paid")
    converted_to_loan = st.selectbox("converted_to_loan", [False, True], key="f_conv")
    notes = st.text_input("notes (optional)", key="f_notes")

    if st.button("Insert Foundation Payment", key="btn_f_insert"):
        payload = {
            "member_id": int(legacy_id_f),
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": str(status),
            "date_paid": f"{date_paid}T00:00:00Z",
            "converted_to_loan": bool(converted_to_loan),
        }
        if notes.strip():
            payload["notes"] = notes.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed")

# ===================== LOANS (NEW) =====================
with tabs[3]:
    st.subheader("Loans (uses UUID members via member_map)")

    LOANS_TABLE = "loans"  # <-- your new system loans table (uuid-based). Change to "loans_legacy" if needed.

    try:
        st.dataframe(to_df(safe_select_autosort(client, LOANS_TABLE, limit=200)), use_container_width=True)
    except Exception as e:
        show_api_error(e, f"Could not load {LOANS_TABLE}")

    st.divider()
    st.markdown("### Create Loan")

    borrower_label = st.selectbox("Borrower", member_labels, key="loan_borrower_label")
    borrower_uuid = label_to_uuid.get(borrower_label)

    surety_label = st.selectbox("Surety (optional)", ["(none)"] + member_labels, key="loan_surety_label")
    surety_uuid = None if surety_label == "(none)" else label_to_uuid.get(surety_label)

    requested = st.number_input("requested amount", min_value=0.0, step=500.0, value=500.0, key="loan_requested")
    status = st.selectbox("status", ["active", "pending", "closed", "paid"], key="loan_status")
    loan_notes = st.text_input("notes (optional)", key="loan_notes")

    if borrower_uuid is None:
        st.error("This borrower has NO member_map UUID. Fix member_map first for this legacy_member_id.")
    if surety_label != "(none)" and surety_uuid is None:
        st.error("This surety has NO member_map UUID. Fix member_map first.")

    st.markdown("### Check Eligibility (borrow_eligibility)")

    if st.button("Check Eligibility", key="btn_check_elig"):
        try:
            # Try calling with UUID params (if your function supports)
            s_uuid = surety_uuid if surety_uuid else borrower_uuid
            res = client.rpc("borrow_eligibility", {
                "p_borrower_id": borrower_uuid,
                "p_surety_id": s_uuid,
                "p_requested": float(requested),
            }).execute()
            st.json(res.data)
            st.session_state["elig"] = (res.data[0] if (res.data and isinstance(res.data, list)) else None)
        except Exception as e:
            show_api_error(e, "Eligibility check failed (your function may be bigint-based)")

    st.divider()
    st.markdown("### Insert Loan (only sends columns that exist)")

    cols = infer_cols(client, LOANS_TABLE)
    if not cols:
        st.warning(f"Cannot infer columns for {LOANS_TABLE} (empty table or RLS blocks select). Use JSON Inserter.")
    else:
        borrower_col = pick(cols, "borrower_member_id", "member_id", "borrower_id")
        surety_col = pick(cols, "surety_id", "surety_member_id")
        principal_col = pick(cols, "principal", "loan_amount", "amount", "requested_amount")
        status_col = pick(cols, "status", "loan_status")
        notes_col = pick(cols, "notes", "note", "remark")
        issued_col = pick(cols, "issued_at", "created_at", "date_issued", "start_date")

        if st.button("Insert Loan", key="btn_insert_loan"):
            if borrower_uuid is None:
                st.error("Borrower has no UUID mapping in member_map.")
                st.stop()
            if requested <= 0:
                st.error("Requested must be > 0.")
                st.stop()

            payload = {}
            if borrower_col:
                payload[borrower_col] = borrower_uuid
            if surety_col and surety_uuid:
                payload[surety_col] = surety_uuid
            if principal_col:
                payload[principal_col] = float(requested)
            if status_col:
                payload[status_col] = str(status)
            if notes_col and loan_notes.strip():
                payload[notes_col] = loan_notes.strip()
            if issued_col:
                payload[issued_col] = pd.Timestamp.utcnow().isoformat()

            try:
                client.table(LOANS_TABLE).insert(payload).execute()
                st.success("Loan inserted.")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Loan insert failed (RLS or column mismatch)")

# ===================== JSON INSERTER =====================
with tabs[4]:
    st.subheader("Universal JSON Inserter")

    table = st.text_input("table", value="contributions_legacy", key="json_table")
    payload_text = st.text_area("payload (json)", value='{"member_id": 1, "amount": 500, "kind": "contribution"}', height=220, key="json_payload")

    if st.button("Run Insert", key="btn_json_insert"):
        try:
            payload = json.loads(payload_text)
            client.table(table).insert(payload).execute()
            st.success("Insert OK")
        except Exception as e:
            show_api_error(e, "Insert failed")
