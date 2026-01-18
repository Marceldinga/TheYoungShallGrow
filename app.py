import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone
from postgrest.exceptions import APIError

# =============================================================================
# The Young Shall Grow — Njangi Dashboard (Legacy)
#
# FIXED (ONLY what you asked):
# ✅ Member can SEE ALL dashboard (read-only tables + KPIs)
# ✅ Member CANNOT add data (no admin insert widgets shown)
# ✅ Member can ONLY apply for loan, choose surety, request shows PENDING until admin approves
# ✅ Admin can APPROVE and ISSUE loan into loans_legacy using YOUR REAL loans_legacy columns
# ✅ KPIs appear SIDE-BY-SIDE (3 columns using st.columns)
# =============================================================================

# -------------------- Page --------------------
st.set_page_config(page_title="The Young Shall Grow — Njangi Dashboard (Legacy)", layout="wide")

# -------------------- CSS --------------------
CUSTOM_CSS = """
<style>
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }
h1,h2,h3 { letter-spacing: -0.02em; }
small { opacity: 0.75; }

.nj-header {
  display:flex; align-items:center; justify-content:space-between;
  padding: 14px 18px;
  border-radius: 10px;
  background: linear-gradient(90deg, rgba(99,102,241,0.20), rgba(16,185,129,0.16), rgba(245,158,11,0.16));
  border: 1px solid rgba(148,163,184,0.25);
}
.nj-title { font-size: 22px; font-weight: 800; margin: 0; }

.kpi-card {
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(148,163,184,0.22);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.kpi-label { font-size: 12px; color: rgba(15,23,42,0.70); margin-bottom: 6px; }
.kpi-value { font-size: 22px; font-weight: 800; color: rgba(15,23,42,0.95); line-height: 1.1; }
.kpi-hint  { font-size: 11px; color: rgba(15,23,42,0.55); margin-top: 6px; }

.kpi-blue { border-left: 4px solid rgba(99,102,241,0.85); }
.kpi-green { border-left: 4px solid rgba(16,185,129,0.85); }
.kpi-cyan { border-left: 4px solid rgba(6,182,212,0.85); }
.kpi-amber { border-left: 4px solid rgba(245,158,11,0.90); }
.kpi-rose { border-left: 4px solid rgba(244,63,94,0.85); }
.kpi-slate { border-left: 4px solid rgba(100,116,139,0.85); }

.card {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(148,163,184,0.18);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.stButton>button { border-radius: 8px; padding: 10px 14px; font-weight: 700; }

[data-testid="stDataFrame"] {
  border-radius: 10px;
  overflow:hidden;
  border: 1px solid rgba(148,163,184,0.18);
}

section[data-testid="stSidebar"] { border-right: 1px solid rgba(148,163,184,0.18); }
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
SUPABASE_SERVICE_KEY = get_secret("SUPABASE_SERVICE_KEY")
ADMIN_EMAILS = (get_secret("ADMIN_EMAILS") or "").strip()

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    st.error("Missing SUPABASE_URL / SUPABASE_ANON_KEY in Streamlit Secrets.")
    st.stop()

# Signup/Login uses ANON key
sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# -------------------- Helpers --------------------
def to_df(resp):
    return pd.DataFrame(resp.data or [])

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def show_api_error(e: Exception, title="Supabase error"):
    st.error(title)
    if isinstance(e, APIError):
        try:
            st.code(e.message)
        except Exception:
            st.code(repr(e))
    else:
        st.code(repr(e))

def service_client():
    if not SUPABASE_SERVICE_KEY:
        raise Exception("Missing SUPABASE_SERVICE_KEY in Streamlit Secrets.")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def user_client_from_session():
    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    sess = st.session_state.get("session")
    if sess:
        try:
            c.auth.set_session(sess.access_token, sess.refresh_token)
        except Exception:
            pass
    return c

def safe_select_autosort(c, table: str, limit=400):
    for col in ["created_at", "issued_at", "updated_at", "date_paid", "borrow_date", "joined_at"]:
        try:
            return c.table(table).select("*").order(col, desc=True).limit(limit).execute()
        except Exception:
            continue
    return c.table(table).select("*").limit(limit).execute()

def load_member_registry(c):
    # Always read members using service key (so dashboard works even if RLS is on)
    c_read = service_client() if SUPABASE_SERVICE_KEY else c
    resp = (
        c_read.table("member_registry")
        .select("legacy_member_id,full_name,is_active,phone,created_at")
        .order("legacy_member_id")
        .execute()
    )
    rows = resp.data or []
    df = pd.DataFrame(rows)

    labels, label_to_legacy, label_to_name = [], {}, {}
    for r in rows:
        mid = int(r.get("legacy_member_id") or 0)
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
    try:
        return c.table("profiles").select("*").eq("id", user_id).single().execute().data
    except Exception:
        return None

def is_admin_profile(profile: dict | None) -> bool:
    return bool(profile) and str(profile.get("role") or "").lower() == "admin"

def get_app_state(c):
    try:
        return c.table("app_state").select("*").eq("id", 1).single().execute().data
    except Exception:
        return None

def sum_contribution_pot(c):
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
    resp = c.table("foundation_payments_legacy").select("amount_paid,amount_pending").limit(10000).execute()
    rows = resp.data or []
    paid = 0.0
    pending = 0.0
    for r in rows:
        paid += float(r.get("amount_paid") or 0)
        pending += float(r.get("amount_pending") or 0)
    return paid, pending, (paid + pending)

def loans_interest_totals(c):
    resp = c.table("loans_legacy").select(
        "total_interest_generated,total_interest_accumulated,unpaid_interest,status"
    ).limit(10000).execute()
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
    resp_c = (
        c.table("contributions_legacy")
        .select("amount,kind,member_id")
        .eq("member_id", legacy_member_id)
        .limit(10000)
        .execute()
    )
    rows_c = resp_c.data or []
    contrib = 0.0
    for r in rows_c:
        if (r.get("kind") or "contribution") == "contribution":
            contrib += float(r.get("amount") or 0)

    resp_f = (
        c.table("foundation_payments_legacy")
        .select("amount_paid,amount_pending,member_id")
        .eq("member_id", legacy_member_id)
        .limit(10000)
        .execute()
    )
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
    <p class="nj-title">The Young Shall Grow — Njangi Dashboard (Legacy)</p>
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

if st.session_state.session is None:
    st.stop()

# Identity from session
user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email

# Clients:
# - svc: for dashboard READs and admin actions (so dashboard always works even if RLS is on)
# - usr: for member identity operations (profiles); safe if you later enable RLS
svc = service_client() if SUPABASE_SERVICE_KEY else user_client_from_session()
usr = user_client_from_session()

member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(svc)
profile = get_profile(svc, user_id)

is_admin = is_admin_profile(profile)
if ADMIN_EMAILS:
    admin_list = [e.strip().lower() for e in ADMIN_EMAILS.split(",") if e.strip()]
    if user_email and user_email.lower() in admin_list:
        is_admin = True

# -------------------- Profile onboarding --------------------
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
                svc.table("profiles").upsert(payload).execute()
                st.success("Profile saved. Reloading...")
                st.rerun()
            except Exception as e:
                show_api_error(e, "Profile save failed.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

my_member_id = int(profile.get("member_id") or 0)
my_name = (profile.get("full_name") or "").strip()

# =============================================================================
# KPIs (SIDE-BY-SIDE, each KPI safe)
# =============================================================================
def kpi_card(css_class, label, value, hint):
    st.markdown(
        f"""
        <div class="kpi-card {css_class}">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-hint">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

try:
    # IMPORTANT: use svc for dashboard reads
    state = get_app_state(svc) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben_name = f"Member {next_idx}"
    try:
        ben = svc.table("member_registry").select("full_name").eq("legacy_member_id", next_idx).single().execute().data
        ben_name = (ben or {}).get("full_name") or ben_name
    except Exception:
        pass

    # If any table has DB recursion error ("stack depth limit exceeded"), KPIs still render what works.
    try:
        pot = sum_contribution_pot(svc)
    except Exception:
        pot = 0
    try:
        total_contrib_all = sum_total_contributions_alltime(svc)
    except Exception:
        total_contrib_all = 0
    try:
        f_paid, f_pending, f_total = foundation_totals(svc)
    except Exception:
        f_total = 0
    try:
        total_interest, unpaid_interest, active_loans = loans_interest_totals(svc)
    except Exception:
        total_interest, active_loans = 0, 0

    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        kpi_card("kpi-blue", "Current beneficiary", f"{next_idx} — {ben_name}", "Rotation uses app_state.next_payout_index")
    with r1c2:
        kpi_card("kpi-green", "Contribution pot (ready)", f"{pot:,.0f}", "kind='contribution'")
    with r1c3:
        kpi_card("kpi-cyan", "All-time contributions", f"{total_contrib_all:,.0f}", "All rows in contributions_legacy")

    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        kpi_card("kpi-amber", "Total foundation (paid+pending)", f"{f_total:,.0f}", "amount_paid + amount_pending")
    with r2c2:
        kpi_card("kpi-rose", "Total interest generated", f"{total_interest:,.0f}", "generated/accumulated (legacy)")
    with r2c3:
        kpi_card("kpi-slate", "Active loans", f"{active_loans}", "status='active'")

except Exception as e:
    show_api_error(e, "Could not load dashboard KPIs")

st.divider()

# =============================================================================
# DASHBOARD (READ-ONLY) visible to everyone
# =============================================================================
st.subheader("Dashboard (Read-only)")
view_tabs = st.tabs(["Members (View)", "Contributions (View)", "Foundation (View)", "Loans (View)"])

with view_tabs[0]:
    st.dataframe(df_registry, use_container_width=True)

with view_tabs[1]:
    try:
        st.dataframe(to_df(safe_select_autosort(svc, "contributions_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load contributions_legacy")

with view_tabs[2]:
    try:
        st.dataframe(to_df(safe_select_autosort(svc, "foundation_payments_legacy", limit=800)), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load foundation_payments_legacy")

with view_tabs[3]:
    try:
        st.dataframe(to_df(svc.table("loans_legacy").select("*").order("created_at", desc=True).limit(400).execute()),
                     use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load loans_legacy")

st.divider()

# =============================================================================
# LOAN APPLICATION (Member) + ADMIN APPROVAL
# =============================================================================
def member_loan_application():
    st.subheader("Loan Application (Member)")

    # show borrow capacity
    try:
        avail, contrib, found = member_available_to_borrow(svc, my_member_id)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Your Borrow Capacity", f"{avail:,.0f}")
        c2.metric("Your Contributions (counted)", f"{contrib:,.0f}")
        c3.metric("Your Foundation used (70%)", f"{(found*0.70):,.0f}")
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception:
        avail = None

    st.markdown("### Apply for a Loan")

    # surety must be different from borrower
    surety_label = st.selectbox("Choose your Surety (required)", member_labels, key="m_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input(
        "Requested amount (principal)",
        min_value=500.0, step=500.0, value=500.0, key="m_principal"
    )

    if st.button("Submit Loan Request (Pending)", use_container_width=True, key="btn_submit_request"):
        if my_member_id <= 0:
            st.error("Your profile has no member_id.")
            return
        if surety_member_id <= 0:
            st.error("Surety is required.")
            return
        if surety_member_id == my_member_id:
            st.error("Surety cannot be the borrower.")
            return
        if avail is not None and float(principal) > float(avail):
            st.error(f"Requested amount is above your borrow capacity ({avail:,.0f}).")
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
            # insert using service so it always works (even if RLS is strict)
            svc.table("loan_requests_legacy").insert(payload).execute()
            st.success("Loan request submitted. Status: PENDING (wait for admin approval).")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan request failed (loan_requests_legacy missing or blocked).")

    st.markdown("### My Loan Requests")
    try:
        resp = (
            svc.table("loan_requests_legacy")
            .select("*")
            .eq("requester_user_id", user_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        st.dataframe(pd.DataFrame(resp.data or []), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load your loan requests")

def admin_approve_issue():
    st.subheader("Admin: Approve & Issue Loan")

    try:
        reqs = (
            svc.table("loan_requests_legacy")
            .select("*")
            .order("created_at", desc=True)
            .limit(400)
            .execute()
            .data or []
        )
    except Exception as e:
        show_api_error(e, "Could not load loan_requests_legacy")
        return

    df_reqs = pd.DataFrame(reqs)
    st.dataframe(df_reqs, use_container_width=True)

    if df_reqs.empty:
        st.info("No requests found.")
        return

    # Choose a request row
    pick_idx = st.number_input("Pick a row index from the table above", min_value=0, max_value=int(len(df_reqs) - 1), value=0, step=1)
    row = df_reqs.iloc[int(pick_idx)].to_dict()

    # required fields we expect in request
    principal = float(row.get("principal") or 0)
    borrower_member_id = int(row.get("borrower_member_id") or 0)
    surety_member_id = int(row.get("surety_member_id") or 0)
    borrower_name = (row.get("borrower_name") or f"Member {borrower_member_id}")
    surety_name = (row.get("surety_name") or f"Member {surety_member_id}")
    req_status = str(row.get("status") or "").lower()

    st.markdown('<div class="card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Borrower", f"{borrower_member_id} — {borrower_name}")
    c2.metric("Surety", f"{surety_member_id} — {surety_name}")
    c3.metric("Requested", f"{principal:,.0f}")
    st.markdown("</div>", unsafe_allow_html=True)

    # We need a stable identifier to update request. Try common columns.
    request_id = row.get("id", None)

    # admin parameters
    interest_rate = st.number_input("Interest rate (e.g. 0.05 = 5%)", min_value=0.0, max_value=1.0, value=0.05, step=0.01)
    cycle_days = st.number_input("Interest cycle days", min_value=1, value=26, step=1)

    if st.button("APPROVE + ISSUE LOAN", use_container_width=True, disabled=(req_status != "pending")):
        try:
            interest = round(principal * float(interest_rate), 6)
            total_due = round(principal + interest, 6)

            loan_payload = {
                # core columns you showed
                "member_id": borrower_member_id,                    # nullable but useful
                "principal": principal,
                "interest": interest,
                "total_due": total_due,
                "balance": total_due,
                "status": "active",
                "issued_at": now_iso(),
                "created_at": now_iso(),
                "borrower_member_id": borrower_member_id,
                "surety_member_id": surety_member_id,
                "borrower_name": borrower_name,
                "surety_name": surety_name,
                "updated_at": now_iso(),

                # extra columns you showed
                "borrow_date": str(date.today()),
                "principal_current": principal,
                "total_interest_accumulated": 0,
                "last_interest_at": None,
                "interest_cycle_days": int(cycle_days),
                "last_interest_date": None,
                "total_interest_generated": 0,
                "unpaid_interest": 0,
            }

            svc.table("loans_legacy").insert(loan_payload).execute()

            # update request -> approved (works whether id exists or not)
            upd = {"status": "approved", "updated_at": now_iso()}
            if request_id is not None:
                svc.table("loan_requests_legacy").update(upd).eq("id", request_id).execute()
            else:
                # fallback update by matching main fields (best-effort)
                svc.table("loan_requests_legacy").update(upd)\
                    .eq("borrower_member_id", borrower_member_id)\
                    .eq("surety_member_id", surety_member_id)\
                    .eq("principal", principal)\
                    .eq("status", "pending")\
                    .execute()

            st.success("Approved and issued loan into loans_legacy.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Approve/Issue failed")

    if st.button("REJECT REQUEST", use_container_width=True, disabled=(req_status != "pending")):
        try:
            upd = {"status": "rejected", "updated_at": now_iso()}
            if request_id is not None:
                svc.table("loan_requests_legacy").update(upd).eq("id", request_id).execute()
            else:
                svc.table("loan_requests_legacy").update(upd)\
                    .eq("borrower_member_id", borrower_member_id)\
                    .eq("surety_member_id", surety_member_id)\
                    .eq("principal", principal)\
                    .eq("status", "pending")\
                    .execute()
            st.success("Request rejected.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Reject failed")

# Show member application always; show admin approve section only for admin
member_loan_application()
if is_admin:
    st.divider()
    admin_approve_issue()

# Optional: Admin payout button (only admin sees it)
if is_admin:
    st.divider()
    st.subheader("Admin: Payout (Option B - Legacy)")
    if st.button("Run Payout Now (Option B)", use_container_width=True, key="btn_run_payout_b"):
        try:
            receipt = legacy_payout_option_b(svc)
            st.success("Payout completed.")
            st.json(receipt)
            st.rerun()
        except Exception as e:
            show_api_error(e, "Payout failed")
