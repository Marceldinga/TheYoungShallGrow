
import os
import streamlit as st
import pandas as pd
from supabase import create_client


# -------------------- Page --------------------
st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")
st.title("Njangi Admin Dashboard")


# -------------------- Secrets --------------------
def get_secret(key: str) -> str | None:
    try:
        return st.secrets.get(key)
    except Exception:
        return os.getenv(key)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_ANON_KEY in Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# -------------------- Helpers --------------------
def to_df(resp):
    return pd.DataFrame(resp.data or [])


def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c


def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    st.code(str(e))


def safe_select_table(c, table: str, order_col: str | None = None, desc: bool = True, limit: int = 500):
    q = c.table(table).select("*")
    if order_col:
        q = q.order(order_col, desc=desc)
    if limit:
        q = q.limit(limit)
    return q.execute()


# -------------------- Login --------------------
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
                show_api_error(e, "Login failed")
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

client = authed_client()
auth_uid = st.session_state.session.user.id
st.caption(f"auth.uid(): {auth_uid}")


# -------------------- Optional Admin Check --------------------
# If your RLS allows reading profiles for the logged-in user, this will work.
# If not, the app still runs, but shows a warning.
is_admin = False
try:
    prof = client.table("profiles").select("id,role,approved").eq("id", auth_uid).single().execute().data
    if prof and prof.get("approved") is False:
        st.error("Your account is not approved yet (profiles.approved = false).")
        st.stop()
    is_admin = bool(prof and prof.get("role") == "admin")
    if not is_admin:
        st.warning("Your role is not admin (profiles.role != 'admin'). Some actions may fail by RLS.")
except Exception:
    st.warning("Could not read profiles (RLS). Continuing without role check.")


# -------------------- Tabs --------------------
tabs = st.tabs(["Members", "Current Season", "Rotation", "Contributions", "Foundation"])


# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("All Njangi Members (member_registry)")

    try:
        members = client.table("member_registry").select("*").order("legacy_member_id").execute()
        st.dataframe(to_df(members), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load member_registry")

    st.markdown("### Activate / Deactivate Member")
    col1, col2 = st.columns(2)
    with col1:
        legacy_id = st.number_input("Legacy Member ID (1–17)", min_value=1, max_value=17, step=1, value=1)
    with col2:
        is_active = st.selectbox("Set Active", [True, False], index=0)

    if st.button("Update Member", use_container_width=True):
        try:
            client.table("member_registry").update({"is_active": bool(is_active)}).eq(
                "legacy_member_id", int(legacy_id)
            ).execute()
            st.success("Member updated.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Update failed (RLS or column mismatch)")


# ===================== CURRENT SEASON =====================
with tabs[1]:
    st.subheader("Current Season (current_season_view)")

    # You already tested: select * from public.current_season_view;
    # So we read that view directly (no rpc sql).
    try:
        season = client.table("current_season_view").select("*").limit(10).execute()
        df_season = to_df(season)
        if df_season.empty:
            st.warning("current_season_view returned no rows. Make sure one season is active.")
        st.dataframe(df_season, use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not read current_season_view (RLS or view permissions)")


# ===================== ROTATION =====================
with tabs[2]:
    st.subheader("Rotation State (app_state)")

    try:
        state = client.table("app_state").select("*").execute()
        st.dataframe(to_df(state), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not read app_state")
        st.stop()

    st.markdown("### Set next beneficiary index (manual)")
    st.caption("Use this to set it back to **2** (or any 1–17).")

    col1, col2 = st.columns(2)
    with col1:
        new_index = st.number_input("next_payout_index", min_value=1, max_value=17, step=1, value=2)
    with col2:
        rotation_start_date = st.date_input("rotation_start_date (optional)")

    if st.button("Save Rotation State", use_container_width=True):
        try:
            payload = {"next_payout_index": int(new_index)}
            # Only update rotation_start_date if your table has that column
            # If it doesn't exist, Supabase will error and we show it.
            payload["rotation_start_date"] = str(rotation_start_date)

            client.table("app_state").update(payload).eq("id", 1).execute()
            st.success("Rotation updated.")
            st.rerun()
        except Exception as e:
            # Try again without rotation_start_date (in case column doesn't exist)
            try:
                client.table("app_state").update({"next_payout_index": int(new_index)}).eq("id", 1).execute()
                st.success("Rotation updated (next_payout_index only).")
                st.rerun()
            except Exception as e2:
                show_api_error(e2, "Rotation update failed (RLS or column mismatch)")

    st.markdown("### Advance to next beneficiary (manual)")
    st.caption("This replaces the missing RPC. It increments 1→17 then wraps back to 1.")
    if st.button("Advance to Next Beneficiary", use_container_width=True):
        try:
            row = client.table("app_state").select("next_payout_index").eq("id", 1).single().execute().data
            cur = int(row["next_payout_index"])
            nxt = cur + 1 if cur < 17 else 1
            client.table("app_state").update({"next_payout_index": nxt}).eq("id", 1).execute()
            st.success(f"Advanced from {cur} → {nxt}")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Advance failed (RLS?)")


# ===================== CONTRIBUTIONS =====================
with tabs[3]:
    st.subheader("Contributions (contributions_legacy)")

    try:
        contribs = safe_select_table(client, "contributions_legacy", order_col="created_at", desc=True, limit=500)
        st.dataframe(to_df(contribs), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy (RLS or table name mismatch)")


# ===================== FOUNDATION =====================
with tabs[4]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        # Your screenshot confirms this table exists and returns rows.
        foundation = safe_select_table(client, "foundation_payments_legacy", order_col="id", desc=True, limit=500)
        st.dataframe(to_df(foundation), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy (RLS or permissions)")
        st.info("If SQL works but Streamlit fails: add a SELECT policy for authenticated users on foundation_payments_legacy.")
