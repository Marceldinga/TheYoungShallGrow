import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client

# -------------------- Page --------------------
st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")
st.title("Njangi Admin Dashboard (Admin CRUD)")

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

def require_admin(client, auth_uid: str) -> bool:
    # Your profiles schema: id, role, created_at, member_id, approved, updated_at
    try:
        prof = client.table("profiles").select("id,role,approved").eq("id", auth_uid).single().execute().data
        if not prof:
            st.error("No profiles row found for your auth user. (RLS might block it.)")
            return False
        if prof.get("approved") is False:
            st.error("Your account is not approved (profiles.approved = false).")
            return False
        if prof.get("role") != "admin":
            st.warning("You are not admin (profiles.role != 'admin'). Inserts/updates may fail by RLS.")
            return False
        return True
    except Exception:
        st.warning("Could not read profiles (RLS). Continuing, but inserts/updates may fail.")
        return False

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

is_admin = require_admin(client, auth_uid)

# -------------------- Tabs --------------------
tabs = st.tabs([
    "Members (member_registry)",
    "Rotation (app_state)",
    "Contributions (legacy)",
    "Foundation (legacy)",
    "Universal Insert/Update (JSON)"
])

# ===================== MEMBERS =====================
with tabs[0]:
    st.subheader("Members Registry (member_registry)")

    try:
        members_resp = client.table("member_registry").select("*").order("legacy_member_id").execute()
        df_members = to_df(members_resp)
        st.dataframe(df_members, use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load member_registry")
        df_members = pd.DataFrame()

    st.divider()
    st.markdown("### Update Member (by legacy_member_id)")

    col1, col2 = st.columns(2)
    with col1:
        legacy_id = st.number_input("legacy_member_id", min_value=1, max_value=1000, step=1, value=1)
    with col2:
        active_val = st.selectbox("is_active", [True, False], index=0)

    full_name_val = st.text_input("full_name (optional)")
    phone_val = st.text_input("phone (optional)")

    if st.button("Save Member Update", use_container_width=True):
        payload = {"is_active": bool(active_val)}
        if full_name_val.strip():
            payload["full_name"] = full_name_val.strip()
        if phone_val.strip():
            payload["phone"] = phone_val.strip()

        try:
            client.table("member_registry").update(payload).eq("legacy_member_id", int(legacy_id)).execute()
            st.success("Member updated.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Update failed (RLS or column mismatch)")

# ===================== ROTATION =====================
with tabs[1]:
    st.subheader("Rotation State (app_state)")

    try:
        state = client.table("app_state").select("*").execute()
        st.dataframe(to_df(state), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not read app_state")
        st.stop()

    st.markdown("### Set next_payout_index (manual)")
    col1, col2 = st.columns(2)
    with col1:
        new_index = st.number_input("next_payout_index", min_value=1, max_value=1000, step=1, value=1)
    with col2:
        next_date = st.date_input("next_payout_date (optional)")

    if st.button("Save Rotation", use_container_width=True):
        payload = {"next_payout_index": int(new_index)}
        # only include if your app_state has this column
        payload["next_payout_date"] = str(next_date)
        try:
            client.table("app_state").update(payload).eq("id", 1).execute()
            st.success("Rotation updated.")
            st.rerun()
        except Exception:
            # retry without next_payout_date
            try:
                client.table("app_state").update({"next_payout_index": int(new_index)}).eq("id", 1).execute()
                st.success("Rotation updated (index only).")
                st.rerun()
            except Exception as e2:
                show_api_error(e2, "Rotation update failed (RLS or column mismatch)")

    st.markdown("### Advance to next beneficiary (manual)")
    if st.button("Advance", use_container_width=True):
        try:
            row = client.table("app_state").select("next_payout_index").eq("id", 1).single().execute().data
            cur = int(row["next_payout_index"])
            nxt = cur + 1 if cur < 17 else 1
            client.table("app_state").update({"next_payout_index": nxt}).eq("id", 1).execute()
            st.success(f"Advanced {cur} → {nxt}")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Advance failed (RLS?)")

# ===================== CONTRIBUTIONS (LEGACY) =====================
with tabs[2]:
    st.subheader("Contributions (contributions_legacy)")

    try:
        contribs = safe_select_table(client, "contributions_legacy", order_col="created_at", desc=True, limit=500)
        df_contrib = to_df(contribs)
        st.dataframe(df_contrib, use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy (RLS or table mismatch)")
        df_contrib = pd.DataFrame()

    st.divider()
    st.markdown("### Insert a Contribution (legacy)")
    st.caption("If this fails, it is RLS. Use the JSON tool tab to match exact columns.")

    # Simple, common fields (adjust if your table differs)
    c1, c2, c3 = st.columns(3)
    with c1:
        contrib_legacy_member_id = st.number_input("legacy_member_id (member_registry)", min_value=1, max_value=1000, step=1, value=1, key="c_leg")
    with c2:
        contrib_amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amt")
    with c3:
        contrib_paid = st.selectbox("paid", [True, False], index=0, key="c_paid")

    contrib_note = st.text_input("note/remark (optional)", key="c_note")

    if st.button("Insert Contribution (legacy)", use_container_width=True):
        payload = {
            # Use legacy_member_id so it matches your registry rotation
            "legacy_member_id": int(contrib_legacy_member_id),
            "amount": float(contrib_amount),
            "paid": bool(contrib_paid),
        }
        if contrib_note.strip():
            payload["note"] = contrib_note.strip()

        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Inserted contribution.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (likely RLS or column mismatch). Try JSON Inserter tab.")

# ===================== FOUNDATION (LEGACY) =====================
with tabs[3]:
    st.subheader("Foundation Payments (foundation_payments_legacy)")

    try:
        foundation = safe_select_table(client, "foundation_payments_legacy", order_col="id", desc=True, limit=500)
        df_found = to_df(foundation)
        st.dataframe(df_found, use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy (RLS or permissions)")
        df_found = pd.DataFrame()

    st.divider()
    st.markdown("### Insert a Foundation Payment (legacy)")
    st.caption("If this fails, it is RLS or column mismatch. Use JSON Inserter tab.")

    f1, f2, f3 = st.columns(3)
    with f1:
        f_legacy_member_id = st.number_input("legacy_member_id", min_value=1, max_value=1000, step=1, value=1, key="f_leg")
    with f2:
        f_amount = st.number_input("amount", min_value=0, step=500, value=500, key="f_amt")
    with f3:
        f_status = st.text_input("status (optional)", value="", key="f_status")

    if st.button("Insert Foundation Payment (legacy)", use_container_width=True):
        payload = {
            "legacy_member_id": int(f_legacy_member_id),
            "amount": float(f_amount),
        }
        if f_status.strip():
            payload["status"] = f_status.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Inserted foundation payment.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (likely RLS or column mismatch). Try JSON Inserter tab.")

# ===================== UNIVERSAL JSON INSERT/UPDATE =====================
with tabs[4]:
    st.subheader("Universal Insert / Update (JSON)")
    st.caption(
        "Use this when table columns are unknown/mismatched. "
        "Paste JSON payload exactly matching your table columns."
    )

    mode = st.radio("Mode", ["INSERT", "UPDATE"], horizontal=True)

    table_name = st.text_input("Table name", value="member_registry")

    if mode == "INSERT":
        st.markdown("#### JSON payload to INSERT")
        example = {"example_col": "value", "another_col": 123}
        payload_text = st.text_area("JSON", value=json.dumps(example, indent=2), height=200)

        if st.button("Run INSERT", use_container_width=True):
            try:
                payload = json.loads(payload_text)
                client.table(table_name).insert(payload).execute()
                st.success("Insert complete.")
            except Exception as e:
                show_api_error(e, "Insert failed")

    else:
        st.markdown("#### JSON payload to UPDATE")
        st.caption("You must provide a filter (column + value) so we update the right rows.")
        filter_col = st.text_input("Filter column (WHERE col = ...)", value="legacy_member_id")
        filter_val = st.text_input("Filter value", value="1")

        payload_text = st.text_area("JSON", value=json.dumps({"is_active": True}, indent=2), height=200)

        if st.button("Run UPDATE", use_container_width=True):
            try:
                payload = json.loads(payload_text)
                # NOTE: filter_val stays text; PostgREST usually casts correctly for int columns.
                client.table(table_name).update(payload).eq(filter_col, filter_val).execute()
                st.success("Update complete.")
            except Exception as e:
                show_api_error(e, "Update failed")
