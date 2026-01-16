
import pandas as pd
import streamlit as st
from supabase import create_client
from datetime import date, datetime

# ============================================================
# THE YOUNG SHALL GROW — SINGLE STREAMLIT APP (ADMIN INPUT UI)
# ------------------------------------------------------------
# ✅ Supabase Auth login (email/password)
# ✅ Member view: only their rows (email -> members.id)  (RLS enforces)
# ✅ Member can request loan with surety rule (writes to loan_requests if exists,
#    else writes to loans as status='requested')
# ✅ Admin can add data from dashboard:
#    - Contributions
#    - Foundation payments
#    - Fines
#    - Repayments
#    - Approve loan request / Issue loan
#    - Conduct payout (records payout + optional rotate index)
# ✅ Ports update immediately after each action
# ✅ Clean UI using dropdowns/expanders
# ============================================================

# ----------------------------
# SETTINGS
# ----------------------------
st.set_page_config(page_title="The Young Shall Grow – Dashboard", page_icon="🌱", layout="wide")
st.set_option("client.showErrorDetails", False)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
ADMIN_EMAILS = [e.strip().lower() for e in str(st.secrets.get("ADMIN_EMAILS", "")).split(",") if e.strip()]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Optional auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh  # pip: streamlit-autorefresh
except Exception:
    st_autorefresh = None

# ----------------------------
# THEME
# ----------------------------
st.markdown("""
<style>
:root{
  --bg:#0b1220;
  --stroke:rgba(148,163,184,.18);
  --text:#e5e7eb;
  --muted:rgba(229,231,235,.65);
  --brand:#22c55e;
  --brand2:#14b8a6;
  --danger:#ef4444;
  --shadow: 0 18px 50px rgba(0,0,0,.35);
}
.stApp { background: linear-gradient(180deg, var(--bg), #070b14 70%); color: var(--text); }
.block-container{max-width:1220px;padding-top:1.0rem;padding-bottom:2rem;}
.hdr{
  border:1px solid var(--stroke);
  background: linear-gradient(135deg, rgba(34,197,94,.10), rgba(20,184,166,.08));
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: var(--shadow);
}
.small-muted{ color: var(--muted); font-size: 13px; }
hr{ border: none; border-top: 1px solid var(--stroke); margin: 14px 0; }
.kpi{
  border:1px solid var(--stroke);
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 26px rgba(0,0,0,.20);
}
.kpi .label{ color: var(--muted); font-size: 13px; }
.kpi .value{ font-size: 26px; font-weight: 800; margin-top: 6px; }
.kpi .accent{ width:100%; height:4px; border-radius:999px; background: linear-gradient(90deg, var(--brand), var(--brand2)); margin-top: 10px; }
.card{
  border:1px solid var(--stroke);
  background: rgba(255,255,255,.03);
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 10px 26px rgba(0,0,0,.20);
}
.badge{
  display:inline-flex; gap:8px; align-items:center;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid var(--stroke);
  background: rgba(255,255,255,.04);
  font-size: 13px;
  color: var(--text);
}
.badge span{ color: var(--muted); }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# HELPERS
# ----------------------------
def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def is_logged_in() -> bool:
    return bool(st.session_state.get("access_token"))

def logout():
    st.session_state.clear()
    st.rerun()

def attach_jwt(access_token: str):
    # IMPORTANT: this makes PostgREST use the logged-in user's JWT (RLS applies)
    supabase.postgrest.auth(access_token)

def safe_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

def table_exists(table: str) -> bool:
    try:
        supabase.table(table).select("*").limit(1).execute()
        return True
    except Exception:
        return False

@st.cache_data(ttl=60, show_spinner=False)
def get_members_min():
    try:
        rows = supabase.table("members").select("id,name,email").order("id").execute().data or []
        out = []
        for r in rows:
            out.append({
                "id": int(r.get("id")),
                "name": (r.get("name") or "").strip(),
                "email": (r.get("email") or "").strip().lower(),
            })
        return out
    except Exception:
        return []

def get_member_by_email(email: str):
    email = (email or "").lower().strip()
    # fast path from list
    for m in get_members_min():
        if (m.get("email") or "").lower() == email:
            return m
    # fallback
    try:
        d = supabase.table("members").select("*").ilike("email", email).limit(1).execute().data
        if d: return d[0]
    except Exception:
        pass
    try:
        d = supabase.table("members").select("*").eq("email", email).limit(1).execute().data
        if d: return d[0]
    except Exception:
        pass
    return None

def member_label(mid: int, members_by_id: dict) -> str:
    m = members_by_id.get(int(mid), {})
    nm = (m.get("name") or "").strip()
    em = (m.get("email") or "").strip()
    base = nm if nm else (em if em else f"Member {mid}")
    return f"{mid} — {base}"

def fetch_df(table: str, cols="*", member_col=None, member_id=None, order_col=None, desc=True) -> pd.DataFrame:
    q = supabase.table(table).select(cols)
    if member_col and member_id is not None:
        q = q.eq(member_col, member_id)
    if order_col:
        q = q.order(order_col, desc=desc)
    data = q.execute().data
    return pd.DataFrame(data or [])

def compute_capacity(member_id: int) -> dict:
    # capacity = contributions + 0.7*(foundation_paid+foundation_pending)
    c = fetch_df("contributions", "amount,member_id", "member_id", member_id)
    f = fetch_df("foundation_payments", "amount_paid,amount_pending,member_id", "member_id", member_id)
    contrib = safe_sum(c, "amount")
    f_paid = safe_sum(f, "amount_paid")
    f_pending = safe_sum(f, "amount_pending")
    total_f = f_paid + f_pending
    cap = contrib + (0.7 * total_f)
    return {
        "contrib": contrib,
        "foundation_paid": f_paid,
        "foundation_pending": f_pending,
        "capacity": cap
    }

def member_has_benefitted(member_id: int) -> bool:
    if not table_exists("payouts"):
        return False
    try:
        r = supabase.table("payouts").select("id").eq("member_id", member_id).limit(1).execute().data or []
        return len(r) > 0
    except Exception:
        return False

# ----------------------------
# LOGIN
# ----------------------------
if not is_logged_in():
    st.markdown(
        "<div class='hdr'><h1 style='margin:0'>🌱 Login</h1>"
        "<div class='small-muted'>Sign in with your Supabase Auth email/password</div></div>",
        unsafe_allow_html=True,
    )
    st.write("")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["access_token"] = res.session.access_token
            st.session_state["refresh_token"] = res.session.refresh_token
            st.session_state["user_email"] = (res.user.email or "").lower()
            attach_jwt(st.session_state["access_token"])
            st.rerun()
        except Exception:
            st.error("Login failed. Check email/password or confirm the user exists in Supabase Auth.")
    st.stop()

attach_jwt(st.session_state["access_token"])
user_email = (st.session_state.get("user_email") or "").lower()
is_admin = user_email in ADMIN_EMAILS

# ----------------------------
# MEMBER CONTEXT
# ----------------------------
me = get_member_by_email(user_email)
if not me:
    st.error("❌ Logged in but no matching row found in public.members for this email.")
    st.stop()

my_member_id = int(me["id"])
members = get_members_min()
members_by_id = {int(m["id"]): m for m in members}
all_member_ids = [int(m["id"]) for m in members] if members else [my_member_id]

# ----------------------------
# HEADER
# ----------------------------
st.markdown(
    f"""
    <div class='hdr'>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
          <h1 style="margin:0">📊 Dashboard</h1>
          <div class="small-muted">
            Logged in as <b>{user_email}</b> {'(admin)' if is_admin else ''} • Your member_id = <b>{my_member_id}</b>
          </div>
        </div>
        <div class="badge"><b>{user_email}</b> <span>{'(admin)' if is_admin else ''}</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)
c1, c2, c3 = st.columns([1,1,6])
with c1:
    st.button("Logout", on_click=logout)
with c2:
    if st.button("🔄 Refresh"):
        st.rerun()

# ----------------------------
# Live Updates
# ----------------------------
with st.expander("🔽 Live Updates", expanded=False):
    enable_live = st.toggle("Enable auto-refresh", value=True)
    refresh_seconds = st.selectbox("Refresh every (seconds)", [10, 20, 30, 60, 120], index=2)
    if enable_live and st_autorefresh:
        st_autorefresh(interval=int(refresh_seconds) * 1000, key="live_refresh")
    elif enable_live and not st_autorefresh:
        st.warning("Auto-refresh missing. Add `streamlit-autorefresh` to requirements.txt on Streamlit Cloud.")

# ============================================================
# ADMIN: CONTROL PANEL (INPUT FORMS)
# ============================================================
with st.expander("🔽 Admin: Control Panel (Add / Approve / Payout)", expanded=is_admin):
    if not is_admin:
        st.info("Admin only.")
    else:
        action = st.selectbox(
            "Select admin action",
            [
                "Add Contribution",
                "Add Foundation Payment",
                "Add Fine",
                "Record Repayment",
                "Approve Loan (Request -> Loan)",
                "Issue Loan (set status Active/Open)",
                "Conduct Payout",
            ],
            index=0,
        )

        # member picker
        member_ids = all_member_ids
        def mid_fmt(x): return member_label(x, members_by_id)

        # 1) Add Contribution
        if action == "Add Contribution":
            with st.form("admin_add_contrib", clear_on_submit=True):
                mid = st.selectbox("Member", member_ids, format_func=mid_fmt)
                amount = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
                kind = st.text_input("Kind", value="contribution")
                ok = st.form_submit_button("✅ Save Contribution")

            if ok:
                try:
                    supabase.table("contributions").insert({
                        "member_id": int(mid),
                        "amount": float(amount),
                        "kind": (kind.strip() or "contribution"),
                    }).execute()
                    st.success("Saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed (RLS/policy/column): {e}")

        # 2) Add Foundation Payment
        elif action == "Add Foundation Payment":
            with st.form("admin_add_foundation", clear_on_submit=True):
                mid = st.selectbox("Member", member_ids, format_func=mid_fmt)
                amount_paid = st.number_input("Amount Paid", min_value=0.0, step=100.0, value=0.0)
                amount_pending = st.number_input("Amount Pending", min_value=0.0, step=100.0, value=0.0)
                status = st.selectbox("Status", ["pending", "paid", "partial"], index=0)
                date_paid = st.date_input("Date", value=date.today())
                notes = st.text_input("Notes", value="")
                ok = st.form_submit_button("✅ Save Foundation Payment")

            if ok:
                try:
                    supabase.table("foundation_payments").insert({
                        "member_id": int(mid),
                        "amount_paid": float(amount_paid),
                        "amount_pending": float(amount_pending),
                        "status": status,
                        "date_paid": str(date_paid),
                        "notes": notes.strip(),
                    }).execute()
                    st.success("Saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed (RLS/policy/column): {e}")

        # 3) Add Fine
        elif action == "Add Fine":
            with st.form("admin_add_fine", clear_on_submit=True):
                mid = st.selectbox("Member", member_ids, format_func=mid_fmt)
                amount = st.number_input("Fine amount", min_value=0.0, step=10.0, value=0.0)
                reason = st.text_input("Reason", value="")
                status = st.selectbox("Status", ["unpaid", "paid"], index=0)
                paid_at = st.date_input("Paid date (if paid)", value=date.today())
                ok = st.form_submit_button("✅ Save Fine")

            if ok:
                try:
                    payload = {
                        "member_id": int(mid),
                        "amount": float(amount),
                        "reason": reason.strip(),
                        "status": status,
                    }
                    if status == "paid":
                        payload["paid_at"] = str(paid_at)
                    supabase.table("fines").insert(payload).execute()
                    st.success("Saved.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed (RLS/policy/column): {e}")

        # 4) Record Repayment
        elif action == "Record Repayment":
            # show loans for picking
            loan_opts = []
            try:
                loans_rows = supabase.table("loans").select("id,borrower_member_id,borrower_name,status").order("id", desc=True).limit(300).execute().data or []
                for r in loans_rows:
                    lid = r.get("id")
                    if lid is None:
                        continue
                    bm = r.get("borrower_member_id")
                    bn = r.get("borrower_name") or f"Member {bm}"
                    stt = r.get("status") or ""
                    loan_opts.append((int(lid), f"Loan {lid} — {bn} (member {bm}) [{stt}]"))
            except Exception:
                loan_opts = []

            with st.form("admin_add_repayment", clear_on_submit=True):
                if loan_opts:
                    lid = st.selectbox("Loan", [x[0] for x in loan_opts], format_func=lambda x: dict(loan_opts).get(x, str(x)))
                else:
                    lid = st.number_input("Loan ID", min_value=1, step=1, value=1)

                borrower_member_id = st.selectbox("Borrower member_id", member_ids, format_func=mid_fmt)
                paid_by_member_id = st.selectbox("Paid by member_id", member_ids, format_func=mid_fmt)
                amount_paid = st.number_input("Amount paid", min_value=0.0, step=50.0, value=0.0)
                paid_at = st.date_input("Paid at", value=date.today())
                notes = st.text_input("Notes", value="")
                ok = st.form_submit_button("✅ Save Repayment")

            if ok:
                try:
                    borrower_name = members_by_id.get(int(borrower_member_id), {}).get("name") or members_by_id.get(int(borrower_member_id), {}).get("email") or f"Member {borrower_member_id}"
                    payer_name = members_by_id.get(int(paid_by_member_id), {}).get("name") or members_by_id.get(int(paid_by_member_id), {}).get("email") or f"Member {paid_by_member_id}"

                    supabase.table("repayments").insert({
                        "loan_id": int(lid),
                        "member_id": int(paid_by_member_id),
                        "member_name": payer_name,
                        "borrower_member_id": int(borrower_member_id),
                        "borrower_name": borrower_name,
                        "amount_paid": float(amount_paid),
                        "paid_at": str(paid_at),
                        "notes": notes.strip(),
                    }).execute()
                    st.success("Saved. Ports will update.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Insert failed (RLS/policy/column): {e}")

        # 5) Approve Loan (Request -> Loan)
        elif action == "Approve Loan (Request -> Loan)":
            if not table_exists("loan_requests"):
                st.error("loan_requests table not found (or RLS blocks). This approve flow needs loan_requests.")
            else:
                try:
                    reqs = supabase.table("loan_requests").select("*").order("created_at", desc=True).limit(200).execute().data or []
                except Exception as e:
                    reqs = []
                    st.error(f"Cannot read loan_requests (RLS): {e}")

                df = pd.DataFrame(reqs or [])
                if df.empty:
                    st.info("No loan requests found.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    with st.form("admin_approve_request", clear_on_submit=False):
                        req_id = st.number_input("Request ID", min_value=1, step=1, value=int(df.iloc[0]["id"]))
                        new_status = st.selectbox("Loan status after approval", ["active", "open", "pending", "approved"], index=0)
                        ok = st.form_submit_button("✅ Approve + Create Loan")

                    if ok:
                        try:
                            row = supabase.table("loan_requests").select("*").eq("id", int(req_id)).limit(1).execute().data
                            if not row:
                                st.error("Request not found.")
                            else:
                                r = row[0]
                                # update request
                                supabase.table("loan_requests").update({
                                    "status": "approved",
                                    "approved_at": now_iso()
                                }).eq("id", int(req_id)).execute()

                                # create loan
                                loan_payload = {
                                    "borrower_member_id": int(r.get("borrower_member_id")),
                                    "borrower_name": r.get("borrower_name"),
                                    "surety_member_id": int(r.get("surety_member_id")) if r.get("surety_member_id") is not None else None,
                                    "surety_name": r.get("surety_name"),
                                    "principal": float(r.get("requested_amount") or 0),
                                    "status": new_status,
                                    "created_at": now_iso(),
                                }
                                if (r.get("notes") or "").strip():
                                    loan_payload["notes"] = r.get("notes").strip()

                                # drop None keys
                                loan_payload = {k: v for k, v in loan_payload.items() if v is not None}
                                supabase.table("loans").insert(loan_payload).execute()

                                st.success("Loan approved and created.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Approve failed (RLS/columns): {e}")

        # 6) Issue Loan (set status)
        elif action == "Issue Loan (set status Active/Open)":
            try:
                pending = supabase.table("loans").select("id,borrower_member_id,borrower_name,principal,status,created_at").order("created_at", desc=True).limit(200).execute().data or []
            except Exception as e:
                pending = []
                st.error(f"Cannot read loans (RLS): {e}")

            df = pd.DataFrame(pending or [])
            if df.empty:
                st.info("No loans found.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
                with st.form("admin_issue_loan"):
                    loan_id = st.number_input("Loan ID", min_value=1, step=1, value=int(df.iloc[0]["id"]))
                    new_status = st.selectbox("New status", ["active", "open", "ongoing", "approved"], index=0)
                    ok = st.form_submit_button("✅ Update Loan Status")

                if ok:
                    try:
                        supabase.table("loans").update({
                            "status": new_status,
                            "issued_at": now_iso()
                        }).eq("id", int(loan_id)).execute()
                        st.success("Loan status updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed (RLS/columns): {e}")

        # 7) Conduct Payout
        elif action == "Conduct Payout":
            st.caption("This records a payout row. If you have app_state rotation, it tries to increment next_payout_index too.")
            with st.form("admin_payout"):
                payout_date = st.date_input("Payout date", value=date.today())
                notes = st.text_input("Notes", value="Bi-weekly payout")
                confirm = st.checkbox("Confirm payout", value=False)
                ok = st.form_submit_button("✅ Conduct Payout")

            if ok:
                if not confirm:
                    st.warning("Please confirm first.")
                else:
                    try:
                        # Find current beneficiary from view/table if you have it
                        beneficiary_member_id = None
                        beneficiary_name = None

                        if table_exists("current_cycle_beneficiary"):
                            cur = supabase.table("current_cycle_beneficiary").select("*").limit(1).execute().data or []
                            if cur:
                                c = cur[0]
                                # best-effort keys
                                beneficiary_member_id = c.get("beneficiary_member_id") or c.get("member_id") or c.get("beneficiary_id")
                                beneficiary_name = c.get("beneficiary_name") or c.get("member_name") or c.get("name")

                        # If view missing, allow manual selection fallback
                        if beneficiary_member_id is None:
                            beneficiary_member_id = st.session_state.get("manual_beneficiary_id")

                        if beneficiary_member_id is None:
                            # ask inside the flow without blocking the whole app
                            st.session_state["manual_beneficiary_id"] = my_member_id
                            st.warning("current_cycle_beneficiary not available. Select beneficiary below and click Conduct Payout again.")
                            manual = st.selectbox("Select beneficiary member_id", all_member_ids, format_func=lambda x: member_label(x, members_by_id))
                            st.session_state["manual_beneficiary_id"] = int(manual)
                        else:
                            # Insert payout
                            if not table_exists("payouts"):
                                st.error("payouts table not found (or RLS blocks). Create payouts or enable it.")
                            else:
                                supabase.table("payouts").insert({
                                    "member_id": int(beneficiary_member_id),
                                    "beneficiary_name": beneficiary_name or (members_by_id.get(int(beneficiary_member_id), {}).get("name") or ""),
                                    "payout_date": str(payout_date),
                                    "notes": notes.strip(),
                                    "created_at": now_iso(),
                                }).execute()

                                # optional: increment app_state.next_payout_index
                                if table_exists("app_state"):
                                    try:
                                        row = supabase.table("app_state").select("id,next_payout_index").eq("id", 1).limit(1).execute().data
                                        if row:
                                            npi = row[0].get("next_payout_index")
                                            npi = int(npi) if npi is not None else 0
                                            supabase.table("app_state").update({"next_payout_index": npi + 1}).eq("id", 1).execute()
                                    except Exception:
                                        pass

                                st.success("Payout recorded.")
                                st.rerun()
                    except Exception as e:
                        st.error(f"Payout failed (RLS/columns): {e}")

# ============================================================
# MEMBER: REQUEST LOAN (RULE + QUALIFIED SURETY)
# ============================================================
with st.expander("🔽 Member: Request Loan", expanded=not is_admin):
    st.caption("Request a loan. You must choose a qualified surety. Admin will approve and issue the loan.")

    surety_ids = [mid for mid in all_member_ids if int(mid) != my_member_id]
    if not surety_ids:
        st.info("No surety options available.")
    else:
        with st.form("member_request_loan", clear_on_submit=True):
            requested_amount = st.number_input("Requested amount", min_value=0.0, step=100.0, value=0.0)
            surety_id = st.selectbox("Select Surety (must be qualified)", surety_ids, format_func=lambda x: member_label(x, members_by_id))
            notes = st.text_input("Notes (optional)", value="")
            ok = st.form_submit_button("✅ Submit Loan Request")

        if ok:
            try:
                # calculate eligibility
                my_tot = compute_capacity(my_member_id)
                surety_tot = compute_capacity(int(surety_id))
                benefitted = member_has_benefitted(my_member_id)

                # surety must be qualified to cover requested amount
                surety_ok = requested_amount <= surety_tot["capacity"]

                eligible = False
                reason = ""
                if not surety_ok:
                    eligible = False
                    reason = "Surety not qualified: surety capacity is below requested amount."
                else:
                    if not benefitted:
                        eligible = requested_amount <= my_tot["capacity"]
                        if not eligible:
                            reason = "Not eligible: requested amount is above your borrowing capacity."
                    else:
                        eligible = requested_amount <= (my_tot["capacity"] + surety_tot["capacity"])
                        if not eligible:
                            reason = "Not eligible: above combined capacity (you already benefitted)."

                borrower_name = members_by_id.get(my_member_id, {}).get("name") or members_by_id.get(my_member_id, {}).get("email") or f"Member {my_member_id}"
                surety_name = members_by_id.get(int(surety_id), {}).get("name") or members_by_id.get(int(surety_id), {}).get("email") or f"Member {surety_id}"

                # write request
                if table_exists("loan_requests"):
                    supabase.table("loan_requests").insert({
                        "borrower_member_id": my_member_id,
                        "borrower_name": borrower_name,
                        "surety_member_id": int(surety_id),
                        "surety_name": surety_name,
                        "requested_amount": float(requested_amount),
                        "status": "eligible" if eligible else "rejected",
                        "notes": notes.strip(),
                        "created_at": now_iso(),
                    }).execute()
                else:
                    # fallback: create a loans row as requested
                    supabase.table("loans").insert({
                        "borrower_member_id": my_member_id,
                        "borrower_name": borrower_name,
                        "surety_member_id": int(surety_id),
                        "surety_name": surety_name,
                        "principal": float(requested_amount),
                        "status": "requested" if eligible else "rejected",
                        "notes": notes.strip(),
                        "created_at": now_iso(),
                    }).execute()

                if eligible:
                    st.success("✅ Request submitted (eligible). Waiting for admin approval.")
                else:
                    st.warning(f"❌ Request submitted but NOT eligible. {reason}")

                st.rerun()
            except Exception as e:
                st.error(f"Loan request failed (RLS/columns): {e}")

# ============================================================
# READ DATA FOR DASHBOARD (Member view by default)
# ============================================================
# Admin can optionally view ALL or a chosen member
with st.expander("🔽 View Mode", expanded=True):
    if is_admin:
        view_mode = st.selectbox("Admin view", ["My data (member)", "All members", "Specific member"], index=1)
        chosen_member = my_member_id
        if view_mode == "Specific member":
            chosen_member = st.selectbox("Choose member_id", all_member_ids, index=0, format_func=lambda x: member_label(x, members_by_id))
        viewing_all = (view_mode == "All members")
    else:
        viewing_all = False
        chosen_member = my_member_id

# Fetch tables
if viewing_all and is_admin:
    contrib_df = fetch_df("contributions", "*", None, None, "created_at")
    found_df = fetch_df("foundation_payments", "*", None, None, "date_paid")
    fines_df = fetch_df("fines", "*", None, None, "created_at")
    loans_df = fetch_df("loans", "*", None, None, "created_at")
    repay_df = fetch_df("repayments", "*", None, None, "paid_at")
else:
    contrib_df = fetch_df("contributions", "*", "member_id", int(chosen_member), "created_at")
    found_df = fetch_df("foundation_payments", "*", "member_id", int(chosen_member), "date_paid")
    fines_df = fetch_df("fines", "*", "member_id", int(chosen_member), "created_at")
    loans_df = fetch_df("loans", "*", "borrower_member_id", int(chosen_member), "created_at")
    repay_df = fetch_df("repayments", "*", "member_id", int(chosen_member), "paid_at")

# KPIs / Ports
total_contrib = safe_sum(contrib_df, "amount")
found_paid = safe_sum(found_df, "amount_paid")
found_pending = safe_sum(found_df, "amount_pending")
rep_col = "amount_paid" if "amount_paid" in repay_df.columns else ("amount" if "amount" in repay_df.columns else None)
total_repaid = safe_sum(repay_df, rep_col) if rep_col else 0.0
found_paid_plus_repay = found_paid + total_repaid

unpaid_fines = 0.0
if not fines_df.empty and "status" in fines_df.columns and "amount" in fines_df.columns:
    unpaid_fines = float(pd.to_numeric(
        fines_df[fines_df["status"].astype(str).str.lower() == "unpaid"]["amount"],
        errors="coerce"
    ).fillna(0).sum())

active_loans = 0
if not loans_df.empty and "status" in loans_df.columns:
    active_loans = int((loans_df["status"].astype(str).str.lower().isin(["active", "open", "ongoing"])).sum())
elif not loans_df.empty:
    active_loans = len(loans_df)

loan_total = 0.0
for c in ["total_due", "balance", "principal_current", "principal"]:
    if not loans_df.empty and c in loans_df.columns:
        loan_total = safe_sum(loans_df, c)
        break

total_interest_generated = 0.0
if is_admin and (not loans_df.empty) and ("total_interest_generated" in loans_df.columns):
    total_interest_generated = safe_sum(loans_df, "total_interest_generated")

# Ports
with st.expander("🔽 Summary (Ports)", expanded=True):
    if is_admin:
        k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    else:
        k1, k2, k3, k4, k5, k6 = st.columns(6)

    k1.markdown(f"<div class='kpi'><div class='label'>Total Contributions</div><div class='value'>{total_contrib:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi'><div class='label'>Foundation Paid (+Repay)</div><div class='value'>{found_paid_plus_repay:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi'><div class='label'>Foundation Pending</div><div class='value'>{found_pending:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi'><div class='label'>Unpaid Fines</div><div class='value'>{unpaid_fines:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k5.markdown(f"<div class='kpi'><div class='label'>Active Loans</div><div class='value'>{active_loans}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    k6.markdown(f"<div class='kpi'><div class='label'>Loan Total</div><div class='value'>{loan_total:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)
    if is_admin:
        k7.markdown(f"<div class='kpi'><div class='label'>Total Interest Generated</div><div class='value'>{total_interest_generated:,.2f}</div><div class='accent'></div></div>", unsafe_allow_html=True)

# Beneficiary / Next Beneficiary ports (best effort)
with st.expander("🔽 Beneficiary (Bi-weekly)", expanded=True):
    # Current beneficiary
    try:
        if table_exists("current_cycle_beneficiary"):
            cur = supabase.table("current_cycle_beneficiary").select("*").limit(1).execute().data or []
        else:
            cur = []
        if cur:
            c = cur[0]
            name = c.get("beneficiary_name") or c.get("member_name") or c.get("name") or "Unknown"
            cyc = c.get("cycle_no") or c.get("cycle_number") or c.get("cycle") or ""
            start = c.get("season_start_date") or c.get("cycle_start_date") or c.get("start_date") or ""
            payout_date = c.get("payout_date") or c.get("next_payout_date") or ""
            st.markdown(
                f"<div class='card'><b>Current Beneficiary:</b> {name}<br>"
                f"<span class='small-muted'>Cycle: {cyc} • Season start: {start} • Payout date: {payout_date}</span></div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown("<div class='card'><b>Current Beneficiary:</b> <span class='small-muted'>Not configured / blocked by RLS</span></div>", unsafe_allow_html=True)
    except Exception:
        st.markdown("<div class='card'><b>Current Beneficiary:</b> <span class='small-muted'>Not available</span></div>", unsafe_allow_html=True)

    # Next beneficiary totals (RPC if you have it)
    try:
        res = supabase.rpc("next_beneficiary_totals", {}).execute()
        rows = res.data or []
        if rows:
            r = rows[0]
            nm = r.get("next_member_name", "")
            mid = r.get("next_member_id", "")
            tc = float(r.get("total_contribution", 0) or 0)
            tfp = float(r.get("total_foundation_paid", 0) or 0)
            tfn = float(r.get("total_foundation_pending", 0) or 0)
            tl = float(r.get("total_loan", 0) or 0)
            st.markdown(
                f"<div class='card'><b>Next Beneficiary After Payout</b><br>"
                f"<span class='small-muted'>{nm} (member_id {mid})</span><br><br>"
                f"• Total Contribution: <b>{tc:,.2f}</b><br>"
                f"• Total Foundation Paid: <b>{tfp:,.2f}</b><br>"
                f"• Total Foundation Pending: <b>{tfn:,.2f}</b><br>"
                f"• Total Loan: <b>{tl:,.2f}</b>"
                f"</div>",
                unsafe_allow_html=True
            )
    except Exception:
        pass

st.markdown("<hr/>", unsafe_allow_html=True)

# ============================================================
# VIEW TABLES (Clean dropdown)
# ============================================================
page = st.selectbox(
    "🔽 View Tables",
    ["Contributions", "Foundation Payments", "Loans", "Repayments", "Fines", "My Profile"],
    index=0,
)

def show_df(title: str, df: pd.DataFrame, preferred=None):
    st.subheader(title)
    if df.empty:
        st.info("No records found.")
        return
    cols = df.columns.tolist()
    if preferred:
        front = [c for c in preferred if c in cols]
        back = [c for c in cols if c not in front]
        cols = front + back
    st.dataframe(df[cols], use_container_width=True, hide_index=True)

if page == "Contributions":
    show_df("Contributions", contrib_df, ["id", "member_id", "amount", "kind", "created_at"])

elif page == "Foundation Payments":
    show_df("Foundation Payments", found_df, ["id", "member_id", "amount_paid", "amount_pending", "status", "date_paid", "notes"])

elif page == "Loans":
    show_df("Loans", loans_df, [
        "id", "borrower_member_id", "borrower_name", "surety_member_id", "surety_name",
        "principal", "total_due", "balance", "status", "created_at", "issued_at"
    ])

elif page == "Repayments":
    show_df("Repayments", repay_df, [
        "id", "loan_id", "member_id", "member_name", "borrower_member_id", "borrower_name",
        "amount_paid", "paid_at", "notes", "created_at"
    ])

elif page == "Fines":
    show_df("Fines", fines_df, ["id", "member_id", "amount", "reason", "status", "paid_at", "created_at"])

else:
    st.subheader("My Profile")
    st.json(me)

# Footer
if not is_admin:
    st.caption("Member mode: you can view only your own data. Loan requests wait for admin approval.")
else:
    st.caption("Admin mode: you can add data from the dashboard. If any insert/update fails, it is RLS policy.")
