
import pandas as pd
import streamlit as st
from supabase import create_client

# ============================================================
# THE YOUNG SHALL GROW — Njangi Dashboard (SINGLE APP)
# ------------------------------------------------------------
# ✅ Supabase Auth login (email/password)
# ✅ Member: sees ONLY own data (RLS enforced)
# ✅ Admin: can view ALL / filter member_id; can add/approve/issue/payout via dashboard
# ✅ Admin data-entry dropdown:
#    - Add Member (email + phone)
#    - Add Contribution
#    - Add Foundation Payment
#    - Add Fine
#    - Record Repayment
#    - Approve Loan (requested -> approved)
#    - Issue Loan (approved -> active/open)
#    - Conduct Payout (RPC best-effort)
# ✅ Member Loan Request:
#    - Inserts loan as status="requested"
#    - Select surety from members list
# ✅ Ports:
#    - Foundation "Paid (+Repay)" includes repayments.amount_paid
#    - Loan remaining balance = total_due - sum(repayments.amount_paid) (best-effort)
# ✅ Clean order: Welcome -> Live updates -> Filters -> Beneficiary -> Ports -> Member request -> Admin -> Tables
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

def safe_float(x, default=0.0):
    try:
        return float(pd.to_numeric(x, errors="coerce"))
    except Exception:
        return default

# Best-effort: infer existing columns from a sample row (your tables already have data)
def get_table_cols(table: str) -> set:
    try:
        d = supabase.table(table).select("*").limit(1).execute().data or []
        if d:
            return set(d[0].keys())
    except Exception:
        pass
    return set()

def filter_payload(payload: dict, cols: set) -> dict:
    if not cols:
        # If we couldn't infer columns, try sending payload as-is (RLS/DB will decide).
        return payload
    return {k: v for k, v in payload.items() if k in cols}

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
        This is a bi-weekly Njangi dashboard. Members can view their own records and request loans.
        Admin manages the group by adding transactions, approving/issuing loans, recording repayments,
        and running payouts/rotation. Every transaction is tracked using <b>member_id</b>
        (loans use <b>borrower_member_id</b>).
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# LIVE UPDATES (dropdown)
# ----------------------------
with st.expander("🔽 Live Updates", expanded=False):
    st.caption("Keeps ports updated when admin adds data, repayments are recorded, or scheduled jobs run.")
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
    df = df.copy()
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
# LOAD MEMBERS (for admin dropdown + surety dropdown)
# ----------------------------
def load_members_df():
    try:
        rows = supabase.table("members").select("*").order("id").execute().data or []
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame([])

members_df = load_members_df()

def member_label(mid: int, name: str, email: str):
    base = name or email or f"Member {mid}"
    return f"{mid} — {base}"

def build_member_options(df: pd.DataFrame):
    if df.empty or "id" not in df.columns:
        return {}, []
    options = {}
    labels = []
    for _, r in df.iterrows():
        mid = int(r.get("id"))
        nm = str(r.get("name") or "")
        em = str(r.get("email") or "")
        lbl = member_label(mid, nm, em)
        options[lbl] = mid
        labels.append(lbl)
    return options, labels

member_opts, member_labels = build_member_options(members_df)

# ----------------------------
# LOAD DATA (tables)
# ----------------------------
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

# ----------------------------
# LOAN BALANCES AFTER REPAYMENTS (best-effort)
# ----------------------------
def compute_loan_balances(loans: pd.DataFrame, repays: pd.DataFrame) -> pd.DataFrame:
    if loans.empty or "id" not in loans.columns:
        return loans
    out = loans.copy()
    if repays.empty or "loan_id" not in repays.columns:
        out["total_repaid"] = 0.0
        if "total_due" in out.columns:
            out["remaining_balance"] = pd.to_numeric(out["total_due"], errors="coerce").fillna(0)
        return out

    col_amt = "amount_paid" if "amount_paid" in repays.columns else ("amount" if "amount" in repays.columns else None)
    if not col_amt:
        return out

    r = repays.copy()
    r[col_amt] = pd.to_numeric(r[col_amt], errors="coerce").fillna(0)
    r = r.groupby("loan_id")[col_amt].sum().reset_index().rename(columns={col_amt: "total_repaid"})

    out = out.merge(r, left_on="id", right_on="loan_id", how="left")
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
        tc = safe_float(r.get("total_contribution", 0) or 0)
        tfp = safe_float(r.get("total_foundation_paid", 0) or 0)
        tfn = safe_float(r.get("total_foundation_pending", 0) or 0)
        tl = safe_float(r.get("total_loan", 0) or 0)

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
        pass

with st.expander("🔽 Beneficiary (Current + Next)", expanded=True):
    show_current_beneficiary_box()
    show_next_beneficiary_port_for_all()

# ----------------------------
# PORTS / KPIs
# ----------------------------
total_contrib = safe_sum(contrib_df, "amount")

found_paid_only = safe_sum(found_df, "amount_paid")
found_pending = safe_sum(found_df, "amount_pending")

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
# - Inserts into loans as status="requested"
# - Uses surety selection
# - Uses member_id for borrower_member_id
# ============================================================
with st.expander("🔽 Member: Request Loan (how it works)", expanded=not is_admin):
    st.markdown(
        "<div class='small-muted'>"
        "Members request a loan here. You choose a surety from the member list. "
        "Your request is saved with status <b>requested</b>. Admin later approves and issues it."
        "</div>",
        unsafe_allow_html=True
    )

    surety_labels = [lbl for lbl in member_labels if not lbl.startswith(f"{my_member_id} —")]
    surety_pick = st.selectbox("Select Surety", surety_labels) if surety_labels else None

    with st.form("member_loan_request_form", clear_on_submit=False):
        req_amount = st.number_input("Requested Amount", min_value=0.0, step=100.0, value=0.0)
        notes = st.text_input("Notes (optional)")
        submit_req = st.form_submit_button("Submit Loan Request")

    if submit_req:
        try:
            surety_member_id = None
            surety_name = None
            if surety_pick:
                surety_member_id = int(surety_pick.split("—")[0].strip())
                surety_name = surety_pick.split("—", 1)[1].strip()

            loans_cols = get_table_cols("loans")
            payload = {
                "borrower_member_id": my_member_id,
                "borrower_name": my_member.get("name") or user_email,
                "principal": float(req_amount),
                "status": "requested",
                "surety_member_id": surety_member_id,
                "surety_name": surety_name,
                "notes": notes.strip() if notes.strip() else None,
            }
            payload = filter_payload(payload, loans_cols)

            supabase.table("loans").insert(payload).execute()
            st.success("✅ Loan request submitted. Please wait for admin approval.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Could not submit loan request (RLS or schema mismatch). Details:\n{e}")

# ============================================================
# ADMIN CONTROL PANEL (dropdown)
# ============================================================
if is_admin:
    with st.expander("🔽 Admin: Control Panel (what each dropdown does)", expanded=True):
        st.markdown(
            "<div class='small-muted'>"
            "<b>Add Member</b>: creates a member row (email + phone). "
            "<b>Add Contribution/Foundation/Fine/Repayment</b>: inserts a transaction using <b>member_id</b>. "
            "<b>Approve/Issue Loan</b>: updates loan status. "
            "<b>Conduct Payout</b>: runs payout rotation via RPC (if you created it)."
            "</div>",
            unsafe_allow_html=True
        )

        action = st.selectbox(
            "Admin Action",
            [
                "Add Member (email + phone)",
                "Add Contribution",
                "Add Foundation Payment",
                "Add Fine",
                "Record Repayment",
                "Approve Loan (requested → approved)",
                "Issue Loan (approved → active/open)",
                "Conduct Payout (RPC)",
            ],
            index=0
        )

        # Shared member picker (for all transactions)
        if not member_labels:
            st.warning("No members found in members table. Add members first.")
            target_member_id = None
            target_member_name = ""
        else:
            target_label = st.selectbox("Target Member", member_labels)
            target_member_id = int(target_label.split("—")[0].strip())
            target_member_name = target_label.split("—", 1)[1].strip()

        # 1) Add Member
        if action == "Add Member (email + phone)":
            st.subheader("Add Member")
            st.caption("This inserts into public.members. NOTE: It does NOT create a Supabase Auth user.")
            with st.form("admin_add_member_form", clear_on_submit=True):
                email = st.text_input("Email").strip().lower()
                phone = st.text_input("Phone").strip()
                name = st.text_input("Name (optional)").strip()
                submit = st.form_submit_button("Create Member")

            if submit:
                try:
                    if not email or not phone:
                        st.error("Email and phone are required.")
                    else:
                        members_cols = get_table_cols("members")
                        payload = {"email": email, "phone": phone, "name": name if name else email.split("@")[0].title()}
                        payload = filter_payload(payload, members_cols)

                        # best-effort duplicate check by email
                        existing = supabase.table("members").select("id").eq("email", email).limit(1).execute().data
                        if existing:
                            st.warning(f"Member already exists: member_id = {existing[0]['id']}")
                        else:
                            supabase.table("members").insert(payload).execute()
                            st.success("✅ Member created.")
                            st.rerun()
                except Exception as e:
                    st.error(f"❌ Could not create member (RLS may block INSERT). Details:\n{e}")

        # 2) Add Contribution
        elif action == "Add Contribution":
            st.subheader("Add Contribution")
            with st.form("admin_add_contribution_form", clear_on_submit=True):
                amount = st.number_input("Amount", min_value=0.0, step=50.0, value=0.0)
                kind = st.text_input("Kind (optional)", value="bi-weekly")
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("Save Contribution")

            if submit and target_member_id:
                try:
                    cols = get_table_cols("contributions")
                    payload = {"member_id": int(target_member_id), "amount": float(amount), "kind": kind, "notes": notes or None}
                    payload = filter_payload(payload, cols)
                    supabase.table("contributions").insert(payload).execute()
                    st.success("✅ Contribution saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Insert failed (RLS may block). Details:\n{e}")

        # 3) Add Foundation Payment
        elif action == "Add Foundation Payment":
            st.subheader("Add Foundation Payment")
            with st.form("admin_add_found_form", clear_on_submit=True):
                paid = st.number_input("Amount Paid", min_value=0.0, step=50.0, value=0.0)
                pending = st.number_input("Amount Pending", min_value=0.0, step=50.0, value=0.0)
                status = st.selectbox("Status", ["paid", "pending", "partial"], index=2)
                date_paid = st.date_input("Date Paid")
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("Save Foundation Payment")

            if submit and target_member_id:
                try:
                    cols = get_table_cols("foundation_payments")
                    payload = {
                        "member_id": int(target_member_id),
                        "amount_paid": float(paid),
                        "amount_pending": float(pending),
                        "status": status,
                        "date_paid": str(date_paid),
                        "notes": notes or None
                    }
                    payload = filter_payload(payload, cols)
                    supabase.table("foundation_payments").insert(payload).execute()
                    st.success("✅ Foundation payment saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Insert failed (RLS may block). Details:\n{e}")

        # 4) Add Fine
        elif action == "Add Fine":
            st.subheader("Add Fine")
            with st.form("admin_add_fine_form", clear_on_submit=True):
                amount = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
                reason = st.text_input("Reason", value="Late payment")
                status = st.selectbox("Status", ["unpaid", "paid"], index=0)
                submit = st.form_submit_button("Save Fine")

            if submit and target_member_id:
                try:
                    cols = get_table_cols("fines")
                    payload = {"member_id": int(target_member_id), "amount": float(amount), "reason": reason, "status": status}
                    payload = filter_payload(payload, cols)
                    supabase.table("fines").insert(payload).execute()
                    st.success("✅ Fine saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Insert failed (RLS may block). Details:\n{e}")

        # 5) Record Repayment
        elif action == "Record Repayment":
            st.subheader("Record Repayment")
            with st.form("admin_add_repay_form", clear_on_submit=True):
                loan_id = st.text_input("Loan ID (optional)", placeholder="e.g. 12")
                amount_paid = st.number_input("Amount Paid", min_value=0.0, step=50.0, value=0.0)
                paid_at = st.date_input("Paid Date")
                notes = st.text_input("Notes (optional)")
                submit = st.form_submit_button("Save Repayment")

            if submit and target_member_id:
                try:
                    cols = get_table_cols("repayments")
                    payload = {
                        "member_id": int(target_member_id),
                        "member_name": target_member_name,
                        "borrower_member_id": int(target_member_id),
                        "borrower_name": target_member_name,
                        "amount_paid": float(amount_paid),
                        "amount": float(amount_paid),
                        "paid_at": str(paid_at),
                        "notes": notes or None,
                    }
                    if loan_id.strip():
                        payload["loan_id"] = int(loan_id.strip())

                    payload = filter_payload(payload, cols)
                    supabase.table("repayments").insert(payload).execute()
                    st.success("✅ Repayment saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Insert failed (RLS may block). Details:\n{e}")

        # 6) Approve Loan
        elif action == "Approve Loan (requested → approved)":
            st.subheader("Approve Loan")
            st.caption("Enter the loan ID you want to approve.")
            loan_id = st.number_input("Loan ID", min_value=1, step=1, value=1)
            if st.button("✅ Approve"):
                try:
                    supabase.table("loans").update({"status": "approved"}).eq("id", int(loan_id)).execute()
                    st.success("✅ Loan approved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Update failed (RLS may block). Details:\n{e}")

        # 7) Issue Loan
        elif action == "Issue Loan (approved → active/open)":
            st.subheader("Issue Loan")
            st.caption("Enter the loan ID you want to issue (make active/open).")
            loan_id = st.number_input("Loan ID", min_value=1, step=1, value=1)
            new_status = st.selectbox("Set status to", ["active", "open", "ongoing"], index=0)
            if st.button("🚀 Issue"):
                try:
                    supabase.table("loans").update({"status": new_status}).eq("id", int(loan_id)).execute()
                    st.success("✅ Loan issued.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Update failed (RLS may block). Details:\n{e}")

        # 8) Conduct Payout (RPC)
        elif action == "Conduct Payout (RPC)":
            st.subheader("Conduct Payout (RPC)")
            st.caption("This calls your payout RPC: record_payout_and_rotate_next(). If your RPC name differs, change it here.")
            if st.button("💰 Execute Payout & Rotate"):
                try:
                    supabase.rpc("record_payout_and_rotate_next", {}).execute()
                    st.success("✅ Payout executed & beneficiary rotated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ RPC failed (function missing/params/RLS). Details:\n{e}")

# ============================================================
# VIEW TABLES (dropdown)
# ============================================================
with st.expander("🔽 View Tables", expanded=True):
    table_page = st.selectbox(
        "Select Table",
        ["My Profile", "Members", "Contributions", "Foundation Payments", "Loans", "Repayments", "Fines"],
        index=0
    )

    if table_page == "My Profile":
        st.subheader("My Profile")
        st.json(my_member)

    elif table_page == "Members":
        st.subheader("Members")
        if members_df.empty:
            st.info("No members found.")
        else:
            st.dataframe(members_df, use_container_width=True, hide_index=True)

    elif table_page == "Contributions":
        st.subheader("Contributions")
        st.dataframe(contrib_df, use_container_width=True, hide_index=True)

    elif table_page == "Foundation Payments":
        st.subheader("Foundation Payments")
        st.markdown(
            f"<div class='small-muted'>Paid (table): <b>{found_paid_only:,.2f}</b> • "
            f"Repayments: <b>{total_repaid:,.2f}</b> • Pending: <b>{found_pending:,.2f}</b></div>",
            unsafe_allow_html=True
        )
        st.dataframe(found_df, use_container_width=True, hide_index=True)

    elif table_page == "Loans":
        st.subheader("Loans")
        if loans_df.empty:
            st.info("No loans found.")
        else:
            preferred = [
                "id", "borrower_member_id", "borrower_name", "surety_member_id", "surety_name",
                "principal", "principal_current", "interest", "total_due", "balance",
                "total_repaid", "remaining_balance",
                "status", "borrow_date", "issued_at", "created_at", "updated_at"
            ]
            cols = [c for c in preferred if c in loans_df.columns] + [c for c in loans_df.columns if c not in preferred]
            st.dataframe(loans_df[cols], use_container_width=True, hide_index=True)

    elif table_page == "Repayments":
        st.subheader("Repayments")
        st.dataframe(repay_df, use_container_width=True, hide_index=True)

    elif table_page == "Fines":
        st.subheader("Fines")
        st.dataframe(fines_df, use_container_width=True, hide_index=True)

st.markdown("<hr/>", unsafe_allow_html=True)
if not is_admin:
    st.caption("Member access: you can only view your own data (email → member_id). Admin actions are hidden.")
else:
    st.caption("Admin access: use Admin Control Panel to add/approve/issue/payout. Viewing ALL members requires admin RLS policies.")
