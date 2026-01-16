
import os
import streamlit as st
import pandas as pd
from supabase import create_client

# =================== CONFIG ===================
st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# =================== HELPERS ===================
def df(resp):
    return pd.DataFrame(resp.data or [])

def get_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

# =================== LOGIN ===================
st.title("Njangi Admin Dashboard")

if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Admin Login")

    if st.session_state.session is None:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True):
            try:
                res = sb.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.session = res.session
                st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        st.success("Logged in")
        if st.button("Logout", use_container_width=True):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = get_client()

# =================== TABS ===================
tabs = st.tabs([
    "Members",
    "Current Season",
    "Rotation",
    "Contributions",
    "Foundation",
])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("All Njangi Members")

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

    try:
        season = client.table("current_season_view").select("*").limit(1).execute()

        if not season.data:
            st.warning("No active season found.")
        else:
            row = season.data[0]

            st.success("Active Season Loaded")

            st.markdown(f"""
            ### Season Info
            - **Season ID:** `{row['season_id']}`
            - **Start Date:** {row['season_start']}
            - **Status:** {row['season_status']}

            ### Next Payout
            - **Next Payout Date:** {row['next_payout_date']}
            - **Next Member ID:** {row['legacy_member_id']}
            - **Next Beneficiary:** {row['next_beneficiary']}
            """)

    except Exception as e:
        st.error("Failed to load season data. Check RLS or permissions.")
        st.stop()

# ===================== ROTATION =====================
with tabs[2]:
    st.subheader("Rotation State")

    state = client.table("app_state").select("*").execute()
    st.dataframe(df(state), use_container_width=True)

    st.markdown("### Advance Rotation (Bi-Weekly)")

    if st.button("Advance to Next Beneficiary"):
        try:
            client.rpc("advance_rotation").execute()
            st.success("Rotation advanced successfully")
            st.rerun()
        except Exception as e:
            st.error(str(e))

# ===================== CONTRIBUTIONS =====================
with tabs[3]:
    st.subheader("Contributions")

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
