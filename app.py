import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timezone
from postgrest.exceptions import APIError

# ============================================================
# The Young Shall Grow — Njangi Dashboard (Legacy)
# SINGLE SCRIPT
# - NO subtitle text shown (only title)
# - Signup/Login
# - Profiles (role: admin/member)
# - Members can ONLY request loan (loan_requests_legacy)
# - Admin can manage legacy data + approve requests into loans_legacy
# ============================================================

# -------------------- Page --------------------
st.set_page_config(
    page_title="The Young Shall Grow — Njangi Dashboard (Legacy)",
    layout="wide"
)

# -------------------- Style --------------------
st.markdown("""
<style>
.block-container { max-width: 1250px; padding-top: 1.2rem; }
.nj-header {
  padding: 18px 22px;
  border-radius: 18px;
  background: linear-gradient(90deg, #6366f1, #10b981, #f59e0b);
  color: white;
  margin-bottom: 18px;
}
.nj-title { font-size: 30px; font-weight: 900; margin: 0; letter-spacing: -0.02em; }
.card {
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(148,163,184,0.25);
  background: rgba(2,6,23,0.03);
}
.stButton>button { border-radius: 12px; font-weight: 700; }
[data-testid="stDataFrame"] { border-radius: 16px; overflow:hidden; border: 1px solid rgba(148,163,184,0.18); }
section[data-testid="stSidebar"] { border-right: 1px solid rgba(148,163,184,0.18); }
</style>
""", unsafe_allow_html=True)

# -------------------- Header (TITLE ONLY) --------------------
st.markdown("""
<div class="nj-header">
  <div class="nj-title">The Young Shall Grow — Njangi Dashboard (Legacy)</div>
</div>
""", unsafe_allow_html=True)

# -------------------- Supabase secrets --------------------
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

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def authed_client():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        c.auth.set_session(sess.access_token, sess.refresh_token)
    return c

def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    if isinstance(e, APIError):
        st.code(e.message)
    else:
        st.code(repr(e))

def to_df(resp):
    return pd.DataFrame(resp.data or [])

def safe_select_autosort(c, table: str, limit=400):
    for col in ["created_at", "issued_at", "updated_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

# -------------------- Registry helpers (for dropdowns) --------------------
def load_member_registry(c):
    resp = c.table("member_registry").select("legacy_member_id,full_name,is_active,phone,created_at") \
        .order("legacy_member_id").execute()
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

# -------------------- Profile helpers --------------------
def get_profile(c, user_id: str):
    try:
        return c.table("profiles").select("*").eq("id", user_id).single().execute().data
    except Exception:
        return None

def is_admin_profile(profile: dict | None) -> bool:
    return bool(profile) and str(profile.get("role") or "").lower() == "admin"

# -------------------- Borrow capacity (UI display only) --------------------
def member_available_to_borrow(c, member_id: int):
    # contributions_legacy: member_id, amount, kind
    resp_c = c.table("contributions_legacy").select("amount,kind,member_id") \
        .eq("member_id", member_id).limit(10000).execute()
    contrib = 0.0
    for r in (resp_c.data or []):
        if (r.get("kind") or "contribution") == "contribution":
            contrib += float(r.get("amount") or 0)

    # foundation_payments_legacy: member_id, amount_paid, amount_pending
    resp_f = c.table("foundation_payments_legacy").select("amount_paid,amount_pending,member_id") \
        .eq("member_id", member_id).limit(10000).execute()
    found = 0.0
    for r in (resp_f.data or []):
        found += float(r.get("amount_paid") or 0) + float(r.get("amount_pending") or 0)

    return contrib + (found * 0.70), contrib, found

# ============================================================
# AUTH UI (Sidebar)
# ============================================================
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Account")

    with st.expander("Setup SQL (run once in Supabase)", expanded=False):
        st.code(
            """
-- PROFILES
create table if not exists public.profiles (
  id uuid primary key,
  email text,
  role text not null default 'member',     -- admin/member
  member_id bigint,                        -- legacy member id (1..17)
  full_name text,
  phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.profiles enable row level security;

create policy if not exists "profiles_select_own"
on public.profiles for select using (auth.uid() = id);

create policy if not exists "profiles_insert_own"
on public.profiles for insert with check (auth.uid() = id);

create policy if not exists "profiles_update_own"
on public.profiles for update using (auth.uid() = id);

-- ADMIN CHECK
create or replace function public.is_admin()
returns boolean language sql stable as $$
  select exists(select 1 from public.profiles p where p.id = auth.uid() and lower(p.role)='admin');
$$;

-- LOAN REQUESTS (members insert, admin approves)
create table if not exists public.loan_requests_legacy (
  id bigint generated by default as identity primary key,
  requester_user_id uuid not null,
  borrower_member_id bigint not null,
  borrower_name text,
  surety_member_id bigint not null,
  surety_name text,
  principal numeric not null,
  status text not null default 'pending',   -- pending/approved/rejected
  admin_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.loan_requests_legacy enable row level security;

create policy if not exists "loanreq_insert_own"
on public.loan_requests_legacy for insert
with check (auth.uid() = requester_user_id);

create policy if not exists "loanreq_select_own"
on public.loan_requests_legacy for select
using (auth.uid() = requester_user_id);

create policy if not exists "loanreq_admin_select_all"
on public.loan_requests_legacy for select
using (public.is_admin());

create policy if not exists "loanreq_admin_update"
on public.loan_requests_legacy for update
using (public.is_admin());
            """.strip(),
            language="sql",
        )

    if st.session_state.session is None:
        mode = st.radio("Choose", ["Login", "Sign up"], horizontal=True)

        if mode == "Login":
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
            st.caption("Create account (member). Then login and complete your profile.")
            email = st.text_input("Email", key="su_email")
            password = st.text_input("Password", type="password", key="su_password")
            if st.button("Create account", use_container_width=True, key="btn_signup"):
                try:
                    sb.auth.sign_up({"email": email, "password": password})
                    st.success("Account created. Now login.")
                except Exception as e:
                    show_api_error(e, "Sign up failed")

    else:
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True, key="btn_logout"):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

# Must be logged in
if st.session_state.session is None:
    st.stop()

client = authed_client()
user = client.auth.get_user()
user_id = user.user.id
user_email = user.user.email

# Load member registry for dropdowns
member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

# Load profile
profile = get_profile(client, user_id)
is_admin = is_admin_profile(profile)

# ============================================================
# PROFILE CREATION (first time after signup)
# ============================================================
if not profile:
    st.warning("Complete your profile to continue.")

    st.markdown('<div class="card">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])

    with c1:
        full_name = st.text_input("Full name", value="")
        phone = st.text_input("Phone", value="")

    with c2:
        pick_label = st.selectbox("Select your member record (legacy_member_id)", member_labels)
        member_id = int(label_to_legacy_id.get(pick_label, 0))
        st.caption("This links your login to your Njangi legacy member ID.")

    if st.button("Save Profile", use_container_width=True):
        if member_id <= 0:
            st.error("Invalid member selection.")
        else:
            payload = {
                "id": user_id,
                "email": user_email,
                "role": "member",
                "member_id": member_id,
                "full_name": full_name.strip() or label_to_name.get(pick_label, ""),
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

# Member fields
my_member_id = int(profile.get("member_id") or 0)
my_name = (profile.get("full_name") or "").strip()

# ============================================================
# MEMBER VIEW (ONLY LOAN REQUEST)
# ============================================================
if not is_admin:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.write(f"**Member:** {my_name or 'Member'}  |  **ID:** {my_member_id}")

    try:
        avail, contrib, found = member_available_to_borrow(client, my_member_id)
        st.info(f"Borrow capacity (display): {avail:,.0f}  |  Contributions: {contrib:,.0f}  |  Foundation used (70%): {(found*0.70):,.0f}")
    except Exception:
        pass

    st.subheader("Request a Loan (Members only)")
    surety_label = st.selectbox("Surety (required)", member_labels, key="m_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")
    principal = st.number_input("Requested principal", min_value=500.0, step=500.0, value=500.0, key="m_principal")

    if st.button("Submit Loan Request", use_container_width=True, key="btn_submit_request"):
        if my_member_id <= 0:
            st.error("Your profile has no member_id.")
        elif surety_member_id <= 0:
            st.error("Surety is required.")
        else:
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
                show_api_error(e, "Loan request failed (check loan_requests_legacy + RLS).")

    st.markdown("</div>", unsafe_allow_html=True)

    st.subheader("My Loan Requests")
    try:
        resp = client.table("loan_requests_legacy").select("*") \
            .eq("requester_user_id", user_id) \
            .order("created_at", desc=True).limit(200).execute()
        st.dataframe(pd.DataFrame(resp.data or []), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load your loan requests")

    st.stop()

# ============================================================
# ADMIN VIEW (MANAGE DATA + APPROVE REQUESTS)
# ============================================================
st.markdown('<div class="card">', unsafe_allow_html=True)
st.write(f"**Admin:** {user_email}")
st.markdown("</div>", unsafe_allow_html=True)

tabs = st.tabs([
    "Member Registry",
    "Loan Requests (Approve)",
    "Loans (Legacy)",
    "Contributions (Legacy)",
    "Foundation (Legacy)",
    "JSON Inserter (Admin)"
])

# --- Member Registry ---
with tabs[0]:
    st.subheader("member_registry")
    st.dataframe(df_registry, use_container_width=True)

# --- Loan Requests (Approve) ---
with tabs[1]:
    st.subheader("loan_requests_legacy")
    try:
        reqs = client.table("loan_requests_legacy").select("*").order("created_at", desc=True).limit(500).execute().data or []
        df_reqs = pd.DataFrame(reqs)
        st.dataframe(df_reqs, use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loan_requests_legacy")
        df_reqs = pd.DataFrame([])

    st.divider()
    st.markdown("### Approve / Reject")

    pending_only = st.checkbox("Show pending only", value=True)
    if not df_reqs.empty:
        if pending_only and "status" in df_reqs.columns:
            view = df_reqs[df_reqs["status"] == "pending"].copy()
        else:
            view = df_reqs.copy()

        if view.empty:
            st.info("No requests to show.")
        else:
            pick_id = st.selectbox("Pick request id", view["id"].tolist(), key="pick_req_id")
            row = view[view["id"] == pick_id].iloc[0].to_dict()

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
                        client.table("loans_legacy").insert(loan_payload).execute()
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

# --- Loans (Legacy) ---
with tabs[2]:
    st.subheader("loans_legacy")
    try:
        st.dataframe(to_df(client.table("loans_legacy").select("*").order("created_at", desc=True).limit(500).execute()), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loans_legacy")

# --- Contributions (Legacy) ---
with tabs[3]:
    st.subheader("contributions_legacy")
    try:
        st.dataframe(to_df(safe_select_autosort(client, "contributions_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

# --- Foundation (Legacy) ---
with tabs[4]:
    st.subheader("foundation_payments_legacy")
    try:
        st.dataframe(to_df(safe_select_autosort(client, "foundation_payments_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

# --- JSON Inserter (Admin) ---
with tabs[5]:
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
