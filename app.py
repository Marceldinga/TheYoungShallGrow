import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone
from postgrest.exceptions import APIError

# =============================================================================
# The Young Shall Grow — Njangi Dashboard (Legacy)
# - Members can SIGN UP + LOGIN (ANON key)
# - Members (non-admin) can ONLY request a loan
# - Admin can add/manage legacy data + approve loan requests (SERVICE key)
# =============================================================================

# -------------------- Page --------------------
st.set_page_config(page_title="The Young Shall Grow — Njangi Dashboard (Legacy)", layout="wide")

# -------------------- CSS (Cleaner Square UI) --------------------
CUSTOM_CSS = """
<style>
/* Layout */
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }
h1,h2,h3 { letter-spacing: -0.02em; }
small { opacity: 0.75; }

/* Header bar */
.nj-header {
  display:flex; align-items:center; justify-content:space-between;
  padding: 14px 18px;
  border-radius: 10px;                 /* less round */
  background: linear-gradient(90deg, rgba(99,102,241,0.20), rgba(16,185,129,0.16), rgba(245,158,11,0.16));
  border: 1px solid rgba(148,163,184,0.25);
}
.nj-title { font-size: 22px; font-weight: 800; margin: 0; }

/* KPI grid */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}
@media (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
.kpi-card {
  padding: 12px 14px;
  border-radius: 8px;                  /* square look */
  border: 1px solid rgba(148,163,184,0.22);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.kpi-label { font-size: 12px; color: rgba(15,23,42,0.70); margin-bottom: 6px; }
.kpi-value { font-size: 22px; font-weight: 800; color: rgba(15,23,42,0.95); line-height: 1.1; }
.kpi-hint  { font-size: 11px; color: rgba(15,23,42,0.55); margin-top: 6px; }

/* subtle left accents */
.kpi-blue { border-left: 4px solid rgba(99,102,241,0.85); }
.kpi-green { border-left: 4px solid rgba(16,185,129,0.85); }
.kpi-cyan { border-left: 4px solid rgba(6,182,212,0.85); }
.kpi-amber { border-left: 4px solid rgba(245,158,11,0.90); }
.kpi-rose { border-left: 4px solid rgba(244,63,94,0.85); }
.kpi-slate { border-left: 4px solid rgba(100,116,139,0.85); }

/* Generic cards */
.card {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(148,163,184,0.18);
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

/* Buttons */
.stButton>button {
  border-radius: 8px;
  padding: 10px 14px;
  font-weight: 700;
}

/* Dataframe */
[data-testid="stDataFrame"] {
  border-radius: 10px;
  overflow:hidden;
  border: 1px solid rgba(148,163,184,0.18);
}

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
SUPABASE_SERVICE_KEY = get_secret("SUPABASE_SERVICE_KEY")  # <-- your key name
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

def authed_client():
    """
    IMPORTANT:
    - Use SERVICE key for all database reads/writes (bypass RLS) => fixes member_registry errors.
    - Fall back to anon+session only if SERVICE key is missing.
    """
    if SUPABASE_SERVICE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

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
    resp_c = c.table("contributions_legacy").select("amount,kind,member_id").eq("member_id", legacy_member_id).limit(10000).execute()
    rows_c = resp_c.data or []
    contrib = 0.0
    for r in rows_c:
        if (r.get("kind") or "contribution") == "contribution":
            contrib += float(r.get("amount") or 0)

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

    with st.expander("Setup SQL (run once in Supabase)", expanded=False):
        st.code("Use your existing Setup SQL here.", language="sql")

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

# IMPORTANT: from here on, use SERVICE KEY client (bypass RLS)
client = authed_client()

# We don't rely on service-client auth state; get identity from session
user_id = st.session_state.session.user.id
user_email = st.session_state.session.user.email

member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

profile = get_profile(client, user_id)

# Keep your original admin logic:
is_admin = is_admin_profile(profile)

# Optional extra safety: treat ADMIN_EMAILS as admin too (if provided)
if ADMIN_EMAILS:
    admin_list = [e.strip().lower() for e in ADMIN_EMAILS.split(",") if e.strip()]
    if user_email and user_email.lower() in admin_list:
        is_admin = True

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

my_member_id = int(profile.get("member_id") or 0)
my_name = (profile.get("full_name") or "").strip()

# -------------------- KPIs (Square Grid) --------------------
try:
    state = get_app_state(client) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben = client.table("member_registry").select("full_name").eq("legacy_member_id", next_idx).single().execute().data
    ben_name = (ben or {}).get("full_name") or f"Member {next_idx}"

    pot = sum_contribution_pot(client)
    total_contrib_all = sum_total_contributions_alltime(client)

    f_paid, f_pending, f_total = foundation_totals(client)
    total_interest, unpaid_interest, active_loans = loans_interest_totals(client)

    st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)

    st.markdown(f"""
      <div class="kpi-card kpi-blue">
        <div class="kpi-label">Current beneficiary</div>
        <div class="kpi-value">{next_idx} — {ben_name}</div>
        <div class="kpi-hint">Rotation uses app_state.next_payout_index</div>
      </div>

      <div class="kpi-card kpi-green">
        <div class="kpi-label">Contribution pot (ready)</div>
        <div class="kpi-value">{pot:,.0f}</div>
        <div class="kpi-hint">kind='contribution'</div>
      </div>

      <div class="kpi-card kpi-cyan">
        <div class="kpi-label">All-time contributions</div>
        <div class="kpi-value">{total_contrib_all:,.0f}</div>
        <div class="kpi-hint">All rows in contributions_legacy</div>
      </div>

      <div class="kpi-card kpi-amber">
        <div class="kpi-label">Total foundation (paid+pending)</div>
        <div class="kpi-value">{f_total:,.0f}</div>
        <div class="kpi-hint">amount_paid + amount_pending</div>
      </div>

      <div class="kpi-card kpi-rose">
        <div class="kpi-label">Total interest generated</div>
        <div class="kpi-value">{total_interest:,.0f}</div>
        <div class="kpi-hint">generated/accumulated (legacy)</div>
      </div>

      <div class="kpi-card kpi-slate">
        <div class="kpi-label">Active loans</div>
        <div class="kpi-value">{active_loans}</div>
        <div class="kpi-hint">status='active'</div>
      </div>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

except Exception as e:
    show_api_error(e, "Could not load dashboard KPIs")

st.divider()

# =============================================================================
# MEMBER PORTAL (Non-admin): Only request loan + view own requests
# =============================================================================
def member_portal():
    st.subheader("Member Portal")

    try:
        avail, contrib, found = member_available_to_borrow(client, my_member_id)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Your Borrow Capacity", f"{avail:,.0f}")
        c2.metric("Your Contributions (counted)", f"{contrib:,.0f}")
        c3.metric("Your Foundation used (70%)", f"{(found*0.70):,.0f}")
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        show_api_error(e, "Could not compute your borrow capacity")

    st.divider()
    st.markdown("### Request a Loan")

    surety_label = st.selectbox("Choose your Surety (required)", member_labels, key="m_surety_label")
    surety_member_id = int(label_to_legacy_id.get(surety_label, 0))
    surety_name = label_to_name.get(surety_label, "")

    principal = st.number_input(
        "Requested amount (principal)",
        min_value=500.0, step=500.0, value=500.0, key="m_principal"
    )

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
        resp = (
            client.table("loan_requests_legacy")
            .select("*")
            .eq("requester_user_id", user_id)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        st.dataframe(pd.DataFrame(resp.data or []), use_container_width=True)
    except Exception as e:
        show_api_error(e, "Could not load your loan requests")

# =============================================================================
# ADMIN DASHBOARD
# =============================================================================
def admin_dashboard():
    st.subheader("Admin Dashboard")

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

    with tabs[0]:
        st.subheader("member_registry")
        st.dataframe(df_registry, use_container_width=True)

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
                show_api_error(e, "Contribution insert failed")

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
                show_api_error(e, "Foundation insert failed")

    with tabs[3]:
        st.subheader("loans_legacy")
        try:
            st.dataframe(to_df(
                client.table("loans_legacy").select("*").order("created_at", desc=True).limit(400).execute()
            ), use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load loans_legacy")

    with tabs[4]:
        st.subheader("Loan Requests (Approve)")
        try:
            reqs = (
                client.table("loan_requests_legacy")
                .select("*")
                .order("created_at", desc=True)
                .limit(400)
                .execute()
                .data or []
            )
            st.dataframe(pd.DataFrame(reqs), use_container_width=True)
        except Exception as e:
            show_api_error(e, "Could not load loan_requests_legacy")

    with tabs[5]:
        st.subheader("Payout (Option B - Legacy)")
        if st.button("Run Payout Now (Option B)", use_container_width=True, key="btn_run_payout_b"):
            try:
                receipt = legacy_payout_option_b(client)
                st.success("Payout completed.")
                st.json(receipt)
                st.rerun()
            except Exception as e:
                show_api_error(e, "Payout failed")

    with tabs[6]:
        st.subheader("Borrow capacity (per member - Legacy rule)")
        pick = st.selectbox("Pick member", member_labels, key="cap_member")
        mid = int(label_to_legacy_id.get(pick, 0))
        try:
            avail, contrib, found = member_available_to_borrow(client, mid)
            st.metric("Available to borrow (rule)", f"{avail:,.0f}")
        except Exception as e:
            show_api_error(e, "Capacity compute failed")

    with tabs[7]:
        st.subheader("Universal JSON Inserter (Admin Only)")
        table = st.text_input("table", value="contributions_legacy", key="json_table")
        payload_text = st.text_area(
            "payload (json)",
            value='{"member_id": 1, "amount": 500, "kind": "contribution"}',
            height=220,
            key="json_payload"
        )
        if st.button("Run Insert", use_container_width=True, key="btn_json_insert"):
            try:
                payload = json.loads(payload_text)
                client.table(table).insert(payload).execute()
                st.success("Insert OK")
            except Exception as e:
                show_api_error(e, "Insert failed")

# -------------------- Routing --------------------
if is_admin:
    admin_dashboard()
else:
    member_portal()
