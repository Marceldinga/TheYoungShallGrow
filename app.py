
import pandas as pd
import streamlit as st
from supabase import create_client

# ============================================================
# SINGLE STREAMLIT APP (Clean + Organized with Dropdowns)
# ------------------------------------------------------------
# ✅ Supabase Auth login (email/password)
# ✅ Member: sees ONLY their own rows (email -> members.id)
# ✅ Admin:
#    - If "Member ID (admin)" is EMPTY => show ALL members data + totals
#    - If "Member ID (admin)" filled => show that member's data
# ✅ Foundation Port:
#    - Total Foundation Paid + Pending (from foundation_payments)
#    - PLUS Repayments (repayments.amount_paid) added to paid totals
# ✅ Loans:
#    - Uses borrower_member_id for filtering
# ✅ Repayments:
#    - Uses your confirmed table public.repayments
# ✅ Next Beneficiary After Payout Port (visible to ALL members):
#    - Calls RPC: public.next_beneficiary_totals() (best-effort)
# ✅ Total Interest Generated (ADMIN ONLY):
#    - From loans.total_interest_generated (best-effort)
# ✅ Live auto-refresh (dropdown) to keep ports updated when admin adds data,
#    repayments happen, or interest job runs.
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
# OPTIONAL AUTO-REFRESH
# ----------------------------
try:
    from streamlit_autorefresh import st_autorefresh  # pip: streamlit-autorefresh
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
        "<div class='hdr'><h1 style='margin:0'>🌱 Login</h1>"
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

# Always re-attach JWT on rerun
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
    unsafe_allow_html=True
)
st.write("")
cA, cB = st.columns([1, 4])
with cA:
    st.button("Logout", on_click=logout)

# ----------------------------
# LIVE UPDATES (dropdown)
# ----------------------------
with st.expander("🔽 Live Updates", expanded=False):
    enable_live = st.toggle("Enable live auto-refresh", value=True)
    refresh_seconds = st.selectbox("Refresh every (seconds)", [10, 20, 30, 60, 120], index=2)
    st.caption("This keeps totals updated when admin adds data, repayments are recorded, or interest jobs run.")
    if enable_live and st_autorefresh:
        st_autorefresh(interval=int(refresh_seconds) * 1000, key="live_refresh")
    elif enable_live and not st_autorefresh:
        st.warning("Auto-refresh package missing. Add `streamlit-autorefresh` to requirements.txt on Streamlit Cloud.")

# ----------------------------
# FILTERS (dropdown)
# ----------------------------
with st.expander("🔽 Filters", expanded=True):
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

# effective member id
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
# FILTER HELPERS
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

# ----------------------------
# FETCH HELPERS (admin all-members aware)
# ----------------------------
def fetch_df(table: str, cols="*", member_col="member_id", order_col=None, date_col=None) -> pd.DataFrame:
    q = supabase.table(table).select(cols)

    # If admin viewing all => no member filter
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
# LOAD DATA (tables)
# ----------------------------
# Contributions
contrib_df = fetch_df(
    "contributions",
    "id,member_id,amount,kind,created_at,updated_at",
    member_col="member_id",
    order_col="created_at",
    date_col="created_at",
)
contrib_df = apply_search(contrib_df, ["kind"])
contrib_df = apply_record_id_filter(contrib_df)

# Foundation payments
found_df = fetch_df(
    "foundation_payments",
    "id,member_id,amount_paid,amount_pending,status,date_paid,notes,updated_at,converted_to_loan,converted_loan_id",
    member_col="member_id",
    order_col="date_paid",
    date_col="date_paid",
)
found_df = apply_search(found_df, ["status", "notes"])
found_df = apply_record_id_filter(found_df)

# Fines
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

# Loans (borrower_member_id)
loans_df = fetch_df(
    "loans",
    "*",
    member_col="borrower_member_id",
    order_col="created_at",
    date_col="created_at",
)
loans_df = apply_search(loans_df, ["status", "borrower_name", "surety_name"])
loans_df = apply_record_id_filter(loans_df)

# Repayments (your confirmed table)
repay_df = fetch_df(
    "repayments",
    "*",
    member_col="member_id",
    order_col="paid_at",
    date_col="paid_at",
)
repay_df = apply_search(repay_df, ["notes", "borrower_name", "member_name"])
repay_df = apply_record_id_filter(repay_df)

# ----------------------------
# COMPUTE LOAN BALANCES AFTER REPAYMENTS (best effort)
# ----------------------------
def compute_loan_balances(loans: pd.DataFrame, repays: pd.DataFrame) -> pd.DataFrame:
    if loans.empty or "id" not in loans.columns:
        return loans
    if repays.empty or "loan_id" not in repays.columns:
        loans["total_repaid"] = 0.0
        if "total_due" in loans.columns:
            loans["remaining_balance"] = pd.to_numeric(loans["total_due"], errors="coerce").fillna(0)
        return loans

    repay_sum = repays.copy()
    col_amt = "amount_paid" if "amount_paid" in repay_sum.columns else ("amount" if "amount" in repay_sum.columns else None)
    if not col_amt:
        return loans

    repay_sum[col_amt] = pd.to_numeric(repay_sum[col_amt], errors="coerce").fillna(0)
    repay_sum = repay_sum.groupby("loan_id")[col_amt].sum().reset_index()
    repay_sum.rename(columns={col_amt: "total_repaid"}, inplace=True)

    merged = loans.merge(repay_sum, left_on="id", right_on="loan_id", how="left")
    merged["total_repaid"] = pd.to_numeric(merged["total_repaid"], errors="coerce").fillna(0)

    # remaining_balance = total_due - repaid (if total_due exists)
    if "total_due" in merged.columns:
        merged["total_due"] = pd.to_numeric(merged["total_due"], errors="coerce").fillna(0)
        merged["remaining_balance"] = merged["total_due"] - merged["total_repaid"]
    return merged

loans_df = compute_loan_balances(loans_df, repay_df)

# ----------------------------
# CURRENT BENEFICIARY BOX (best effort)
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
        payout_date = c.get("payout_date") or c.get("next_payout_date") or c.get("next_payout_date") or ""
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
        # don't crash
        pass

show_current_beneficiary_box()

# ----------------------------
# NEXT BENEFICIARY AFTER PAYOUT PORT (RPC, visible to ALL)
# Requires you to create SQL function: public.next_beneficiary_totals()
# ----------------------------
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
            </div>
            """,
            unsafe_allow_html=True
        )
    except Exception:
        # don't crash if function isn't created yet
        pass

show_next_beneficiary_port_for_all()

# ----------------------------
# KPIs (Foundation includes repayments)
# ----------------------------
total_contrib = safe_sum(contrib_df, "amount")

found_paid_only = safe_sum(found_df, "amount_paid")
found_pending = safe_sum(found_df, "amount_pending")

rep_col = "amount_paid" if "amount_paid" in repay_df.columns else ("amount" if "amount" in repay_df.columns else None)
total_repaid = safe_sum(repay_df, rep_col) if rep_col else 0.0

total_found_paid_plus_repaid = found_paid_only + total_repaid

unpaid_fines_amt = 0.0
if not fines_df.empty and "status" in fines_df.columns and "amount" in fines_df.columns:
    unpaid_fines_amt = float(
        pd.to_numeric(
            fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"],
            errors="coerce",
        ).fillna(0).sum()
    )

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

# loan total (best effort)
loan_total = 0.0
for col in ["total_due", "balance", "principal_current", "principal"]:
    if not loans_df.empty and col in loans_df.columns:
        loan_total = safe_sum(loans_df, col)
        break

# admin-only total interest generated (best effort)
total_interest_generated = 0.0
if is_admin and (not loans_df.empty) and ("total_interest_generated" in loans_df.columns):
    total_interest_generated = safe_sum(loans_df, "total_interest_generated")

with st.expander("🔽 Summary (Ports)", expanded=True):
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
        k7.markdown(f"<div class='kpi'><div class='label'>Total Interest Generated</div><div class='value'>{total_interest_generated:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ----------------------------
# CLEAN NAVIGATION (dropdown)
# ----------------------------
page = st.selectbox(
    "🔽 Select Section",
    [
        "My Profile",
        "Contributions",
        "Foundation Payments",
        "Loans",
        "Repayments",
        "Fines",
    ],
    index=0,
)

# ----------------------------
# SECTIONS
# ----------------------------
if page == "My Profile":
    st.subheader("My Profile")
    st.json(my_member)

    if is_admin:
        st.caption("Admin tip: leave Member ID empty to view ALL members totals and tables (requires admin RLS).")

elif page == "Contributions":
    st.subheader("Contributions")
    st.dataframe(contrib_df, use_container_width=True, hide_index=True)

elif page == "Foundation Payments":
    st.subheader("Foundation Payments")
    st.markdown(
        f"<div class='small-muted'>"
        f"Paid Total (table): <b>{found_paid_only:,.2f}</b> • "
        f"Repaid Total (repayments): <b>{total_repaid:,.2f}</b> • "
        f"Pending Total: <b>{found_pending:,.2f}</b>"
        f"</div>",
        unsafe_allow_html=True
    )
    st.dataframe(found_df, use_container_width=True, hide_index=True)

elif page == "Loans":
    st.subheader("Loans")
    if loans_df.empty:
        st.info("No loans found for this view.")
    else:
        # Put the most useful columns first if they exist
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
        preferred = [
            "id", "loan_id", "member_id", "member_name",
            "borrower_member_id", "borrower_name",
            "amount_paid", "amount", "paid_at", "created_at", "notes"
        ]
        cols = [c for c in preferred if c in repay_df.columns] + [c for c in repay_df.columns if c not in preferred]
        st.dataframe(repay_df[cols], use_container_width=True, hide_index=True)

elif page == "Fines":
    st.subheader("Fines")
    st.dataframe(fines_df, use_container_width=True, hide_index=True)

# ----------------------------
# SECURITY NOTE
# ----------------------------
if not is_admin:
    st.caption("Security: you can only view your own data (by email → member_id).")
else:
    st.caption("Admin: leave Member ID empty to view ALL members (only if your RLS policies allow admin cross-member access).")
