
import os
import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")

# ------------------- Secrets -------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ------------------- Helpers -------------------
def df(resp):
    return pd.DataFrame(resp.data or [])

# ------------------- Login -------------------
st.title("Njangi Admin Dashboard")

if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Admin Login")

    if st.session_state.session is None:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            res = sb.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.session = res.session
            st.rerun()
    else:
        st.success("Logged in")
        if st.button("Logout"):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

# ------------------- Client with RLS -------------------
client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
client.auth.set_session(
    st.session_state.session.access_token,
    st.session_state.session.refresh_token,
)

# ------------------- Tabs -------------------
tabs = st.tabs([
    "Members",
    "Current Season",
    "Rotation",
    "Contributions",
    "Foundation",
])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("All Njangi Members (Legacy Registry)")

    members = client.table("member_registry") \
        .select("*") \
        .order("legacy_member_id") \
        .execute()

    st.dataframe(df(members), use_container_width=True)

    st.markdown("### Activate / Deactivate Member")

    col1, col2 = st.columns(2)
    with col1:
        mid = st.number_input("Legacy Member ID (1–17)", min_value=1, max_value=17, step=1)
    with col2:
        active = st.selectbox("Set Active", [True, False])

    if st.button("Update Member"):
        client.table("member_registry") \
            .update({"is_active": active}) \
            .eq("legacy_member_id", int(mid)) \
            .execute()
        st.success("Member updated")
        st.rerun()

# ===================== CURRENT SEASON =====================
with tabs[1]:
    st.subheader("Current Season")

    season = client.rpc("sql", {
        "query": """
        select
            s.id as season_id,
            s.start_date,
            s.end_date,
            s.status,
            a.next_payout_index,
            m.full_name as next_beneficiary
        from public.sessions_legacy s
        cross join public.app_state a
        join public.member_registry m
          on m.legacy_member_id = a.next_payout_index
        where s.status = 'active'
        limit 1;
        """
    }).execute()

    st.dataframe(df(season), use_container_width=True)

# ===================== ROTATION =====================
with tabs[2]:
    st.subheader("Rotation State")

    state = client.table("app_state").select("*").execute()
    st.dataframe(df(state), use_container_width=True)

    st.markdown("### Advance Rotation (Bi-Weekly)")

    if st.button("Advance to Next Beneficiary"):
        client.rpc("advance_rotation").execute()
        st.success("Rotation advanced")
        st.rerun()

# ===================== CONTRIBUTIONS =====================
with tabs[3]:
    st.subheader("Contributions (Current Season)")

    contribs = client.table("contributions_legacy") \
        .select("*") \
        .order("created_at", desc=True) \
        .execute()

    st.dataframe(df(contribs), use_container_width=True)

# ===================== FOUNDATION =====================
with tabs[4]:
    st.subheader("Foundation Payments")

    foundation = client.table("foundation_payments_legacy") \
        .select("*") \
        .order("created_at", desc=True) \
        .execute()

    st.dataframe(df(foundation), use_container_width=True)
