import os
import json
import streamlit as st
import pandas as pd
import altair as alt
from supabase import create_client
from datetime import datetime, timezone

# ============================================================
# CONFIG + THEME (dark like your screenshot)
# ============================================================
st.set_page_config(page_title="The Young Shall Grow – Njangi (Legacy)", layout="wide")

st.markdown(
    """
<style>
:root{
  --bg:#0b1220;
  --card:#0f1b31;
  --text:#e8eefc;
  --muted:#a9b6d5;
  --accent:#4f8cff;
  --accent2:#22c55e;
  --warn:#f59e0b;
  --danger:#ef4444;
  --border:rgba(255,255,255,0.10);
}
.stApp{
  background: linear-gradient(180deg, var(--bg) 0%, #070b14 70%, #05070f 100%);
  color: var(--text);
}
h1,h2,h3{ color: var(--text); }
p,li,span,div{ color: var(--text); }
small, .stCaption, .stMarkdown p{ color: var(--muted) !important; }
.block-container{ padding-top: 1.2rem; padding-bottom: 2rem; }

section[data-testid="stSidebar"]{
  background: rgba(15, 27, 49, 0.75);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] *{ color: var(--text) !important; }

.kpi-card{
  background: rgba(15, 27, 49, 0.75);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 14px 12px 14px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.25);
}
.kpi-top{
  display:flex; align-items:center; justify-content:space-between;
  gap:10px; margin-bottom:8px;
}
.kpi-title{
  font-size: 0.85rem;
  color: var(--muted);
  font-weight: 700;
}
.kpi-value{
  font-size: 1.35rem;
  font-weight: 900;
  color: var(--text);
}
.kpi-sub{
  font-size: 0.78rem;
  color: var(--muted);
}
.badge{
  display:inline-flex;
  align-items:center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 800;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
}
.badge-accent{ color: #cfe0ff; border-color: rgba(79,140,255,.45); background: rgba(79,140,255,.12); }
.badge-green{ color: #d1fae5; border-color: rgba(34,197,94,.45); background: rgba(34,197,94,.12); }
.badge-warn{ color: #ffedd5; border-color: rgba(245,158,11,.45); background: rgba(245,158,11,.12); }

.panel{
  background: rgba(13, 23, 43, 0.70);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.18);
}
.stButton>button{
  background: linear-gradient(135deg, rgba(79,140,255,.95), rgba(59,130,246,.85));
  color: white;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 0.55rem 0.85rem;
  font-weight: 900;
}
.stButton>button:hover{
  background: linear-gradient(135deg, rgba(79,140,255,1), rgba(37,99,235,1));
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🌱 The Young Shall Grow – Njangi (Legacy)")

# ============================================================
# SUPABASE SECRETS
# ============================================================
def get_secret(key: str):
    try:
        return st.secrets.get(key)
    except Exception:
        return os.getenv(key)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("❌ Missing SUPABASE_URL or SUPABASE_ANON_KEY in Streamlit Secrets.")
    st.stop()

sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ============================================================
# HELPERS
# ============================================================
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def safe_df(data) -> pd.DataFrame:
    return pd.DataFrame(data or [])

def to_number(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def money(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "0"

def kpi_card(title, value, badge_text=None, badge_kind="accent", sub=None):
    badge_class = {
        "accent": "badge badge-accent",
        "green": "badge badge-green",
        "warn": "badge badge-warn",
    }.get(badge_kind, "badge badge-accent")
    badge_html = f'<span class="{badge_class}">{badge_text}</span>' if badge_text else ""
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    st.markdown(
        f"""
<div class="kpi-card">
  <div class="kpi-top">
    <div class="kpi-title">{title}</div>
    {badge_html}
  </div>
  <div class="kpi-value">{value}</div>
  {sub_html}
</div>
""",
        unsafe_allow_html=True,
    )

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def fetch_one(query_builder):
    try:
        res = query_builder.limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        return None

@st.cache_data(ttl=20)
def load_table_readonly(c, table_name: str, limit: int = 1000) -> pd.DataFrame:
    try:
        res = c.table(table_name).select("*").limit(limit).execute()
        return safe_df(res.data)
    except Exception:
        return pd.DataFrame()

def get_profile(c, auth_id: str):
    return fetch_one(c.table("profiles").select("role,approved,member_id").eq("id", auth_id))

def get_member_name(c, legacy_member_id: int):
    row = fetch_one(c.table("member_registry").select("full_name").eq("legacy_member_id", legacy_member_id))
    return (row or {}).get("full_name") or f"Member {legacy_member_id}"

# ============================================================
# AUTH UI (Login + Sign Up)
# ============================================================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.markdown("### Account")

    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        if st.session_state.session is None:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", use_container_width=True, key="btn_login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.session = res.session
                    st.rerun()
                except Exception as e:
                    st.error("Login failed")
                    st.code(repr(e))
        else:
            st.success(f"Logged in: {st.session_state.session.user.email}")
            if st.button("Logout", use_container_width=True, key="btn_logout"):
                try:
                    sb.auth.sign_out()
                except Exception:
                    pass
                st.session_state.session = None
                st.rerun()

    with tab_signup:
        st.caption("Sign up creates an account. Admin must approve you in `profiles`.")
        su_email = st.text_input("Email", key="su_email")
        su_password = st.text_input("Password", type="password", key="su_password")
        su_member_id = st.number_input("Your legacy member_id (1..17)", min_value=1, step=1, key="su_member_id")
        if st.button("Create account", use_container_width=True, key="btn_signup"):
            try:
                res = sb.auth.sign_up({"email": su_email, "password": su_password})
                # If your DB has a trigger to auto-create profiles, good.
                # If not, try inserting a profile row (may require policy to allow this).
                user = getattr(res, "user", None)
                if user and getattr(user, "id", None):
                    try:
                        # create profile as member, not approved (admin will approve later)
                        sb.table("profiles").insert({
                            "id": user.id,
                            "role": "member",
                            "approved": False,
                            "member_id": int(su_member_id),
                            "created_at": now_iso(),
                            "updated_at": now_iso(),
                        }).execute()
                    except Exception:
                        pass

                st.success("Account created. Now go to Login. If approval is required, admin must approve in profiles.")
            except Exception as e:
                st.error("Sign up failed")
                st.code(repr(e))

# Stop if not logged in
if st.session_state.session is None:
    st.info("Please Login (or Sign Up) using the sidebar.")
    st.stop()

client = authed_client()
auth_id = st.session_state.session.user.id
auth_email = st.session_state.session.user.email

profile = get_profile(client, auth_id)
if not profile:
    st.error("No profile row found for this user in `profiles`. Admin must create/approve it.")
    st.stop()

if not bool(profile.get("approved", False)):
    st.warning("Your account is not approved yet. Please contact admin.")
    st.stop()

role = (profile.get("role") or "member").lower()
member_id = int(profile.get("member_id") or 0)

# ============================================================
# Sidebar menu (your requested style)
# ============================================================
with st.sidebar:
    st.markdown("---")
    st.write(f"**Role:** {role}")
    st.write(f"**member_id:** {member_id}")
    st.caption("If you see 0 rows, RLS is blocking reads for this user.")

    pages = [
        "Dashboard",
        "Members",
        "Contributions (Legacy)",
        "Foundation (Legacy)",
        "Loans (Legacy)",
        "Fines (Legacy)",
        "Payouts (Legacy)",
    ]
    page = st.radio("Menu", pages, index=0)

# ============================================================
# LOAD DATA (legacy tables)
# Member = only sees own rows IF your RLS is correct.
# ============================================================
members_df = load_table_readonly(client, "member_registry", limit=500)
contrib_df = load_table_readonly(client, "contributions_legacy", limit=2000)
foundation_df = load_table_readonly(client, "foundation_payments_legacy", limit=2000)
loans_df = load_table_readonly(client, "loans_legacy", limit=2000)
fines_df = load_table_readonly(client, "fines_legacy", limit=2000)
payouts_df = load_table_readonly(client, "payouts_legacy", limit=2000)

# ============================================================
# METRICS
# ============================================================
members_count = len(members_df) if role == "admin" else (1 if member_id else 0)

pot_total = 0
if not contrib_df.empty and "amount" in contrib_df.columns:
    # pot = kind='contribution'
    if "kind" in contrib_df.columns:
        pot_total = to_number(contrib_df.loc[contrib_df["kind"] == "contribution", "amount"]).sum()
    else:
        pot_total = to_number(contrib_df["amount"]).sum()

all_time_contrib = to_number(contrib_df["amount"]).sum() if (not contrib_df.empty and "amount" in contrib_df.columns) else 0

f_paid = f_pending = f_total = 0
if not foundation_df.empty:
    if "amount_paid" in foundation_df.columns:
        f_paid = to_number(foundation_df["amount_paid"]).sum()
    if "amount_pending" in foundation_df.columns:
        f_pending = to_number(foundation_df["amount_pending"]).sum()
    f_total = float(f_paid) + float(f_pending)

active_loans = 0
active_total_due = 0
total_interest = 0
unpaid_interest = 0
if not loans_df.empty:
    if "status" in loans_df.columns:
        active = loans_df[loans_df["status"].astype(str).str.lower() == "active"]
        active_loans = len(active)
        if "total_due" in active.columns:
            active_total_due = to_number(active["total_due"]).sum()
    if "total_interest_generated" in loans_df.columns:
        total_interest = to_number(loans_df["total_interest_generated"]).sum()
    elif "total_interest_accumulated" in loans_df.columns:
        total_interest = to_number(loans_df["total_interest_accumulated"]).sum()
    if "unpaid_interest" in loans_df.columns:
        unpaid_interest = to_number(loans_df["unpaid_interest"]).sum()

total_fines = 0
if not fines_df.empty:
    for col in ["amount", "fine_amount", "value"]:
        if col in fines_df.columns:
            total_fines = to_number(fines_df[col]).sum()
            break

# ============================================================
# DASHBOARD PAGE
# ============================================================
if page == "Dashboard":
    title = "Njangi Admin Dashboard" if role == "admin" else "Njangi Member Dashboard"

    st.markdown(
        f"""
<div class="panel">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
    <div>
      <div style="font-size:1.5rem;font-weight:900;margin:0;">{title}</div>
      <div style="color:var(--muted);font-weight:650;margin-top:2px;">
        Legacy tables mode • contributions_legacy • foundation_payments_legacy • loans_legacy • fines_legacy
      </div>
    </div>
    <div class="badge badge-accent">v1.0</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(f"Logged in user id: {auth_id}")
    st.caption(f"Logged in email: {auth_email}")

    # KPI row (same card vibe)
    if role == "admin":
        # next beneficiary from app_state
        state = fetch_one(client.table("app_state").select("*").eq("id", 1)) or {}
        next_idx = int(state.get("next_payout_index") or 1)
        ben_name = get_member_name(client, next_idx)

        r1 = st.columns(7)
        with r1[0]:
            kpi_card("Current Beneficiary", f"{next_idx} — {ben_name}", badge_text="Rotation", badge_kind="accent",
                     sub="From app_state.next_payout_index")
        with r1[1]:
            kpi_card("Contribution Pot", money(pot_total), badge_text="Ready",
                     badge_kind=("green" if pot_total > 0 else "warn"),
                     sub="Sum where kind='contribution'")
        with r1[2]:
            kpi_card("All-time Contributions", money(all_time_contrib), badge_text="History", badge_kind="accent",
                     sub="All rows in contributions_legacy")
        with r1[3]:
            kpi_card("Foundation Total", money(f_total), badge_text="Paid+Pending", badge_kind="accent",
                     sub=f"Paid {money(f_paid)} • Pending {money(f_pending)}")
        with r1[4]:
            kpi_card("Total Interest", money(total_interest), badge_text="Loans", badge_kind="accent",
                     sub=f"Unpaid {money(unpaid_interest)}")
        with r1[5]:
            kpi_card("Active Loans", str(active_loans), badge_text="Due",
                     badge_kind=("warn" if active_total_due > 0 else "green"),
                     sub=f"Active total_due {money(active_total_due)}")
        with r1[6]:
            kpi_card("Total Fines", money(total_fines), badge_text="Fines", badge_kind="warn",
                     sub="Sum fines_legacy")

        st.write("")
        st.markdown("<div class='panel'>Tip: If KPIs fail or show 0, it’s usually RLS blocking SELECT for this user.</div>",
                    unsafe_allow_html=True)

    else:
        # member summary (read-only)
        r1 = st.columns(5)
        with r1[0]:
            kpi_card("My Member ID", str(member_id), badge_text="Member", badge_kind="accent")
        with r1[1]:
            kpi_card("My Contributions", money(all_time_contrib), badge_text="Total", badge_kind="accent")
        with r1[2]:
            kpi_card("My Foundation", money(f_total), badge_text="Paid+Pending", badge_kind="accent")
        with r1[3]:
            kpi_card("My Active Loan Due", money(active_total_due), badge_text="Loans",
                     badge_kind=("warn" if active_total_due > 0 else "green"))
        with r1[4]:
            kpi_card("My Fines", money(total_fines), badge_text="Fines", badge_kind="warn")

    st.divider()

    # CHART: Top 10 contributions
    st.subheader("📈 Contributions (Top 10)")
    if contrib_df.empty or "amount" not in contrib_df.columns:
        st.info("No contributions found (or RLS blocked).")
    else:
        work = contrib_df.copy()
        work["amount"] = to_number(work["amount"])
        name_col = "member_id" if "member_id" in work.columns else None

        if name_col == "member_id" and not members_df.empty and "legacy_member_id" in members_df.columns:
            # join member names for nicer chart
            join_df = members_df[["legacy_member_id", "full_name"]].rename(columns={"legacy_member_id": "member_id"})
            work = work.merge(join_df, on="member_id", how="left")
            work["label"] = work["full_name"].fillna(work["member_id"].astype(str))
        else:
            work["label"] = "Member"

        top = (
            work.groupby("label")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
            .rename(columns={"label": "Member", "amount": "Amount"})
        )

        chart = (
            alt.Chart(top)
            .mark_bar()
            .encode(
                x=alt.X("Member:N", sort="-y"),
                y=alt.Y("Amount:Q"),
                tooltip=["Member", alt.Tooltip("Amount:Q", format=",.0f")],
            )
            .properties(height=320)
        )
        st.altair_chart(chart, use_container_width=True)

# ============================================================
# TABLE PAGES
# ============================================================
def table_page(title: str, df: pd.DataFrame):
    st.subheader(title)
    if df.empty:
        st.info("No rows (or blocked by RLS).")
    else:
        st.dataframe(df, use_container_width=True)

if page == "Members":
    # Member: allow read only their own member row if RLS or filter
    if role == "admin":
        table_page("👥 member_registry", members_df)
    else:
        if not members_df.empty and "legacy_member_id" in members_df.columns and member_id:
            table_page("👤 My member_registry row", members_df[members_df["legacy_member_id"] == member_id])
        else:
            table_page("👤 My member_registry row", pd.DataFrame())

elif page == "Contributions (Legacy)":
    table_page("💰 contributions_legacy", contrib_df)

elif page == "Foundation (Legacy)":
    table_page("🏦 foundation_payments_legacy", foundation_df)

elif page == "Loans (Legacy)":
    table_page("💳 loans_legacy", loans_df)

elif page == "Fines (Legacy)":
    table_page("⚠️ fines_legacy", fines_df)

elif page == "Payouts (Legacy)":
    table_page("💸 payouts_legacy", payouts_df)

# ============================================================
# ADMIN INSERT FORMS (ONLY ADMIN)
# ============================================================
if role == "admin":
    st.divider()
    st.markdown("### ✅ Admin: Add Records")

    form_tabs = st.tabs(["Add Contribution", "Add Foundation", "Add Fine"])

    # --- Add Contribution
    with form_tabs[0]:
        st.markdown("**Insert into contributions_legacy**")
        member_id_in = st.number_input("member_id (legacy)", min_value=1, step=1, key="ins_c_mid")
        amount_in = st.number_input("amount", min_value=0, step=500, value=500, key="ins_c_amount")
        kind_in = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="ins_c_kind")

        if st.button("Insert Contribution", use_container_width=True, key="btn_ins_contrib"):
            try:
                client.table("contributions_legacy").insert({
                    "member_id": int(member_id_in),
                    "amount": int(amount_in),
                    "kind": str(kind_in),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }).execute()
                st.success("Contribution inserted.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error("Insert failed (RLS/columns)")
                st.code(repr(e))

    # --- Add Foundation
    with form_tabs[1]:
        st.markdown("**Insert into foundation_payments_legacy**")
        member_id_in = st.number_input("member_id (legacy)", min_value=1, step=1, key="ins_f_mid")
        amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="ins_f_paid")
        amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="ins_f_pending")
        status = st.selectbox("status", ["paid", "pending", "converted"], index=0, key="ins_f_status")
        if st.button("Insert Foundation Payment", use_container_width=True, key="btn_ins_found"):
            try:
                client.table("foundation_payments_legacy").insert({
                    "member_id": int(member_id_in),
                    "amount_paid": float(amount_paid),
                    "amount_pending": float(amount_pending),
                    "status": str(status),
                    "date_paid": now_iso(),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }).execute()
                st.success("Foundation payment inserted.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error("Insert failed (RLS/columns)")
                st.code(repr(e))

    # --- Add Fine
    with form_tabs[2]:
        st.markdown("**Insert into fines_legacy**")
        member_id_in = st.number_input("member_id (legacy)", min_value=1, step=1, key="ins_x_mid")
        fine_amount = st.number_input("amount", min_value=0, step=500, value=500, key="ins_x_amount")
        reason = st.text_input("reason (optional)", value="", key="ins_x_reason")
        if st.button("Insert Fine", use_container_width=True, key="btn_ins_fine"):
            try:
                payload = {
                    "member_id": int(member_id_in),
                    "amount": float(fine_amount),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }
                if reason.strip():
                    payload["reason"] = reason.strip()
                client.table("fines_legacy").insert(payload).execute()
                st.success("Fine inserted.")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error("Insert failed (RLS/columns)")
                st.code(repr(e))

else:
    st.caption("Member mode: read-only. Admin mode required to add records.")
