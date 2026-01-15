import pandas as pd
import streamlit as st
from supabase import create_client

# ============================================================
# The Young Shall Grow – Dashboard (Single Script)
# - Member login (Supabase Auth)
# - Member sees ONLY their data (RLS) + extra safety filters
# - Admin can switch "Member ID" to view another member
# - IMPORTANT FIX: Loans fetch tries multiple possible member columns
#   (member_id / borrower_id / user_id) and falls back gracefully
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
# PRO UI THEME
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
    # Make all PostgREST queries use the logged-in user's JWT (RLS applies)
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

# Re-attach JWT on refresh
attach_jwt(st.session_state["access_token"])

user_email = st.session_state.get("user_email", "").lower()
is_admin = user_email in ADMIN_EMAILS

# ----------------------------
# GET MY MEMBER ROW (RLS should return only my row)
# ----------------------------
try:
    rows = supabase.table("members").select("id,name,email,phone,has_benefits,position").limit(1).execute().data
    my_member = rows[0] if rows else None
except Exception:
    my_member = None

if not my_member:
    st.warning("No member profile found. Ensure public.members.email matches the Auth email exactly.")
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
            Logged in as <b>{user_email}</b> {'(admin)' if is_admin else ''} •
            Default member_id = <b>{my_member_id}</b>
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
st.button("Logout", on_click=logout)

# ----------------------------
# FILTER PANEL
# ----------------------------
st.subheader("Filters")
f1, f2, f3, f4, f5 = st.columns([2, 3, 2, 2, 2])

range_opt = f1.selectbox("Time range", ["All time", "Last 30 days", "Last 90 days", "This year"], index=0)
search_text = f2.text_input("Quick search", placeholder="e.g. unpaid, paid, pending, late, foundation...")
member_filter = f3.text_input("Member ID", placeholder="leave blank = me")
record_id = f4.text_input("Record ID", placeholder="e.g. 58")
show_only_unpaid = f5.checkbox("Only unpaid fines", value=False)

# Which member_id to view:
# - Members: always their own member_id
# - Admin: can type another member_id
effective_member_id = my_member_id
if is_admin and member_filter.strip():
    try:
        effective_member_id = int(member_filter.strip())
    except Exception:
        effective_member_id = my_member_id

# ----------------------------
# FILTER FUNCTIONS
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

# ----------------------------
# FETCH HELPERS (by member_id)
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

def fetch_loans_best_effort() -> pd.DataFrame:
    """
    Fix for your issue:
    Some projects store loans with a different column name (member_id vs borrower_id vs user_id).
    This tries multiple options so loans will show when the member actually has a loan.
    """
    # Try common schemas in order:
    candidates = [
        ("member_id", "created_at"),
        ("borrower_id", "created_at"),
        ("user_id", "created_at"),  # sometimes uuid (may not match member_id; still try)
    ]

    # Try selecting everything first (safe; RLS still applies)
    for member_col, date_col in candidates:
        try:
            df = fetch_df("loans", "*", member_col=member_col, order_col=date_col, date_col=date_col)
            if not df.empty:
                df["_matched_on"] = member_col
                return df
        except Exception:
            continue

    # If still empty: maybe loans date column is not created_at
    # Try without ordering/date filter
    for member_col, _ in candidates:
        try:
            q = supabase.table("loans").select("*").eq(member_col, effective_member_id)
            data = q.execute().data
            df = pd.DataFrame(data or [])
            if not df.empty:
                df["_matched_on"] = member_col
                return df
        except Exception:
            continue

    return pd.DataFrame()

# ----------------------------
# LOAD DATA + APPLY FILTERS
# ----------------------------
# Contributions table (your schema has created_at)
contrib_df = fetch_df("contributions", "id,member_id,amount,kind,created_at,updated_at", member_col="member_id",
                      order_col="created_at", date_col="created_at")
contrib_df = apply_search(contrib_df, ["kind"])
contrib_df = apply_record_id_filter(contrib_df)

# Foundation payments (your schema has date_paid)
found_df = fetch_df(
    "foundation_payments",
    "id,member_id,amount_paid,amount_pending,status,date_paid,notes,updated_at,converted_to_loan,converted_loan_id",
    member_col="member_id",
    order_col="date_paid",
    date_col="date_paid",
)
found_df = apply_search(found_df, ["status", "notes"])
found_df = apply_record_id_filter(found_df)

# Fines (your schema has created_at)
fines_df = fetch_df("fines", "id,member_id,amount,reason,status,paid_at,created_at,updated_at", member_col="member_id",
                    order_col="created_at", date_col="created_at")
fines_df = apply_search(fines_df, ["reason", "status"])
if show_only_unpaid and "status" in fines_df.columns:
    fines_df = fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]
fines_df = apply_record_id_filter(fines_df)

# Loans (BEST EFFORT FIX)
loans_df = fetch_loans_best_effort()
loans_df = apply_search(loans_df, ["status", "notes", "type", "_matched_on"])
loans_df = apply_record_id_filter(loans_df)

# ----------------------------
# KPIs
# ----------------------------
def safe_sum(df, col):
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

total_contrib = safe_sum(contrib_df, "amount")
total_found_paid = safe_sum(found_df, "amount_paid")

unpaid_fines_amt = 0.0
if not fines_df.empty and "status" in fines_df.columns and "amount" in fines_df.columns:
    unpaid_fines_amt = float(
        pd.to_numeric(
            fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"],
            errors="coerce"
        ).fillna(0).sum()
    )

# Loan principal: try common names
loan_principal = 0.0
for possible in ["principal", "amount", "loan_amount"]:
    if not loans_df.empty and possible in loans_df.columns:
        loan_principal = safe_sum(loans_df, possible)
        break

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

st.write("")
st.markdown(f"<div class='small-muted'>Currently viewing: <b>member_id = {effective_member_id}</b></div>", unsafe_allow_html=True)

k1, k2, k3, k4, k5 = st.columns(5)
k1.markdown(f"<div class='kpi'><div class='label'>Total Contributions</div><div class='value'>{total_contrib:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k2.markdown(f"<div class='kpi'><div class='label'>Total Foundation Paid</div><div class='value'>{total_found_paid:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k3.markdown(f"<div class='kpi'><div class='label'>Unpaid Fines</div><div class='value'>{unpaid_fines_amt:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k4.markdown(f"<div class='kpi'><div class='label'>Active Loans</div><div class='value'>{active_loans}</div><div class='accent'></div></div>", unsafe_allow_html=True)
k5.markdown(f"<div class='kpi'><div class='label'>Loan Total (best)</div><div class='value'>{loan_principal:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# ----------------------------
# TABLES
# ----------------------------
tabs = st.tabs(["Contributions", "Foundation Payments", "Fines", "Loans", "My Profile"])

with tabs[0]:
    st.subheader("Contributions")
    st.dataframe(contrib_df, use_container_width=True)

with tabs[1]:
    st.subheader("Foundation Payments")
    st.dataframe(found_df, use_container_width=True)

with tabs[2]:
    st.subheader("Fines")
    st.dataframe(fines_df, use_container_width=True)

with tabs[3]:
    st.subheader("Loans")
    if loans_df.empty:
        st.warning(
            "No loans returned for this member. This usually means ONE of these is true:\n"
            "1) loans table uses a different member column name not tried here, OR\n"
            "2) RLS is blocking admin from reading loans for other members.\n\n"
            "If you want, I can give you the exact RLS SQL for admin read (safe)."
        )
    else:
        if "_matched_on" in loans_df.columns:
            st.caption(f"Loans matched using column: {loans_df['_matched_on'].iloc[0]}")
        st.dataframe(loans_df, use_container_width=True)

with tabs[4]:
    st.subheader("My Profile")
    st.json(my_member)

# ----------------------------
# ADMIN NOTE
# ----------------------------
if is_admin:
    st.info(
        "Admin detected. You can type a Member ID to view that member’s records. "
        "If loans still don’t show for some members, it’s almost always an RLS policy or a different loans schema."
    )
else:
    st.caption("You can only view your own data.")
