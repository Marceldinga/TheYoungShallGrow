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

def load_member_choices(c):
    """
    Dropdown data from member_registry:
      label: "10 — John Doe (inactive)"
      value inserted into legacy tables: member_id = legacy_member_id (int)
    """
    try:
        resp = c.table("member_registry").select("legacy_member_id,full_name,is_active").order("legacy_member_id").execute()
        rows = resp.data or []
        df = pd.DataFrame(rows)

        choices = []
        label_to_id = {}
        for r in rows:
            mid = r.get("legacy_member_id")
            name = r.get("full_name") or f"Member {mid}"
            active = r.get("is_active")
            tag = "" if active in (None, True) else " (inactive)"
            label = f"{mid} — {name}{tag}"
            choices.append(label)
            label_to_id[label] = int(mid)

        if not choices:
            choices = ["No members found"]
            label_to_id = {"No members found": 0}

        return choices, label_to_id, df
    except Exception as e:
        show_api_error(e, "Could not load member_registry for dropdown")
        return ["No members found"], {"No members found": 0}, pd.DataFrame()

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

# Load member dropdown ONCE
member_choices, member_label_to_id, df_member_registry = load_member_choices(client)

# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Rotation", "Contributions", "Foundation", "Loans", "JSON Inserter"])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("All Njangi Members (member_registry)")
    st.dataframe(df_member_registry, use_container_width=True)

# ===================== ROTATION =====================
with tabs[1]:
    st.subheader("Rotation State (app_state)")
    try:
        state = client.table("app_state").select("*").execute()
        st.dataframe(to_df(state), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load app_state")

# ===================== CONTRIBUTIONS =====================
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
        chosen_member_label = st.selectbox("Member", options=member_choices, index=0, key="c_member_label")
        c_member_id = member_label_to_id.get(chosen_member_label, 0)
        st.caption(f"member_id to insert: **{c_member_id}**")
    with c2:
        c_amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
    with c3:
        c_kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
    with c4:
        c_session_id = st.text_input("session_id (uuid, optional)", value="", key="c_session")

    if st.button("Insert Contribution (legacy)", use_container_width=True, key="btn_ins_contrib"):
        if c_member_id <= 0:
            st.error("No valid member selected.")
        else:
            payload = {
                "member_id": int(c_member_id),
                "amount": int(c_amount),
                "kind": str(c_kind),
            }
            if c_session_id.strip():
                payload["session_id"] = c_session_id.strip()

            try:
                client.table("contributions_legacy").insert(payload).execute()
                st.success("Inserted contribution.")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Insert failed (RLS or invalid session_id uuid)")

# ===================== FOUNDATION =====================
with tabs[3]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        foundation = safe_select_table(client, "foundation_payments_legacy", order_col="id", desc=True, limit=500)
        st.dataframe(to_df(foundation), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment (legacy)")
    st.caption("Columns: member_id, amount_paid, amount_pending, status, date_paid, notes, converted_to_loan.")

    f1, f2, f3 = st.columns(3)
    with f1:
        chosen_member_label_f = st.selectbox("Member", options=member_choices, index=0, key="f_member_label")
        f_member_id = member_label_to_id.get(chosen_member_label_f, 0)
        st.caption(f"member_id to insert: **{f_member_id}**")
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
        if f_member_id <= 0:
            st.error("No valid member selected.")
        else:
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

# ===================== LOANS (SURETY QUALIFY + INSERT) =====================
with tabs[4]:
    st.subheader("Loans (Surety Qualification + Insert)")

    LOANS_TABLE = "loans_legacy"  # change to "loans" if needed

    try:
        loans_resp = safe_select_table(client, LOANS_TABLE, order_col="id", desc=True, limit=200)
        st.dataframe(to_df(loans_resp), use_container_width=True)
    except Exception as e:
        show_api_error(e, f"Could not load {LOANS_TABLE}")

    st.divider()
    st.markdown("### Create a Loan")

    a1, a2, a3 = st.columns(3)
    with a1:
        borrower_label = st.selectbox("Borrower", options=member_choices, index=0, key="loan_borrower")
        borrower_id = member_label_to_id.get(borrower_label, 0)
        st.caption(f"borrower_id: **{borrower_id}**")
    with a2:
        surety_label = st.selectbox("Surety (optional)", options=["(none)"] + member_choices, index=0, key="loan_surety")
        surety_id = None if surety_label == "(none)" else member_label_to_id.get(surety_label, 0)
        st.caption(f"surety_id: **{surety_id if surety_id else 'None'}**")
    with a3:
        requested = st.number_input("Requested amount", min_value=0.0, step=500.0, value=500.0, key="loan_requested")

    st.markdown("### Check Surety Eligibility (borrow_eligibility)")
    st.caption("Calls your DB function: borrow_eligibility(p_borrower_id, p_surety_id, p_requested)")

    elig_result = None
    if st.button("Check Eligibility", use_container_width=True, key="btn_check_elig"):
        if borrower_id <= 0:
            st.error("Select a valid borrower.")
        elif requested <= 0:
            st.error("Requested amount must be > 0.")
        else:
            try:
                s_id = surety_id if surety_id is not None else borrower_id
                elig = client.rpc(
                    "borrow_eligibility",
                    {"p_borrower_id": int(borrower_id), "p_surety_id": int(s_id), "p_requested": float(requested)},
                ).execute()
                rows = elig.data or []
                if rows:
                    elig_result = rows[0]
                    st.success(f"Eligible: {elig_result.get('eligible')} — {elig_result.get('reason')}")
                    st.json(elig_result)
                else:
                    st.warning("No eligibility rows returned.")
            except Exception as e:
                show_api_error(e, "Eligibility check failed (RPC missing or RLS blocked)")

    st.divider()
    st.markdown("### Insert Loan")

    status = st.selectbox("status (optional)", ["active", "pending", "closed", "paid"], index=0, key="loan_status")
    notes = st.text_input("notes (optional)", value="", key="loan_notes")

    if st.button("Insert Loan", use_container_width=True, key="btn_insert_loan"):
        if borrower_id <= 0:
            st.error("Select a valid borrower.")
            st.stop()
        if requested <= 0:
            st.error("Requested amount must be > 0.")
            st.stop()

        # If eligibility was checked and returned false, block.
        if elig_result is not None and not bool(elig_result.get("eligible")):
            st.error(f"Not eligible: {elig_result.get('reason')}")
            st.stop()

        # Infer loans table columns from one row (avoids column mismatch)
        sample = None
        try:
            sample_resp = client.table(LOANS_TABLE).select("*").limit(1).execute()
            sample_rows = sample_resp.data or []
            sample = sample_rows[0] if sample_rows else None
        except Exception:
            sample = None

        if not sample:
            st.error(
                f"{LOANS_TABLE} is empty (or RLS blocks select). "
                "Add one row manually or use JSON Inserter with correct columns."
            )
            st.stop()

        cols = set(sample.keys())

        def pick(*names):
            for n in names:
                if n in cols:
                    return n
            return None

        borrower_col = pick("borrower_id", "borrower_member_id", "member_id", "member")
        surety_col = pick("surety_id", "surety_member_id", "guarantor_id")
        principal_col = pick("principal", "amount", "loan_amount", "principal_amount", "requested_amount")
        interest_col = pick("interest", "interest_amount")
        total_due_col = pick("total_due", "total", "total_amount", "amount_due")
        status_col = pick("status", "loan_status")
        issued_col = pick("issued_at", "created_at", "date_issued", "start_date")
        notes_col = pick("notes", "note", "remark", "reason")

        if not borrower_col:
            st.error(f"Could not find borrower column in {LOANS_TABLE}. Columns: {sorted(list(cols))}")
            st.stop()

        payload = {borrower_col: int(borrower_id)}

        if surety_col and surety_id is not None:
            payload[surety_col] = int(surety_id)

        if principal_col:
            payload[principal_col] = float(requested)

        # Optional: 5% upfront interest if columns exist
        if interest_col and total_due_col:
            upfront_interest = float(requested) * 0.05
            payload[interest_col] = upfront_interest
            payload[total_due_col] = float(requested) + upfront_interest
        elif total_due_col and principal_col:
            payload[total_due_col] = float(requested)

        if status_col:
            payload[status_col] = str(status)

        # date/issued: try ISO; if DB has defaults, you can omit it
        if issued_col:
            payload[issued_col] = pd.Timestamp.utcnow().isoformat()

        if notes_col and notes.strip():
            payload[notes_col] = notes.strip()

        try:
            client.table(LOANS_TABLE).insert(payload).execute()
            st.success("Loan inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (RLS or column mismatch). Use JSON Inserter.")

# ===================== JSON INSERTER =====================
with tabs[5]:
    st.subheader("Universal Insert / Update (JSON)")
    st.caption("Use this to insert/update any table with exact column names.")

    mode = st.radio("Mode", ["INSERT", "UPDATE"], horizontal=True)
    table_name = st.text_input("Table name", value="contributions_legacy")

    if mode == "INSERT":
        payload_text = st.text_area(
            "JSON payload",
            value=json.dumps({"member_id": 1, "amount": 500, "kind": "contribution"}, indent=2),
            height=200,
        )
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
