
import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")

st.set_page_config(page_title="Njangi Admin Dashboard", layout="wide")

# Base client (anon). We will attach user session after login for RLS.
sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def df(resp):
    return pd.DataFrame(resp.data or [])


def auth_client():
    """Supabase client with current user's access token (RLS applies)."""
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c


def require_login():
    if st.session_state.get("session") is None:
        st.warning("Please login as an admin.")
        st.stop()


def get_profile(c):
    user = st.session_state["session"].user
    r = c.table("profiles").select("id,full_name,phone,role").eq("id", user.id).single().execute()
    return r.data


def must_be_admin(profile):
    if not profile or profile.get("role") != "admin":
        st.error("Access denied. Your account is not an admin. (profiles.role must be 'admin')")
        st.stop()


# -----------------------
# Sidebar Login
# -----------------------
st.title("Njangi Admin Dashboard")

with st.sidebar:
    st.header("Login")

    if "session" not in st.session_state:
        st.session_state.session = None

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
        u = st.session_state.session.user
        st.success(f"Logged in: {u.email}")
        if st.button("Logout", use_container_width=True):
            sb.auth.sign_out()
            st.session_state.session = None
            st.rerun()

require_login()
c = auth_client()
profile = get_profile(c)
must_be_admin(profile)

st.caption(f"Admin: **{profile.get('full_name') or profile['id']}**")

# -----------------------
# Helper queries
# -----------------------
def list_cycles():
    return c.table("cycles").select("cycle_id,name,start_date,is_active,created_at").order("created_at", desc=True).execute()

def list_sessions(cycle_id=None):
    q = c.table("sessions").select("session_id,cycle_id,session_date,due_date,status,created_at").order("created_at", desc=True)
    if cycle_id:
        q = q.eq("cycle_id", cycle_id)
    return q.execute()

def list_active_members():
    # members table is UUID-based now
    return c.table("members").select("member_id,is_active,contribution_amount,surety_id,joined_at").order("joined_at", desc=True).execute()

def list_cycle_members(cycle_id):
    return c.table("cycle_members").select("cycle_id,member_id,payout_position").eq("cycle_id", cycle_id).order("payout_position").execute()

def upsert_contribution(session_id, member_id, amount, paid):
    payload = {
        "session_id": session_id,
        "member_id": member_id,
        "amount": int(amount),
        "paid": bool(paid),
    }
    # store paid_at only when paid
    if paid:
        payload["paid_at"] = pd.Timestamp.utcnow().isoformat()
    else:
        payload["paid_at"] = None

    return c.table("contributions").upsert(payload, on_conflict="session_id,member_id").execute()

def upsert_foundation(session_id, member_id, amount, paid):
    payload = {
        "session_id": session_id,
        "member_id": member_id,
        "amount": int(amount),
        "paid": bool(paid),
    }
    if paid:
        payload["paid_at"] = pd.Timestamp.utcnow().isoformat()
    else:
        payload["paid_at"] = None

    return c.table("foundation_payments").upsert(payload, on_conflict="session_id,member_id").execute()

def create_session_rows_for_cycle_members(session_id, cycle_id):
    """
    Auto-create contributions + foundation rows for all members in cycle_members.
    Safe to run multiple times due to upsert unique constraint (session_id, member_id).
    """
    cm = list_cycle_members(cycle_id).data or []
    if not cm:
        return 0

    # For each member, default contribution amount comes from members table
    count = 0
    for row in cm:
        mid = row["member_id"]
        m = c.table("members").select("contribution_amount").eq("member_id", mid).single().execute().data
        contrib_amt = int(m["contribution_amount"]) if m else 500

        upsert_contribution(session_id, mid, contrib_amt, False)
        upsert_foundation(session_id, mid, 500, False)
        count += 1

    return count

# -----------------------
# Tabs
# -----------------------
tabs = st.tabs([
    "1) Approve Members",
    "2) Cycles",
    "3) Payout Order",
    "4) Sessions",
    "5) Contributions",
    "6) Foundation",
    "7) Close Session + Fines",
    "8) Loans",
    "9) Payouts",
    "10) Reports & Settings"
])

# 1) Approve Members
with tabs[0]:
    st.subheader("Approve Members")
    r = list_active_members()
    st.dataframe(df(r), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        member_uuid = st.text_input("Member UUID (member_id) to approve")
    with col2:
        active = st.selectbox("Set is_active", [True, False], index=0)

    if st.button("Update Member Status"):
        try:
            c.table("members").update({"is_active": active}).eq("member_id", member_uuid).execute()
            st.success("Member updated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

# 2) Cycles
with tabs[1]:
    st.subheader("Cycles")

    col1, col2, col3 = st.columns(3)
    with col1:
        cycle_name = st.text_input("Cycle name", value="Njangi Cycle 1")
    with col2:
        start_date = st.date_input("Start date")
    with col3:
        is_active = st.selectbox("Active?", [True, False], index=0)

    if st.button("Create Cycle"):
        try:
            c.table("cycles").insert({
                "name": cycle_name,
                "start_date": str(start_date),
                "is_active": bool(is_active),
                "created_by": profile["id"]
            }).execute()
            st.success("Cycle created.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.markdown("### Existing cycles")
    st.dataframe(df(list_cycles()), use_container_width=True)

# 3) Payout Order
with tabs[2]:
    st.subheader("Cycle Members (Payout Order)")

    cycles_df = df(list_cycles())
    st.dataframe(cycles_df, use_container_width=True)

    cycle_id = st.text_input("Cycle ID (cycle_id)")

    st.markdown("### Current payout order for this cycle")
    if cycle_id:
        st.dataframe(df(list_cycle_members(cycle_id)), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        member_id = st.text_input("Member UUID to add")
    with col2:
        pos = st.number_input("Payout position", min_value=1, step=1, value=1)

    if st.button("Add/Upsert member in payout order"):
        try:
            c.table("cycle_members").upsert({
                "cycle_id": cycle_id,
                "member_id": member_id,
                "payout_position": int(pos)
            }, on_conflict="cycle_id,member_id").execute()
            st.success("Saved payout order.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

# 4) Sessions
with tabs[3]:
    st.subheader("Sessions")

    st.markdown("### Create a session")
    col1, col2, col3 = st.columns(3)
    with col1:
        cycle_id = st.text_input("Cycle ID for session", key="sess_cycle_id")
    with col2:
        session_date = st.date_input("Session date", key="sess_date")
    with col3:
        due_date = st.date_input("Due date", key="sess_due_date")

    if st.button("Create Session + Auto-generate rows"):
        try:
            res = c.table("sessions").insert({
                "cycle_id": cycle_id,
                "session_date": str(session_date),
                "due_date": str(due_date),
                "status": "open"
            }).execute()

            new_session_id = res.data[0]["session_id"]
            created = create_session_rows_for_cycle_members(new_session_id, cycle_id)
            st.success(f"Session created. Generated rows for {created} members (contributions + foundation).")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.markdown("### Sessions list (latest first)")
    st.dataframe(df(list_sessions()), use_container_width=True)

# 5) Contributions
with tabs[4]:
    st.subheader("Contributions")

    session_id = st.text_input("Session ID to view/edit contributions", key="contrib_session_id")
    if session_id:
        r = c.table("contributions").select("*").eq("session_id", session_id).order("created_at").execute()
        st.dataframe(df(r), use_container_width=True)

    st.markdown("### Update a member contribution")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        u_session = st.text_input("Session ID", key="uc_sess")
    with col2:
        u_member = st.text_input("Member UUID", key="uc_member")
    with col3:
        u_amount = st.number_input("Amount", min_value=0, step=500, value=500, key="uc_amt")
    with col4:
        u_paid = st.selectbox("Paid?", [True, False], index=0, key="uc_paid")

    if st.button("Save contribution (upsert)"):
        try:
            upsert_contribution(u_session, u_member, u_amount, u_paid)
            st.success("Contribution saved.")
        except Exception as e:
            st.error(str(e))

# 6) Foundation
with tabs[5]:
    st.subheader("Foundation Payments")

    session_id = st.text_input("Session ID to view/edit foundation payments", key="f_session_id")
    if session_id:
        r = c.table("foundation_payments").select("*").eq("session_id", session_id).order("created_at").execute()
        st.dataframe(df(r), use_container_width=True)

    st.markdown("### Update a member foundation payment")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        u_session = st.text_input("Session ID", key="uf_sess")
    with col2:
        u_member = st.text_input("Member UUID", key="uf_member")
    with col3:
        u_amount = st.number_input("Amount", min_value=0, step=500, value=500, key="uf_amt")
    with col4:
        u_paid = st.selectbox("Paid?", [True, False], index=0, key="uf_paid")

    if st.button("Save foundation payment (upsert)"):
        try:
            upsert_foundation(u_session, u_member, u_amount, u_paid)
            st.success("Foundation payment saved.")
        except Exception as e:
            st.error(str(e))

# 7) Close Session + Fines
with tabs[6]:
    st.subheader("Close Session + Apply Late Fines")

    session_id = st.text_input("Session ID to close", key="close_session_id")

    if st.button("Close session + apply fines"):
        try:
            c.table("sessions").update({"status": "closed"}).eq("session_id", session_id).execute()
            c.rpc("apply_late_fines", {"p_session_id": session_id}).execute()
            st.success("Session closed and fines applied to unpaid contributions.")
        except Exception as e:
            st.error(str(e))

    st.markdown("### View fines for a session")
    sess = st.text_input("Session ID for fines", key="fine_sess")
    if sess:
        r = c.table("fines").select("*").eq("session_id", sess).order("created_at").execute()
        st.dataframe(df(r), use_container_width=True)

# 8) Loans
with tabs[7]:
    st.subheader("Loans")

    st.markdown("### All loans")
    r = c.table("loans").select("*").order("requested_at", desc=True).execute()
    st.dataframe(df(r), use_container_width=True)

    st.markdown("### Approve / Reject / Activate / Close")
    col1, col2, col3 = st.columns(3)
    with col1:
        loan_id = st.text_input("Loan ID", key="loan_id")
    with col2:
        new_status = st.selectbox("New status", ["approved", "rejected", "active", "closed", "defaulted"], index=0)
    with col3:
        note_time = st.checkbox("Set approved_at/disbursed_at automatically?", value=True)

    if st.button("Update loan status"):
        try:
            payload = {"status": new_status}
            now = pd.Timestamp.utcnow().isoformat()

            if note_time and new_status in ("approved", "active"):
                payload["approved_at"] = now
                payload["approved_by"] = profile["id"]
            if note_time and new_status == "active":
                payload["disbursed_at"] = now
            if note_time and new_status == "closed":
                payload["closed_at"] = now

            c.table("loans").update(payload).eq("loan_id", loan_id).execute()
            st.success("Loan updated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    st.markdown("### Record a loan payment")
    col1, col2 = st.columns(2)
    with col1:
        pay_loan_id = st.text_input("Loan ID for payment", key="pay_loan_id")
    with col2:
        pay_amount = st.number_input("Payment amount", min_value=1, step=100, value=100, key="pay_amt")

    if st.button("Add loan payment"):
        try:
            c.table("loan_payments").insert({
                "loan_id": pay_loan_id,
                "amount": int(pay_amount),
                "confirmed_by": profile["id"]
            }).execute()
            st.success("Payment recorded.")
        except Exception as e:
            st.error(str(e))

    st.markdown("### Loan balances (principal only view)")
    rb = c.from_("loan_balances").select("*").execute()
    st.dataframe(df(rb), use_container_width=True)

# 9) Payouts
with tabs[8]:
    st.subheader("Payouts")

    st.markdown("### Release payout")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        p_cycle = st.text_input("Cycle ID", key="p_cycle")
    with col2:
        p_session = st.text_input("Session ID", key="p_session")
    with col3:
        p_member = st.text_input("Member UUID (receiver)", key="p_member")
    with col4:
        p_amount = st.number_input("Amount", min_value=1, step=500, value=500, key="p_amount")

    if st.button("Release payout"):
        try:
            c.table("payouts").insert({
                "cycle_id": p_cycle,
                "session_id": p_session,
                "member_id": p_member,
                "amount": int(p_amount),
                "released_by": profile["id"]
            }).execute()
            st.success("Payout released.")
        except Exception as e:
            st.error(str(e))

    st.markdown("### Payout history")
    r = c.table("payouts").select("*").order("released_at", desc=True).execute()
    st.dataframe(df(r), use_container_width=True)

# 10) Reports & Settings
with tabs[9]:
    st.subheader("Reports & Settings")

    st.markdown("### Session totals")
    r = c.from_("njangi_session_total").select("*").execute()
    st.dataframe(df(r), use_container_width=True)

    st.markdown("### Foundation balance")
    r = c.from_("foundation_balance").select("*").execute()
    st.dataframe(df(r), use_container_width=True)

    st.markdown("### App settings (late fine amount)")
    cfg = c.table("app_config").select("*").execute()
    st.dataframe(df(cfg), use_container_width=True)

    new_fine = st.number_input("Set late_fine_amount", min_value=0, step=10, value=50)
    if st.button("Update late fine amount"):
        try:
            c.table("app_config").upsert({"key": "late_fine_amount", "value": str(int(new_fine))}, on_conflict="key").execute()
            st.success("Updated.")
            st.rerun()
        except Exception as e:
            st.error(str(e))
