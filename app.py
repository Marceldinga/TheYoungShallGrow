import pandas as pd
import streamlit as st
from supabase import create_client

# ============================================================
# UPDATED SECURE DASHBOARD (Single Script)
# ✅ Member sees ONLY their own data (email -> members.id)
# ✅ Loans FIX: loans table uses borrower_member_id (NOT member_id)
# ✅ Admin can optionally switch member_id (requires admin RLS)
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
st.button("Logout", on_click=logout)

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

st.markdown(f"<div class='small-muted'>Currently viewing: <b>member_id = {effective_member_id}</b></div>", unsafe_allow_html=True)

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

# ----------------------------
# LOAD DATA
# ----------------------------
# contributions: member_id ✅
contrib_df = fetch_df("contributions", "id,member_id,amount,kind,created_at,updated_at",
                      member_col="member_id", order_col="created_at", date_col="created_at")
contrib_df = apply_search(contrib_df, ["kind"])
contrib_df = apply_record_id_filter(contrib_df)

# foundation_payments: member_id ✅
found_df = fetch_df(
    "foundation_payments",
    "id,member_id,amount_paid,amount_pending,status,date_paid,notes,updated_at,converted_to_loan,converted_loan_id",
    member_col="member_id", order_col="date_paid", date_col="date_paid"
)
found_df = apply_search(found_df, ["status", "notes"])
found_df = apply_record_id_filter(found_df)

# fines: member_id ✅
fines_df = fetch_df("fines", "id,member_id,amount,reason,status,paid_at,created_at,updated_at",
                    member_col="member_id", order_col="created_at", date_col="created_at")
fines_df = apply_search(fines_df, ["reason", "status"])
if show_only_unpaid and "status" in fines_df.columns:
    fines_df = fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]
fines_df = apply_record_id_filter(fines_df)

# ✅ loans: borrower_member_id (FIX)
loans_df = fetch_df("loans", "*",
                    member_col="borrower_member_id", order_col="created_at", date_col="created_at")
loans_df = apply_search(loans_df, ["status"])
loans_df = apply_record_id_filter(loans_df)

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
            errors="coerce"
        ).fillna(0).sum()
    )

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

loan_total = 0.0
for col in ["principal", "total_due", "balance"]:
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
        st.info("No loans found for this member.")
    else:
        st.dataframe(loans_df, use_container_width=True)

with tabs[4]:
    st.subheader("My Profile")
    st.json(my_member)

# ----------------------------
# SECURITY NOTE
# ----------------------------
if not is_admin:
    st.caption("Security: you can only view your own data (by email → member_id).")
else:
    st.info("Admin: You can switch Member ID (works only if admin RLS policies allow cross-member access).")
