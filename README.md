# Airline Delay & Reliability Analysis

Are flight delays mainly about the airline, the airport, the route or the time of travel, and which airlines
remain less reliable after controlling for those?

## Data (real)
US Bureau of Transportation Statistics on-time records for **all 336,776 flights departing JFK, LGA and EWR in
2013**, with NOAA hourly airport weather and the FAA aircraft registry, as published in the `nycflights13`
dataset. `python src/get_data.py` pulls it from PyPI. The same code runs on any BTS TranStats extract with the
same columns.

## Method
| Question | Approach |
|---|---|
| Q1 Which airlines have the highest delay and cancellation rates on comparable routes? | SQL: carrier summary; like-for-like comparison on the 83 routes flown by 2+ carriers (each carrier vs the average of all carriers on the same routes) |
| Q2 How much do time, season, airport and weather matter? | Linear probability models; R^2 of each factor alone and added last; weather effects (rain, low visibility, wind) with carrier/route/month/hour fixed effects; aircraft-age effects |
| Q3 After controls, are some airlines still worse? | `unreliable ~ carrier | route + origin x date + scheduled hour`, two-way clustered SEs (date, route); effects vs the flight-weighted average carrier; robustness on competitive routes only; same model for cancellations |
| Passenger app | Route x carrier rates with Wilson 95% intervals and empirical-Bayes (beta-binomial) shrinkage |

Unreliable = arrived 15+ minutes late (BTS on-time definition), cancelled, or diverted.

## Results (`outputs/results.json`)
- 26.6% of flights were unreliable; 2.5% were cancelled.
- Daily airport conditions (origin x date) alone explain 15.6% of the variation; carrier 1.6%, route 1.6%,
  scheduled hour 4.1%. Rain at departure: +22.3 pp (95% CI 17.9-26.7); low visibility +16.8 pp.
- Departures scheduled at 21:00 were unreliable 39.8% of the time vs 11.1% at 05:00.
- After controls, 5 carriers were significantly worse than average (ExpressJet +10.2 pp, 95% CI +8.2 to +12.2;
  AirTran, Envoy, Endeavor, JetBlue) and 5 significantly better (Delta -9.1 pp, American, Virgin America,
  US Airways, United). The ranking is identical on competitive routes only (Spearman 1.00).
- Aircraft 21+ years old: +4.1 pp vs 0-5 years (95% CI 2.6-5.6).

## Run
```bash
pip install -r requirements.txt
python src/get_data.py
python src/build_db.py
python src/analysis.py
streamlit run app/dashboard.py
```

## Limitations
One year, NYC departures only; several carriers have since merged. No delay-cause codes in this extract.
Regional carriers operate flights sold under mainline brands. Effects are associations: carriers choose schedules,
fleets and hubs.
