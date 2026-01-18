import os
import json
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date, datetime, timezone

# -------------------- Page --------------------
st.set_page_config(page_title="Njangi Admin Dashboard (Legacy)", layout="wide")
st.title("Njangi Admin Dashboard (Legacy)")

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
    st.code(repr(e))  # better visibility than str(e)

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

def now_iso():
    return datetime.now(timezone.utc).isoformat()

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
    # prefer total_interest_generated if present
    total_interest = total_gen if total_gen > 0 else total_acc
    return total_interest, unpaid, active_count

def member_available_to_borrow(c, legacy_member_id: int):
    """
    Your Njangi rule (legacy):
      available = sum(contributions_legacy where kind='contribution') + 0.70 * sum(foundation (paid+pending))
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
    """
    Option B (Legacy): app_state.next_payout_index is the legacy_member_id (1..17)
    - Compute pot = sum contributions_legacy where kind='contribution'
    - Log payout into payouts_legacy IF possible (best effort)
    - Mark contributions kind='paid'
    - Advance next_payout_index (1..17 wrap)
    """
    st_row = c.table("app_state").select("*").eq("id", 1).single().execute().data
    if not st_row:
        raise Exception("app_state id=1 not found")

    idx = int(st_row.get("next_payout_index") or 1)
    pot = sum_contribution_pot(c)
    if pot <= 0:
        raise Exception("Pot is zero (no kind='contribution' rows in contributions_legacy).")

    # beneficiary
    ben = c.table("member_registry").select("legacy_member_id,full_name").eq("legacy_member_id", idx).single().execute().data
    ben_name = (ben or {}).get("full_name") or f"Member {idx}"

    # best-effort: insert into payouts_legacy (if schema matches)
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
        # if schema mismatch, we still continue (payout still processed)
        payout_inserted = False

    # mark pot as paid
    # Update all rows with kind='contribution' -> 'paid'
    c.table("contributions_legacy").update({"kind": "paid", "updated_at": now_iso()}).eq("kind", "contribution").execute()

    # advance index
    nxt = idx + 1
    if nxt > 17:
        nxt = 1

    # update app_state
    c.table("app_state").update({
        "next_payout_index": nxt,
        "next_payout_date": str(date.today()),  # keep simple; change if you want +14d
        "updated_at": now_iso()
    }).eq("id", 1).execute()

    return {
        "beneficiary_legacy_member_id": idx,
        "beneficiary_name": ben_name,
        "pot_paid_out": pot,
        "payout_logged": payout_inserted,
        "next_payout_index": nxt
    }

# -------------------- Login --------------------
if "session" not in st.session_state:
    st.session_state.session = None

with st.sidebar:
    st.header("Admin Login")
    if st.session_state.session is None:
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
        st.success(f"Logged in: {st.session_state.session.user.email}")
        if st.button("Logout", use_container_width=True, key="btn_logout"):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            st.session_state.session = None
            st.rerun()

if st.session_state.session is None:
    st.stop()

client = authed_client()

# -------------------- Load Members --------------------
member_labels, label_to_legacy_id, label_to_name, df_registry = load_member_registry(client)

# -------------------- Dashboard KPIs (Top) --------------------
try:
    state = get_app_state(client) or {}
    next_idx = int(state.get("next_payout_index") or 1)
    ben = client.table("member_registry").select("full_name").eq("legacy_member_id", next_idx).single().execute().data
    ben_name = (ben or {}).get("full_name") or f"Member {next_idx}"

    pot = sum_contribution_pot(client)
    total_contrib_all = sum_total_contributions_alltime(client)

    f_paid, f_pending, f_total = foundation_totals(client)
    total_interest, unpaid_interest, active_loans = loans_interest_totals(client)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Current beneficiary", f"{next_idx} — {ben_name}")
    c2.metric("Contribution pot (ready)", f"{pot:,.0f}")
    c3.metric("All-time contributions", f"{total_contrib_all:,.0f}")
    c4.metric("Total foundation (paid+pending)", f"{f_total:,.0f}")
    c5.metric("Total interest generated", f"{total_interest:,.0f}")
    c6.metric("Active loans", f"{active_loans}")
except Exception as e:
    show_api_error(e, "Could not load dashboard KPIs")

st.divider()

# -------------------- Tabs --------------------
tabs = st.tabs([
    "Members",
    "Contributions (Legacy)",
    "Foundation (Legacy)",
    "Loans (Legacy)",
    "Payout (Option B)",
    "Member Borrow Capacity",
    "JSON Inserter"
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
    st.markdown("### Insert Contribution (legacy)")

    mem_label = st.selectbox("Member", member_labels, key="c_member_label")
    legacy_id = int(label_to_legacy_id.get(mem_label, 0))
    st.caption(f"member_id (legacy): **{legacy_id}**")

    amount = st.number_input("amount", min_value=0, step=500, value=500, key="c_amount")
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
with tabs[2]:
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

    # Njangi rule: 5% interest upfront
    interest = float(principal) * 0.05
    total_due = float(principal) + interest
    st.caption(f"Interest (5%): {interest}")
    st.caption(f"Total Due: {total_due}")

    # Show borrower capacity (legacy rule)
    try:
        b_avail, b_contrib, b_found = member_available_to_borrow(client, borrower_member_id)
        st.info(
            f"Borrower capacity (legacy): contributions {b_contrib:,.0f} + 70% foundation {(b_found*0.70):,.0f} = **{b_avail:,.0f}**"
        )
    except Exception:
        pass

    if st.button("Insert Loan", use_container_width=True, key="btn_insert_loan"):
        now_utc = now_iso()
        payload = {
            "member_id": borrower_member_id,                  # nullable in schema
            "borrower_member_id": borrower_member_id,         # NOT NULL
            "surety_member_id": surety_member_id,             # NOT NULL
            "borrower_name": borrower_name,                   # nullable
            "surety_name": surety_name,                       # nullable
            "principal": float(principal),                    # NOT NULL
            "interest": float(interest),                      # NOT NULL
            "total_due": float(total_due),                    # NOT NULL
            "principal_current": float(principal),            # nullable
            "unpaid_interest": float(interest),               # nullable
            "total_interest_generated": float(interest),       # nullable
            "total_interest_accumulated": 0.0,                # NOT NULL in your schema
            "interest_cycle_days": int(interest_cycle_days),   # NOT NULL
            "last_interest_at": now_utc,                       # nullable
            "last_interest_date": now_utc,                     # nullable
            "issued_at": now_utc,                              # NOT NULL
            "created_at": now_utc,                             # NOT NULL
            "status": str(status),                             # NOT NULL
        }

        try:
            client.table("loans_legacy").insert(payload).execute()
            st.success("Loan inserted successfully.")
            st.rerun()
        except Exception as e:
            show_api_error(e, "Loan insert failed (RLS/constraint/column mismatch)")

# ===================== PAYOUT (OPTION B - LEGACY) =====================
with tabs[4]:
    st.subheader("Payout (Option B - Legacy)")

    st.write(
        "This pays the **current contribution pot** (all `contributions_legacy.kind='contribution'`) "
        "to the member whose **legacy_member_id = app_state.next_payout_index**, then marks pot as paid and advances rotation."
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
                "If your table schema differs, the payout still completes (pot is cleared + rotation advances)."
            )
            st.rerun()
        except Exception as e:
            show_api_error(e, "Payout failed")

# ===================== MEMBER BORROW CAPACITY =====================
with tabs[5]:
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
        st.caption("Rule: available = contributions + 0.70 × (foundation paid + pending)")
    except Exception as e:
        show_api_error(e, f"Could not compute borrow capacity for {mid} — {name}")

# ===================== JSON INSERTER =====================
with tabs[6]:
    st.subheader("Universal JSON Inserter")

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
