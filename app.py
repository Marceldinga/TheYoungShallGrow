
# ============================================================
# THE YOUNG SHALL GROW — Njangi Dashboard (SINGLE APP)
# PART 1 (PART 2 CONTINUES BELOW)
# ------------------------------------------------------------
# ✅ Supabase Auth login (email/password)
# ✅ Rotation POT (permanent rule):
#    - POT counts ONLY contributions AFTER last payout execution time (payouts.created_at)
#    - Window = 14 days after last payout execution time
# ✅ Member: view own data + request loan (RULE ENFORCED before insert)
#    - capacity = contributions + 70% * foundation_paid
#    - borrower MUST qualify AND surety MUST qualify (same rule) before request can be submitted
# ✅ Admin: (Part 2) add members + all transactions + approve/issue + payout + view tables
#
# IMPORTANT
# - Money inputs are forced to INTEGER (prevents 500.0 -> integer error)
# - Every transaction uses member_id (loans use borrower_member_id)
# - Admin view ALL depends on your RLS policies.
# ============================================================

import pandas as pd
import streamlit as st
from supabase import create_client
from datetime import date

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
# ROTATION SETTINGS
# ----------------------------
SEASON_START_DATE = date(2026, 1, 3)  # used only if payouts table is empty
PAYOUT_EVERY_DAYS = 14

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
# HELPERS
# ----------------------------
def is_logged_in() -> bool:
    return bool(st.session_state.get("access_token"))

def logout():
    st.session_state.clear()
    st.rerun()

def attach_jwt(access_token: str):
    supabase.postgrest.auth(access_token)

def safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

def money_int(label: str, value: int = 0, step: int = 500, min_value: int = 0):
    return st.number_input(label, min_value=min_value, value=value, step=step, format="%d")

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
# MEMBERS LIST (for admin & surety dropdowns)
# ----------------------------
def load_members_df():
    try:
        rows = supabase.table("members").select("*").order("id").execute().data or []
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame([])

members_df = load_members_df()

def member_display(mid: int, name: str, email: str):
    nm = (name or "").strip()
    if nm:
        return nm
    em = (email or "").strip()
    if em:
        return em
    return f"Member {mid}"

def member_label(mid: int, display: str):
    return f"{mid} — {display}"

def build_member_labels(df: pd.DataFrame):
    if df.empty or "id" not in df.columns:
        return []
    labels = []
    for _, r in df.iterrows():
        mid = int(pd.to_numeric(r.get("id"), errors="coerce"))
        disp = member_display(mid, str(r.get("name") or ""), str(r.get("email") or ""))
        labels.append(member_label(mid, disp))
    return labels

member_labels = build_member_labels(members_df)

def member_name_by_id(member_id: int) -> str:
    try:
        if not members_df.empty and "id" in members_df.columns:
            s = members_df.copy()
            s["id"] = pd.to_numeric(s["id"], errors="coerce")
            row = s[s["id"] == int(member_id)]
            if not row.empty:
                nm = str(row.iloc[0].get("name") or "").strip()
                if nm:
                    return nm
        row2 = supabase.table("members").select("name").eq("id", int(member_id)).limit(1).execute().data or []
        nm2 = str(row2[0].get("name") or "").strip() if row2 else ""
        return nm2 if nm2 else f"Member {member_id}"
    except Exception:
        return f"Member {member_id}"

# ----------------------------
# HEADER
# ----------------------------
st.markdown(
    f"""
    <div class='hdr'>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h1 style="margin:0">📊 The Young Shall Grow — Njangi Dashboard</h1>
          <div class="small-muted">
            Logged in as <b>{user_email}</b> {'(admin)' if is_admin else ''} • Your member_id = <b>{my_member_id}</b> • Name: <b>{member_name_by_id(my_member_id)}</b>
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

c1, _ = st.columns([1, 6])
with c1:
    st.button("Logout", on_click=logout)

# ----------------------------
# LIVE UPDATES
# ----------------------------
with st.expander("🔽 Live Updates (auto refresh)", expanded=False):
    st.caption("Keeps ports updated when admin adds data, repayments are recorded, or payouts happen.")
    enable_live = st.toggle("Enable auto-refresh", value=True)
    refresh_seconds = st.selectbox("Refresh every (seconds)", [10, 20, 30, 60, 120], index=2)
    if st.button("🔄 Refresh now"):
        st.rerun()
    if enable_live and st_autorefresh:
        st_autorefresh(interval=int(refresh_seconds) * 1000, key="live_refresh")
    elif enable_live and not st_autorefresh:
        st.warning("Add `streamlit-autorefresh` to requirements.txt on Streamlit Cloud to enable auto-refresh.")

# ----------------------------
# FILTERS
# ----------------------------
with st.expander("🔽 Filters", expanded=True):
    if is_admin:
        a1, f1, f2, f3, f4 = st.columns([2, 2, 3, 2, 2])
        admin_member_id = a1.text_input("Member ID (admin)", placeholder="Leave empty = ALL members")
    else:
        f1, f2, f3, f4 = st.columns([2, 3, 2, 2])
        admin_member_id = ""

    range_opt = f1.selectbox("Time range", ["All time", "Last 30 days", "Last 90 days", "This year"], index=0)
    search_text = f2.text_input("Quick search", placeholder="e.g. unpaid, paid, pending...")
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
# ROTATION POT
# ----------------------------
def get_last_payout_row():
    try:
        rows = (
            supabase.table("payouts")
            .select("member_id,member_name,payout_amount,payout_date,created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
    except Exception:
        return None

def get_rotation_pot_total():
    # Try VIEW if you created it
    try:
        v = supabase.table("current_rotation").select("*").limit(1).execute().data or []
        if v:
            row = v[0]
            start_ts = pd.to_datetime(row["rotation_start_ts"], utc=True)
            end_ts = pd.to_datetime(row["rotation_end_ts"], utc=True)
            pot = float(row["rotation_total"] or 0)
            return start_ts, end_ts, pot
    except Exception:
        pass

    # fallback
    try:
        last = (
            supabase.table("payouts")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if last and last[0].get("created_at"):
            start_ts = pd.to_datetime(last[0]["created_at"], utc=True)
        else:
            start_ts = pd.to_datetime(str(SEASON_START_DATE) + " 00:00:00+00:00")
    except Exception:
        start_ts = pd.to_datetime(str(SEASON_START_DATE) + " 00:00:00+00:00")

    end_ts = start_ts + pd.Timedelta(days=PAYOUT_EVERY_DAYS)

    try:
        rows = (
            supabase.table("contributions")
            .select("amount,created_at")
            .gt("created_at", start_ts.isoformat())
            .lte("created_at", end_ts.isoformat())
            .execute()
            .data
            or []
        )
        df = pd.DataFrame(rows)
        pot = float(pd.to_numeric(df["amount"], errors="coerce").fillna(0).sum()) if not df.empty else 0.0
    except Exception:
        pot = 0.0

    return start_ts, end_ts, pot

with st.expander("🔽 Rotation Ports (POT)", expanded=True):
    last = get_last_payout_row()
    if last:
        st.markdown(
            f"""
            <div class="card">
              <div style="font-size:16px;font-weight:800">✅ Last payout recorded</div>
              <div class="small-muted" style="margin-top:8px">
                Paid: <b>{last.get('member_name','')}</b> (ID <b>{last.get('member_id','')}</b>)<br>
                Amount: <b>{last.get('payout_amount','')}</b> • Date: <b>{last.get('payout_date','')}</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("No payout row found yet. Rotation starts from season start date.")

    rot_start_ts, rot_end_ts, rot_total = get_rotation_pot_total()
    st.caption(f"Rotation window (execution-time based): {rot_start_ts} → {rot_end_ts}")

    st.markdown(
        f"<div class='kpi'><div class='label'>Current Rotation POT (Total Contributions)</div>"
        f"<div class='value'>{rot_total:,.2f}</div><div class='accent'></div></div>",
        unsafe_allow_html=True
    )

# ----------------------------
# LOAD DATA
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
# SUMMARY PORTS
# ----------------------------
def compute_loan_balances(loans: pd.DataFrame, repays: pd.DataFrame) -> pd.DataFrame:
    if loans.empty or "id" not in loans.columns:
        return loans
    out = loans.copy()

    if repays.empty or "loan_id" not in repays.columns:
        out["total_repaid"] = 0
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

with st.expander("🔽 Summary Ports (Totals)", expanded=True):
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.markdown(f"<div class='kpi'><div class='label'>Total Contributions (Viewed)</div><div class='value'>{total_contrib:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi'><div class='label'>Foundation Paid (+Repay)</div><div class='value'>{total_found_paid_plus_repaid:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi'><div class='label'>Foundation Pending</div><div class='value'>{found_pending:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi'><div class='label'>Unpaid Fines</div><div class='value'>{unpaid_fines_amt:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k5.markdown(f"<div class='kpi'><div class='label'>Active Loans</div><div class='value'>{active_loans}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k6.markdown(f"<div class='kpi'><div class='label'>Loan Total</div><div class='value'>{loan_total:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ----------------------------
# LOAN RULE HELPERS
# ----------------------------
def sum_member_contrib(member_id: int) -> float:
    try:
        rows = supabase.table("contributions").select("amount").eq("member_id", int(member_id)).execute().data or []
        df = pd.DataFrame(rows)
        if df.empty:
            return 0.0
        return float(pd.to_numeric(df["amount"], errors="coerce").fillna(0).sum())
    except Exception:
        return 0.0

def sum_member_foundation_paid(member_id: int) -> float:
    try:
        rows = supabase.table("foundation_payments").select("amount_paid").eq("member_id", int(member_id)).execute().data or []
        df = pd.DataFrame(rows)
        if df.empty:
            return 0.0
        return float(pd.to_numeric(df["amount_paid"], errors="coerce").fillna(0).sum())
    except Exception:
        return 0.0

def borrow_capacity(member_id: int) -> float:
    return float(sum_member_contrib(member_id) + 0.70 * sum_member_foundation_paid(member_id))

# ============================================================
# MEMBER: REQUEST LOAN (Borrower + Surety must BOTH qualify)
# ============================================================
with st.expander("🔽 Member: Request Loan (Borrower + Surety Must Qualify)", expanded=not is_admin):
    st.caption(
        "You MUST select a surety. "
        "Eligibility: BOTH you and your surety must qualify using: capacity = contributions + 70%*foundation_paid."
    )

    surety_labels = [lbl for lbl in member_labels if not lbl.startswith(f"{my_member_id} —")]
    if not surety_labels:
        st.warning("No other members available to select as surety.")
        st.stop()

    surety_pick = st.selectbox("Select Surety (member_id — name)", surety_labels, key="surety_required")
    surety_id = int(surety_pick.split("—")[0].strip())
    surety_name = member_name_by_id(surety_id)

    req_amount = money_int("Requested Amount", value=0, step=500)
    req_amount_int = int(req_amount)

    my_name = member_name_by_id(my_member_id)
    my_cap = borrow_capacity(my_member_id)
    surety_cap = borrow_capacity(surety_id)

    st.info(f"Your capacity (ID {my_member_id} — {my_name}) = **{my_cap:,.2f}**")
    st.write(f"Surety capacity (ID {surety_id} — {surety_name}) = **{surety_cap:,.2f}**")

    if req_amount_int <= 0:
        st.caption("Enter a requested amount to evaluate eligibility.")
        st.stop()

    borrower_ok = my_cap >= req_amount_int
    surety_ok = surety_cap >= req_amount_int
    eligible = borrower_ok and surety_ok

    if eligible:
        st.success("✅ Eligible: borrower qualifies AND surety qualifies.")
    else:
        if not borrower_ok:
            st.error("❌ Borrower not eligible: your capacity is less than requested amount.")
        if not surety_ok:
            st.error("❌ Surety not eligible: choose a stronger surety.")

    with st.form("member_loan_request_form_both_qualify", clear_on_submit=False):
        notes = st.text_input("Notes (optional)")
        submit_req = st.form_submit_button("Submit Loan Request")

    if submit_req:
        try:
            if not eligible:
                st.error("❌ Cannot submit: borrower and surety must both qualify.")
                st.stop()

            loans_cols = get_table_cols("loans")
            payload = {
                "borrower_member_id": my_member_id,
                "borrower_name": my_name,
                "principal": req_amount_int,
                "status": "requested",
                "surety_member_id": int(surety_id),
                "surety_name": surety_name,
                "notes": notes.strip() if notes.strip() else None,
            }
            payload = filter_payload(payload, loans_cols)

            supabase.table("loans").insert(payload).execute()
            st.success("✅ Loan request submitted (rule passed). Waiting for admin approval.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Could not submit loan request. Details:\n{e}")

# ------------------------------------------------------------
# PART 2 CONTINUES BELOW
# ------------------------------------------------------------

# ============================================================
# PART 2 — ADMIN CONTROL PANEL + VIEW TABLES
# ============================================================

if is_admin:
    with st.expander("🔽 Admin Control Panel (Manage All Njangi Operations)", expanded=True):

        action = st.selectbox(
            "Select Admin Action",
            [
                "Add Member",
                "Add Contribution",
                "Add Foundation Payment",
                "Add Fine",
                "Record Repayment",
                "Approve Loan",
                "Issue Loan",
                "Conduct Payout",
            ]
        )

        if members_df.empty:
            st.warning("No members found. Please add members first.")
            target_member_id = None
        else:
            target_label = st.selectbox("Select Member (member_id — name/email)", member_labels)
            target_member_id = int(target_label.split("—")[0].strip())

        # 1) ADD MEMBER
        if action == "Add Member":
            st.subheader("➕ Add Member (email + phone + name)")
            with st.form("add_member_form"):
                email = st.text_input("Email").strip().lower()
                phone = st.text_input("Phone").strip()
                name = st.text_input("Name (required)").strip()
                submit = st.form_submit_button("Create Member")
            if submit:
                try:
                    if not email or not phone or not name:
                        st.error("Email, phone, and name are required.")
                    else:
                        payload = {"email": email, "phone": phone, "name": name}
                        payload = filter_payload(payload, get_table_cols("members"))
                        supabase.table("members").insert(payload).execute()
                        st.success("✅ Member created.")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 2) ADD CONTRIBUTION
        elif action == "Add Contribution":
            st.subheader("➕ Add Contribution")
            with st.form("add_contribution_form"):
                amount = money_int("Amount", step=500)
                kind = st.text_input("Kind", value="bi-weekly")
                submit = st.form_submit_button("Save Contribution")
            if submit and target_member_id:
                try:
                    payload = {"member_id": int(target_member_id), "amount": int(amount), "kind": kind}
                    payload = filter_payload(payload, get_table_cols("contributions"))
                    supabase.table("contributions").insert(payload).execute()
                    st.success("✅ Contribution saved. POT updates automatically.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 3) ADD FOUNDATION PAYMENT
        elif action == "Add Foundation Payment":
            st.subheader("➕ Add Foundation Payment")
            with st.form("add_foundation_form"):
                paid = money_int("Amount Paid", step=500)
                pending = money_int("Amount Pending", step=500)
                status = st.selectbox("Status", ["paid", "pending", "partial"])
                date_paid = st.date_input("Date Paid")
                submit = st.form_submit_button("Save Foundation Payment")
            if submit and target_member_id:
                try:
                    payload = {
                        "member_id": int(target_member_id),
                        "amount_paid": int(paid),
                        "amount_pending": int(pending),
                        "status": status,
                        "date_paid": str(date_paid),
                    }
                    payload = filter_payload(payload, get_table_cols("foundation_payments"))
                    supabase.table("foundation_payments").insert(payload).execute()
                    st.success("✅ Foundation payment saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 4) ADD FINE
        elif action == "Add Fine":
            st.subheader("➕ Add Fine")
            with st.form("add_fine_form"):
                amount = money_int("Fine Amount", step=100)
                reason = st.text_input("Reason", value="Late payment")
                status = st.selectbox("Status", ["unpaid", "paid"])
                submit = st.form_submit_button("Save Fine")
            if submit and target_member_id:
                try:
                    payload = {"member_id": int(target_member_id), "amount": int(amount), "reason": reason, "status": status}
                    payload = filter_payload(payload, get_table_cols("fines"))
                    supabase.table("fines").insert(payload).execute()
                    st.success("✅ Fine saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 5) RECORD REPAYMENT
        elif action == "Record Repayment":
            st.subheader("➕ Record Repayment")
            with st.form("add_repayment_form"):
                loan_id = st.number_input("Loan ID", min_value=1, step=1)
                amount_paid = money_int("Amount Paid", step=500)
                paid_at = st.date_input("Paid Date")
                submit = st.form_submit_button("Save Repayment")
            if submit and target_member_id:
                try:
                    payload = {
                        "member_id": int(target_member_id),
                        "loan_id": int(loan_id),
                        "amount_paid": int(amount_paid),
                        "paid_at": str(paid_at),
                    }
                    payload = filter_payload(payload, get_table_cols("repayments"))
                    supabase.table("repayments").insert(payload).execute()
                    st.success("✅ Repayment recorded.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 6) APPROVE LOAN
        elif action == "Approve Loan":
            st.subheader("✅ Approve Loan (requested → approved)")
            loan_id = st.number_input("Loan ID", min_value=1, step=1)
            if st.button("Approve Loan"):
                try:
                    supabase.table("loans").update({"status": "approved"}).eq("id", int(loan_id)).execute()
                    st.success("✅ Loan approved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 7) ISSUE LOAN
        elif action == "Issue Loan":
            st.subheader("🚀 Issue Loan (approved → active)")
            loan_id = st.number_input("Loan ID", min_value=1, step=1)
            if st.button("Issue Loan"):
                try:
                    supabase.table("loans").update({"status": "active"}).eq("id", int(loan_id)).execute()
                    st.success("✅ Loan issued.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed: {e}")

        # 8) CONDUCT PAYOUT
        elif action == "Conduct Payout":
            st.subheader("💰 Conduct Payout & Rotate Beneficiary")
            st.caption("Tries RPC record_payout_and_rotate_next() if it exists. POT auto-updates from payouts table.")
            if st.button("Execute Payout"):
                try:
                    try:
                        supabase.rpc("record_payout_and_rotate_next", {}).execute()
                    except Exception:
                        pass
                    st.success("✅ Payout executed (if RPC exists).")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Payout failed: {e}")

# ============================================================
# VIEW TABLES
# ============================================================
with st.expander("🔽 View Tables", expanded=True):
    table_page = st.selectbox(
        "Select Table",
        ["My Profile", "Members", "Contributions", "Foundation Payments", "Loans", "Repayments", "Fines", "Payouts"],
        index=0
    )

    if table_page == "My Profile":
        st.subheader("My Profile")
        st.json(my_member)

    elif table_page == "Members":
        st.subheader("Members")
        st.dataframe(members_df, use_container_width=True, hide_index=True)

    elif table_page == "Contributions":
        st.subheader("Contributions")
        st.dataframe(contrib_df, use_container_width=True, hide_index=True)

    elif table_page == "Foundation Payments":
        st.subheader("Foundation Payments")
        st.dataframe(found_df, use_container_width=True, hide_index=True)

    elif table_page == "Loans":
        st.subheader("Loans")
        st.dataframe(loans_df, use_container_width=True, hide_index=True)

    elif table_page == "Repayments":
        st.subheader("Repayments")
        st.dataframe(repay_df, use_container_width=True, hide_index=True)

    elif table_page == "Fines":
        st.subheader("Fines")
        st.dataframe(fines_df, use_container_width=True, hide_index=True)

    elif table_page == "Payouts":
        st.subheader("Payouts")
        try:
            payouts_df = pd.DataFrame(
                supabase.table("payouts").select("*").order("created_at", desc=True).execute().data or []
            )
        except Exception:
            payouts_df = pd.DataFrame([])
        st.dataframe(payouts_df, use_container_width=True, hide_index=True)

st.markdown("<hr/>", unsafe_allow_html=True)
st.caption("End of Dashboard.")
