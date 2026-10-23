-- Airline reliability: cleaned flight table with weather and aircraft attributes.
-- Placeholder in curly braces is filled by src/build_db.py.

CREATE OR REPLACE TABLE airlines AS SELECT * FROM read_csv_auto('{raw}/airlines.csv');
CREATE OR REPLACE TABLE airports AS SELECT * FROM read_csv_auto('{raw}/airports.csv', nullstr = 'NA');
CREATE OR REPLACE TABLE planes   AS SELECT * FROM read_csv_auto('{raw}/planes.csv', nullstr = 'NA');
CREATE OR REPLACE TABLE weather  AS SELECT * FROM read_csv_auto('{raw}/weather.csv', nullstr = 'NA');

CREATE OR REPLACE TABLE flights AS
WITH f AS (
    SELECT *, make_date(year, month, day) AS flight_date
    FROM read_csv_auto('{raw}/flights.csv', nullstr = 'NA')
),
w AS (  -- one weather row per airport-hour (a few hours are duplicated in the source)
    SELECT origin, time_hour, any_value(temp) AS temp, any_value(wind_speed) AS wind_speed,
           any_value(precip) AS precip, any_value(visib) AS visib
    FROM weather GROUP BY ALL
)
SELECT
    f.flight_date, f.month, f.day, isodow(f.flight_date) AS dow, f.hour AS sched_hour,
    f.carrier, a.name AS carrier_name, f.flight, f.tailnum, f.origin, f.dest,
    f.origin || '-' || f.dest AS route, f.distance,
    f.dep_delay, f.arr_delay,
    f.dep_time IS NULL                                    AS cancelled,
    f.dep_time IS NOT NULL AND f.arr_delay IS NULL        AS diverted,
    CASE WHEN f.arr_delay IS NULL THEN NULL
         WHEN f.arr_delay >= 15 THEN 1 ELSE 0 END         AS late15,        -- BTS on-time definition
    CASE WHEN f.dep_time IS NULL OR f.arr_delay IS NULL OR f.arr_delay >= 15
         THEN 1 ELSE 0 END                                AS unreliable,    -- late, cancelled or diverted
    w.temp, w.wind_speed, w.precip, w.visib,
    p.year AS plane_year, p.seats, p.manufacturer
FROM f
LEFT JOIN airlines a ON a.carrier = f.carrier
LEFT JOIN w ON w.origin = f.origin AND w.time_hour = f.time_hour
LEFT JOIN planes p ON p.tailnum = f.tailnum;

-- Routes flown by at least 2 carriers with >= 100 flights each: the comparable set
CREATE OR REPLACE TABLE competitive_routes AS
WITH rc AS (SELECT route, carrier, count(*) AS n FROM flights GROUP BY ALL HAVING count(*) >= 100)
SELECT route FROM rc GROUP BY route HAVING count(DISTINCT carrier) >= 2;

CREATE OR REPLACE TABLE carrier_summary AS
SELECT carrier, carrier_name,
       count(*)                                  AS flights,
       avg(cancelled::INT)                       AS cancel_rate,
       avg(late15)                               AS late_rate,
       avg(unreliable)                           AS unreliable_rate,
       median(arr_delay)                         AS median_arr_delay,
       quantile_cont(arr_delay, 0.9)             AS p90_arr_delay
FROM flights GROUP BY ALL ORDER BY unreliable_rate DESC;

-- Like-for-like: each carrier vs the average of all carriers on the SAME competitive routes
CREATE OR REPLACE TABLE carrier_route_compare AS
WITH rc AS (
    SELECT f.route, f.carrier, count(*) AS n, avg(f.unreliable) AS rate
    FROM flights f JOIN competitive_routes USING (route) GROUP BY ALL
),
rm AS (SELECT route, sum(rate * n) / sum(n) AS route_rate FROM rc GROUP BY route)
SELECT rc.carrier,
       sum(rc.n)                                     AS flights_on_shared_routes,
       count(*)                                      AS shared_routes,
       sum(rc.n * rc.rate) / sum(rc.n)               AS carrier_rate,
       sum(rc.n * rm.route_rate) / sum(rc.n)         AS same_routes_avg_rate,
       sum(rc.n * (rc.rate - rm.route_rate)) / sum(rc.n) AS excess_rate
FROM rc JOIN rm USING (route)
GROUP BY rc.carrier ORDER BY excess_rate DESC;

CREATE OR REPLACE TABLE route_carrier AS
SELECT route, origin, dest, carrier, count(*) AS flights,
       sum(unreliable) AS unreliable_flights, avg(unreliable) AS unreliable_rate,
       avg(cancelled::INT) AS cancel_rate, median(arr_delay) AS median_arr_delay,
       quantile_cont(arr_delay, 0.9) AS p90_arr_delay
FROM flights GROUP BY ALL;
