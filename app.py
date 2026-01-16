
import streamlit as st
import pandas as pd
from supabase import create_client
from postgrest.exceptions import APIError

st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")

# ------------------- Secrets -------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ------------------- Helpers -------------------
def to_df(resp):
    return pd.DataFrame(resp.data or [])

def show_api_error(e: Exception, where: str):
    st.error(f"❌ Supabase error at: {where}")
    if isinstance(e, APIError):
        # APIError usually has dict payload inside .args[0]
        try:
            payload = e.args[0] if e.args else {}
            st.code(str(payload), language="json")
        except Exception:
            st.code(str(e))
    else:
        st.code(str(e))

def auth_client():
    """Client with the logged-in user's JWT so RLS applies correctly."""
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

# ------------------- Login -------------------
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
                show_api_error(e, "Login")
    else:
        u = st.session_state.session.user
        st.success(f"Logged in: {u.email}")
        if st.button("Logout", use_container_width=True):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = auth_client()

# Optional: display auth uid
try:
    st.caption(f"auth.uid(): {st.session_state.session.user.id}")
except Exception:
    pass

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
    st.subheader("All Njangi Members (member_registry)")

    try:
        members = (
            client.table("member_registry")
            .select("*")
            .order("legacy_member_id")
            .execute()
        )
        st.dataframe(to_df(members), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Select member_registry")

    st.markdown("### Activate / Deactivate Member")

    col1, col2 = st.columns(2)
    with col1:
        mid = st.number_input("Legacy Member ID (1–17)", min_value=1, max_value=17, step=1)
    with col2:
        active = st.selectbox("Set Active", [True, False], index=0)

    if st.button("Update Member", use_container_width=True):
        try:
            client.table("member_registry") \
                .update({"is_active": bool(active)}) \
                .eq("legacy_member_id", int(mid)) \
                .execute()
            st.success("✅ Member updated")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Update member_registry (is_active)")

# ===================== CURRENT SEASON =====================
with tabs[1]:
    st.subheader("Current Season (from current_season_view)")

    # IMPORTANT: do NOT use rpc('sql'). Just select from the view.
    try:
        season = client.table("current_season_view").select("*").execute()
        df_season = to_df(season)
        st.dataframe(df_season, use_container_width=True)

        if df_season.empty:
            st.warning("current_season_view returned 0 rows. That means no active season OR RLS blocked it.")
    except Exception as e:
        show_api_error(e, "Select current_season_view")

# ===================== ROTATION =====================
with tabs[2]:
    st.subheader("Rotation State (app_state)")

    try:
        state = client.table("app_state").select("*").execute()
        st.dataframe(to_df(state), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Select app_state")

    st.markdown("### Advance Rotation (Bi-Weekly)")

    if st.button("Advance to Next Beneficiary", use_container_width=True):
        try:
            # requires RPC function exists: advance_rotation()
            client.rpc("advance_rotation").execute()
            st.success("✅ Rotation advanced")
            st.rerun()
        except Exception as e:
            show_api_error(e, "RPC advance_rotation")

# ===================== CONTRIBUTIONS =====================
with tabs[3]:
    st.subheader("Contributions (contributions_legacy)")

    try:
        contribs = (
            client.table("contributions_legacy")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        st.dataframe(to_df(contribs), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Select contributions_legacy")

# ===================== FOUNDATION =====================
with tabs[4]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        foundation = (
            client.table("foundation_payments_legacy")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        st.dataframe(to_df(foundation), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Select foundation_payments_legacy")
