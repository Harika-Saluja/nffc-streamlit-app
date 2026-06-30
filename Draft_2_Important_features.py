import duckdb

# ---------------------------------------------------------
# 1. Connect to DuckDB
# ---------------------------------------------------------
con = duckdb.connect("nffc.duckdb")

# ---------------------------------------------------------
# 2. Load existing parquet files
# ---------------------------------------------------------
con.execute("CREATE OR REPLACE TABLE lineups AS SELECT * FROM 'lineups.parquet'")
con.execute("CREATE OR REPLACE TABLE matches AS SELECT * FROM 'matches.parquet'")
con.execute("CREATE OR REPLACE TABLE events AS SELECT * FROM 'events.parquet'")
con.execute("CREATE OR REPLACE TABLE injuries AS SELECT * FROM 'injuries.parquet'")
con.execute("CREATE OR REPLACE TABLE catapult AS SELECT * FROM 'catapult.parquet'")

print("All parquet files loaded into DuckDB!")

# ---------------------------------------------------------
# 3. H1 – Adaptation Tax
# ---------------------------------------------------------
con.execute("""
CREATE OR REPLACE TABLE H1 AS
WITH first10 AS (
    SELECT
        e.player_id,
        e.match_id,
        m.match_date,
        e.pass_pass_success_probability,
        e.shot_statsbomb_xg,
        e.counterpress,
        ROW_NUMBER() OVER (PARTITION BY e.player_id ORDER BY m.match_date) AS rn
    FROM events e
    JOIN matches m ON e.match_id = m.match_id
)
SELECT
    player_id,
    AVG(pass_pass_success_probability) FILTER (WHERE rn <= 10) AS first10_pass_success,
    AVG(pass_pass_success_probability) FILTER (WHERE rn > 10) AS later_pass_success,
    AVG(shot_statsbomb_xg) FILTER (WHERE rn <= 10) AS first10_xg,
    AVG(shot_statsbomb_xg) FILTER (WHERE rn > 10) AS later_xg
FROM first10
GROUP BY player_id;
""")

print("H1 created!")

# ---------------------------------------------------------
# 4. H4 – Transfer Timing
# ---------------------------------------------------------
con.execute("""
CREATE OR REPLACE TABLE H4 AS
WITH perf AS (
    SELECT
        e.player_id,
        TRY_CAST(m.match_date AS DATE) AS match_date,
        e.pass_pass_success_probability,
        e.shot_statsbomb_xg
    FROM events e
    JOIN matches m ON e.match_id = m.match_id
),
tagged AS (
    SELECT *,
        CASE WHEN match_date < DATE '2024-02-01' THEN 'before_window'
             ELSE 'after_window'
        END AS period
    FROM perf
    WHERE match_date IS NOT NULL
)
SELECT
    player_id,
    AVG(pass_pass_success_probability) FILTER (WHERE period='before_window') AS pass_before,
    AVG(pass_pass_success_probability) FILTER (WHERE period='after_window') AS pass_after,
    AVG(shot_statsbomb_xg) FILTER (WHERE period='before_window') AS xg_before,
    AVG(shot_statsbomb_xg) FILTER (WHERE period='after_window') AS xg_after
FROM tagged
GROUP BY player_id;
""")

print("H4 created!")

# ---------------------------------------------------------
# 5. H5 – Age Optimization
# ---------------------------------------------------------
con.execute("""
CREATE OR REPLACE TABLE H5 AS
WITH ages AS (
    SELECT
        l.player_id,
        TRY_CAST(l.birth_date AS DATE) AS birth_date,
        TRY_CAST(m.match_date AS DATE) AS match_date,
        e.pass_pass_success_probability,
        e.shot_statsbomb_xg
    FROM lineups l
    JOIN events e ON l.player_id = e.player_id
    JOIN matches m ON e.match_id = m.match_id
),
clean AS (
    SELECT
        player_id,
        DATE_PART('year', match_date) - DATE_PART('year', birth_date) AS age,
        pass_pass_success_probability,
        shot_statsbomb_xg
    FROM ages
    WHERE birth_date IS NOT NULL
      AND match_date IS NOT NULL
)
SELECT
    age,
    AVG(pass_pass_success_probability) AS avg_pass_success,
    AVG(shot_statsbomb_xg) AS avg_xg
FROM clean
GROUP BY age
ORDER BY age;
""")

print("H5 created!")

# ---------------------------------------------------------
# H6 – Squad Balance (Corrected Version)
# ---------------------------------------------------------

# Part A — Technical + Availability (StatsBomb + Injuries)
con.execute("""
CREATE OR REPLACE TABLE H6_tech AS
SELECT
    l.player_id,
    l.player_name,
    AVG(e.pass_pass_success_probability) AS pass_success,
    AVG(e.shot_statsbomb_xg) AS xg,
    SUM(i.days_missed) AS total_days_missed
FROM lineups l
LEFT JOIN events e ON l.player_id = e.player_id
LEFT JOIN injuries i ON l.player_id = i.player_id
GROUP BY 1,2;
""")

print("H6_tech created!")

# Part B — Physical (Catapult only)
con.execute("""
CREATE OR REPLACE TABLE H6_phys AS
SELECT
    athlete_id AS catapult_id,
    AVG(v) AS avg_speed,
    AVG(a) AS avg_accel,
    AVG(hr) AS avg_hr,
    AVG(mp) AS avg_metabolic_power
FROM catapult
GROUP BY 1;
""")

print("H6_phys created!")

# Final H6 — Technical + Availability only
# (Physical metrics cannot be merged due to ID mismatch)
con.execute("""
CREATE OR REPLACE TABLE H6 AS
SELECT *
FROM H6_tech;
""")

print("H6 created (technical + availability only)!")

con.execute("COPY H1 TO 'H1.parquet' (FORMAT PARQUET);")
con.execute("COPY H4 TO 'H4.parquet' (FORMAT PARQUET);")
con.execute("COPY H5 TO 'H5.parquet' (FORMAT PARQUET);")
con.execute("COPY H6 TO 'H6.parquet' (FORMAT PARQUET);")

print("Exported H1, H4, H5, H6 to parquet!")

print("Pipeline complete!")
