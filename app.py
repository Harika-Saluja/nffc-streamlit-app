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
# The actual password lives in Streamlit's secrets store (Settings ->
# Secrets on Streamlit Cloud, or .streamlit/secrets.toml locally), not
# in this file.
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
# NAVIGATION — explicitly lists every real page, matching the actual
# filenames in pages/. The "app" entry from the old auto-discovered
# sidebar is gone because this script is now the router, not a page
# itself. The number prefixes on these filenames only matter for
# finding the file — st.navigation() controls the sidebar labels
# directly via title=, so they never show up on screen.
# ===========================================================
pages = [
    st.Page("pages/1_Profile_Dashboard.py", title="Profile Profile", default=True),
    st.Page("pages/2_League_Adaptation.py", title="League Adaptation"),
    st.Page("pages/3_Workload_And_Injury_Risk.py", title="Workload And Injury Risk"),
    st.Page("pages/4_Age_Optimization.py", title="Age Optimization"),
    st.Page("pages/5_Squad_Optimizer.py", title="Squad Optimizer"),
    st.Page("pages/6_Myth_Verdict.py", title="Myth Verdict"),
]

pg = st.navigation(pages)
pg.run()