# CAISO Node Watch — draft 2026-09-07

Sources: CAISO Public Queue Report (run date in file), CAISO Cluster 15 report (posted 2026-07-16),
OpenStreetMap substations (ODbL). All figures are net MW to grid as filed.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** 266 active projects, 74,687 MW,
  92% with storage, 214 already under executed IAs.
- **Cluster 15 today:** 86 active projects, 28,449 MW (22,005 MW storage).
  84 projects / 30,564 MW have withdrawn since intake. CAISO's July 2025 briefing put the
  studied set at 145 projects / ~68 GW; the cohort has since shed roughly 58% of its MW.
- **All-time withdrawn:** 1763 projects / 381,917 MW.

## Where Cluster 15 capacity is still standing (requested service)

| service_type                                            |   count |   sum |
|:--------------------------------------------------------|--------:|------:|
| ENERGY ONLY REQUESTED                                   |      35 | 10931 |
| FULL CAPACITY DELIVERABILITY STATUS REQUESTED           |      50 | 17506 |
| MERCHANT- FULL CAPACITY DELIVERABILITY STATUS REQUESTED |       1 |    12 |

## Top nodes by total pipeline MW (legacy + C15)

| poi_base                | county         | utility   |   legacy_active_mw |   c15_active_mw |   total_withdrawn_mw |   churn_ratio |   c15_survival |
|:------------------------|:---------------|:----------|-------------------:|----------------:|---------------------:|--------------:|---------------:|
| WINDHUB SUBSTATION      | KERN           | SCE       |               4050 |             550 |                11044 |             2 |              1 |
| RED BLUFF SUBSTATION    | RIVERSIDE      | SCE       |               2867 |             725 |                10482 |             2 |              1 |
| VINCENT SUBSTATION      | LOS ANGELES    | SCE       |               2070 |            1450 |                 5240 |             1 |              1 |
| WHIRLWIND SUBSTATION    | KERN           | SCE       |               2472 |             801 |                 7115 |             1 |              1 |
| DELANEY-COLORADO RIVER  | MARICOPA       | DCRT      |               3200 |               0 |                 1472 |             0 |            nan |
| TROUT CANYON SUBSTATION | CLARK          | GLW       |               3000 |               0 |                 1500 |             0 |              0 |
| DRY LAKE SW STA         | KINGS          | PGAE      |                  0 |            2950 |                    0 |             0 |              1 |
| MANNING                 | FRESNO         | LSPC      |                  0 |            2662 |                 1782 |             1 |              1 |
| GATES SUBSTATION        | FRESNO         | PGAE      |               2521 |               0 |                 5233 |             2 |              0 |
| MOSS LANDING            | MONTEREY       | PGAE      |               2250 |             199 |                 1000 |             0 |              1 |
| LUGO                    | SAN BERNARDINO | SCE       |                500 |            1798 |                 5153 |             2 |              0 |
| TESLA                   | ALAMEDA        | PGAE      |               1280 |            1000 |                 3635 |             1 |              0 |

## Graveyard nodes (>2 GW withdrawn, ranked by churn)

| poi_base                   | county          | utility   |   pipeline_mw |   total_withdrawn_mw |   churn_ratio |
|:---------------------------|:----------------|:----------|--------------:|---------------------:|--------------:|
| ELDORADO SUBSTATION        | CLARK           | SCE       |           250 |                10697 |            43 |
| JOHANNA SUBSTATION         | ORANGE          | SCE       |           100 |                 2541 |            25 |
| HIGHWIND SUBSTATION        | KERN            | SCE       |             0 |                 3660 |            23 |
| PISGAH SUBSTATION          | SAN BERNARDINO  | SCE       |           600 |                 7799 |            13 |
| DIABLO CANYON              | SAN LUIS OBISPO | PGAE      |          1000 |                 9451 |             9 |
| ETIWANDA SUBSTATION        | SAN BERNARDINO  | SCE       |           412 |                 2927 |             6 |
| IMPERIAL VALLEY SUBSTATION | IMPERIAL        | SDGE      |           875 |                12100 |             5 |
| PITTSBURG                  | CONTRA COSTA    | PGAE      |           500 |                 2851 |             5 |

## Cluster 15 nodes with little historical wreckage (<500 MW ever withdrawn)

| poi_base                                     | county     | utility   |   c15_active_mw |   c15_fcds_req_mw |   hist_withdrawn_mw |   legacy_active_mw |
|:---------------------------------------------|:-----------|:----------|----------------:|------------------:|--------------------:|-------------------:|
| DRY LAKE SW STA                              | KINGS      | PGAE      |            2950 |              2050 |                   0 |                  0 |
| MANNING                                      | FRESNO     | LSPC      |            2662 |              2662 |                   0 |                  0 |
| VALLEY SWITCH                                | NYE        | GLW       |            1450 |                 0 |                 180 |                550 |
| HARLAN SW STA                                | FRESNO     | PGAE      |            1450 |              1450 |                   0 |                  0 |
| MAGUNDEN-PASTORIA                            | KERN       | SCE       |             600 |                 0 |                 200 |                  0 |
| QUINTO SW STA                                | MERCED     | PGAE      |             500 |               500 |                 400 |                150 |
| NORTH GILA - HOODOO WASH (SDGE PORTION ONLY) | YUMA       | SDGE      |             500 |                 0 |                   0 |                  0 |
| QUINTO SW STA- FINK SW STA                   | STANISLAUS | PGAE      |             400 |               400 |                   0 |                  0 |

## Cluster 15 survival by node (lowest first; >500 MW requested)

| poi_base                       | county         | utility   |   c15_active_mw |   c15_withdrawn_mw |   c15_survival |
|:-------------------------------|:---------------|:----------|----------------:|-------------------:|---------------:|
| MIDWAY - VINCENT               | KERN           | SCE       |               0 |               1150 |              0 |
| VIEJO                          | ORANGE         | SCE       |               0 |               1000 |              0 |
| BEATTY                         | NYE            | GLW       |               0 |               1350 |              0 |
| TROUT CANYON SUBSTATION        | CLARK          | GLW       |               0 |               1500 |              0 |
| SLOAN CANYON SWITCHING STATION | CLARK          | GLW       |               0 |                550 |              0 |
| MOHAVE SUBSTATION              | CLARK          | SCE       |               0 |               1050 |              0 |
| LOS BANOS                      | MERCED         | PGAE      |             400 |               1995 |              0 |
| LUGO                           | SAN BERNARDINO | SCE       |            1798 |               4453 |              0 |

## Cluster 15 withdrawals by month

| withdrawn_date   |   count |   sum |
|:-----------------|--------:|------:|
| 2025-04          |      11 |  4887 |
| 2025-05          |      14 |  6200 |
| 2025-11          |      10 |  2449 |
| 2025-12          |      27 |  8231 |
| 2026-06          |       8 |  3928 |
| 2026-07          |      14 |  4868 |

## Caveats (say these out loud to any reader)

1. POI strings are free text. `poi_geocode.csv` shows every match and its score; audit anything under 0.9.
2. Cluster 15 "deliverability" is *requested*, not allocated. TPD allocation is decided by CAISO's
   Transmission Plan Deliverability process; this file cannot tell you who gets it.
3. Withdrawal is not failure at the node — it is often a portfolio decision by the developer.
4. Nothing here is load-side. Data center load interconnection is a utility (PG&E/SCE/SDGE) process with no public queue.
