
import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone, timedelta

# ============================================================
# Page + Theme (Nice UI / fixed colors)
# ============================================================
st.set_page_config(page_title="Njangi Dashboard (Legacy)", layout="wide")

st.markdown(
    """
<style>
:root{
  --bg:#0b1220;
  --card:#0f1b31;
  --card2:#0d172b;
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
  font-weight: 600;
  letter-spacing: .2px;
}
.kpi-value{
  font-size: 1.35rem;
  font-weight: 800;
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
  font-weight: 700;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
}
.badge-accent{ color: #cfe0ff; border-color: rgba(79,140,255,.45); background: rgba(79,140,255,.12); }
.badge-green{ color: #d1fae5; border-color: rgba(34,197,94,.45); background: rgba(34,197,94,.12); }
.badge-warn{ color: #ffedd5; border-color: rgba(245,158,11,.45); background: rgba(245,158,11,.12); }
.badge-danger{ color: #fee2e2; border-color: rgba(239,68,68,.45); background: rgba(239,68,68,.12); }

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
  font-weight: 800;
}
.stButton>button:hover{
  background: linear-gradient(135deg, rgba(79,140,255,1), rgba(37,99,235,1));
  border-color: rgba(255,255,255,0.18);
}
.stButton>button:disabled{ opacity: 0.6; }

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea{
  background: rgba(255,255,255,0.04) !important;
  border-radius: 12px !important;
  border-color: rgba(255,255,255,0.10) !important;
  color: var(--text) !important;
}
label{ color: var(--muted) !important; font-weight: 650 !important; }

[data-testid="stDataFrame"]{
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
}

.stTabs [data-baseweb="tab"]{ color: var(--muted); font-weight: 800; }
.stTabs [aria-selected="true"]{ color: var(--text); }
.stAlert{ border-radius: 14px; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# Secrets + Supabase
# ============================================================
def get_secret(key: str):
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

# ============================================================
# Helpers
# ============================================================
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
    st.code(repr(e))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def fetch_one(query_builder):
    try:
        res = query_builder.limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        return None

def safe_select_autosort(c, table: str, limit=400):
    for col in ["created_at", "issued_at", "updated_at", "paid_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def money(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)

def kpi_card(title, value, badge_text=None, badge_kind="accent", sub=None):
    badge_class = {
        "accent": "badge badge-accent",
        "green": "badge badge-green",
        "warn": "badge badge-warn",
        "danger": "badge badge-danger",
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

# ============================================================
# Role / approvals (profiles table)
# ============================================================
def get_profile(c, user_id: str):
    return fetch_one(c.table("profiles").select("id,role,approved,member_id").eq("id", user_id))

def is_admin(profile: dict | None) -> bool:
    if not profile:
        return False
    return str(profile.get("role") or "").lower() == "admin" and bool(profile.get("approved") is True)

def is_member(profile: dict | None) -> bool:
    if not profile:
        return False
    return str(profile.get("role") or "").lower() == "member" and bool(profile.get("approved") is True)

# ============================================================
# Auth UI (Login + Signup)  ✅ SHOW FIRST, NOTHING ELSE
# ============================================================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.markdown("### Login / Sign Up")

    if st.session_state.session is None:
        mode = st.radio("Mode", ["Login", "Sign Up"], horizontal=True)

        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_password")

        if mode == "Sign Up":
            st.caption("After sign up, admin must approve you in profiles (approved=true).")
            if st.button("Create account", use_container_width=True):
                try:
                    sb.auth.sign_up({"email": email, "password": password})
                    st.success("Account created. Now login.")
                except Exception as e:
                    show_api_error(e, "Sign up failed")

        else:
            if st.button("Login", use_container_width=True, key="btn_login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.session = res.session
                    st.rerun()
                except Exception as e:
                    show_api_error(e, "Login failed")

    else:
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

# ✅ If not logged in, stop BEFORE showing dashboard header/body
if st.session_state.session is None:
    st.markdown(
        """
        <div class="panel">
          <div style="font-size:1.4rem;font-weight:900;">Njangi Login</div>
          <div style="color:var(--muted);margin-top:6px;">
            Please login or sign up from the sidebar to access the dashboard.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ============================================================
# Continue after login
# ============================================================
client = authed_client()
user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email
# ============================================================
# Load / profile check
# ============================================================
st.caption(f"Logged in user id: {user_id}")
st.caption(f"Logged in email: {user_email}")

profile = get_profile(client, user_id)
role_txt = (profile or {}).get("role", "unknown")
approved_txt = (profile or {}).get("approved", False)

st.caption(f"Profile role: {role_txt} • approved: {approved_txt}")

if not (is_admin(profile) or is_member(profile)):
    st.warning("Your account is not approved yet. Ask admin to set profiles.approved=true.")
    st.stop()

# ============================================================
# Load registry
# ============================================================
def load_member_registry(c):
    resp = c.table("member_registry").select(
        "legacy_member_id,full_name,is_active,phone,created_at"
    ).order("legacy_member_id").execute()

    rows = resp.data or []
    df = pd.DataFrame(rows)

    labels, label_to_legacy, label_to_name = [], {}, {}
    for r in rows:
        mid = int(r.get("legacy_member_id"))
        name = (r.get("full_name") or f"Member {mid}").strip()
        active = r.get("is_active", True)
        tag = "" if active in (None, True) else " (inactive)"
        label = f"{mid} — {name}{tag}"
        labels.append(label)
        label_to_legacy[label] = mid
        label_to_name[label] = name

    if not labels:
        labels = ["No members found"]
        label_to_legacy = {"No members found": 0}
        label_to_name = {"No members found": ""}

    return labels, label_to_legacy, label_to_name, df

member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

# ============================================================
# KPIs helpers
# ============================================================
def get_app_state(c):
    return fetch_one(c.table("app_state").select("*").eq("id", 1))

def sum_contribution_pot(c):
    resp = c.table("contributions_legacy").select("amount,kind").limit(10000).execute()
    pot = 0
    for r in (resp.data or []):
        if (r.get("kind") or "contribution") == "contribution":
            try:
                pot += int(r.get("amount") or 0)
            except Exception:
                pass
    return pot

def sum_total_contributions_alltime(c):
    resp = c.table("contributions_legacy").select("amount").limit(10000).execute()
    total = 0
    for r in (resp.data or []):
        try:
            total += int(r.get("amount") or 0)
        except Exception:
            pass
    return total

def foundation_totals(c):
    resp = c.table("foundation_payments_legacy").select("amount_paid,amount_pending").limit(10000).execute()
    paid = 0.0
    pending = 0.0
    for r in (resp.data or []):
        paid += float(r.get("amount_paid") or 0)
        pending += float(r.get("amount_pending") or 0)
    return paid, pending, (paid + pending)

def loans_interest_totals(c):
    resp = c.table("loans_legacy").select(
        "total_interest_generated,total_interest_accumulated,unpaid_interest,status,total_due"
    ).limit(10000).execute()

    total_gen = 0.0
    total_acc = 0.0
    unpaid = 0.0
    active_count = 0
    active_total_due = 0.0

    for r in (resp.data or []):
        total_gen += float(r.get("total_interest_generated") or 0)
        total_acc += float(r.get("total_interest_accumulated") or 0)
        unpaid += float(r.get("unpaid_interest") or 0)
        if str(r.get("status") or "").lower() == "active":
            active_count += 1
            active_total_due += float(r.get("total_due") or 0)

    total_interest = total_gen if total_gen > 0 else total_acc
    return total_interest, unpaid, active_count, active_total_due

def fines_totals(c):
    resp = c.table("fines_legacy").select("amount,status").limit(10000).execute()
    total = 0.0
    unpaid = 0.0
    for r in (resp.data or []):
        amt = float(r.get("amount") or 0)
        total += amt
        stt = str(r.get("status") or "").lower()
        if stt not in ("paid", "cleared", "settled"):
            unpaid += amt
    return total, unpaid

# ============================================================
# Borrow capacity (use kind='paid')
# ============================================================
def member_available_to_borrow(c, legacy_member_id: int):
    resp_c = (
        c.table("contributions_legacy")
        .select("amount,kind,member_id")
        .eq("member_id", legacy_member_id)
        .limit(10000)
        .execute()
    )
    contrib = 0.0
    for r in (resp_c.data or []):
        if (r.get("kind") or "").lower().strip() == "paid":
            contrib += float(r.get("amount") or 0)

    resp_f = (
        c.table("foundation_payments_legacy")
        .select("amount_paid,amount_pending,member_id")
        .eq("member_id", legacy_member_id)
        .limit(10000)
        .execute()
    )
    found = 0.0
    for r in (resp_f.data or []):
        found += float(r.get("amount_paid") or 0) + float(r.get("amount_pending") or 0)

    return contrib + (found * 0.70), contrib, found

# ============================================================
# ✅ FIX: Member Loan Totals (so loans are not 0 per member)
# ============================================================
def member_loan_totals(c, legacy_member_id: int):
    resp = (
        c.table("loans_legacy")
        .select("principal_current,unpaid_interest,")
        .eq("member_id", legacy_member_id)
        .limit(10000)
        .execute()
    )

    principal = 0.0
    unpaid_interest = 0.0
    active_loans = 0


    for r in (resp.data or []):
        if str(r.get("status") or "").lower() == "active":
            active_loans += 1
            principal += float(r.get("principal_current") or 0)
            unpaid_interest += float(r.get("unpaid_interest") or 0)
            total_due += float(r.get("principal_current") or 0)

    return principal, unpaid_interest, active_loans

# ============================================================
# Header (✅ NOW ONLY AFTER LOGIN)
# ============================================================
st.markdown(
    """
<div class="panel">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
    <div>
      <div style="font-size:1.5rem;font-weight:900;margin:0;">Njangi Dashboard</div>
      <div style="color:var(--muted);font-weight:650;margin-top:2px;">
        Legacy tables mode • member_registry • contributions_legacy • foundation_payments_legacy • loans_legacy • fines_legacy
      </div>
    </div>
    <div class="badge badge-accent">v1.0</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)
st.write("")

# ============================================================
# KPI Row (Global)
# ============================================================
try:
    state = get_app_state(client) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben_row = fetch_one(client.table("member_registry").select("full_name").eq("legacy_member_id", next_idx))
    ben_name = (ben_row or {}).get("full_name") or f"Member {next_idx}"

    pot = sum_contribution_pot(client)
    total_contrib_all = sum_total_contributions_alltime(client)
    f_paid, f_pending, f_total = foundation_totals(client)
    total_interest, unpaid_interest, active_loans, active_total_due = loans_interest_totals(client)
    fines_total, fines_unpaid = fines_totals(client)

    r1 = st.columns(7)
    with r1[0]:
        kpi_card("Current Beneficiary", f"{next_idx} — {ben_name}", badge_text="Rotation", badge_kind="accent", sub="From app_state.next_payout_index")
    with r1[1]:
        kpi_card("Contribution Pot", money(pot), badge_text="Ready", badge_kind=("green" if pot > 0 else "warn"), sub="Sum where kind='contribution'")
    with r1[2]:
        kpi_card("All-time Contributions", money(total_contrib_all), badge_text="History", badge_kind="accent", sub="All rows in contributions_legacy")
    with r1[3]:
        kpi_card("Foundation Total", money(f_total), badge_text="Paid+Pending", badge_kind="accent", sub=f"Paid {money(f_paid)} • Pending {money(f_pending)}")
    with r1[4]:
        kpi_card("Total Interest", money(total_interest), badge_text="Loans", badge_kind="accent", sub=f"Unpaid {money(unpaid_interest)}")
    with r1[5]:
        kpi_card("Active Loans", str(active_loans), badge_text="Due", badge_kind=("warn" if active_total_due > 0 else "green"), sub=f"Active total_due {money(active_total_due)}")
    with r1[6]:
        kpi_card("Fines", money(fines_total), badge_text="Unpaid", badge_kind=("warn" if fines_unpaid > 0 else "green"), sub=f"Unpaid {money(fines_unpaid)}")

except Exception as e:
    show_api_error(e, "Could not load dashboard KPIs")

st.write("")
st.markdown("<div class='panel'>Tip: If tables are blank or inserts fail, it’s usually RLS blocking SELECT/INSERT for that role.</div>", unsafe_allow_html=True)
st.divider()

# ============================================================
# Tabs
# ============================================================
admin_mode = is_admin(profile)

tab_names_admin = [
    "Members",
    "Contributions (Legacy)",
    "Foundation (Legacy)",
    "Loans (Legacy)",
    "Fines (Legacy)",
    "Payout (Option B)",
    "Member Borrow Capacity",
    "JSON Inserter",
]
tab_names_member = [
    "Members",
    "Member Borrow Capacity",
]

tabs = st.tabs(tab_names_admin if admin_mode else tab_names_member)

def tab_index(name: str) -> int:
    names = tab_names_admin if admin_mode else tab_names_member
    return names.index(name)

# ===================== MEMBERS =====================
with tabs[tab_index("Members")]:
    st.subheader("member_registry")
    st.dataframe(df_registry, use_container_width=True)

# ===================== MEMBER BORROW CAPACITY (✅ SHOW MEMBER LOANS TOO) =====================
with tabs[tab_index("Member Borrow Capacity")]:
    st.subheader("Borrow capacity (per member - Legacy rule)")
    st.caption("UPDATED: Contributions counted from contributions_legacy where kind='paid' + shows member loan balance.")

    pick = st.selectbox("Pick member", member_labels, key="cap_member")
    mid = int(label_to_legacy_id.get(pick, 0))
    name = label_to_name.get(pick, "")

    try:
        avail, paid_contrib, found = member_available_to_borrow(client, mid)
        principal, unpaid_int, active_cnt, due_total = member_loan_totals(client, mid)

        top = st.columns(6)
        with top[0]:
            kpi_card("Member", f"{mid} — {name}", badge_text="Legacy ID", badge_kind="accent", sub="From member_registry")
        with top[1]:
            kpi_card("Paid Contributions", money(paid_contrib), badge_text="Counted", badge_kind="accent", sub="kind='paid'")
        with top[2]:
            kpi_card("Foundation", money(found), badge_text="Raw", badge_kind="accent", sub="paid + pending")
        with top[3]:
            kpi_card("Available to borrow", money(avail), badge_text="Rule", badge_kind="green", sub="paid + 0.70×foundation")
        with top[4]:
            kpi_card("Active Loans", str(active_cnt), badge_text="Loans", badge_kind=("warn" if active_cnt > 0 else "green"), sub="status='active'")
        with top[5]:
            kpi_card("Loan Balance", money(due_total), badge_text="Due", badge_kind=("danger" if due_total > 0 else "green"), sub=f"Unpaid interest {money(unpaid_int)}")

        st.caption("Rule: available = paid_contributions + 0.70 × (foundation paid + pending)")

    except Exception as e:
        show_api_error(e, f"Could not compute borrow capacity/loans for {mid} — {name}")

# Stop here for members (read-only)
if not admin_mode:
    st.info("Member mode: read-only dashboard (no inserts).")
    st.stop()

# ============================================================
# (KEEP THE REST OF YOUR ADMIN TABS EXACTLY AS YOU ALREADY HAVE)
# ============================================================

# ===================== CONTRIBUTIONS (LEGACY) =====================
with tabs[tab_index("Contributions (Legacy)")]:
    st.subheader("contributions_legacy")
    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### Insert Contribution (legacy)")

    mem_label = st.selectbox("Member", member_labels, key="c_member_label")
    legacy_id = int(label_to_legacy_id.get(mem_label, 0))
    st.caption(f"member_id (legacy): **{legacy_id}**")

    amount = st.number_input("amount (int)", min_value=0, step=500, value=500, key="c_amount")
    kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
    session_id = st.text_input("session_id (uuid optional)", value="", key="c_session_id")

    if st.button("Insert Contribution", use_container_width=True, key="btn_c_insert"):
        payload = {"member_id": legacy_id, "amount": int(amount), "kind": str(kind)}
        if session_id.strip():
            payload["session_id"] = session_id.strip()
        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Contribution inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Contribution insert failed (RLS or invalid data)")

# ===================== FOUNDATION (LEGACY) =====================
with tabs[tab_index("Foundation (Legacy)")]:
    st.subheader("foundation_payments_legacy")
    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### Insert Foundation Payment (legacy)")

    mem_label_f = st.selectbox("Member", member_labels, key="f_member_label")
    legacy_id_f = int(label_to_legacy_id.get(mem_label_f, 0))
    st.caption(f"member_id (legacy): **{legacy_id_f}**")

    amount_paid = st.number_input("amount_paid (numeric)", min_value=0.0, step=500.0, value=500.0, key="f_paid")
    amount_pending = st.number_input("amount_pending (numeric)", min_value=0.0, step=500.0, value=0.0, key="f_pending")
    status = st.selectbox("status", ["paid", "pending", "converted"], index=0, key="f_status")
    date_paid = st.date_input("date_paid", key="f_date_paid")
    converted_to_loan = st.selectbox("converted_to_loan", [False, True], index=0, key="f_conv")
    notes_f = st.text_input("notes (optional)", value="", key="f_notes")

    if st.button("Insert Foundation Payment", use_container_width=True, key="btn_f_insert"):
        payload = {
            "member_id": legacy_id_f,
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": str(status),
            "date_paid": f"{date_paid}T00:00:00Z",
            "converted_to_loan": bool(converted_to_loan),
        }
        if notes_f.strip():
            payload["notes"] = notes_f.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Foundation payment inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Foundation insert failed (RLS/invalid data/column mismatch)")

# ===================== LOANS (LEGACY) =====================
with tabs[tab_index("Loans (Legacy)")]:
    st.subheader("loans_legacy")
    try:
        st.dataframe(to_df(client.table("loans_legacy").select("*").order("created_at", desc=True).limit(400).execute()), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loans_legacy")

    st.divider()
    st.markdown("### Insert Loan (loans_legacy)")

    borrower_label = st.selectbox("Borrower", member_labels, key="loan_borrower_label")
    borrower_member_id = int(label_to_legacy_id.get(borrower_label, 0))
    borrower_name = label_to_name.get(borrower_label, "")

    surety_label = st.selectbox("Surety", member_labels, key="loan_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input("principal", min_value=500.0, step=500.0, value=500.0, key="loan_principal")
    interest_cycle_days = st.number_input("interest_cycle_days", min_value=1, value=26, step=1, key="loan_cycle_days")
    status = st.selectbox("status", ["active", "pending", "closed", "paid"], index=0, key="loan_status")

    interest = float(principal) * 0.05
    total_due = float(principal) + interest
    st.info(f"Interest (5%): **{money(interest)}** • Total Due: **{money(total_due)}**")

    try:
        b_avail, b_paid, b_found = member_available_to_borrow(client, borrower_member_id)
        st.markdown(
            f"""
<div class="panel">
  <div style="font-weight:900;">Borrower capacity check</div>
  <div style="color:var(--muted);margin-top:4px;">
    Paid contributions <b>{money(b_paid)}</b> + 70% foundation <b>{money(b_found*0.70)}</b> = <b>{money(b_avail)}</b>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        if principal > b_avail:
            st.warning("Requested principal is higher than calculated capacity (paid+foundation rule).")
    except Exception:
        pass

    if st.button("Insert Loan", use_container_width=True, key="btn_insert_loan"):
        now_utc = now_iso()
        payload = {
            "member_id": borrower_member_id,
            "borrower_member_id": borrower_member_id,
            "surety_member_id": surety_member_id,
            "borrower_name": borrower_name,
            "surety_name": surety_name,
            "principal": float(principal),
            "interest": float(interest),
            "total_due": float(total_due),
            "principal_current": float(principal),
            "unpaid_interest": float(interest),
            "total_interest_generated": float(interest),
            "total_interest_accumulated": 0.0,
            "interest_cycle_days": int(interest_cycle_days),
            "last_interest_at": now_utc,
            "last_interest_date": now_utc,
            "issued_at": now_utc,
            "created_at": now_utc,
            "status": str(status),
        }

        try:
            client.table("loans_legacy").insert(payload).execute()
            st.success("Loan inserted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (RLS/constraint/column mismatch)")

# ===================== FINES (LEGACY) =====================
with tabs[tab_index("Fines (Legacy)")]:
    st.subheader("fines_legacy")

    try:
        st.dataframe(to_df(safe_select_autosort(client, "fines_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load fines_legacy")

    st.divider()
    st.markdown("### Insert Fine (fines_legacy)")

    mem_label_x = st.selectbox("Member", member_labels, key="fine_member_label")
    fine_member_id = int(label_to_legacy_id.get(mem_label_x, 0))
    fine_member_name = label_to_name.get(mem_label_x, "")

    fine_amount = st.number_input("amount (numeric)", min_value=0.0, step=500.0, value=500.0, key="fine_amount")
    fine_reason = st.text_input("reason", value="Late payment", key="fine_reason")
    fine_status = st.selectbox("status", ["unpaid", "paid"], index=0, key="fine_status")
    fine_paid_at = st.date_input("paid_at (optional)", key="fine_paid_at")
    paid_at_value = None if fine_status == "unpaid" else f"{fine_paid_at}T00:00:00Z"

    if st.button("Insert Fine", use_container_width=True, key="btn_fine_insert"):
        payload = {
            "member_id": fine_member_id,
            "member_name": fine_member_name,
            "amount": float(fine_amount),
            "reason": str(fine_reason),
            "status": str(fine_status),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        if paid_at_value:
            payload["paid_at"] = paid_at_value

        try:
            client.table("fines_legacy").insert(payload).execute()
            st.success("Fine inserted.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Fine insert failed (RLS/column mismatch)")

# ===================== PAYOUT (OPTION B - LEGACY) =====================
def legacy_payout_option_b(c):
    st_row = get_app_state(c)
    if not st_row:
        raise Exception("app_state id=1 not found or blocked by RLS")

    idx = int(st_row.get("next_payout_index") or 1)
    pot = sum_contribution_pot(c)
    if pot <= 0:
        raise Exception("Pot is zero (no kind='contribution' rows in contributions_legacy).")

    ben = fetch_one(c.table("member_registry").select("legacy_member_id,full_name").eq("legacy_member_id", idx))
    ben_name = (ben or {}).get("full_name") or f"Member {idx}"

    payout_payload = {
        "member_id": idx,
        "member_name": ben_name,
        "payout_amount": pot,
        "payout_date": str(date.today()),
        "created_at": now_iso(),
    }
    payout_inserted = False
    try:
        c.table("payouts_legacy").insert(payout_payload).execute()
        payout_inserted = True
    except Exception:
        payout_inserted = False

    c.table("contributions_legacy").update({"kind": "paid", "updated_at": now_iso()}).eq("kind", "contribution").execute()

    nxt = idx + 1
    if nxt > 17:
        nxt = 1

    next_date = (date.today() + timedelta(days=14)).isoformat()

    c.table("app_state").update({
        "next_payout_index": nxt,
        "next_payout_date": next_date,
        "updated_at": now_iso()
    }).eq("id", 1).execute()

    return {
        "beneficiary_legacy_member_id": idx,
        "beneficiary_name": ben_name,
        "pot_paid_out": pot,
        "payout_logged": payout_inserted,
        "next_payout_index": nxt,
        "next_payout_date": next_date,
    }

with tabs[tab_index("Payout (Option B)")]:
    st.subheader("Payout (Option B - Legacy)")

    st.markdown(
        """
<div class="panel">
  <div style="font-weight:900;">How payout works (Option B)</div>
  <ul style="margin-top:8px;color:var(--muted);">
    <li>Beneficiary = <b>app_state.next_payout_index</b> (legacy_member_id)</li>
    <li>Pot = sum(contributions_legacy.amount) where kind='contribution'</li>
    <li>Marks pot contributions as kind='paid' (does not delete)</li>
    <li>Advances next_payout_index (1..17 wrap) and next_payout_date (+14 days)</li>
  </ul>
</div>
""",
        unsafe_allow_html=True,
    )

    try:
        state = get_app_state(client) or {}
        idx = int(state.get("next_payout_index") or 1)
        ben = fetch_one(client.table("member_registry").select("full_name").eq("legacy_member_id", idx))
        ben_name = (ben or {}).get("full_name") or f"Member {idx}"
        pot = sum_contribution_pot(client)
        next_dt = (state.get("next_payout_date") or "unknown")

        colA, colB = st.columns([2, 1])
        with colA:
            st.info(f"Next beneficiary: **{idx} — {ben_name}**")
            st.info(f"Pot ready to pay: **{money(pot)}**")
            st.caption(f"Next payout date (from app_state): {next_dt}")
        with colB:
            st.markdown(
                "<div class='panel'><div style='font-weight:900;'>Safety</div>"
                "<div style='color:var(--muted);margin-top:6px;'>Run payout once per cycle. It clears the pot.</div></div>",
                unsafe_allow_html=True
            )
    except Exception as e:
        show_api_error(e, "Could not load payout state")

    if st.button("Run Payout Now (Option B)", use_container_width=True):
        try:
            receipt = legacy_payout_option_b(client)
            st.success("Payout completed.")
            st.json(receipt)
            st.caption("If payouts_legacy insert fails (schema mismatch), payout still clears pot and advances rotation.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Payout failed")

# ===================== JSON INSERTER =====================
with tabs[tab_index("JSON Inserter")]:
    st.subheader("Universal JSON Inserter")

    table = st.text_input("table", value="contributions_legacy", key="json_table")
    payload_text = st.text_area(
        "payload (json)",
        value='{"member_id": 1, "amount": 500, "kind": "contribution"}',
        height=220,
        key="json_payload",
    )

    if st.button("Run Insert", use_container_width=True):
        try:
            payload = json.loads(payload_text)
            client.table(table).insert(payload).execute()
            st.success("Insert OK")
        except Exception as e:
            show_api_error(e, "Insert failed")
