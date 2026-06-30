import streamlit as st
import duckdb

# -------------------------------
# Page config
# -------------------------------
st.set_page_config(page_title="Player Profile Dashboard", layout="wide")

st.title("Player Profile Dashboard")

# -------------------------------
# Load data (lineups only for now)
# -------------------------------
con = duckdb.connect(database=':memory:')

con.execute("""
    CREATE TABLE lineups AS SELECT * FROM read_parquet('lineups.parquet');
""")

# -------------------------------
# Sidebar – Player selector
# -------------------------------
st.sidebar.title("Player Selector")

players = con.execute("""
    SELECT DISTINCT player_id, player_name
    FROM lineups
    ORDER BY player_name
""").df()

player_name = st.sidebar.selectbox("Select Player", players["player_name"])
player_id = int(players.loc[players["player_name"] == player_name, "player_id"].iloc[0])

st.markdown("---")
st.header(f"Player Profile — {player_name}")

# -------------------------------
# Player bio (nice layout)
# -------------------------------
bio = con.execute(f"""
    SELECT player_id, player_name, player_nickname, birth_date, player_gender,
           player_height, player_weight, jersey_number, country, formations
    FROM lineups
    WHERE player_id = {player_id}
    LIMIT 1
""").df()

if bio.empty:
    st.info("No bio data available for this player.")
else:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Basic Information")
        st.write(f"**Player ID:** {int(bio['player_id'].iloc[0])}")
        st.write(f"**Name:** {bio['player_name'].iloc[0]}")
        st.write(f"**Nickname:** {bio['player_nickname'].iloc[0]}")
        st.write(f"**Birth Date:** {bio['birth_date'].iloc[0]}")
        st.write(f"**Gender:** {bio['player_gender'].iloc[0]}")
        st.write(f"**Country:** {bio['country'].iloc[0]}")

    with col2:
        st.subheader("Physical & Squad Info")
        st.write(f"**Height:** {bio['player_height'].iloc[0]} cm")
        st.write(f"**Weight:** {bio['player_weight'].iloc[0]} kg")
        st.write(f"**Jersey Number:** {bio['jersey_number'].iloc[0]}")
        #st.write(f"**Formation:** {bio['formations'].iloc[0]}")

st.markdown("---")
#st.caption("Step 1: Player bio with sidebar selector")
