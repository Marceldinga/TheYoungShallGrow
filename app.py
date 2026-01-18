import os, json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone
from postgrest.exceptions import APIError

# ================= PAGE =================
st.set_page_config(page_title="The Young Shall Grow — Njangi Dashboard (Legacy)", layout="wide")

# ================= STYLE =================
CUSTOM_CSS = """
<style>
.block-container { max-width: 1300px; padding-top: 1.2rem; }

.nj-header {
  padding: 18px;
  border-radius: 10px;
  background: linear-gradient(90deg, #4f46e5, #10b981, #f59e0b);
  color: white;
  font-size: 26px;
  font-weight: 800;
}

.kpi-card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  min-height: 100px;
}

.kpi-label { font-size: 13px; color: #6b7280; }
.kpi-value { font-size: 24px; font-weight: 800; margin-top: 6px; }
.kpi-hint { font-size: 11px; color: #9ca3af; margin-top: 6px; }

.k-blue { border-left: 5px solid #4f46e5; }
.k-green { border-left: 5px solid #10b981; }
.k-cyan { border-left: 5px solid #06b6d4; }
.k-amber { border-left: 5px solid #f59e0b; }
.k-rose { border-left: 5px solid #f43f5e; }
.k-slate { border-left: 5px solid #64748b; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ================= HEADER =================
st.markdown('<div class="nj-header">The Young Shall Grow — Njangi Dashboard (Legacy)</div>', unsafe_allow_html=True)
st.caption("Admin manages data • Members can only request loans")

# ================= SUPABASE =================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def now():
    return datetime.now(timezone.utc).isoformat()

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if "session" in st.session_state:
        c.auth.set_session(
            st.session_state.session.access_token,
            st.session_state.session.refresh_token
        )
    return c

# ================= AUTH =================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Account")

    if not st.session_state.session:
        tab = st.radio("Choose", ["Login", "Sign up"], horizontal=True)

        if tab == "Login":
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Login", use_container_width=True):
                try:
                    res = sb.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.session = res.session
                    st.rerun()
                except Exception as e:
                    st.error("Login failed")

        else:
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Create account", use_container_width=True):
                try:
                    sb.auth.sign_up({"email": email, "password": password})
                    st.success("Account created. Now login.")
                except:
                    st.error("Signup failed")

    else:
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

if not st.session_state.session:
    st.stop()

client = authed_client()
user = client.auth.get_user()
user_id = user.user.id
user_email = user.user.email

# ================= PROFILE =================
profile = client.table("profiles").select("*").eq("id", user_id).single().execute().data
is_admin = profile and profile["role"] == "admin"
member_id = profile["member_id"]

# ================= KPIs =================
def kpi(cls, label, value, hint):
    st.markdown(f"""
    <div class="kpi-card {cls}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-hint">{hint}</div>
    </div>
    """, unsafe_allow_html=True)

def sum_table(table, field):
    rows = client.table(table).select(field).limit(10000).execute().data or []
    return sum(float(r[field]) for r in rows if r[field])

pot = sum(r["amount"] for r in client.table("contributions_legacy").select("amount,kind").execute().data if r["kind"]=="contribution")
total_contrib = sum_table("contributions_legacy", "amount")

f_rows = client.table("foundation_payments_legacy").select("amount_paid,amount_pending").execute().data
foundation_total = sum(r["amount_paid"]+r["amount_pending"] for r in f_rows)

loan_rows = client.table("loans_legacy").select("total_interest_generated,status").execute().data
interest_total = sum(r["total_interest_generated"] for r in loan_rows)
active_loans = len([r for r in loan_rows if r["status"]=="active"])

c1,c2,c3 = st.columns(3)
with c1: kpi("k-blue","Contribution Pot", f"{pot:,.0f}", "Ready for payout")
with c2: kpi("k-green","All-time Contributions", f"{total_contrib:,.0f}", "Total collected")
with c3: kpi("k-cyan","Foundation Total", f"{foundation_total:,.0f}", "Paid + Pending")

c4,c5,c6 = st.columns(3)
with c4: kpi("k-amber","Interest Generated", f"{interest_total:,.0f}", "All loans")
with c5: kpi("k-rose","Active Loans", active_loans, "Currently running")
with c6: kpi("k-slate","Your Member ID", member_id, "Profile linked")

st.divider()

# ================= MEMBER PORTAL =================
if not is_admin:
    st.subheader("Member Loan Request")

    surety = st.number_input("Surety Member ID", min_value=1, step=1)
    amount = st.number_input("Loan Amount", min_value=500, step=500)

    if st.button("Submit Loan Request", use_container_width=True):
        payload = {
            "requester_user_id": user_id,
            "borrower_member_id": member_id,
            "surety_member_id": int(surety),
            "principal": float(amount),
            "status": "pending",
            "created_at": now()
        }
        client.table("loan_requests_legacy").insert(payload).execute()
        st.success("Loan request submitted")

# ================= ADMIN DASHBOARD =================
else:
    st.subheader("Admin Dashboard")

    tab1,tab2,tab3 = st.tabs(["Members","Loan Requests","Insert Contribution"])

    with tab1:
        df = client.table("profiles").select("email,role,member_id").execute().data
        st.dataframe(pd.DataFrame(df), use_container_width=True)

    with tab2:
        reqs = client.table("loan_requests_legacy").select("*").execute().data
        df = pd.DataFrame(reqs)
        st.dataframe(df, use_container_width=True)

    with tab3:
        mid = st.number_input("Member ID", min_value=1, step=1)
        amt = st.number_input("Amount", min_value=500, step=500)
        if st.button("Insert Contribution"):
            client.table("contributions_legacy").insert({
                "member_id": int(mid),
                "amount": int(amt),
                "kind": "contribution",
                "created_at": now()
            }).execute()
            st.success("Contribution added")
