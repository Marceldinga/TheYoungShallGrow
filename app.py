import pandas as pd
import streamlit as st
from supabase import create_client

# ----------------------------
# SETTINGS
# ----------------------------
st.set_page_config(page_title="The Young Shall Grow – Member Dashboard", page_icon="🌱", layout="wide")
st.set_option("client.showErrorDetails", False)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
ADMIN_EMAILS = [e.strip().lower() for e in str(st.secrets.get("ADMIN_EMAILS", "")).split(",") if e.strip()]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ----------------------------
# UI STYLE
# ----------------------------
st.markdown("""
<style>
.block-container{max-width:1150px;padding-top:1.2rem;padding-bottom:2rem;}
.kpi{border:1px solid rgba(120,120,120,.25);border-radius:14px;padding:14px;background:rgba(255,255,255,.04)}
.muted{opacity:.7}
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
    # This is the KEY step for RLS. All queries now run as this user.
    supabase.postgrest.auth(access_token)

# ----------------------------
# LOGIN SCREEN
# ----------------------------
if not is_logged_in():
    st.title("🌱 Member Login")

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", placeholder="you@example.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            access_token = res.session.access_token
            refresh_token = res.session.refresh_token

            st.session_state["access_token"] = access_token
            st.session_state["refresh_token"] = refresh_token
            st.session_state["user_email"] = (res.user.email or "").lower()

            attach_jwt(access_token)

            st.success("Login successful.")
            st.rerun()
        except Exception:
            st.error("Login failed. Check email/password or confirm the user exists in Supabase Auth.")
    st.stop()

# If page refresh happened, re-attach JWT for RLS
attach_jwt(st.session_state["access_token"])

# ----------------------------
# DASHBOARD (LOGGED IN)
# ----------------------------
user_email = st.session_state.get("user_email", "").lower()
is_admin = user_email in ADMIN_EMAILS

top = st.columns([3, 1])
with top[0]:
    st.title("📊 Member Dashboard")
    st.write(f"Signed in as **{user_email}**" + (" (admin)" if is_admin else ""))
with top[1]:
    st.button("Logout", on_click=logout)

# ----------------------------
# LOAD MY PROFILE (RLS restricts to own row)
# ----------------------------
try:
    rows = supabase.table("members").select("*").limit(1).execute().data
    my_member = rows[0] if rows else None
except Exception:
    my_member = None

if not my_member:
    st.warning("No member profile found. Ensure public.members.email matches the Auth email exactly.")
    st.stop()

# ----------------------------
# FILTERS
# ----------------------------
st.subheader("My Overview")
c1, c2, c3, c4 = st.columns(4)

range_opt = st.selectbox("Time range", ["All time", "Last 30 days", "Last 90 days", "This year"], index=0)

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

def fetch_df(table: str, cols="*", order_col=None) -> pd.DataFrame:
    q = supabase.table(table).select(cols)
    if order_col:
        q = q.order(order_col, desc=True)
    data = q.execute().data
    return pd.DataFrame(data or [])

# ----------------------------
# FETCH TABLES (RLS handles "my data")
# ----------------------------
contrib_df = fetch_df("contributions", "id,member_id,amount,kind,created_at,updated_at", order_col="created_at")
contrib_df = apply_date_filter(contrib_df, "created_at")

found_df = fetch_df(
    "foundation_payments",
    "id,member_id,amount_paid,amount_pending,status,date_paid,notes,updated_at,converted_to_loan,converted_loan_id",
    order_col="date_paid"
)
found_df = apply_date_filter(found_df, "date_paid")

fines_df = fetch_df("fines", "id,member_id,amount,reason,status,paid_at,created_at,updated_at", order_col="created_at")
fines_df = apply_date_filter(fines_df, "created_at")

# Loans table is optional (only show if exists)
loans_df = pd.DataFrame()
try:
    loans_df = fetch_df("loans", "*", order_col="created_at")
    if not loans_df.empty and "created_at" in loans_df.columns:
        loans_df = apply_date_filter(loans_df, "created_at")
except Exception:
    loans_df = pd.DataFrame()

# ----------------------------
# KPIs
# ----------------------------
total_contrib = float(contrib_df["amount"].sum()) if "amount" in contrib_df.columns and not contrib_df.empty else 0.0
total_found_paid = float(found_df["amount_paid"].sum()) if "amount_paid" in found_df.columns and not found_df.empty else 0.0

unpaid_fines = 0.0
if not fines_df.empty and "status" in fines_df.columns and "amount" in fines_df.columns:
    unpaid_fines = float(fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"].sum())

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())

c1.markdown(f"<div class='kpi'><div class='muted'>Total Contributions</div><h2>{total_contrib:,.2f}</h2></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='kpi'><div class='muted'>Total Foundation Paid</div><h2>{total_found_paid:,.2f}</h2></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='kpi'><div class='muted'>Unpaid Fines</div><h2>{unpaid_fines:,.2f}</h2></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='kpi'><div class='muted'>Active Loans</div><h2>{active_loans}</h2></div>", unsafe_allow_html=True)

st.divider()

# ----------------------------
# TABLES
# ----------------------------
tabs = st.tabs(["Contributions", "Foundation Payments", "Fines", "Loans", "My Profile"])

with tabs[0]:
    st.subheader("My Contributions")
    st.dataframe(contrib_df, use_container_width=True)

with tabs[1]:
    st.subheader("My Foundation Payments")
    st.dataframe(found_df, use_container_width=True)

with tabs[2]:
    st.subheader("My Fines")
    st.dataframe(fines_df, use_container_width=True)

with tabs[3]:
    st.subheader("My Loans")
    if loans_df.empty:
        st.info("Loans table not found or no loans available for this user.")
    else:
        st.dataframe(loans_df, use_container_width=True)

with tabs[4]:
    st.subheader("My Profile")
    st.write(my_member)

if is_admin:
    st.info("Admin detected. If you want an Admin view of all members, we can add admin-only RLS policies (still without service key).")
