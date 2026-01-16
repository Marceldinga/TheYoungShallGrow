
import pandas as pd
import streamlit as st
from datetime import date, timedelta
from supabase import create_client

# ============================================================
# UPDATED SECURE DASHBOARD (Single Script)
# ✅ Member sees ONLY their own data (email -> members.id)
# ✅ Loans FIX: loans table uses borrower_member_id (NOT member_id)
# ✅ Admin can optionally switch member_id (requires admin RLS)
# ✅ NEW: Member can request loan (loan_requests)
# ✅ NEW: Admin can approve/reject loan requests (+ optional RPC approve_loan_request)
# ✅ NEW: Admin can add data (contributions/foundation/fines/payouts/loans) from dashboard
# ✅ NEW: Show current bi-weekly beneficiary (if view current_cycle_beneficiary exists)
# ✅ NEW: Admin payout + rotate next beneficiary (if RPC record_payout_and_rotate_next exists)
# ============================================================

# ----------------------------
# SETTINGS
# ----------------------------
st.set_page_config(page_title="The Young Shall Grow – Dashboard", page_icon="🌱", layout="wide")
st.set_option("client.showErrorDetails", False)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
ADMIN_EMAILS = [e.strip().lower() for e in str(st.secrets.get("ADMIN_EMAILS", "")).split(",") if e.strip()]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ----------------------------
# THEME
# ----------------------------
st.markdown(
    """
<style>
:root{
  --bg:#0b1220;
  --stroke:rgba(148,163,184,.18);
  --text:#e5e7eb;
  --muted:rgba(229,231,235,.65);
  --brand:#22c55e;
  --brand2:#14b8a6;
  --shadow: 0 18px 50px rgba(0,0,0,.35);
}
.stApp { background: linear-gradient(180deg, var(--bg), #070b14 70%); color: var(--text); }
.block-container{max-width:1180px;padding-top:1.2rem;padding-bottom:2rem;}
.hdr{
  border:1px solid var(--stroke);
  background: linear-gradient(135deg, rgba(34,197,94,.10), rgba(20,184,166,.08));
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: var(--shadow);
}
.badge{
  display:inline-flex; gap:8px; align-items:center;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid var(--stroke);
  background: rgba(255,255,255,.04);
  font-size: 13px;
  color: var(--text);
}
.badge span{ color: var(--muted); }
.kpi{
  border:1px solid var(--stroke);
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 26px rgba(0,0,0,.20);
}
.kpi .label{ color: var(--muted); font-size: 13px; }
.kpi .value{ font-size: 28px; font-weight: 800; margin-top: 6px; }
.kpi .accent{ width:100%; height:4px; border-radius:999px; background: linear-gradient(90deg, var(--brand), var(--brand2)); margin-top: 10px; }
.small-muted{ color: var(--muted); font-size: 13px; }
hr{ border: none; border-top: 1px solid var(--stroke); margin: 14px 0; }
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------
# SESSION HELPERS
# ----------------------------
def is_logged_in() -> bool:
    return bool(st.session_state.get("access_token"))

def logout():
    st.session_state.clear()
    st.rerun()

def attach_jwt(access_token: str):
    supabase.postgrest.auth(access_token)

# ----------------------------
# LOGIN
# ----------------------------
if not is_logged_in():
    st.markdown(
        "<div class='hdr'><h1 style='margin:0'>🌱 Login</h1>"
        "<div class='small-muted'>Sign in with your Supabase Auth email/password</div></div>",
        unsafe_allow_html=True,
    )
    st.write("")

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["access_token"] = res.session.access_token
            st.session_state["refresh_token"] = res.session.refresh_token
            st.session_state["user_email"] = (res.user.email or "").lower()
            attach_jwt(st.session_state["access_token"])
            st.rerun()
        except Exception:
            st.error("Login failed. Check email/password or confirm the user exists in Supabase Auth.")
    st.stop()

# Always re-attach JWT on rerun
attach_jwt(st.session_state["access_token"])

user_email = (st.session_state.get("user_email") or "").lower()
is_admin = user_email in ADMIN_EMAILS

# ----------------------------
# ✅ IMPORTANT: Get member row by email (NOT limit(1) without filter)
# ----------------------------
def get_member_by_email(email: str):
    try:
        data = supabase.table("members").select("*").ilike("email", email).limit(1).execute().data
        if data:
            return data[0]
    except Exception:
        pass

    try:
        data = supabase.table("members").select("*").eq("email", email).limit(1).execute().data
        if data:
            return data[0]
    except Exception:
        pass

    return None

my_member = get_member_by_email(user_email)
if not my_member:
    st.error(
        "❌ Logged in, but no matching row found in public.members.\n\n"
        "Fix: ensure public.members.email matches the Auth email exactly."
    )
    st.stop()

# NOTE: your app uses members.id as the numeric member id (e.g., 1,2,3...)
my_member_id = int(my_member["id"])

# ----------------------------
# HEADER
# ----------------------------
st.markdown(
    f"""
    <div class='hdr'>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h1 style="margin:0">📊 Dashboard</h1>
          <div class="small-muted">
            Logged in as <b>{user_email}</b> {'(admin)' if is_admin else ''} • Your member_id = <b>{my_member_id}</b>
          </div>
        </div>
        <div style="display:flex;gap:10px;align-items:center">
          <div class="badge"><b>{user_email}</b> <span>{'(admin)' if is_admin else ''}</span></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")
st.button("Logout", on_click=logout)

# ----------------------------
# BENEFICIARY (bi-weekly) – best effort
# ----------------------------
def show_current_beneficiary():
    try:
        # This should be a VIEW you created: public.current_cycle_beneficiary
        cur = supabase.table("current_cycle_beneficiary").select("*").execute().data or []
        if not cur:
            return
        c = cur[0]
        bname = c.get("beneficiary_name") or c.get("beneficiary_email") or "Unknown"
        st.info(
            f"👤 **Current Beneficiary:** {bname}\n\n"
            f"🔁 **Cycle #{c.get('cycle_no','')}**: {c.get('start_date','')} → {c.get('end_date','')}\n\n"
            f"💰 **Payout Date:** {c.get('payout_date','')}"
        )
    except Exception:
        # If the view does not exist, ignore silently
        pass

show_current_beneficiary()

# ----------------------------
# FILTERS
# ----------------------------
st.subheader("Filters")

if is_admin:
    a1, f1, f2, f3, f4 = st.columns([2, 2, 3, 2, 2])
    admin_member_id = a1.text_input("Member ID (admin)", placeholder="e.g. 10")
else:
    f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
    admin_member_id = ""

range_opt = f1.selectbox("Time range", ["All time", "Last 30 days", "Last 90 days", "This year"], index=0)
search_text = f2.text_input("Quick search", placeholder="e.g. unpaid, paid, pending, late...")
record_id = f3.text_input("Record ID", placeholder="e.g. 58")
show_only_unpaid = f4.checkbox("Only unpaid fines", value=False)

# effective member view
effective_member_id = my_member_id
if is_admin and admin_member_id.strip():
    try:
        effective_member_id = int(admin_member_id.strip())
    except Exception:
        effective_member_id = my_member_id

st.markdown(
    f"<div class='small-muted'>Currently viewing: <b>member_id = {effective_member_id}</b></div>",
    unsafe_allow_html=True,
)

# ----------------------------
# FILTER HELPERS
# ----------------------------
def apply_date_filter(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    if range_opt == "Last 30 days":
        return df[df[date_col] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=30))]
    if range_opt == "Last 90 days":
        return df[df[date_col] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=90))]
    if range_opt == "This year":
        start = pd.Timestamp.utcnow().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return df[df[date_col] >= start]
    return df

def apply_search(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df.empty or not search_text.strip():
        return df
    s = search_text.strip().lower()
    mask = pd.Series(False, index=df.index)
    for c in cols:
        if c in df.columns:
            mask = mask | df[c].astype(str).str.lower().str.contains(s, na=False)
    return df[mask]

def apply_record_id_filter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or not record_id.strip():
        return df
    try:
        rid = int(record_id.strip())
    except Exception:
        return df
    if "id" not in df.columns:
        return df
    return df[pd.to_numeric(df["id"], errors="coerce") == rid]

def safe_sum(df, col):
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

# ----------------------------
# FETCH HELPERS
# ----------------------------
def fetch_df(table: str, cols="*", member_col="member_id", order_col=None, date_col=None) -> pd.DataFrame:
    q = supabase.table(table).select(cols).eq(member_col, effective_member_id)
    if order_col:
        q = q.order(order_col, desc=True)
    data = q.execute().data
    df = pd.DataFrame(data or [])
    if date_col:
        df = apply_date_filter(df, date_col)
    return df

def fetch_all_df_admin(table: str, cols="*", order_col=None, date_col=None) -> pd.DataFrame:
    # For admin-only pages where you want all rows (RLS must allow admin)
    q = supabase.table(table).select(cols)
    if order_col:
        q = q.order(order_col, desc=True)
    data = q.execute().data
    df = pd.DataFrame(data or [])
    if date_col:
        df = apply_date_filter(df, date_col)
    return df

# ----------------------------
# LOAD DATA (member-scoped view)
# ----------------------------
contrib_df = fetch_df(
    "contributions",
    "id,member_id,amount,kind,created_at,updated_at",
    member_col="member_id",
    order_col="created_at",
    date_col="created_at",
)
contrib_df = apply_search(contrib_df, ["kind"])
contrib_df = apply_record_id_filter(contrib_df)

found_df = fetch_df(
    "foundation_payments",
    "id,member_id,amount_paid,amount_pending,status,date_paid,notes,updated_at,converted_to_loan,converted_loan_id",
    member_col="member_id",
    order_col="date_paid",
    date_col="date_paid",
)
found_df = apply_search(found_df, ["status", "notes"])
found_df = apply_record_id_filter(found_df)

fines_df = fetch_df(
    "fines",
    "id,member_id,amount,reason,status,paid_at,created_at,updated_at",
    member_col="member_id",
    order_col="created_at",
    date_col="created_at",
)
fines_df = apply_search(fines_df, ["reason", "status"])
if show_only_unpaid and "status" in fines_df.columns:
    fines_df = fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]
fines_df = apply_record_id_filter(fines_df)

# ✅ loans: borrower_member_id (FIX)
loans_df = fetch_df(
    "loans",
    "*",
    member_col="borrower_member_id",
    order_col="created_at",
    date_col="created_at",
)
loans_df = apply_search(loans_df, ["status", "borrower_name", "surety_name"])
loans_df = apply_record_id_filter(loans_df)

# Loan requests (members see their own by RLS; admin can see all on admin tab)
def fetch_loan_requests_member() -> pd.DataFrame:
    try:
        q = supabase.table("loan_requests").select("*").eq("member_id", effective_member_id).order("created_at", desc=True)
        data = q.execute().data
        return pd.DataFrame(data or [])
    except Exception:
        return pd.DataFrame([])

loan_req_df = fetch_loan_requests_member()

# ----------------------------
# KPIs
# ----------------------------
total_contrib = safe_sum(contrib_df, "amount")
total_found_paid = safe_sum(found_df, "amount_paid")

unpaid_fines_amt = 0.0
if not fines_df.empty and "status" in fines_df.columns and "amount" in fines_df.columns:
    unpaid_fines_amt = float(
        pd.to_numeric(
            fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

loan_total = 0.0
for col in ["principal", "total_due", "balance", "principal_current"]:
    if not loans_df.empty and col in loans_df.columns:
        loan_total = safe_sum(loans_df, col)
        break

k1, k2, k3, k4, k5 = st.columns(5)
k1.markdown(f"<div class='kpi'><div class='label'>Total Contributions</div><div class='value'>{total_contrib:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='kpi'><div class='label'>Total Foundation Paid</div><div class='value'>{total_found_paid:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='kpi'><div class='label'>Unpaid Fines</div><div class='value'>{unpaid_fines_amt:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k4.markdown(f"<div class='kpi'><div class='label'>Active Loans</div><div class='value'>{active_loans}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k5.markdown(f"<div class='kpi'><div class='label'>Loan Total</div><div class='value'>{loan_total:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ----------------------------
# ACTION HELPERS (Admin Inserts)
# ----------------------------
def admin_insert(table: str, payload: dict):
    # Best-effort insert; RLS must allow admin
    return supabase.table(table).insert(payload).execute()

def admin_update(table: str, payload: dict, where_col: str, where_val):
    return supabase.table(table).update(payload).eq(where_col, where_val).execute()

# ----------------------------
# TABLES + ACTIONS
# ----------------------------
tab_names = ["Contributions", "Foundation Payments", "Fines", "Loans", "Loan Requests", "My Profile"]
if is_admin:
    tab_names += ["Admin: Add Data", "Admin: Approvals", "Admin: Payout & Rotate"]

tabs = st.tabs(tab_names)

# 1) Contributions
with tabs[0]:
    st.subheader("Contributions")
    st.dataframe(contrib_df, use_container_width=True)

# 2) Foundation
with tabs[1]:
    st.subheader("Foundation Payments")
    st.dataframe(found_df, use_container_width=True)

# 3) Fines
with tabs[2]:
    st.subheader("Fines")
    st.dataframe(fines_df, use_container_width=True)

# 4) Loans (ALL COLUMNS)
with tabs[3]:
    st.subheader("Loans (All Columns)")
    if loans_df.empty:
        st.info("No loans found for this member.")
    else:
        st.dataframe(loans_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Loans CSV",
            data=loans_df.to_csv(index=False).encode("utf-8"),
            file_name="loans.csv",
            mime="text/csv",
            use_container_width=True,
        )

# 5) Loan Requests (Member can request)
with tabs[4]:
    st.subheader("Loan Requests")

    # Member request form (members + admin can also request as a member)
    with st.expander("➕ Request a loan", expanded=not is_admin):
        with st.form("loan_request_form", clear_on_submit=True):
            req_amount = st.number_input("Requested Amount", min_value=0.0, value=0.0, step=500.0)
            req_purpose = st.text_input("Purpose (optional)")
            submit_req = st.form_submit_button("Submit Loan Request")

        if submit_req:
            if req_amount <= 0:
                st.error("Amount must be greater than 0.")
            else:
                try:
                    payload = {
                        "member_id": effective_member_id,  # numeric member id in your schema
                        "amount": float(req_amount),
                        "purpose": req_purpose,
                        "status": "pending",
                    }
                    supabase.table("loan_requests").insert(payload).execute()
                    st.success("Loan request submitted. Please wait for admin approval.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to submit request: {e}")

    # Show my requests (member-scoped)
    if loan_req_df.empty:
        st.info("No loan requests found.")
    else:
        st.dataframe(loan_req_df, use_container_width=True, hide_index=True)

# 6) Profile
with tabs[5]:
    st.subheader("My Profile")
    st.json(my_member)

# ----------------------------
# ADMIN TABS
# ----------------------------
if is_admin:
    # Admin: Add Data
    with tabs[6]:
        st.subheader("Admin: Add Data (Insert)")

        st.caption("These inserts require your admin RLS policies to allow writes.")

        c1, c2 = st.columns(2)

        # Add Contribution
        with c1:
            st.markdown("### Add Contribution")
            with st.form("add_contrib", clear_on_submit=True):
                m_id = st.number_input("Member ID", min_value=1, value=int(effective_member_id), step=1)
                amount = st.number_input("Amount", min_value=0.0, value=0.0, step=500.0)
                kind = st.text_input("Kind", value="contribution")
                ok = st.form_submit_button("Insert Contribution")
            if ok:
                try:
                    admin_insert("contributions", {"member_id": int(m_id), "amount": float(amount), "kind": kind})
                    st.success("Contribution inserted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        # Add Foundation Payment
        with c2:
            st.markdown("### Add Foundation Payment")
            with st.form("add_found", clear_on_submit=True):
                m_id = st.number_input("Member ID ", min_value=1, value=int(effective_member_id), step=1, key="fp_mid")
                amt_paid = st.number_input("Amount Paid", min_value=0.0, value=0.0, step=500.0)
                amt_pending = st.number_input("Amount Pending", min_value=0.0, value=0.0, step=500.0)
                status = st.selectbox("Status", ["paid", "pending"], index=0)
                date_paid = st.date_input("Date", value=date.today())
                notes = st.text_input("Notes", value="")
                ok = st.form_submit_button("Insert Foundation Payment")
            if ok:
                try:
                    admin_insert(
                        "foundation_payments",
                        {
                            "member_id": int(m_id),
                            "amount_paid": float(amt_paid),
                            "amount_pending": float(amt_pending),
                            "status": status,
                            "date_paid": str(date_paid),
                            "notes": notes,
                        },
                    )
                    st.success("Foundation payment inserted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        st.markdown("---")
        c3, c4 = st.columns(2)

        # Add Fine
        with c3:
            st.markdown("### Add Fine")
            with st.form("add_fine", clear_on_submit=True):
                m_id = st.number_input("Member ID  ", min_value=1, value=int(effective_member_id), step=1, key="fine_mid")
                amt = st.number_input("Fine Amount", min_value=0.0, value=0.0, step=50.0)
                reason = st.text_input("Reason", value="")
                status = st.selectbox("Status ", ["unpaid", "paid"], index=0)
                paid_at = st.date_input("Paid at (if paid)", value=None)
                ok = st.form_submit_button("Insert Fine")
            if ok:
                try:
                    payload = {"member_id": int(m_id), "amount": float(amt), "reason": reason, "status": status}
                    if status == "paid" and paid_at:
                        payload["paid_at"] = str(paid_at)
                    admin_insert("fines", payload)
                    st.success("Fine inserted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        # Add Payout (if you have payouts table)
        with c4:
            st.markdown("### Add Payout")
            with st.form("add_payout", clear_on_submit=True):
                m_id = st.number_input("Member ID   ", min_value=1, value=int(effective_member_id), step=1, key="pay_mid")
                amt = st.number_input("Payout Amount", min_value=0.0, value=0.0, step=100.0)
                paid_on = st.date_input("Paid on", value=date.today(), key="paid_on")
                ok = st.form_submit_button("Insert Payout")
            if ok:
                try:
                    admin_insert("payouts", {"member_id": int(m_id), "amount": float(amt), "paid_on": str(paid_on)})
                    st.success("Payout inserted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")

        st.markdown("---")
        st.markdown("### Add Loan (Admin)")
        st.caption("Use this only if admin creates loans manually (or after approving a request).")

        with st.form("add_loan", clear_on_submit=True):
            borrower_mid = st.number_input("Borrower member_id", min_value=1, value=int(effective_member_id), step=1)
            surety_mid = st.number_input("Surety member_id (optional)", min_value=0, value=0, step=1)
            borrower_name = st.text_input("Borrower name (optional)", value="")
            surety_name = st.text_input("Surety name (optional)", value="")
            principal = st.number_input("Principal", min_value=0.0, value=0.0, step=100.0)
            interest = st.number_input("Interest (optional)", min_value=0.0, value=0.0, step=10.0)
            total_due = st.number_input("Total due (optional)", min_value=0.0, value=0.0, step=100.0)
            balance = st.number_input("Balance (optional)", min_value=0.0, value=0.0, step=100.0)
            status = st.text_input("Status", value="active")
            borrow_date = st.date_input("Borrow date", value=date.today())
            ok = st.form_submit_button("Insert Loan")

        if ok:
            try:
                payload = {
                    "borrower_member_id": int(borrower_mid),
                    "principal": float(principal),
                    "interest": float(interest),
                    "total_due": float(total_due) if total_due > 0 else float(principal) + float(interest),
                    "balance": float(balance) if balance > 0 else float(principal) + float(interest),
                    "status": status,
                    "borrow_date": str(borrow_date),
                }
                # Best-effort optional fields (only include if provided)
                if surety_mid and int(surety_mid) > 0:
                    payload["surety_member_id"] = int(surety_mid)
                if borrower_name.strip():
                    payload["borrower_name"] = borrower_name.strip()
                if surety_name.strip():
                    payload["surety_name"] = surety_name.strip()

                admin_insert("loans", payload)
                st.success("Loan inserted.")
                st.rerun()
            except Exception as e:
                st.error(f"Insert failed: {e}")

    # Admin: Approvals
    with tabs[7]:
        st.subheader("Admin: Loan Request Approvals")

        try:
            reqs = fetch_all_df_admin("loan_requests", "*", order_col="created_at", date_col="created_at")
            if reqs.empty:
                st.info("No loan requests found (or admin RLS is blocking).")
            else:
                # Focus on pending
                pending = reqs.copy()
                if "status" in pending.columns:
                    pending = pending[pending["status"].astype(str).str.lower() == "pending"]

                st.markdown("### Pending Requests")
                if pending.empty:
                    st.success("No pending requests.")
                else:
                    st.dataframe(pending, use_container_width=True, hide_index=True)

                    st.markdown("### Approve / Reject")
                    rid = st.number_input("Request ID", min_value=1, value=int(pending.iloc[0]["id"]) if len(pending) else 1, step=1)
                    colA, colB, colC = st.columns(3)
                    with colA:
                        approved_amount = st.number_input("Approved amount", min_value=0.0, value=0.0, step=100.0)
                    with colB:
                        start_date = st.date_input("Loan start/borrow date", value=date.today())
                    with colC:
                        action = st.selectbox("Action", ["approve", "reject"], index=0)

                    if st.button("Submit decision", use_container_width=True):
                        try:
                            if action == "reject":
                                admin_update("loan_requests", {"status": "rejected", "reviewed_at": "now()"}, "id", int(rid))
                                st.success("Request rejected.")
                                st.rerun()
                            else:
                                # Try RPC first (recommended)
                                try:
                                    supabase.rpc(
                                        "approve_loan_request",
                                        {
                                            "p_request_id": int(rid),
                                            "p_approved_amount": float(approved_amount),
                                            "p_start_date": str(start_date),
                                        },
                                    ).execute()
                                    st.success("Request approved and loan created (RPC).")
                                    st.rerun()
                                except Exception:
                                    # Fallback: only mark approved (admin can then add loan in Add Data tab)
                                    admin_update("loan_requests", {"status": "approved", "reviewed_at": "now()"}, "id", int(rid))
                                    st.warning(
                                        "Request marked approved, but loan was NOT auto-created (RPC not found or failed). "
                                        "Go to 'Admin: Add Data' tab to insert the loan."
                                    )
                                    st.rerun()

                        except Exception as e:
                            st.error(f"Approval failed: {e}")

                st.markdown("---")
                st.markdown("### All Requests")
                st.dataframe(reqs, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"Could not load loan_requests: {e}")

    # Admin: Payout rotate
    with tabs[8]:
        st.subheader("Admin: Payout & Rotate Next Beneficiary")

        st.caption("This requires the RPC function: record_payout_and_rotate_next(...) and a current cycle view.")

        # Get current cycle info (best effort)
        cur = None
        try:
            cur_data = supabase.table("current_cycle_beneficiary").select("*").execute().data or []
            if cur_data:
                cur = cur_data[0]
        except Exception:
            cur = None

        if not cur:
            st.warning("No current_cycle_beneficiary view found or no active cycle. Admin should create cycles first.")
        else:
            cycle_id = cur.get("cycle_id")
            end_date_str = cur.get("end_date")
            try:
                end_dt = date.fromisoformat(str(end_date_str))
            except Exception:
                end_dt = date.today()

            st.info(
                f"Current Cycle ID: **{cycle_id}**\n\n"
                f"Beneficiary: **{cur.get('beneficiary_name', '')}**\n\n"
                f"Cycle: **{cur.get('start_date','')} → {cur.get('end_date','')}**\n\n"
                f"Payout date: **{cur.get('payout_date','')}**"
            )

            with st.form("payout_rotate_form", clear_on_submit=False):
                payout_amount = st.number_input("Payout Amount", min_value=0.0, value=0.0, step=100.0)
                paid_on = st.date_input("Paid On", value=date.today())
                next_start_date = st.date_input("Next Cycle Start Date", value=end_dt + timedelta(days=1))
                ok = st.form_submit_button("✅ Record payout + rotate next beneficiary")

            if ok:
                if payout_amount <= 0:
                    st.error("Payout amount must be > 0.")
                else:
                    try:
                        supabase.rpc(
                            "record_payout_and_rotate_next",
                            {
                                "p_cycle_id": int(cycle_id),
                                "p_payout_amount": float(payout_amount),
                                "p_paid_on": str(paid_on),
                                "p_next_start_date": str(next_start_date),
                            },
                        ).execute()
                        st.success("Payout recorded and next cycle created.")
                        st.rerun()
                    except Exception as e:
                        st.error(
                            f"RPC failed: {e}\n\n"
                            "Make sure you created the function record_payout_and_rotate_next and payouts.cycle_id exists."
                        )

# ----------------------------
# SECURITY NOTE
# ----------------------------
if not is_admin:
    st.caption("Security: you can only view your own data (by email → member_id).")
else:
    st.info("Admin: You can switch Member ID (works only if admin RLS policies allow cross-member access).")
