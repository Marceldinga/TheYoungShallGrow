
import pandas as pd
import streamlit as st
from supabase import create_client

# ============================================================
# THE YOUNG SHALL GROW — Njangi Dashboard (Single Streamlit App)
# ------------------------------------------------------------
# ✅ Login (Supabase Auth email/password)
# ✅ Member: sees ONLY their own data (email -> members.id)  [RLS enforced]
# ✅ Admin: can view ALL members or filter by member_id; can ADD data via dashboard
# ✅ Admin input panels: Add Member, Contribution, Foundation Payment, Fine,
#    Record Repayment, Approve Loan, Issue Loan, Conduct Payout (RPC best-effort)
# ✅ Ports auto-update (manual refresh + optional auto-refresh)
# ✅ Every transaction uses member_id (or borrower_member_id for loans)
# ============================================================

# ----------------------------
# SETTINGS
# ----------------------------
st.set_page_config(page_title="The Young Shall Grow — Dashboard", page_icon="🌱", layout="wide")
st.set_option("client.showErrorDetails", False)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
ADMIN_EMAILS = [e.strip().lower() for e in str(st.secrets.get("ADMIN_EMAILS", "")).split(",") if e.strip()]
supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Optional auto-refresh (Streamlit Cloud: add streamlit-autorefresh to requirements.txt)
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

# ----------------------------
# THEME
# ----------------------------
st.markdown("""
<style>
:root{
  --bg:#0b1220;
  --stroke:rgba(148,163,184,.18);
  --text:#e5e7eb;
  --muted:rgba(229,231,235,.65);
  --brand:#22c55e;
  --brand2:#14b8a6;
  --danger:#ef4444;
  --shadow: 0 18px 50px rgba(0,0,0,.35);
}
.stApp { background: linear-gradient(180deg, var(--bg), #070b14 70%); color: var(--text); }
.block-container{max-width:1180px;padding-top:1.0rem;padding-bottom:2rem;}
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
.small-muted{ color: var(--muted); font-size: 13px; }
hr{ border: none; border-top: 1px solid var(--stroke); margin: 14px 0; }

.kpi{
  border:1px solid var(--stroke);
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 26px rgba(0,0,0,.20);
}
.kpi .label{ color: var(--muted); font-size: 13px; }
.kpi .value{ font-size: 26px; font-weight: 800; margin-top: 6px; }
.kpi .accent{ width:100%; height:4px; border-radius:999px; background: linear-gradient(90deg, var(--brand), var(--brand2)); margin-top: 10px; }

.card{
  border:1px solid var(--stroke);
  background: rgba(255,255,255,.03);
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 26px rgba(0,0,0,.20);
}
</style>
""", unsafe_allow_html=True)

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
        "<div class='hdr'><h1 style='margin:0'>🌱 The Young Shall Grow — Login</h1>"
        "<div class='small-muted'>Sign in with your Supabase Auth email/password</div></div>",
        unsafe_allow_html=True
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

attach_jwt(st.session_state["access_token"])
user_email = (st.session_state.get("user_email") or "").lower()
is_admin = user_email in ADMIN_EMAILS

# ----------------------------
# MEMBER LOOKUP (email -> members row)
# ----------------------------
def get_member_by_email(email: str):
    for mode in ["ilike", "eq"]:
        try:
            q = supabase.table("members").select("*")
            q = q.ilike("email", email) if mode == "ilike" else q.eq("email", email)
            data = q.limit(1).execute().data
            if data:
                return data[0]
        except Exception:
            pass
    return None

my_member = get_member_by_email(user_email)
if not my_member:
    st.error("❌ Logged in, but no matching row found in public.members. Ensure members.email matches Auth email.")
    st.stop()

my_member_id = int(my_member["id"])

# ----------------------------
# HEADER + WELCOME NOTE
# ----------------------------
st.markdown(
    f"""
    <div class='hdr'>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h1 style="margin:0">📊 The Young Shall Grow — Njangi Dashboard</h1>
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
    unsafe_allow_html=True
)
st.write("")
cA, cB = st.columns([1, 6])
with cA:
    st.button("Logout", on_click=logout)

st.markdown(
    """
    <div class="card">
      <div style="font-size:16px;font-weight:800;margin-bottom:6px">👋 Welcome</div>
      <div class="small-muted">
        This dashboard is for a bi-weekly Njangi cycle. Members can view their own records (contributions, foundation,
        fines, loans, repayments) and request loans. Admins manage the group by adding transactions, approving/issuing loans,
        recording repayments, and running payouts/rotation. All transactions are tracked by <b>member_id</b> (loans use <b>borrower_member_id</b>).
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# LIVE UPDATES (dropdown)
# ----------------------------
with st.expander("🔽 Live Updates (keeps totals fresh)", expanded=False):
    st.caption("Use this when admin adds data, repayments are recorded, or scheduled interest jobs run.")
    enable_live = st.toggle("Enable auto-refresh", value=True)
    refresh_seconds = st.selectbox("Refresh every (seconds)", [10, 20, 30, 60, 120], index=2)
    if st.button("🔄 Refresh now"):
        st.rerun()
    if enable_live and st_autorefresh:
        st_autorefresh(interval=int(refresh_seconds) * 1000, key="live_refresh")
    elif enable_live and not st_autorefresh:
        st.warning("Auto-refresh not installed. Add `streamlit-autorefresh` to requirements.txt on Streamlit Cloud.")

# ----------------------------
# FILTERS (dropdown)
# ----------------------------
with st.expander("🔽 Filters (what data you are viewing)", expanded=True):
    if is_admin:
        a1, f1, f2, f3, f4 = st.columns([2, 2, 3, 2, 2])
        admin_member_id = a1.text_input("Member ID (admin)", placeholder="Leave empty = ALL members")
    else:
        f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
        admin_member_id = ""

    range_opt = f1.selectbox("Time range", ["All time", "Last 30 days", "Last 90 days", "This year"], index=0)
    search_text = f2.text_input("Quick search", placeholder="e.g. unpaid, paid, pending, late...")
    record_id = f3.text_input("Record ID", placeholder="e.g. 58")
    show_only_unpaid = f4.checkbox("Only unpaid fines", value=False)

effective_member_id = my_member_id
viewing_all_members = False
if is_admin and not admin_member_id.strip():
    viewing_all_members = True
elif is_admin and admin_member_id.strip():
    try:
        effective_member_id = int(admin_member_id.strip())
    except Exception:
        effective_member_id = my_member_id

st.markdown(
    f"<div class='small-muted'>Currently viewing: "
    f"<b>{'ALL members' if viewing_all_members else f'member_id = {effective_member_id}'}</b>"
    f"</div>",
    unsafe_allow_html=True
)

# ----------------------------
# HELPERS
# ----------------------------
def apply_date_filter(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    now = pd.Timestamp.utcnow()
    if range_opt == "Last 30 days":
        return df[df[date_col] >= (now - pd.Timedelta(days=30))]
    if range_opt == "Last 90 days":
        return df[df[date_col] >= (now - pd.Timedelta(days=90))]
    if range_opt == "This year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
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
    if df.empty or not record_id.strip() or "id" not in df.columns:
        return df
    try:
        rid = int(record_id.strip())
    except Exception:
        return df
    return df[pd.to_numeric(df["id"], errors="coerce") == rid]

def safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

def fetch_df(table: str, cols="*", member_col="member_id", order_col=None, date_col=None) -> pd.DataFrame:
    q = supabase.table(table).select(cols)
    if not (is_admin and viewing_all_members):
        q = q.eq(member_col, effective_member_id)
    if order_col:
        q = q.order(order_col, desc=True)
    data = q.execute().data
    df = pd.DataFrame(data or [])
    if date_col:
        df = apply_date_filter(df, date_col)
    return df

# ----------------------------
# LOAD DATA
# ----------------------------
members_df = pd.DataFrame(supabase.table("members").select("id,name,email,phone,position,has_benefits").order("id").execute().data or [])

contrib_df = fetch_df("contributions", "*", member_col="member_id", order_col="created_at", date_col="created_at")
contrib_df = apply_search(contrib_df, ["kind", "notes"]) if not contrib_df.empty else contrib_df
contrib_df = apply_record_id_filter(contrib_df)

found_df = fetch_df("foundation_payments", "*", member_col="member_id", order_col="date_paid", date_col="date_paid")
found_df = apply_search(found_df, ["status", "notes"]) if not found_df.empty else found_df
found_df = apply_record_id_filter(found_df)

fines_df = fetch_df("fines", "*", member_col="member_id", order_col="created_at", date_col="created_at")
fines_df = apply_search(fines_df, ["reason", "status"]) if not fines_df.empty else fines_df
if show_only_unpaid and (not fines_df.empty) and ("status" in fines_df.columns):
    fines_df = fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]
fines_df = apply_record_id_filter(fines_df)

loans_df = fetch_df("loans", "*", member_col="borrower_member_id", order_col="created_at", date_col="created_at")
loans_df = apply_search(loans_df, ["status", "borrower_name", "surety_name"]) if not loans_df.empty else loans_df
loans_df = apply_record_id_filter(loans_df)

repay_df = fetch_df("repayments", "*", member_col="member_id", order_col="paid_at", date_col="paid_at")
repay_df = apply_search(repay_df, ["notes", "borrower_name", "member_name"]) if not repay_df.empty else repay_df
repay_df = apply_record_id_filter(repay_df)

# Compute loan balances after repayments (best effort)
def compute_loan_balances(loans: pd.DataFrame, repays: pd.DataFrame) -> pd.DataFrame:
    if loans.empty or "id" not in loans.columns:
        return loans
    loans = loans.copy()
    if repays.empty or "loan_id" not in repays.columns:
        loans["total_repaid"] = 0.0
        if "total_due" in loans.columns:
            loans["remaining_balance"] = pd.to_numeric(loans["total_due"], errors="coerce").fillna(0)
        return loans

    col_amt = "amount_paid" if "amount_paid" in repays.columns else ("amount" if "amount" in repays.columns else None)
    if not col_amt:
        return loans

    r = repays.copy()
    r[col_amt] = pd.to_numeric(r[col_amt], errors="coerce").fillna(0)
    r = r.groupby("loan_id")[col_amt].sum().reset_index().rename(columns={col_amt: "total_repaid"})

    out = loans.merge(r, left_on="id", right_on="loan_id", how="left")
    out["total_repaid"] = pd.to_numeric(out["total_repaid"], errors="coerce").fillna(0)
    if "total_due" in out.columns:
        out["total_due"] = pd.to_numeric(out["total_due"], errors="coerce").fillna(0)
        out["remaining_balance"] = out["total_due"] - out["total_repaid"]
    return out

loans_df = compute_loan_balances(loans_df, repay_df)

# ----------------------------
# BENEFICIARY PANELS (best-effort)
# ----------------------------
def show_current_beneficiary_box():
    try:
        cur = supabase.table("current_cycle_beneficiary").select("*").limit(1).execute().data or []
        if not cur:
            return
        c = cur[0]
        name = c.get("beneficiary_name") or c.get("name") or c.get("member_name") or ""
        cycle_no = c.get("cycle_no") or c.get("cycle_number") or c.get("cycle") or ""
        start_date = c.get("cycle_start_date") or c.get("start_date") or c.get("rotation_start_date") or ""
        payout_date = c.get("payout_date") or c.get("next_payout_date") or ""
        st.markdown(
            f"""
            <div class="card">
              <div style="font-size:16px;font-weight:800">👤 Current Beneficiary: {name}</div>
              <div class="small-muted" style="margin-top:8px">🔁 Cycle #{cycle_no}: {start_date}</div>
              <div class="small-muted" style="margin-top:4px">💰 Payout Date: {payout_date}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    except Exception:
        pass

def show_next_beneficiary_port_for_all():
    try:
        res = supabase.rpc("next_beneficiary_totals", {}).execute()
        rows = res.data or []
        if not rows:
            return
        r = rows[0]
        nm = r.get("next_member_name", "")
        mid = r.get("next_member_id", "")
        tc = float(r.get("total_contribution", 0) or 0)
        tfp = float(r.get("total_foundation_paid", 0) or 0)
        tfn = float(r.get("total_foundation_pending", 0) or 0)
        tl = float(r.get("total_loan", 0) or 0)

        st.markdown(
            f"""
            <div class="card" style="margin-top:12px">
              <div style="font-size:16px;font-weight:800">➡️ Next Beneficiary After Payout</div>
              <div class="small-muted" style="margin-top:6px">{nm} (member_id {mid})</div>
              <div style="margin-top:10px">
                <div>• <b>Total Contribution:</b> {tc:,.2f}</div>
                <div>• <b>Total Foundation (Paid):</b> {tfp:,.2f}</div>
                <div>• <b>Total Foundation (Pending):</b> {tfn:,.2f}</div>
                <div>• <b>Total Loan:</b> {tl:,.2f}</div>
              </div>
              <div class="small-muted" style="margin-top:10px">
                This “Next Beneficiary” port helps everyone see the next person’s totals after payout.
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    except Exception:
        pass

with st.expander("🔽 Beneficiary (Current + Next)", expanded=True):
    show_current_beneficiary_box()
    show_next_beneficiary_port_for_all()

# ----------------------------
# PORTS / KPIs
# ----------------------------
total_contrib = safe_sum(contrib_df, "amount") if "amount" in contrib_df.columns else 0.0

found_paid_only = safe_sum(found_df, "amount_paid") if "amount_paid" in found_df.columns else 0.0
found_pending = safe_sum(found_df, "amount_pending") if "amount_pending" in found_df.columns else 0.0

rep_col = "amount_paid" if "amount_paid" in repay_df.columns else ("amount" if "amount" in repay_df.columns else None)
total_repaid = safe_sum(repay_df, rep_col) if rep_col else 0.0

total_found_paid_plus_repaid = found_paid_only + total_repaid

unpaid_fines_amt = 0.0
if (not fines_df.empty) and ("status" in fines_df.columns) and ("amount" in fines_df.columns):
    unpaid_fines_amt = float(
        pd.to_numeric(
            fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"],
            errors="coerce",
        ).fillna(0).sum()
    )

active_loans = 0
if (not loans_df.empty) and ("status" in loans_df.columns):
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

loan_total = 0.0
for col in ["total_due", "balance", "principal_current", "principal"]:
    if (not loans_df.empty) and (col in loans_df.columns):
        loan_total = safe_sum(loans_df, col)
        break

total_interest_generated = 0.0
if is_admin and (not loans_df.empty) and ("total_interest_generated" in loans_df.columns):
    total_interest_generated = safe_sum(loans_df, "total_interest_generated")

with st.expander("🔽 Summary Ports (Totals)", expanded=True):
    if is_admin:
        k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    else:
        k1, k2, k3, k4, k5, k6 = st.columns(6)

    k1.markdown(f"<div class='kpi'><div class='label'>Total Contributions</div><div class='value'>{total_contrib:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi'><div class='label'>Foundation Paid (+Repay)</div><div class='value'>{total_found_paid_plus_repaid:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi'><div class='label'>Foundation Pending</div><div class='value'>{found_pending:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi'><div class='label'>Unpaid Fines</div><div class='value'>{unpaid_fines_amt:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k5.markdown(f"<div class='kpi'><div class='label'>Active Loans</div><div class='value'>{active_loans}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k6.markdown(f"<div class='kpi'><div class='label'>Loan Total</div><div class='value'>{loan_total:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    if is_admin:
        k7.markdown(f"<div class='kpi'><div class='label'>Total Interest (Admin)</div><div class='value'>{total_interest_generated:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ============================================================
# MEMBER LOAN REQUEST (dropdown)
# - Uses loans table (status="requested") so you don't need loan_requests table
# - Uses borrower_member_id + surety_member_id (if columns exist)
# - Real eligibility rules should be enforced by your DB function/RLS if you have it
# ============================================================
with st.expander("🔽 Member: Request Loan (Members only)", expanded=not is_admin):
    st.caption("Members request a loan here. Admin later approves/issue. Eligibility should be enforced by your existing rules/RLS.")
    # surety pick list (exclude self)
    surety_options = []
    if not members_df.empty:
        for _, r in members_df.iterrows():
            mid = int(r["id"])
            if mid == my_member_id:
                continue
            nm = r.get("name") or f"Member {mid}"
            surety_options.append((mid, nm))

    surety_label = [f"{mid} — {nm}" for mid, nm in surety_options]
    surety_idx = 0 if surety_label else None

    with st.form("member_loan_request_form", clear_on_submit=False):
        req_amount = st.number_input("Requested Amount", min_value=0.0, step=100.0, value=0.0)
        surety_pick = st.selectbox("Surety (qualified member)", options=surety_label) if surety_label else None
        notes = st.text_input("Notes (optional)")
        submit_req = st.form_submit_button("Submit Loan Request")

    if submit_req:
        try:
            surety_member_id = None
            surety_name = None
            if surety_pick:
                surety_member_id = int(surety_pick.split("—")[0].strip())
                surety_name = surety_pick.split("—", 1)[1].strip()

            payload = {
                "borrower_member_id": my_member_id,
                "borrower_name": my_member.get("name", ""),
                "principal": float(req_amount),
                "status": "requested",
            }

            # optional columns if they exist
            if "surety_member_id" in (loans_df.columns.tolist() if not loans_df.empty else []):
                payload["surety_member_id"] = surety_member_id
            else:
                payload["surety_member_id"] = surety_member_id  # harmless if column exists; if not, insert fails

            payload["surety_name"] = surety_name
            if notes.strip():
                payload["notes"] = notes.strip()

            # Insert request into loans
            supabase.table("loans").insert(payload).execute()
            st.success("✅ Loan request submitted. Please wait for admin approval.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Could not submit loan request (likely RLS or missing column). Details: {str(e)}")

# ============================================================
# ADMIN CONTROL PANEL (dropdown)
# - Add Member (email + phone) -> inserts into public.members
# - Add Contribution / Foundation / Fine / Repayment
# - Approve Loan (requested -> approved)
# - Issue Loan (approved -> active/open)
# - Conduct Payout (calls RPC record_payout_and_rotate_next if exists)
# ============================================================
if is_admin:
    with st.expander("🔽 Admin: Control Panel (Add/Approve/Payout)", expanded=True):
        st.caption(
            "Admin actions. Tip: after adding/approving/recording, the ports update automatically (or use Refresh)."
        )

        admin_action = st.selectbox(
            "Choose Admin Action",
            [
                "Add Member",
                "Add Contribution",
                "Add Foundation Payment",
                "Add Fine",
                "Record Repayment",
                "Approve Loan (requested → approved)",
                "Issue Loan (approved → active/open)",
                "Conduct Payout (rotate beneficiary)",
            ],
            index=0,
        )

        # shared member selector for admin inputs
        member_pick = None
        if not members_df.empty:
            member_labels = [f"{int(r['id'])} — {r.get('name','')}" for _, r in members_df.iterrows()]
            member_pick = st.selectbox("Target Member", member_labels, index=0)

        def picked_member_id():
            if not member_pick:
                return None
            return int(member_pick.split("—")[0].strip())

        def picked_member_name():
            if not member_pick:
                return ""
            return member_pick.split("—", 1)[1].strip()

        if admin_action == "Add Member":
            st.markdown("**Add a member record (email + phone).**")
            st.caption("Note: This adds the member row in `public.members`. The user must still be created in Supabase Auth to log in.")
            with st.form("admin_add_member_form", clear_on_submit=True):
                email = st.text_input("Member Email")
                phone = st.text_input("Phone Number")
                submit = st.form_submit_button("Add Member")

            if submit:
                try:
                    if not email.strip() or not phone.strip():
                        st.error("Email and phone are required.")
                    else:
                        name_guess = email.split("@")[0].replace(".", " ").title()
                        payload = {"email": email.strip().lower(), "phone": phone.strip(), "name": name_guess}
                        supabase.table("members").insert(payload).execute()
                        st.success("✅ Member added to members table.")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Could not add member (likely RLS or unique email). Details: {str(e)}")

        elif admin_action == "Add Contribution":
            st.markdown("**Add a contribution (recorded using member_id).**")
            with st.form("admin_add_contrib_form", clear_on_submit=True):
                amt = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
                kind = st.text_input("Kind (optional)", value="bi-weekly")
                submit = st.form_submit_button("Save Contribution")
            if submit:
                try:
                    mid = picked_member_id()
                    payload = {"member_id": mid, "amount": float(amt), "kind": kind}
                    supabase.table("contributions").insert(payload).execute()
                    st.success("✅ Contribution saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to save contribution. Details: {str(e)}")

        elif admin_action == "Add Foundation Payment":
            st.markdown("**Add foundation payment (paid + pending).**")
            with st.form("admin_add_found_form", clear_on_submit=True):
                paid = st.number_input("Amount Paid", min_value=0.0, step=100.0, value=0.0)
                pending = st.number_input("Amount Pending", min_value=0.0, step=100.0, value=0.0)
                status = st.selectbox("Status", ["paid", "pending", "partial"], index=2)
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("Save Foundation Payment")
            if submit:
                try:
                    mid = picked_member_id()
                    payload = {
                        "member_id": mid,
                        "amount_paid": float(paid),
                        "amount_pending": float(pending),
                        "status": str(status),
                        "notes": notes.strip() if notes.strip() else None,
                    }
                    supabase.table("foundation_payments").insert(payload).execute()
                    st.success("✅ Foundation payment saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to save foundation payment. Details: {str(e)}")

        elif admin_action == "Add Fine":
            st.markdown("**Add a fine (member_id-based).**")
            with st.form("admin_add_fine_form", clear_on_submit=True):
                amt = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
                reason = st.text_input("Reason")
                status = st.selectbox("Status", ["unpaid", "paid"], index=0)
                submit = st.form_submit_button("Save Fine")
            if submit:
                try:
                    mid = picked_member_id()
                    payload = {"member_id": mid, "amount": float(amt), "reason": reason, "status": status}
                    supabase.table("fines").insert(payload).execute()
                    st.success("✅ Fine saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to save fine. Details: {str(e)}")

        elif admin_action == "Record Repayment":
            st.markdown("**Record a repayment (updates foundation port because repayments are included in totals).**")
            st.caption("Repayments table columns are based on your screenshot: loan_id, member_id, amount, paid_at, amount_paid, borrower_member_id, borrower_name, member_name, notes.")
            with st.form("admin_add_repay_form", clear_on_submit=True):
                loan_id = st.number_input("Loan ID", min_value=0, step=1, value=0)
                amt_paid = st.number_input("Amount Paid", min_value=0.0, step=50.0, value=0.0)
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("Save Repayment")
            if submit:
                try:
                    mid = picked_member_id()
                    payload = {
                        "loan_id": int(loan_id) if loan_id else None,
                        "member_id": mid,
                        "amount_paid": float(amt_paid),
                        "amount": float(amt_paid),  # keep both fields aligned
                        "borrower_member_id": mid,
                        "borrower_name": picked_member_name(),
                        "member_name": picked_member_name(),
                        "notes": notes.strip() if notes.strip() else None,
                    }
                    supabase.table("repayments").insert(payload).execute()
                    st.success("✅ Repayment saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to save repayment. Details: {str(e)}")

        elif admin_action == "Approve Loan (requested → approved)":
            st.markdown("**Approve loan requests.**")
            st.caption("This changes loans.status from 'requested' to 'approved'.")
            try:
                q = supabase.table("loans").select("*").eq("status", "requested").order("created_at", desc=True)
                pending = q.execute().data or []
                if not pending:
                    st.info("No requested loans found.")
                else:
                    dfp = pd.DataFrame(pending)
                    st.dataframe(dfp, use_container_width=True, hide_index=True)
                    loan_to_approve = st.number_input("Loan ID to approve", min_value=0, step=1, value=int(dfp.iloc[0]["id"]))
                    if st.button("✅ Approve Selected Loan"):
                        supabase.table("loans").update({"status": "approved"}).eq("id", int(loan_to_approve)).execute()
                        st.success("Approved.")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Could not load/approve requests. Details: {str(e)}")

        elif admin_action == "Issue Loan (approved → active/open)":
            st.markdown("**Issue approved loans (make them active/open).**")
            st.caption("This changes loans.status from 'approved' to 'active'.")
            try:
                q = supabase.table("loans").select("*").eq("status", "approved").order("created_at", desc=True)
                ap = q.execute().data or []
                if not ap:
                    st.info("No approved loans found.")
                else:
                    dfa = pd.DataFrame(ap)
                    st.dataframe(dfa, use_container_width=True, hide_index=True)
                    loan_to_issue = st.number_input("Loan ID to issue", min_value=0, step=1, value=int(dfa.iloc[0]["id"]))
                    if st.button("🚀 Issue Selected Loan"):
                        supabase.table("loans").update({"status": "active"}).eq("id", int(loan_to_issue)).execute()
                        st.success("Issued (active).")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Could not load/issue approved loans. Details: {str(e)}")

        elif admin_action == "Conduct Payout (rotate beneficiary)":
            st.markdown("**Conduct payout & rotate next beneficiary.**")
            st.caption("This calls your existing RPC if you have it: record_payout_and_rotate_next(...).")
            with st.form("admin_payout_form", clear_on_submit=False):
                payout_amount = st.number_input("Payout Amount", min_value=0.0, step=100.0, value=0.0)
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("💰 Execute Payout")
            if submit:
                try:
                    # best-effort RPC; adjust params inside your SQL function if needed
                    supabase.rpc("record_payout_and_rotate_next", {"payout_amount": float(payout_amount), "notes": notes}).execute()
                    st.success("✅ Payout executed & rotation updated.")
                    st.rerun()
                except Exception as e:
                    st.error(
                        "❌ Payout RPC failed. If your function name/params differ, tell me the exact RPC signature.\n\n"
                        f"Details: {str(e)}"
                    )

# ============================================================
# VIEW TABLES (dropdown)
# ============================================================
with st.expander("🔽 View Tables (organized)", expanded=True):
    st.caption("Use the dropdown to view each table cleanly.")
    page = st.selectbox(
        "Choose a table/section",
        ["My Profile", "Members", "Contributions", "Foundation Payments", "Loans", "Repayments", "Fines"],
        index=0
    )

    if page == "My Profile":
        st.subheader("My Profile")
        st.json(my_member)

    elif page == "Members":
        st.subheader("Members")
        st.dataframe(members_df, use_container_width=True, hide_index=True)

    elif page == "Contributions":
        st.subheader("Contributions")
        st.dataframe(contrib_df, use_container_width=True, hide_index=True)

    elif page == "Foundation Payments":
        st.subheader("Foundation Payments")
        st.markdown(
            f"<div class='small-muted'>Paid (table): <b>{found_paid_only:,.2f}</b> • "
            f"Repayments: <b>{total_repaid:,.2f}</b> • Pending: <b>{found_pending:,.2f}</b></div>",
            unsafe_allow_html=True
        )
        st.dataframe(found_df, use_container_width=True, hide_index=True)

    elif page == "Loans":
        st.subheader("Loans")
        if loans_df.empty:
            st.info("No loans found for this view.")
        else:
            preferred = [
                "id", "borrower_member_id", "borrower_name", "surety_member_id", "surety_name",
                "principal", "principal_current", "interest", "total_due", "balance",
                "total_repaid", "remaining_balance",
                "status", "borrow_date", "issued_at", "created_at", "updated_at"
            ]
            cols = [c for c in preferred if c in loans_df.columns] + [c for c in loans_df.columns if c not in preferred]
            st.dataframe(loans_df[cols], use_container_width=True, hide_index=True)

    elif page == "Repayments":
        st.subheader("Repayments")
        if repay_df.empty:
            st.info("No repayments found for this view.")
        else:
            preferred = ["id", "loan_id", "member_id", "member_name", "amount_paid", "amount", "paid_at", "created_at", "notes"]
            cols = [c for c in preferred if c in repay_df.columns] + [c for c in repay_df.columns if c not in preferred]
            st.dataframe(repay_df[cols], use_container_width=True, hide_index=True)

    elif page == "Fines":
        st.subheader("Fines")
        st.dataframe(fines_df, use_container_width=True, hide_index=True)

# ----------------------------
# FOOTER NOTES
# ----------------------------
st.markdown("<hr/>", unsafe_allow_html=True)
if not is_admin:
    st.caption("Member access: you can only view your own data (email → member_id). Admin actions are hidden.")
else:
    st.caption("Admin access: you can add/approve/issue/record from the Admin Control Panel. Viewing ALL members requires admin RLS policies.")
