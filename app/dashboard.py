"""Airline reliability dashboard.  Run:  streamlit run app/dashboard.py"""
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config import DB_PATH, OUT_DIR  # noqa: E402

st.set_page_config(page_title="Airline Reliability", layout="wide")


@st.cache_resource
def con():
    return duckdb.connect(str(DB_PATH), read_only=True)


def q(sql, params=None):
    return con().execute(sql, params or []).df()


R = json.loads((OUT_DIR / "results.json").read_text())
D = R["data"]
st.title("Which airlines are reliably late?")
st.caption(f"US BTS on-time records, all {D['flights']:,} flights departing JFK, LGA and EWR in 2013 "
           f"({D['carriers']} carriers, {D['routes']} routes), joined to hourly airport weather and aircraft data. "
           "Unreliable = arrived 15+ minutes late, cancelled, or diverted.")
tabs = st.tabs(["Compare a route", "Carrier ranking", "What drives delays", "SQL console", "Limitations"])

with tabs[0]:
    routes = q("""SELECT origin, dest, count(DISTINCT carrier) AS carriers, sum(flights) AS flights
                  FROM route_carrier GROUP BY ALL HAVING count(DISTINCT carrier) >= 2 ORDER BY flights DESC""")
    c1, c2 = st.columns(2)
    origin = c1.selectbox("From", sorted(routes.origin.unique()))
    dest = c2.selectbox("To", routes[routes.origin == origin].dest.tolist())
    eb = q("""SELECT e.*, a.name FROM route_carrier_eb e JOIN airlines a USING (carrier)
              WHERE route = ? ORDER BY eb_rate""", [f"{origin}-{dest}"])
    if eb.empty:
        st.info("Not enough flights on this route.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=100 * eb.raw_rate, y=eb.name, mode="markers", name="Observed",
                                 error_x=dict(type="data", symmetric=False,
                                              array=100 * (eb.wilson_high - eb.raw_rate),
                                              arrayminus=100 * (eb.raw_rate - eb.wilson_low))))
        fig.add_trace(go.Scatter(x=100 * eb.eb_rate, y=eb.name, mode="markers", name="Shrunk estimate",
                                 marker_symbol="diamond"))
        fig.update_layout(title=f"{origin} to {dest}: % of flights late 15+ min, cancelled or diverted (95% CI)",
                          xaxis_title="%", height=300 + 40 * len(eb))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Shrunk estimates pull small samples toward the route average (empirical Bayes), so a carrier "
                   "with 30 flights cannot top the ranking by luck.")
        dist = q("""SELECT carrier_name, arr_delay FROM flights
                    WHERE origin = ? AND dest = ? AND arr_delay IS NOT NULL AND arr_delay BETWEEN -60 AND 240""",
                 [origin, dest])
        st.plotly_chart(px.box(dist, x="carrier_name", y="arr_delay", points=False,
                               title="Arrival delay distribution (minutes, trimmed to -60..240)"),
                        use_container_width=True)

with tabs[1]:
    eff = pd.DataFrame(R["q3_carrier_effects"])
    model = st.radio("Model", eff.model.unique().tolist(), horizontal=True)
    e = eff[eff.model == model].sort_values("effect_pp")
    names = q("SELECT * FROM airlines").set_index("carrier").name
    fig = go.Figure(go.Scatter(x=e.effect_pp, y=e.carrier.map(names), mode="markers",
                               error_x=dict(type="data", symmetric=False, array=e.ci_high - e.effect_pp,
                                            arrayminus=e.effect_pp - e.ci_low)))
    fig.add_vline(x=0, line_dash="dot")
    fig.update_layout(title=f"Adjusted carrier effect vs average carrier, percentage points ({model}), 95% CI",
                      height=520, xaxis_title="pp (positive = less reliable)")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("Controls: route, origin-airport x date (that day's weather, air-traffic programs and congestion), "
                "scheduled departure hour. Standard errors clustered by date and route.")
    st.subheader("Raw vs like-for-like")
    st.dataframe(pd.DataFrame(R["q1_like_for_like"]).round(3), use_container_width=True)

with tabs[2]:
    r2 = R["q2_drop_one_r2"]
    dd = pd.DataFrame({"factor": list(r2["alone"]), "alone": list(r2["alone"].values()),
                       "added last": [r2["drop_one"][k] for k in r2["alone"]]})
    st.plotly_chart(px.bar(dd.melt("factor"), x="value", y="factor", color="variable", barmode="group",
                           orientation="h", title="Share of variation in unreliability explained (R^2)"),
                    use_container_width=True)
    hr = q("SELECT sched_hour, avg(unreliable) AS rate, count(*) AS n FROM flights GROUP BY 1 HAVING n >= 1000 ORDER BY 1")
    st.plotly_chart(px.line(hr, x="sched_hour", y="rate", markers=True, title="Unreliable share by scheduled hour"),
                    use_container_width=True)
    w = R["q2_effects"]["weather_pp"]
    st.markdown("**Weather at departure** (vs none, controlling for carrier, route, month, hour): " + "; ".join(
        f"{k.replace('_', ' ')} {v['effect_pp']:+.1f} pp" for k, v in w.items()))

with tabs[3]:
    st.write("Tables: `flights`, `airlines`, `airports`, `planes`, `weather`, `carrier_summary`, "
             "`carrier_route_compare`, `route_carrier`, `route_carrier_eb`, `carrier_effects`")
    sql = st.text_area("Read-only SQL", "SELECT carrier, avg(unreliable) AS rate, count(*) AS n\nFROM flights GROUP BY 1 ORDER BY 2 DESC")
    if st.button("Run"):
        if not sql.strip().lower().startswith(("select", "with")):
            st.error("Only SELECT queries are allowed.")
        else:
            try:
                st.dataframe(q(sql))
            except Exception as ex:  # noqa: BLE001
                st.error(str(ex))

with tabs[4]:
    st.markdown("""
- One year (2013) and one region (NYC departures). Carriers have since merged (US into AA, VX into AS, EV and 9E
  restructured), so this is a methods demonstration, not a booking guide for today.
- The data have no delay-cause codes; weather comes from hourly airport observations instead.
- Regional carriers (EV, 9E, MQ, YV) operate flights sold under mainline brands; passengers may not see the operator.
- Adjusted effects compare carriers flying the same routes on the same day from the same airport, but carriers
  still choose their schedules, fleets and hubs, so effects are associations, not proof of operational inferiority.
""")
