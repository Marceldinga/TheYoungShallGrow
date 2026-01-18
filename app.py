import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone
from postgrest.exceptions import APIError

# -------------------- Header --------------------
st.markdown(
    """
<div class="nj-header">
  <div>
    <p class="nj-title">The Young Shall Grow — Njangi Dashboard (Legacy)</p>
    <p class="nj-sub">Admin manages data • Members can only request loans • Clean, colorful view</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------- Page --------------------
st.set_page_config(page_title="The Young Shall Grow — Njangi Dashboard (Legacy)", layout="wide")

# -------------------- CSS (Appearance) --------------------
CUSTOM_CSS = """
<style>
/* Global */
.block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1250px; }
h1, h2, h3 { letter-spacing: -0.02em; }
small { opacity: 0.8; }

/* Header */
.nj-header {
  display:flex; align-items:center; justify-content:space-between;
  padding: 14px 16px; border-radius: 18px;
  background: linear-gradient(90deg, rgba(99,102,241,0.18), rgba(16,185,129,0.14), rgba(245,158,11,0.12));
  border: 1px solid rgba(148,163,184,0.25);
}
.nj-title { font-size: 28px; font-weight: 800; margin: 0; }
.nj-sub { margin: 0; opacity: 0.85; font-size: 13px; }

/* KPI cards */
.kpi-wrap { display:flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
.kpi {
  flex: 1 1 180px; min-width: 180px;
  padding: 14px 14px; border-radius: 18px;
  background: rgba(2,6,23,0.04);
  border: 1px solid rgba(148,163,184,0.22);
}
.kpi .label { font-size: 12px; opacity: 0.75; margin-bottom: 6px; }
.kpi .value { font-size: 24px; font-weight: 800; line-height: 1.1; }
.kpi .hint { font-size: 12px; opacity: 0.75; margin-top: 6px; }
.kpi.blue { background: rgba(99,102,241,0.10); }
.kpi.green { background: rgba(16,185,129,0.10); }
.kpi.amber { background: rgba(245,158,11,0.10); }
.kpi.rose { background: rgba(244,63,94,0.09); }
.kpi.cyan { background: rgba(6,182,212,0.10); }
.kpi.slate { background: rgba(100,116,139,0.10); }

/* Cards */
.card {
  padding: 14px 14px; border-radius: 18px;
  border: 1px solid rgba(148,163,184,0.22);
  background: rgba(255,255,255,0.03);
}

/* Buttons */
.stButton>button {
  border-radius: 14px;
  padding: 10px 14px;
  font-weight: 700;
}

/* Dataframe */
[data-testid="stDataFrame"] { border-radius: 16px; overflow:hidden; border: 1px solid rgba(148,163,184,0.18); }

/* Sidebar */
section[data-testid="stSidebar"] {
  border-right: 1px solid rgba(148,163,184,0.18);
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

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

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    if isinstance(e, APIError):
        st.code(e.message)
    else:
        st.code(repr(e))

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def safe_select_autosort(c, table: str, limit=400):
    for col in ["created_at", "issued_at", "updated_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def load_member_registry(c):
    """
    member_registry:
      legacy_member_id (int), full_name (text), phone (text), is_active (bool), created_at (timestamptz)
    """
    resp = c.table("member_registry").select("legacy_member_id,full_name,is_active,phone,created_at").order("legacy_member_id").execute()
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

def get_profile(c, user_id: str):
    # profiles: id (uuid, same as auth user id), role ('admin'/'member'), member_id (bigint), full_name, phone, email
    try:
        return c.table("profiles").select("*").eq("id", user_id).single().execute().data
    except Exception:
        return None

def is_admin_profile(profile: dict | None) -> bool:
    if not profile:
        return False
    return str(profile.get("role") or "").lower() == "admin"

def get_app_state(c):
    try:
        return c.table("app_state").select("*").eq("id", 1).single().execute().data
    except Exception:
        return None

def sum_contribution_pot(c):
    # Legacy pot = all contributions_legacy with kind = 'contribution'
    resp = c.table("contributions_legacy").select("amount,kind").limit(10000).execute()
    rows = resp.data or []
    pot = 0
    for r in rows:
        if (r.get("kind") or "contribution") == "contribution":
            try:
                pot += int(r.get("amount") or 0)
            except Exception:
                pass
    return pot

def sum_total_contributions_alltime(c):
    resp = c.table("contributions_legacy").select("amount").limit(10000).execute()
    rows = resp.data or []
    total = 0
    for r in rows:
        try:
            total += int(r.get("amount") or 0)
        except Exception:
            pass
    return total

def foundation_totals(c):
    # foundation total (paid + pending), and paid only
    resp = c.table("foundation_payments_legacy").select("amount_paid,amount_pending").limit(10000).execute()
    rows = resp.data or []
    paid = 0.0
    pending = 0.0
    for r in rows:
        paid += float(r.get("amount_paid") or 0)
        pending += float(r.get("amount_pending") or 0)
    return paid, pending, (paid + pending)

def loans_interest_totals(c):
    # total interest generated (or accumulated)
    resp = c.table("loans_legacy").select("total_interest_generated,total_interest_accumulated,interest,unpaid_interest,status").limit(10000).execute()
    rows = resp.data or []
    total_gen = 0.0
    total_acc = 0.0
    unpaid = 0.0
    active_count = 0
    for r in rows:
        total_gen += float(r.get("total_interest_generated") or 0)
        total_acc += float(r.get("total_interest_accumulated") or 0)
        unpaid += float(r.get("unpaid_interest") or 0)
        if str(r.get("status") or "").lower() == "active":
            active_count += 1
    total_interest = total_gen if total_gen > 0 else total_acc
    return total_interest, unpaid, active_count

def member_available_to_borrow(c, legacy_member_id: int):
    """
    Legacy borrow capacity used by your dashboard:
      capacity = sum(contributions_legacy where kind='contribution') + 0.70 * sum(foundation (paid+pending))
    NOTE: contributions_legacy and foundation_payments_legacy use member_id (legacy int)
    """
    # contributions
    resp_c = c.table("contributions_legacy").select("amount,kind,member_id").eq("member_id", legacy_member_id).limit(10000).execute()
    rows_c = resp_c.data or []
    contrib = 0.0
    for r in rows_c:
        if (r.get("kind") or "contribution") == "contribution":
            contrib += float(r.get("amount") or 0)

    # foundation
    resp_f = c.table("foundation_payments_legacy").select("amount_paid,amount_pending,member_id").eq("member_id", legacy_member_id).limit(10000).execute()
    rows_f = resp_f.data or []
    found = 0.0
    for r in rows_f:
        found += float(r.get("amount_paid") or 0) + float(r.get("amount_pending") or 0)

    return contrib + (found * 0.70), contrib, found

def legacy_payout_option_b(c):
    st_row = c.table("app_state").select("*").eq("id", 1).single().execute().data
    if not st_row:
        raise Exception("app_state id=1 not found")

    idx = int(st_row.get("next_payout_index") or 1)
    pot = sum_contribution_pot(c)
    if pot <= 0:
        raise Exception("Pot is zero (no kind='contribution' rows in contributions_legacy).")

    ben = c.table("member_registry").select("legacy_member_id,full_name").eq("legacy_member_id", idx).single().execute().data
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

    c.table("app_state").update({
        "next_payout_index": nxt,
        "next_payout_date": str(date.today()),
        "updated_at": now_iso()
    }).eq("id", 1).execute()

    return {
        "beneficiary_legacy_member_id": idx,
        "beneficiary_name": ben_name,
        "pot_paid_out": pot,
        "payout_logged": payout_inserted,
        "next_payout_index": nxt
    }

# -------------------- Header --------------------
st.markdown(
    """
<div class="nj-header">
  <div>
    <p class="nj-title">Njangi Dashboard (Legacy)</p>
    <p class="nj-sub">Admin manages data • Members can only request loans • Clean, colorful view</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# -------------------- Auth state --------------------
if "session" not in st.session_state:
    st.session_state.session = None

# -------------------- Sidebar (Login/Signup) --------------------
with st.sidebar:
    st.header("Account")

    # Setup SQL (so you can paste into Supabase SQL Editor)
    with st.expander("Setup SQL (run once in Supabase)", expanded=False):
        st.code(
            """
-- 1) PROFILES TABLE
create table if not exists public.profiles (
  id uuid primary key,                         -- auth.users.id
  email text,
  role text not null default 'member',         -- 'admin' or 'member'
  member_id bigint,                            -- legacy member id (1..17)
  full_name text,
  phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Members can read/update their own profile
create policy if not exists "profiles_select_own"
on public.profiles for select
using (auth.uid() = id);

create policy if not exists "profiles_upsert_own"
on public.profiles for insert
with check (auth.uid() = id);

create policy if not exists "profiles_update_own"
on public.profiles for update
using (auth.uid() = id);

-- OPTIONAL: make first admin manually
-- update public.profiles set role='admin' where email='YOUR_ADMIN_EMAIL';

-- 2) LOAN REQUESTS TABLE (members write here, admin approves into loans_legacy)
create table if not exists public.loan_requests_legacy (
  id bigint generated by default as identity primary key,
  requester_user_id uuid not null,            -- auth.uid()
  borrower_member_id bigint not null,
  borrower_name text,
  surety_member_id bigint not null,
  surety_name text,
  principal numeric not null,
  status text not null default 'pending',     -- pending/approved/rejected
  admin_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.loan_requests_legacy enable row level security;

-- Members can insert requests for themselves
create policy if not exists "loanreq_insert_own"
on public.loan_requests_legacy for insert
with check (auth.uid() = requester_user_id);

-- Members can view their own requests
create policy if not exists "loanreq_select_own"
on public.loan_requests_legacy for select
using (auth.uid() = requester_user_id);

-- Admin can read all requests (simple email allowlist fallback is handled in app,
-- but DB-side admin check can be done via profiles role)
create or replace function public.is_admin()
returns boolean language sql stable as $$
  select exists(select 1 from public.profiles p where p.id = auth.uid() and lower(p.role)='admin');
$$;

create policy if not exists "loanreq_admin_select_all"
on public.loan_requests_legacy for select
using (public.is_admin());

create policy if not exists "loanreq_admin_update"
on public.loan_requests_legacy for update
using (public.is_admin());

-- IMPORTANT: Keep RLS on legacy tables strict so only admin can insert/update.
-- You should ensure policies on contributions_legacy/foundation_payments_legacy/loans_legacy
-- allow inserts/updates only for admin.
            """.strip(),
            language="sql",
        )

    if st.session_state.session is None:
        auth_tab = st.radio("Choose", ["Login", "Sign up"], horizontal=True)

        if auth_tab == "Login":
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", use_container_width=True, key="btn_login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.session = res.session
                    st.rerun()
                except Exception as e:
                    show_api_error(e, "Login failed")

        else:
            st.caption("Sign up as a member. After signup, you will complete your member profile.")
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password", type="password", key="su_password")
            if st.button("Create account", use_container_width=True, key="btn_signup"):
                try:
                    sb.auth.sign_up({"email": email, "password": password})
                    st.success("Account created. Now login with your email/password.")
                except Exception as e:
                    show_api_error(e, "Sign up failed")

    else:
        user_email = st.session_state.session.user.email
        st.success(f"Logged in: {user_email}")
        if st.button("Logout", use_container_width=True, key="btn_logout"):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

# Stop if not logged in
if st.session_state.session is None:
    st.stop()

client = authed_client()
user = client.auth.get_user()
user_id = user.user.id
user_email = user.user.email

# -------------------- Load members registry --------------------
member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

# -------------------- Load profile / role --------------------
profile = get_profile(client, user_id)
is_admin = is_admin_profile(profile)

# If no profile row yet, ask user to create it (self-serve)
if not profile:
    st.warning("Complete your profile to continue.")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        full_name = st.text_input("Full name", value="")
        phone = st.text_input("Phone", value="")
    with c2:
        member_label = st.selectbox("Select your member record (legacy_member_id)", member_labels)
        member_id = int(label_to_legacy_id.get(member_label, 0))
        st.caption("This links your login to your Njangi member ID.")
    if st.button("Save Profile", use_container_width=True):
        if member_id <= 0:
            st.error("Invalid member selection.")
        else:
            payload = {
                "id": user_id,
                "email": user_email,
                "role": "member",
                "member_id": member_id,
                "full_name": full_name.strip() or label_to_name.get(member_label, ""),
                "phone": phone.strip(),
                "updated_at": now_iso(),
            }
            try:
                client.table("profiles").upsert(payload).execute()
                st.success("Profile saved. Reloading...")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Profile save failed (check profiles table + RLS).")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# Member_id from profile (for member portal)
my_member_id = int(profile.get("member_id") or 0)
my_name = (profile.get("full_name") or "").strip()

# -------------------- Top KPIs --------------------
try:
    state = get_app_state(client) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben = client.table("member_registry").select("full_name").eq("legacy_member_id", next_idx).single().execute().data
    ben_name = (ben or {}).get("full_name") or f"Member {next_idx}"

    pot = sum_contribution_pot(client)
    total_contrib_all = sum_total_contributions_alltime(client)

    f_paid, f_pending, f_total = foundation_totals(client)
    total_interest, unpaid_interest, active_loans = loans_interest_totals(client)

    st.markdown('<div class="kpi-wrap">', unsafe_allow_html=True)
    st.markdown(f"""
      <div class="kpi blue">
        <div class="label">Current beneficiary</div>
        <div class="value">{next_idx} — {ben_name}</div>
        <div class="hint">Rotation uses app_state.next_payout_index</div>
      </div>
      <div class="kpi green">
        <div class="label">Contribution pot (ready)</div>
        <div class="value">{pot:,.0f}</div>
        <div class="hint">kind='contribution'</div>
      </div>
      <div class="kpi cyan">
        <div class="label">All-time contributions</div>
        <div class="value">{total_contrib_all:,.0f}</div>
        <div class="hint">All rows in contributions_legacy</div>
      </div>
      <div class="kpi amber">
        <div class="label">Total foundation (paid+pending)</div>
        <div class="value">{f_total:,.0f}</div>
        <div class="hint">amount_paid + amount_pending</div>
      </div>
      <div class="kpi rose">
        <div class="label">Total interest generated</div>
        <div class="value">{total_interest:,.0f}</div>
        <div class="hint">generated/accumulated (legacy)</div>
      </div>
      <div class="kpi slate">
        <div class="label">Active loans</div>
        <div class="value">{active_loans}</div>
        <div class="hint">status='active'</div>
      </div>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
except Exception as e:
    show_api_error(e, "Could not load dashboard KPIs")

st.divider()

# =============================================================================
# MEMBER PORTAL (Non-admin): Only request loan + view own capacity + view own requests
# =============================================================================
def member_portal():
    st.subheader("Member Portal")
    st.caption("As a member, you can only request a loan. Admin will approve and create the actual loan record.")

    # My capacity
    try:
        avail, contrib, found = member_available_to_borrow(client, my_member_id)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Your Borrow Capacity", f"{avail:,.0f}")
        c2.metric("Your Contributions (counted)", f"{contrib:,.0f}")
        c3.metric("Your Foundation used (70%)", f"{(found*0.70):,.0f}")
        st.caption("Rule: capacity = contributions(kind='contribution') + 0.70 × (foundation paid + pending)")
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        show_api_error(e, "Could not compute your borrow capacity")

    st.divider()
    st.markdown("### Request a Loan")

    # Surety required for all members (self-surety allowed if eligible, but still requires a surety field)
    surety_label = st.selectbox("Choose your Surety (required)", member_labels, key="m_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input("Requested amount (principal)", min_value=500.0, step=500.0, value=500.0, key="m_principal")

    # Display quick check (not enforcement; DB trigger/RLS should enforce rules)
    try:
        my_avail, _, _ = member_available_to_borrow(client, my_member_id)
        surety_avail, _, _ = member_available_to_borrow(client, surety_member_id) if surety_member_id > 0 else (0,0,0)
        st.info(
            f"Capacity check: You {my_avail:,.0f} | Surety {surety_avail:,.0f} | Combined {(my_avail + surety_avail):,.0f}"
        )
    except Exception:
        pass

    if st.button("Submit Loan Request", use_container_width=True, key="btn_submit_request"):
        if my_member_id <= 0:
            st.error("Your profile has no member_id. Please complete your profile.")
            return
        if surety_member_id <= 0:
            st.error("Surety is required.")
            return

        payload = {
            "requester_user_id": user_id,
            "borrower_member_id": my_member_id,
            "borrower_name": my_name or f"Member {my_member_id}",
            "surety_member_id": surety_member_id,
            "surety_name": surety_name,
            "principal": float(principal),
            "status": "pending",
            "updated_at": now_iso(),
        }

        try:
            client.table("loan_requests_legacy").insert(payload).execute()
            st.success("Loan request submitted. Admin will review.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan request failed (check loan_requests_legacy table + RLS).")

    st.divider()
    st.markdown("### My Loan Requests")
    try:
        resp = client.table("loan_requests_legacy") \
            .select("*") \
            .eq("requester_user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(200).execute()
        st.dataframe(pd.DataFrame(resp.data or []), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load your loan requests")

# =============================================================================
# ADMIN DASHBOARD: full data management + approve requests into loans_legacy
# =============================================================================
def admin_dashboard():
    st.subheader("Admin Dashboard")
    st.caption("Admin can add data. Members can only request loans.")

    tabs = st.tabs([
        "Members",
        "Contributions (Legacy)",
        "Foundation (Legacy)",
        "Loans (Legacy)",
        "Loan Requests (Approve)",
        "Payout (Option B)",
        "Member Borrow Capacity",
        "JSON Inserter (Admin)"
    ])

    # ===================== MEMBERS =====================
    with tabs[0]:
        st.subheader("member_registry")
        st.dataframe(df_registry, use_container_width=True)

    # ===================== CONTRIBUTIONS (LEGACY) =====================
    with tabs[1]:
        st.subheader("contributions_legacy")
        try:
            st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy", limit=800)), use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load contributions_legacy")

        st.divider()
        st.markdown("### Insert Contribution (admin only)")
        mem_label = st.selectbox("Member", member_labels, key="c_member_label")
        legacy_id = int(label_to_legacy_id.get(mem_label, 0))
        st.caption(f"member_id (legacy): **{legacy_id}**")

        amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
        kind = st.selectbox("kind", ["contribution", "paid", "other"], index=0, key="c_kind")
        session_id = st.text_input("session_id (uuid optional)", value="", key="c_session_id")

        if st.button("Insert Contribution", use_container_width=True, key="btn_c_insert"):
            payload = {"member_id": legacy_id, "amount": int(amount), "kind": str(kind), "updated_at": now_iso()}
            if session_id.strip():
                payload["session_id"] = session_id.strip()
            try:
                client.table("contributions_legacy").insert(payload).execute()
                st.success("Contribution inserted.")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Contribution insert failed (RLS or invalid data)")

    # ===================== FOUNDATION (LEGACY) =====================
    with tabs[2]:
        st.subheader("foundation_payments_legacy")
        try:
            st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy", limit=800)), use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load foundation_payments_legacy")

        st.divider()
        st.markdown("### Insert Foundation Payment (admin only)")

        mem_label_f = st.selectbox("Member", member_labels, key="f_member_label")
        legacy_id_f = int(label_to_legacy_id.get(mem_label_f, 0))
        st.caption(f"member_id (legacy): **{legacy_id_f}**")

        amount_paid = st.number_input("amount_paid", min_value=0.0, step=500.0, value=500.0, key="f_paid")
        amount_pending = st.number_input("amount_pending", min_value=0.0, step=500.0, value=0.0, key="f_pending")
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
                "updated_at": now_iso()
            }
            if notes_f.strip():
                payload["notes"] = notes_f.strip()

            try:
                client.table("foundation_payments_legacy").insert(payload).execute()
                st.success("Foundation payment inserted.")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Foundation insert failed (RLS or invalid data)")

    # ===================== LOANS (LEGACY) =====================
    with tabs[3]:
        st.subheader("loans_legacy")
        try:
            st.dataframe(to_df(client.table("loans_legacy").select("*").order("created_at", desc=True).limit(400).execute()), use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load loans_legacy")

        st.divider()
        st.markdown("### Insert Loan (admin only)")
        borrower_label = st.selectbox("Borrower", member_labels, key="loan_borrower_label")
        borrower_member_id = int(label_to_legacy_id.get(borrower_label, 0))
        borrower_name = label_to_name.get(borrower_label, "")

        surety_label = st.selectbox("Surety", member_labels, key="loan_surety_label")
        surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
        surety_name = label_to_name.get(surety_label, "")

        principal = st.number_input("principal", min_value=500.0, step=500.0, value=500.0, key="loan_principal")
        interest_cycle_days = st.number_input("interest_cycle_days", min_value=1, value=26, step=1, key="loan_cycle_days")
        status = st.selectbox("status", ["active", "pending", "closed", "paid"], index=0, key="loan_status")

        # 5% interest upfront (legacy UI)
        interest = float(principal) * 0.05
        total_due = float(principal) + interest
        st.caption(f"Interest (5%): {interest}")
        st.caption(f"Total Due: {total_due}")

        try:
            b_avail, b_contrib, b_found = member_available_to_borrow(client, borrower_member_id)
            st.info(
                f"Borrower capacity: contributions {b_contrib:,.0f} + 70% foundation {(b_found*0.70):,.0f} = **{b_avail:,.0f}**"
            )
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
                "updated_at": now_utc,
                "status": str(status),
            }

            try:
                client.table("loans_legacy").insert(payload).execute()
                st.success("Loan inserted successfully.")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Loan insert failed (RLS/constraint/column mismatch)")

    # ===================== LOAN REQUESTS (Approve) =====================
    with tabs[4]:
        st.subheader("Loan Requests (Members submit here)")
        st.caption("Approve to create an actual record in loans_legacy (admin only).")

        try:
            reqs = client.table("loan_requests_legacy").select("*").order("created_at", desc=True).limit(400).execute().data or []
            df_reqs = pd.DataFrame(reqs)
            st.dataframe(df_reqs, use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load loan_requests_legacy")
            df_reqs = pd.DataFrame([])

        st.divider()
        st.markdown("### Approve / Reject")

        if not df_reqs.empty:
            pick_id = st.selectbox("Pick request id", df_reqs["id"].tolist(), key="pick_req_id")
            row = df_reqs[df_reqs["id"] == pick_id].iloc[0].to_dict()

            st.markdown('<div class="card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Borrower", f'{int(row["borrower_member_id"])} — {row.get("borrower_name","")}')
            c2.metric("Surety", f'{int(row["surety_member_id"])} — {row.get("surety_name","")}')
            c3.metric("Principal", f'{float(row["principal"]):,.0f}')
            st.markdown("</div>", unsafe_allow_html=True)

            admin_note = st.text_input("Admin note (optional)", value=row.get("admin_note") or "", key="admin_note")

            colA, colB = st.columns(2)
            with colA:
                if st.button("Approve & Create Loan", use_container_width=True):
                    # Create a loan record (status active by default)
                    principal = float(row["principal"])
                    interest = principal * 0.05
                    total_due = principal + interest
                    now_utc = now_iso()

                    loan_payload = {
                        "member_id": int(row["borrower_member_id"]),
                        "borrower_member_id": int(row["borrower_member_id"]),
                        "surety_member_id": int(row["surety_member_id"]),
                        "borrower_name": row.get("borrower_name"),
                        "surety_name": row.get("surety_name"),
                        "principal": principal,
                        "interest": float(interest),
                        "total_due": float(total_due),
                        "principal_current": principal,
                        "unpaid_interest": float(interest),
                        "total_interest_generated": float(interest),
                        "total_interest_accumulated": 0.0,
                        "interest_cycle_days": 26,
                        "last_interest_at": now_utc,
                        "last_interest_date": now_utc,
                        "issued_at": now_utc,
                        "created_at": now_utc,
                        "updated_at": now_utc,
                        "status": "active",
                    }

                    try:
                        # 1) insert into loans_legacy
                        client.table("loans_legacy").insert(loan_payload).execute()
                        # 2) update request status
                        client.table("loan_requests_legacy").update({
                            "status": "approved",
                            "admin_note": admin_note.strip(),
                            "updated_at": now_iso()
                        }).eq("id", int(pick_id)).execute()

                        st.success("Approved. Loan created in loans_legacy.")
                        st.rerun()
                    except Exception as e:
                        show_api_error(e, "Approve failed (check loans_legacy RLS + loan rules trigger).")

            with colB:
                if st.button("Reject Request", use_container_width=True):
                    try:
                        client.table("loan_requests_legacy").update({
                            "status": "rejected",
                            "admin_note": admin_note.strip(),
                            "updated_at": now_iso()
                        }).eq("id", int(pick_id)).execute()
                        st.success("Request rejected.")
                        st.rerun()
                    except Exception as e:
                        show_api_error(e, "Reject failed")

        else:
            st.info("No requests yet. Members will submit requests here.")

    # ===================== PAYOUT =====================
    with tabs[5]:
        st.subheader("Payout (Option B - Legacy)")
        st.write(
            "Pays the current contribution pot (all `contributions_legacy.kind='contribution'`) "
            "to the member whose `legacy_member_id = app_state.next_payout_index`, then marks pot as paid and advances rotation."
        )
        try:
            state = get_app_state(client) or {}
            idx = int(state.get("next_payout_index") or 1)
            ben = client.table("member_registry").select("full_name").eq("legacy_member_id", idx).single().execute().data
            ben_name = (ben or {}).get("full_name") or f"Member {idx}"
            pot = sum_contribution_pot(client)
            st.info(f"Next beneficiary: **{idx} — {ben_name}**")
            st.info(f"Current pot ready to pay: **{pot:,.0f}**")
        except Exception as e:
            show_api_error(e, "Could not load payout state")

        if st.button("Run Payout Now (Option B)", use_container_width=True, key="btn_run_payout_b"):
            try:
                receipt = legacy_payout_option_b(client)
                st.success("Payout completed.")
                st.json(receipt)
                st.caption(
                    "Note: payout logging into `payouts_legacy` is best-effort. "
                    "If your table schema differs, payout still completes (pot cleared + rotation advances)."
                )
                st.rerun()
            except Exception as e:
                show_api_error(e, "Payout failed")

    # ===================== MEMBER BORROW CAPACITY =====================
    with tabs[6]:
        st.subheader("Borrow capacity (per member - Legacy rule)")
        pick = st.selectbox("Pick member", member_labels, key="cap_member")
        mid = int(label_to_legacy_id.get(pick, 0))
        name = label_to_name.get(pick, "")
        try:
            avail, contrib, found = member_available_to_borrow(client, mid)
            st.metric("Available to borrow (rule)", f"{avail:,.0f}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Contributions (counted)", f"{contrib:,.0f}")
            c2.metric("Foundation (raw total)", f"{found:,.0f}")
            c3.metric("Foundation used (70%)", f"{(found*0.70):,.0f}")
            st.caption("Rule: capacity = contributions(kind='contribution') + 0.70 × (foundation paid + pending)")
        except Exception as e:
            show_api_error(e, f"Could not compute borrow capacity for {mid} — {name}")

    # ===================== JSON INSERTER =====================
    with tabs[7]:
        st.subheader("Universal JSON Inserter (Admin Only)")
        st.warning("Use carefully. This writes directly to your tables.")
        table = st.text_input("table", value="contributions_legacy", key="json_table")
        payload_text = st.text_area(
            "payload (json)",
            value='{"member_id": 1, "amount": 500, "kind": "contribution"}',
            height=220,
            key="json_payload",
        )

        if st.button("Run Insert", use_container_width=True, key="btn_json_insert"):
            try:
                payload = json.loads(payload_text)
                client.table(table).insert(payload).execute()
                st.success("Insert OK")
            except Exception as e:
                show_api_error(e, "Insert failed")

# =============================================================================
# MAIN ROUTING
# =============================================================================
if is_admin:
    admin_dashboard()
else:
    member_portal()
