
import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone, timedelta

# ============================================================
# BANK DASHBOARD THEME (premium UI)
# ============================================================
st.set_page_config(page_title="Njangi Bank Dashboard", layout="wide", page_icon="🏦")

st.markdown(
    """
<style>
:root{
  --bg:#070b14;
  --surface:#0b1220;
  --card:#0f1b31;
  --text:#eef4ff;
  --muted:#a8b6d6;
  --brand:#1d4ed8;
  --good:#22c55e;
  --warn:#f59e0b;
  --danger:#ef4444;
  --border:rgba(255,255,255,0.10);
  --shadow: 0 14px 30px rgba(0,0,0,0.30);
}
.stApp{
  background: radial-gradient(1200px 700px at 20% 0%, rgba(29,78,216,0.18), transparent 60%),
              radial-gradient(1000px 600px at 90% 10%, rgba(34,197,94,0.10), transparent 55%),
              linear-gradient(180deg, var(--bg) 0%, #05070f 100%);
  color: var(--text);
}
.block-container{ padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1450px; }
h1,h2,h3{ color: var(--text); }
p,li,span,div{ color: var(--text); }
small, .stCaption, .stMarkdown p{ color: var(--muted) !important; }

section[data-testid="stSidebar"]{
  background: rgba(11, 18, 32, 0.85);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] *{ color: var(--text) !important; }

.bank-topbar{
  background: rgba(15, 27, 49, 0.75);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 16px;
  box-shadow: var(--shadow);
}
.bank-title{
  font-size: 1.25rem;
  font-weight: 950;
  letter-spacing: .2px;
}
.bank-sub{
  color: var(--muted);
  font-weight: 700;
  font-size: .86rem;
  margin-top: 3px;
}
.pill{
  display:inline-flex; align-items:center; gap:8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.04);
  font-weight: 850;
  font-size: .78rem;
}
.pill-blue{ border-color: rgba(29,78,216,0.45); background: rgba(29,78,216,0.12); color: #cfe0ff; }
.pill-green{ border-color: rgba(34,197,94,0.45); background: rgba(34,197,94,0.12); color: #d1fae5; }
.pill-warn{ border-color: rgba(245,158,11,0.45); background: rgba(245,158,11,0.12); color: #ffedd5; }
.pill-danger{ border-color: rgba(239,68,68,0.45); background: rgba(239,68,68,0.12); color: #fee2e2; }

.card{
  background: rgba(15, 27, 49, 0.75);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 14px 12px 14px;
  box-shadow: var(--shadow);
  height: 100%;
}
.kpi-title{ color: var(--muted); font-weight: 800; font-size: .82rem; letter-spacing: .2px; }
.kpi-value{ font-weight: 950; font-size: 1.40rem; margin-top: 6px; }
.kpi-sub{ color: var(--muted); font-size: .78rem; margin-top: 5px; }

.panel{
  background: rgba(12, 23, 44, 0.70);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px;
  box-shadow: 0 10px 24px rgba(0,0,0,0.22);
}

.stButton>button{
  background: linear-gradient(135deg, rgba(29,78,216,.98), rgba(37,99,235,.85));
  color: white;
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 12px;
  padding: 0.55rem 0.85rem;
  font-weight: 950;
}
.stButton>button:hover{
  background: linear-gradient(135deg, rgba(29,78,216,1), rgba(59,130,246,1));
  border-color: rgba(255,255,255,0.18);
}

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea{
  background: rgba(255,255,255,0.04) !important;
  border-radius: 12px !important;
  border-color: rgba(255,255,255,0.10) !important;
  color: var(--text) !important;
}
label{ color: var(--muted) !important; font-weight: 800 !important; }

[data-testid="stDataFrame"]{
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
}
.stTabs [data-baseweb="tab"]{ color: var(--muted); font-weight: 950; }
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
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def money(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)

def to_df(resp):
    return pd.DataFrame(resp.data or [])

def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    st.code(repr(e))

def fetch_one(qb):
    try:
        res = qb.limit(1).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:
        return None

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def safe_select_autosort(c, table: str, limit=800):
    for col in ["created_at", "issued_at", "updated_at", "paid_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def kpi(title, value, sub="", pill_text=None, pill_kind="blue"):
    pill_map = {
        "blue": "pill pill-blue",
        "green": "pill pill-green",
        "warn": "pill pill-warn",
        "danger": "pill pill-danger",
    }
    pill_html = f'<span class="{pill_map.get(pill_kind,"pill pill-blue")}">{pill_text}</span>' if pill_text else ""
    st.markdown(
        f"""
<div class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
    <div class="kpi-title">{title}</div>
    {pill_html}
  </div>
  <div class="kpi-value">{value}</div>
  <div class="kpi-sub">{sub}</div>
</div>
""",
        unsafe_allow_html=True,
    )

def download_csv_button(df: pd.DataFrame, filename: str, label: str):
    if df is None or df.empty:
        st.caption("No data to export.")
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=label,
        data=csv,
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )

def filter_df_ui(df: pd.DataFrame, key_prefix="flt"):
    if df is None or df.empty:
        return df

    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        q = st.text_input("Search", value="", key=f"{key_prefix}_q", placeholder="Search...")
    with cols[1]:
        limit = st.selectbox("Rows", [50, 100, 200, 500, 800, 1000], index=3, key=f"{key_prefix}_limit")
    with cols[2]:
        status_val = None
        if "status" in df.columns:
            opts = ["All"] + sorted([str(x) for x in df["status"].dropna().unique().tolist()])
            status_val = st.selectbox("status", opts, index=0, key=f"{key_prefix}_status")
    with cols[3]:
        kind_val = None
        if "kind" in df.columns:
            opts = ["All"] + sorted([str(x) for x in df["kind"].dropna().unique().tolist()])
            kind_val = st.selectbox("kind", opts, index=0, key=f"{key_prefix}_kind")

    out = df.copy()

    if q.strip():
        needle = q.strip().lower()
        out = out[out.astype(str).apply(lambda r: r.str.lower().str.contains(needle, na=False)).any(axis=1)]

    if "status" in out.columns and status_val and status_val != "All":
        out = out[out["status"].astype(str) == status_val]

    if "kind" in out.columns and kind_val and kind_val != "All":
        out = out[out["kind"].astype(str) == kind_val]

    return out.head(int(limit))

def get_profile(c, user_id: str):
    return fetch_one(c.table("profiles").select("id,role,approved,member_id").eq("id", user_id))

def is_admin(profile):
    return bool(profile) and str(profile.get("role") or "").lower() == "admin" and bool(profile.get("approved") is True)

def is_member(profile):
    return bool(profile) and str(profile.get("role") or "").lower() == "member" and bool(profile.get("approved") is True)

# ============================================================
# Auth UI
# ============================================================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.markdown("### 🏦 Njangi Bank Access")

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
        st.success(f"Signed in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.markdown(
        """
        <div class="panel">
          <div style="font-size:1.35rem;font-weight:950;">Welcome to Njangi Bank Dashboard</div>
          <div style="color:var(--muted);margin-top:6px;">
            Please login from the sidebar to access accounts, transactions, and loans.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ============================================================
# After login
# ============================================================
client = authed_client()
user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email

profile = get_profile(client, user_id)
if not (is_admin(profile) or is_member(profile)):
    st.warning("Your account is not approved yet. Ask admin to set profiles.approved=true.")
    st.stop()

admin_mode = is_admin(profile)

# ============================================================
# Load member_registry
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
# KPI helpers
# ============================================================
def get_app_state(c):
    return fetch_one(c.table("app_state").select("*").eq("id", 1))

def sum_contribution_pot(c):
    resp = c.table("contributions_legacy").select("amount,kind").limit(20000).execute()
    pot = 0.0
    for r in (resp.data or []):
        if (r.get("kind") or "contribution") == "contribution":
            pot += float(r.get("amount") or 0)
    return pot

def sum_total_contributions_alltime(c):
    resp = c.table("contributions_legacy").select("amount").limit(20000).execute()
    return sum(float(r.get("amount") or 0) for r in (resp.data or []))

def foundation_totals(c):
    resp = c.table("foundation_payments_legacy").select("amount_paid,amount_pending").limit(20000).execute()
    paid = sum(float(r.get("amount_paid") or 0) for r in (resp.data or []))
    pending = sum(float(r.get("amount_pending") or 0) for r in (resp.data or []))
    return paid, pending, (paid + pending)

def loans_portfolio_totals(c):
    # Portfolio view for monthly interest model
    resp = c.table("loans_legacy").select("status,total_due,balance,accrued_interest").limit(20000).execute()
    active_count = 0
    active_total_due = 0.0
    active_balance = 0.0
    active_interest = 0.0

    for r in (resp.data or []):
        if str(r.get("status") or "").lower().strip() == "active":
            active_count += 1
            active_total_due += float(r.get("total_due") or 0)
            active_balance += float(r.get("balance") or 0)
            active_interest += float(r.get("accrued_interest") or 0)

    return active_count, active_total_due, active_balance, active_interest

def fines_totals(c):
    resp = c.table("fines_legacy").select("amount,status").limit(20000).execute()
    total = 0.0
    unpaid = 0.0
    for r in (resp.data or []):
        amt = float(r.get("amount") or 0)
        total += amt
        stt = str(r.get("status") or "").lower().strip()
        if stt not in ("paid", "cleared", "settled"):
            unpaid += amt
    return total, unpaid

# Borrow capacity
def member_available_to_borrow(c, legacy_member_id: int):
    resp_c = c.table("contributions_legacy").select("amount,kind,member_id").eq("member_id", legacy_member_id).limit(20000).execute()
    paid_contrib = sum(float(r.get("amount") or 0) for r in (resp_c.data or []) if str(r.get("kind") or "").lower().strip() == "paid")

    resp_f = c.table("foundation_payments_legacy").select("amount_paid,amount_pending,member_id").eq("member_id", legacy_member_id).limit(20000).execute()
    found = sum(float(r.get("amount_paid") or 0) + float(r.get("amount_pending") or 0) for r in (resp_f.data or []))

    available = paid_contrib + (found * 0.70)
    return available, paid_contrib, found

def member_loan_totals_monthly(c, legacy_member_id: int):
    resp = c.table("loans_legacy").select("status,total_due,balance,accrued_interest").eq("member_id", legacy_member_id).limit(20000).execute()
    active_cnt = 0
    due_total = 0.0
    bal_total = 0.0
    int_total = 0.0

    for r in (resp.data or []):
        if str(r.get("status") or "").lower().strip() == "active":
            active_cnt += 1
            due_total += float(r.get("total_due") or 0)
            bal_total += float(r.get("balance") or 0)
            int_total += float(r.get("accrued_interest") or 0)

    return active_cnt, due_total, bal_total, int_total

# ============================================================
# Bank Top Bar
# ============================================================
st.markdown(
    f"""
<div class="bank-topbar">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
    <div style="display:flex;align-items:center;gap:12px;">
      <div style="width:42px;height:42px;border-radius:14px;
                  background: linear-gradient(135deg, rgba(29,78,216,.95), rgba(34,197,94,.55));
                  display:flex;align-items:center;justify-content:center;
                  font-weight:950;">
        N
      </div>
      <div>
        <div class="bank-title">Njangi Bank Dashboard</div>
        <div class="bank-sub">Accounts • Transactions • Loans • Compliance</div>
      </div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <span class="pill pill-blue">User: {user_email}</span>
      <span class="pill {'pill-green' if admin_mode else 'pill-warn'}">Mode: {"Admin" if admin_mode else "Member"}</span>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)
st.write("")

# ============================================================
# Global KPI Row + Admin Interest Button
# ============================================================
try:
    state = get_app_state(client) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben_row = fetch_one(client.table("member_registry").select("full_name").eq("legacy_member_id", next_idx))
    ben_name = (ben_row or {}).get("full_name") or f"Member {next_idx}"

    pot = sum_contribution_pot(client)
    total_contrib_all = sum_total_contributions_alltime(client)
    f_paid, f_pending, f_total = foundation_totals(client)
    active_loans, active_total_due, active_balance, active_interest = loans_portfolio_totals(client)
    fines_total, fines_unpaid = fines_totals(client)

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    with c1: kpi("Next Beneficiary", f"{next_idx} — {ben_name}", "Rotation index from app_state", pill_text="Rotation", pill_kind="blue")
    with c2: kpi("Contribution Pot", money(pot), "Sum where kind='contribution'", pill_text="Available", pill_kind=("green" if pot > 0 else "warn"))
    with c3: kpi("All-time Contributions", money(total_contrib_all), "Historical total", pill_text="Ledger", pill_kind="blue")
    with c4: kpi("Foundation Total", money(f_total), f"Paid {money(f_paid)} • Pending {money(f_pending)}", pill_text="Capital", pill_kind="blue")
    with c5: kpi("Active Loans", str(active_loans), f"Due {money(active_total_due)}", pill_text="Exposure", pill_kind=("warn" if active_total_due > 0 else "green"))
    with c6: kpi("Loan Balance", money(active_balance), f"Accrued interest {money(active_interest)}", pill_text="Monthly 5%", pill_kind="blue")
    with c7: kpi("Fines", money(fines_total), f"Unpaid {money(fines_unpaid)}", pill_text="Risk", pill_kind=("warn" if fines_unpaid > 0 else "green"))
except Exception as e:
    show_api_error(e, "Could not load KPIs")

st.write("")

# Admin button to apply monthly interest (calls DB function)
if admin_mode:
    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("Apply Monthly Interest Now (5%)", use_container_width=True):
            try:
                # This calls your SQL function: select public.apply_monthly_interest_simple();
                res = client.rpc("apply_monthly_interest_simple", {}).execute()
                # supabase may return scalar in data, handle both patterns
                applied = 0
                if isinstance(res.data, int):
                    applied = res.data
                elif isinstance(res.data, list) and len(res.data) > 0:
                    # sometimes returned like [{"apply_monthly_interest_simple": 2}]
                    applied = list(res.data[0].values())[0]
                st.success(f"Interest applied to {applied} loan(s).")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Could not apply monthly interest (check function/RLS)")
    with colB:
        st.markdown(
            "<div class='panel'><b>Monthly interest rule:</b> 5% per month from borrow date. "
            "Interest is applied only when a full month has passed since last_interest_at.</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ============================================================
# Tabs
# ============================================================
tab_names_admin = [
    "Overview (Charts)",
    "Members",
    "Transactions (Contributions)",
    "Foundation",
    "Loans",
    "Fines",
    "Payout (Option B)",
    "Borrow Capacity",
    "Audit Log",
    "JSON Inserter",
]
tab_names_member = [
    "Overview (Charts)",
    "Members",
    "Borrow Capacity",
]

tabs = st.tabs(tab_names_admin if admin_mode else tab_names_member)

def tab_index(name: str) -> int:
    names = tab_names_admin if admin_mode else tab_names_member
    return names.index(name)

# ============================================================
# Overview (Charts)
# ============================================================
with tabs[tab_index("Overview (Charts)")]:
    st.subheader("Portfolio Overview")
    st.caption("Charts use created_at/issued_at timestamps. Apply monthly interest from the top button (admin).")

    # Contributions trend
    st.markdown("#### Contributions Trend")
    try:
        df_contrib = to_df(safe_select_autosort(client, "contributions_legacy", limit=5000))
    except Exception:
        df_contrib = pd.DataFrame()

    if not df_contrib.empty and any(c in df_contrib.columns for c in ["created_at", "updated_at"]):
        ts_col = "created_at" if "created_at" in df_contrib.columns else "updated_at"
        d = df_contrib.copy()
        d[ts_col] = pd.to_datetime(d[ts_col], errors="coerce")
        d = d.dropna(subset=[ts_col])
        d["day"] = d[ts_col].dt.date
        d["amount"] = pd.to_numeric(d.get("amount"), errors="coerce").fillna(0)
        d["kind"] = d.get("kind", "unknown").astype(str)
        trend = d.groupby(["day", "kind"], as_index=False)["amount"].sum()
        pivot = trend.pivot(index="day", columns="kind", values="amount").fillna(0)
        st.line_chart(pivot)
    else:
        st.info("No contribution timestamps available (or RLS blocked).")

    # Loans by status + exposure
    st.markdown("#### Loans by Status (Count) + Exposure (Total Due)")
    try:
        df_loans = to_df(safe_select_autosort(client, "loans_legacy", limit=5000))
    except Exception:
        df_loans = pd.DataFrame()

    if not df_loans.empty and "status" in df_loans.columns:
        l = df_loans.copy()
        l["status"] = l["status"].astype(str).str.lower().str.strip()
        counts = l["status"].value_counts().sort_index()
        st.bar_chart(counts)

        if "total_due" in l.columns:
            l["total_due"] = pd.to_numeric(l["total_due"], errors="coerce").fillna(0)
            exposure = l.groupby("status")["total_due"].sum().sort_index()
            st.bar_chart(exposure)
    else:
        st.info("No loans/status data available (or RLS blocked).")

    # Fines breakdown
    st.markdown("#### Fines Breakdown")
    try:
        df_fines = to_df(safe_select_autosort(client, "fines_legacy", limit=5000))
    except Exception:
        df_fines = pd.DataFrame()

    if not df_fines.empty and "status" in df_fines.columns:
        f = df_fines.copy()
        f["amount"] = pd.to_numeric(f.get("amount"), errors="coerce").fillna(0)
        f["status"] = f["status"].astype(str).str.lower().str.strip()
        breakdown = f.groupby("status", as_index=True)["amount"].sum().sort_index()
        st.bar_chart(breakdown)
    else:
        st.info("No fines/status data available (or RLS blocked).")

# ============================================================
# Members
# ============================================================
with tabs[tab_index("Members")]:
    st.subheader("Members")
    if df_registry.empty:
        st.info("No members found (or RLS blocked).")
    else:
        df_show = filter_df_ui(df_registry, key_prefix="mem")
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        download_csv_button(df_registry, "members.csv", "Download Members CSV")

# ============================================================
# Borrow Capacity (Member + Admin)
# ============================================================
with tabs[tab_index("Borrow Capacity")]:
    st.subheader("Borrow Capacity (Per Member)")
    st.caption("Rule: available = paid_contributions(kind='paid') + 0.70 × (foundation paid+pending).")

    pick = st.selectbox("Select member", member_labels, key="cap_member")
    mid = int(label_to_legacy_id.get(pick, 0))
    name = label_to_name.get(pick, "")

    try:
        avail, paid_contrib, found = member_available_to_borrow(client, mid)
        active_cnt, due_total, bal_total, int_total = member_loan_totals_monthly(client, mid)

        a, b, c, d, e, f = st.columns(6)
        with a: kpi("Member", f"{mid} — {name}", "Legacy member id", pill_text="Account", pill_kind="blue")
        with b: kpi("Paid Contributions", money(paid_contrib), "Counted kind='paid'", pill_text="Eligible", pill_kind="blue")
        with c: kpi("Foundation", money(found), "paid + pending", pill_text="Capital", pill_kind="blue")
        with d: kpi("Available to Borrow", money(avail), "paid + 0.70×foundation", pill_text="Limit", pill_kind="green")
        with e: kpi("Active Loans", str(active_cnt), f"Due {money(due_total)}", pill_text="Exposure", pill_kind=("warn" if active_cnt > 0 else "green"))
        with f: kpi("Balance + Interest", money(bal_total + int_total), f"Bal {money(bal_total)} + Int {money(int_total)}", pill_text="Monthly", pill_kind="blue")
    except Exception as e:
        show_api_error(e, "Could not compute borrow capacity/loans")

# Stop here for members
if not admin_mode:
    st.info("Member mode: read-only access.")
    st.stop()

# ============================================================
# Admin Tabs
# ============================================================

# --------------------- Transactions (Contributions) ---------------------
with tabs[tab_index("Transactions (Contributions)")]:
    st.subheader("Transactions: Contributions (Legacy)")
    st.caption("Filter, export, and insert contributions.")

    try:
        df = to_df(safe_select_autosort(client, "contributions_legacy", limit=1500))
        df_view = filter_df_ui(df, key_prefix="contrib")
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        download_csv_button(df, "contributions_legacy.csv", "Download Contributions CSV")
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

    st.divider()
    st.markdown("### New Contribution Transaction")

    mem_label = st.selectbox("Member", member_labels, key="c_member_label")
    legacy_id = int(label_to_legacy_id.get(mem_label, 0))
    amount = st.number_input("amount (int)", min_value=0, step=500, value=500, key="c_amount")
    kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
    session_id = st.text_input("session_id (uuid optional)", value="", key="c_session_id")

    if st.button("Post Contribution", use_container_width=True):
        payload = {
            "member_id": legacy_id,
            "amount": int(amount),
            "kind": str(kind),
            "created_at": now_iso(),   # keep created_at
            # updated_at NOT needed (DB trigger handles)
        }
        if session_id.strip():
            payload["session_id"] = session_id.strip()

        try:
            client.table("contributions_legacy").insert(payload).execute()
            st.success("Contribution posted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS/constraints)")

# --------------------- Foundation ---------------------
with tabs[tab_index("Foundation")]:
    st.subheader("Foundation Ledger (Legacy)")
    st.caption("Filter/export + insert foundation payments.")

    try:
        df = to_df(safe_select_autosort(client, "foundation_payments_legacy", limit=1500))
        df_view = filter_df_ui(df, key_prefix="found")
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        download_csv_button(df, "foundation_payments_legacy.csv", "Download Foundation CSV")
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

    st.divider()
    st.markdown("### New Foundation Entry")

    mem_label_f = st.selectbox("Member", member_labels, key="f_member_label")
    legacy_id_f = int(label_to_legacy_id.get(mem_label_f, 0))

    amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="f_paid")
    amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="f_pending")
    status = st.selectbox("status", ["paid", "pending", "converted"], index=0, key="f_status")
    date_paid = st.date_input("date_paid", key="f_date_paid")
    converted_to_loan = st.selectbox("converted_to_loan", [False, True], index=0, key="f_conv")
    notes_f = st.text_input("notes (optional)", value="", key="f_notes")

    if st.button("Post Foundation Payment", use_container_width=True):
        payload = {
            "member_id": legacy_id_f,
            "amount_paid": float(amount_paid),
            "amount_pending": float(amount_pending),
            "status": str(status),
            "date_paid": f"{date_paid}T00:00:00Z",
            "converted_to_loan": bool(converted_to_loan),
            "created_at": now_iso(),   # your table now has created_at
        }
        if notes_f.strip():
            payload["notes"] = notes_f.strip()

        try:
            client.table("foundation_payments_legacy").insert(payload).execute()
            st.success("Foundation payment posted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS/constraints)")

# --------------------- Loans (Monthly 5%) ---------------------
with tabs[tab_index("Loans")]:
    st.subheader("Loans Portfolio (Monthly Interest)")
    st.caption("Monthly interest = 5% per month from issued_at. Admin can apply interest from top button.")

    try:
        df = to_df(safe_select_autosort(client, "loans_legacy", limit=1500))
        df_view = filter_df_ui(df, key_prefix="loans")
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        download_csv_button(df, "loans_legacy.csv", "Download Loans CSV")
    except Exception as e:
        show_api_error(e, "Could not load loans_legacy")

    st.divider()
    st.markdown("### Issue New Loan (Monthly 5%)")

    borrower_label = st.selectbox("Borrower", member_labels, key="loan_borrower_label")
    borrower_member_id = int(label_to_legacy_id.get(borrower_label, 0))
    borrower_name = label_to_name.get(borrower_label, "")

    surety_label = st.selectbox("Surety", member_labels, key="loan_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input("principal", min_value=500.0, step=500.0, value=500.0, key="loan_principal")
    status = st.selectbox("status", ["active", "pending", "closed", "paid"], index=0, key="loan_status")

    # NOTE: for monthly model, we do NOT set interest upfront.
    st.info("Monthly interest: 5% per month from borrow date. Interest will be added when a full month passes.")

    # capacity check
    try:
        b_avail, b_paid, b_found = member_available_to_borrow(client, borrower_member_id)
        st.markdown(
            f"""
<div class="panel">
  <div style="font-weight:950;">Capacity Check</div>
  <div style="color:var(--muted);margin-top:8px;">
    Paid contributions <b>{money(b_paid)}</b> + 70% foundation <b>{money(b_found*0.70)}</b> = <b>{money(b_avail)}</b>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        if principal > b_avail:
            st.warning("Requested principal is higher than calculated capacity (paid + 70% foundation).")
    except Exception:
        pass

    if st.button("Issue Loan", use_container_width=True):
        issued = now_iso()
        payload = {
            "member_id": borrower_member_id,
            "borrower_member_id": borrower_member_id,
            "surety_member_id": surety_member_id,
            "borrower_name": borrower_name,
            "surety_name": surety_name,

            # principal/balance
            "principal": float(principal),
            "balance": float(principal),

            # monthly interest tracking fields (must exist in DB)
            "interest_rate_monthly": 0.05,
            "accrued_interest": 0.0,
            "interest_start_at": issued,
            "last_interest_at": issued,

            # due starts as principal; interest will accrue monthly via SQL function
            "total_due": float(principal),

            "issued_at": issued,
            "created_at": issued,
            "status": str(status),
        }

        try:
            client.table("loans_legacy").insert(payload).execute()
            st.success("Loan issued successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (missing columns/RLS/constraints)")

# --------------------- Fines ---------------------
with tabs[tab_index("Fines")]:
    st.subheader("Fines Ledger (Legacy)")
    st.caption("Filter/export + post fines.")

    try:
        df = to_df(safe_select_autosort(client, "fines_legacy", limit=1500))
        df_view = filter_df_ui(df, key_prefix="fines")
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        download_csv_button(df, "fines_legacy.csv", "Download Fines CSV")
    except Exception as e:
        show_api_error(e, "Could not load fines_legacy")

    st.divider()
    st.markdown("### Post Fine")

    mem_label_x = st.selectbox("Member", member_labels, key="fine_member_label")
    fine_member_id = int(label_to_legacy_id.get(mem_label_x, 0))
    fine_member_name = label_to_name.get(mem_label_x, "")

    fine_amount = st.number_input("amount", min_value=0.0, step=500.0, value=500.0, key="fine_amount")
    fine_reason = st.text_input("reason", value="Late payment", key="fine_reason")
    fine_status = st.selectbox("status", ["unpaid", "paid"], index=0, key="fine_status")
    fine_paid_at = st.date_input("paid_at (optional)", key="fine_paid_at")
    paid_at_value = None if fine_status == "unpaid" else f"{fine_paid_at}T00:00:00Z"

    if st.button("Post Fine", use_container_width=True):
        payload = {
            "member_id": fine_member_id,
            "member_name": fine_member_name,
            "amount": float(fine_amount),
            "reason": str(fine_reason),
            "status": str(fine_status),
            "created_at": now_iso(),
        }
        if paid_at_value:
            payload["paid_at"] = paid_at_value

        try:
            client.table("fines_legacy").insert(payload).execute()
            st.success("Fine posted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Insert failed (RLS/constraints)")

# --------------------- Payout (Option B) ---------------------
def legacy_payout_option_b(c):
    st_row = get_app_state(c)
    if not st_row:
        raise Exception("app_state id=1 not found or blocked by RLS")

    idx = int(st_row.get("next_payout_index") or 1)
    pot = sum_contribution_pot(c)
    if pot <= 0:
        raise Exception("Pot is zero (no kind='contribution' rows).")

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

    c.table("contributions_legacy").update({"kind": "paid"}).eq("kind", "contribution").execute()

    nxt = idx + 1
    if nxt > 17:
        nxt = 1
    next_date = (date.today() + timedelta(days=14)).isoformat()

    c.table("app_state").update({
        "next_payout_index": nxt,
        "next_payout_date": next_date,
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
    st.subheader("Payout Processor (Option B)")
    st.caption("Clears pot (kind='contribution' -> 'paid') and advances rotation.")

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
            st.info(f"Pot ready: **{money(pot)}**")
            st.caption(f"Next payout date: {next_dt}")
        with colB:
            st.markdown(
                "<div class='panel'><div style='font-weight:950;'>Risk Controls</div>"
                "<div style='color:var(--muted);margin-top:8px;'>Run once per cycle. Clears pot and advances rotation.</div></div>",
                unsafe_allow_html=True
            )
    except Exception as e:
        show_api_error(e, "Could not load payout state")

    if st.button("Run Payout Now", use_container_width=True):
        try:
            with st.spinner("Executing payout..."):
                receipt = legacy_payout_option_b(client)
            st.success("Payout completed.")
            st.json(receipt)
            st.rerun()
        except Exception as e:
            show_api_error(e, "Payout failed")

# --------------------- Audit Log ---------------------
with tabs[tab_index("Audit Log")]:
    st.subheader("Audit Log (Admin)")
    st.caption("Compliance trail. If blank, check RLS on audit_log.")

    try:
        df_audit = to_df(safe_select_autosort(client, "audit_log", limit=800))
        if df_audit.empty:
            st.info("No audit entries found (or RLS blocked).")
        else:
            df_view = filter_df_ui(df_audit, key_prefix="audit")
            st.dataframe(df_view, use_container_width=True, hide_index=True)
            download_csv_button(df_audit, "audit_log.csv", "Download Audit Log CSV")
    except Exception as e:
        show_api_error(e, "Could not load audit_log")

# --------------------- JSON Inserter ---------------------
with tabs[tab_index("JSON Inserter")]:
    st.subheader("Universal JSON Inserter")
    st.caption("Admin tool: inserts raw JSON into any table (use carefully).")

    table = st.text_input("table", value="contributions_legacy", key="json_table")
    payload_text = st.text_area(
        "payload (json)",
        value='{"member_id": 1, "amount": 500, "kind": "contribution", "created_at": "2026-01-01T00:00:00Z"}',
        height=220,
        key="json_payload",
    )

    if st.button("Run Insert", use_container_width=True):
        try:
            payload = json.loads(payload_text)
            payload.setdefault("created_at", now_iso())
            client.table(table).insert(payload).execute()
            st.success("Insert OK")
        except Exception as e:
            show_api_error(e, "Insert failed")
