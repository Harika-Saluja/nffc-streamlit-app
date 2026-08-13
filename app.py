import streamlit as st
import hmac

st.set_page_config(page_title="Squad Analytics", layout="wide")

# ===========================================================
# PASSWORD GATE
#
# Runs BEFORE navigation is set up, so it protects every page in one
# place — this only works cleanly because we're using st.navigation()
# below instead of the classic auto-discovered pages/ sidebar. With
# the classic approach, each page script runs independently when a
# user navigates directly to it, so a gate placed only in app.py could
# be bypassed by opening a page's own URL directly; st.navigation()
# routes every page through this same script, so there's no bypass.
#
# The actual password lives in Streamlit's secrets store, not in this
# file — see the setup note below the code.
# ===========================================================


def check_password() -> bool:
    def password_entered():
        if hmac.compare_digest(st.session_state["password_input"], st.secrets["app_password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]  # don't keep the raw password in memory
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.title("Squad Analytics")
    st.text_input("Password", type="password", on_change=password_entered, key="password_input")
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

# ===========================================================
# NAVIGATION — explicitly lists every real page. The "app" entry from
# the old auto-discovered sidebar is gone because this script is now
# the router, not a page itself. Page files can stay in pages/ (as
# below) or move anywhere — st.Page() just needs a valid path.
# ===========================================================
pages = [
    st.Page("pages/profile_dashboard.py", title="Profile Dashboard", default=True),
    st.Page("pages/league_adaptation.py", title="League Adaptation"),
    st.Page("pages/workload_injury_risk.py", title="Workload And Injury Risk"),
    st.Page("pages/age_optimization.py", title="Age Optimization"),
    st.Page("pages/squad_optimizer.py", title="Squad Optimizer"),
    st.Page("pages/myth_verdict.py", title="Myth Verdict"),
]

pg = st.navigation(pages)
pg.run()