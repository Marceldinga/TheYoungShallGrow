import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone
from postgrest.exceptions import APIError

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="The Young Shall Grow — Njangi Dashboard (Legacy)",
    layout="wide"
)

# ============================================================
# STYLE
# ============================================================
st.markdown("""
<style>
.block-container { max-width: 1250px; padding-top: 1.5rem; }

.nj-header {
  padding: 18px 22px;
  border-radius: 18px;
  background: linear-gradient(90deg, #6366f1, #10b981, #f59e0b);
  color: white;
  margin-bottom: 25px;
}

.nj-title { font-size: 28px; font-weight: 800; margin: 0; }
.nj-sub { font-size: 14px; opacity: 0.95; margin-top: 6px; }

.card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.stButton>button {
  border-radius: 12px;
  font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER (ONLY ONE)
# ============================================================
st.markdown("""
<div class="nj-header">
  <div class="nj-title">The Young Shall Grow — Njangi Dashboard (Legacy)</div>
  <div class="nj-sub">Admin manages data • Members can only request loans • Clean, colorful view</div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# SUPABASE CONNECTION
# ============================================================
def get_secret(key):
    try:
        return st.secrets.get(key)
    except:
        return os.getenv(key)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing Supabase credentials.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if "session" in st.session_state and st.session_state.session:
        sess = st.session_state.session
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ============================================================
# AUTH
# ============================================================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Account")

    if st.session_state.session is None:
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
                    st.success("Account created. Please login.")
                except Exception as e:
                    st.error("Signup failed")

    else:
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = authed_client()
user = client.auth.get_user()
user_id = user.user.id
email = user.user.email

# ============================================================
# PROFILE & ROLE
# ============================================================
def get_profile():
    try:
        return client.table("profiles").select("*").eq("id", user_id).single().execute().data
    except:
        return None

profile = get_profile()

if not profile:
    st.warning("Complete your profile to continue")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    name = st.text_input("Full name")
    phone = st.text_input("Phone")
    member_id = st.number_input("Your legacy member ID", min_value=1, step=1)

    if st.button("Save Profile", use_container_width=True):
        payload = {
            "id": user_id,
            "email": email,
            "role": "member",
            "member_id": int(member_id),
            "full_name": name,
            "phone": phone,
            "created_at": now_iso(),
            "updated_at": now_iso()
        }
        client.table("profiles").insert(payload).execute()
        st.success("Profile saved. Reloading...")
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

is_admin = profile.get("role") == "admin"
my_member_id = int(profile.get("member_id"))
my_name = profile.get("full_name")

# ============================================================
# MEMBER PORTAL
# ============================================================
if not is_admin:
    st.subheader("Member Portal — Loan Request")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write(f"Welcome **{my_name}** (Member ID: {my_member_id})")

    surety_id = st.number_input("Surety Member ID", min_value=1, step=1)
    amount = st.number_input("Loan Amount", min_value=500, step=500)

    if st.button("Submit Loan Request", use_container_width=True):
        payload = {
            "requester_user_id": user_id,
            "borrower_member_id": my_member_id,
            "borrower_name": my_name,
            "surety_member_id": int(surety_id),
            "principal": float(amount),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso()
        }
        client.table("loan_requests_legacy").insert(payload).execute()
        st.success("Loan request submitted. Admin will review.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("My Loan Requests")
    reqs = client.table("loan_requests_legacy") \
        .select("*") \
        .eq("requester_user_id", user_id) \
        .order("created_at", desc=True).execute().data

    st.dataframe(pd.DataFrame(reqs), use_container_width=True)

# ============================================================
# ADMIN DASHBOARD
# ============================================================
else:
    st.subheader("Admin Dashboard")

    tabs = st.tabs(["Members", "Loan Requests", "Loans", "Contributions", "Foundation"])

    # ---------------- Members ----------------
    with tabs[0]:
        df = client.table("member_registry").select("*").order("legacy_member_id").execute().data
        st.dataframe(pd.DataFrame(df), use_container_width=True)

    # ---------------- Loan Requests ----------------
    with tabs[1]:
        df = client.table("loan_requests_legacy").select("*").order("created_at", desc=True).execute().data
        df = pd.DataFrame(df)
        st.dataframe(df, use_container_width=True)

        if not df.empty:
            pick = st.selectbox("Pick Request ID", df["id"])
            row = df[df["id"] == pick].iloc[0]

            if st.button("Approve Request"):
                principal = float(row["principal"])
                interest = principal * 0.05
                total_due = principal + interest

                loan_payload = {
                    "borrower_member_id": int(row["borrower_member_id"]),
                    "surety_member_id": int(row["surety_member_id"]),
                    "borrower_name": row["borrower_name"],
                    "principal": principal,
                    "interest": interest,
                    "total_due": total_due,
                    "status": "active",
                    "created_at": now_iso()
                }

                client.table("loans_legacy").insert(loan_payload).execute()
                client.table("loan_requests_legacy").update({"status": "approved"}).eq("id", int(pick)).execute()

                st.success("Loan approved and created.")
                st.rerun()

    # ---------------- Loans ----------------
    with tabs[2]:
        df = client.table("loans_legacy").select("*").order("created_at", desc=True).execute().data
        st.dataframe(pd.DataFrame(df), use_container_width=True)

    # ---------------- Contributions ----------------
    with tabs[3]:
        df = client.table("contributions_legacy").select("*").order("created_at", desc=True).execute().data
        st.dataframe(pd.DataFrame(df), use_container_width=True)

    # ---------------- Foundation ----------------
    with tabs[4]:
        df = client.table("foundation_payments_legacy").select("*").order("created_at", desc=True).execute().data
        st.dataframe(pd.DataFrame(df), use_container_width=True)
