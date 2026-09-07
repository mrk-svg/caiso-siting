# CAISO Node Watch — draft 2026-09-07

Sources: CAISO Public Queue Report (run date 2026-09-07), CAISO Cluster 15 report (posted 2026-07-16),
CAISO notice "PG&E information on POI availability for Cluster 16" (2026-01-15), OpenStreetMap substations (ODbL).
All MW are net-to-grid as filed. No figure below states a *cause*; the CAISO files carry none.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** 266 active projects, 74,687 MW,
  92% with storage, 214 already under executed IAs.
- **Cluster 15 today:** 86 active projects, 28,449 MW (22,005 MW storage);
  84 projects / 30,564 MW withdrawn since intake. CAISO's July 2025 briefing put the studied set at
  145 projects / ~68 GW; the cohort has since shed roughly 58% of its MW.
- **Withdrawn, last 5 years (both reports):** 134,913 MW,
  of which 120,466 MW storage.
  (All-time since 2006: 381,917 MW — a number that mostly describes dead wind and solar-era projects.)

## Official Cluster 16 POI statements (the layer no spreadsheet tool has)

| poi_base           | utility   | c16_poi_status   | c16_poi_note                                                                        |   legacy_active_mw |   c15_active_mw |
|:-------------------|:----------|:-----------------|:------------------------------------------------------------------------------------|-------------------:|----------------:|
| DRY LAKE SW STA    | PGAE      | AVAILABLE        | New 500 kV switching station; stated as a viable POI option for C16 [2026-01-15]    |                  0 |            2950 |
| HARLAN SW STA      | PGAE      | AVAILABLE        | New 500 kV switching station designed with future expansion capability [2026-01-15] |                  0 |            1450 |
| BITTERWATER SW STA | PGAE      | AVAILABLE        | New 230 kV switching station designed with future expansion capability [2026-01-15] |                  0 |             300 |
| TESLA              | PGAE      | CONDITIONAL      | Conceptual layout modification enables new 230 kV terminals [2026-01-15]            |               1280 |            1000 |
| GATES SUBSTATION   | PGAE      | RELIEVED         | 500 kV removed from Table G2-A space limitation per revised plan [2026-01-15]       |               2521 |               0 |

The same notice says PG&E stations exceeding 63 kA short-circuit duty are restricted but does not name them, and that the
Transmission Interconnection Handbook will not reflect this "until updated, no ETA". Read the notice, not the handbook.

## Top nodes by total pipeline MW (legacy + C15)

| poi_base                | county         | utility   |   legacy_active_mw |   c15_active_mw |   operating_mw |   wd_recent_mw |   storage_churn |   c15_survival |
|:------------------------|:---------------|:----------|-------------------:|----------------:|---------------:|---------------:|----------------:|---------------:|
| WINDHUB SUBSTATION      | KERN           | SCE       |               4050 |             550 |           2268 |           2250 |            0.54 |           0.55 |
| RED BLUFF SUBSTATION    | RIVERSIDE      | SCE       |               2867 |             725 |           1620 |           3025 |            1.62 |           1    |
| VINCENT SUBSTATION      | LOS ANGELES    | SCE       |               2070 |            1450 |            199 |           2575 |            0.7  |           0.54 |
| WHIRLWIND SUBSTATION    | KERN           | SCE       |               2472 |             801 |           2120 |           1000 |            0.25 |           1    |
| DELANEY-COLORADO RIVER  | MARICOPA       | DCRT      |               3200 |               0 |            500 |            500 |            0.17 |         nan    |
| TROUT CANYON SUBSTATION | CLARK          | GLW       |               3000 |               0 |              0 |           1500 |            0.54 |           0    |
| DRY LAKE SW STA         | KINGS          | PGAE      |                  0 |            2950 |              0 |              0 |            0    |           1    |
| MANNING                 | FRESNO         | LSPC      |                  0 |            2662 |              0 |           1782 |            0.67 |           0.6  |
| GATES SUBSTATION        | FRESNO         | PGAE      |               2521 |               0 |            820 |           1039 |            0.45 |           0    |
| MOSS LANDING            | MONTEREY       | PGAE      |               2250 |             199 |            932 |              0 |            0    |           1    |
| LUGO                    | SAN BERNARDINO | SCE       |                500 |            1798 |              0 |           4953 |            2.18 |           0.29 |
| TESLA                   | ALAMEDA        | PGAE      |               1280 |            1000 |            436 |           2180 |            0.76 |           0.33 |

## Storage churn, last 5 years (nodes with >300 MW storage surviving and >300 MW storage withdrawn)

| poi_base                   | county         | utility   |   pipeline_storage_mw |   operating_storage_mw |   wd_recent_storage_mw |   storage_churn |
|:---------------------------|:---------------|:----------|----------------------:|-----------------------:|-----------------------:|----------------:|
| ETIWANDA SUBSTATION        | SAN BERNARDINO | SCE       |                   418 |                    101 |                   1899 |            3.66 |
| VIEJO                      | ORANGE         | SCE       |                   302 |                      0 |                   1029 |            3.4  |
| MIRA LOMA SUBSTATION       | SAN BERNARDINO | SCE       |                   680 |                      0 |                   2031 |            2.99 |
| CIELO AZUL SUBSTATION      | LA PAZ         | DCRT      |                  1408 |                      0 |                   4136 |            2.94 |
| PITTSBURG                  | CONTRA COSTA   | PGAE      |                   533 |                      0 |                   1507 |            2.83 |
| BEATTY                     | NYE            | GLW       |                   515 |                      0 |                   1402 |            2.72 |
| DELANEY SUBSTATION         | MARICOPA       | DCRT      |                   881 |                      0 |                   2331 |            2.65 |
| IMPERIAL VALLEY SUBSTATION | IMPERIAL       | SDGE      |                   425 |                    550 |                   2455 |            2.52 |
| SPRINGVILLE SUBSTATION     | TULARE         | SCE       |                   345 |                      0 |                    774 |            2.24 |
| LUGO                       | SAN BERNARDINO | SCE       |                  2327 |                      0 |                   5062 |            2.18 |

Example of why the window matters — Whirlwind (Kern, SCE): all-time churn 1.32 looks like a graveyard; storage churn over the last 5 years is 0.25, with 2,120 MW operating and 3,273 MW in pipeline. The old number describes 2008-era wind projects, not today's batteries.

## Withdrew after Phase II / Facilities Study results (public report; MW)

These developers had upgrade cost estimates in hand when they left. That is the closest thing to a cost signal in the file — it is still not a cause.

| poi_base                   | county          | utility   |   wd_post_phase2_mw |   pipeline_mw |   operating_mw |
|:---------------------------|:----------------|:----------|--------------------:|--------------:|---------------:|
| COLORADO RIVER SUBSTATION  | RIVERSIDE       | SCE       |                3636 |          2016 |           2259 |
| RED BLUFF SUBSTATION       | RIVERSIDE       | SCE       |                3452 |          3592 |           1620 |
| IMPERIAL VALLEY SUBSTATION | IMPERIAL        | SDGE      |                3231 |           875 |           1347 |
| MORRO BAY SUBSTATION       | SAN LUIS OBISPO | PGAE      |                2906 |             0 |              0 |
| DIABLO CANYON              | SAN LUIS OBISPO | PGAE      |                2900 |          1000 |              0 |
| CIELO AZUL SUBSTATION      | LA PAZ          | DCRT      |                2000 |          1350 |              0 |
| EAST COUNTY SUBSTATION     | BAJA CALIFORNIA | SDGE      |                1980 |          1573 |            276 |
| PISGAH SUBSTATION          | SAN BERNARDINO  | SCE       |                1650 |           600 |              0 |
| VINCENT SUBSTATION         | LOS ANGELES     | SCE       |                1565 |          3520 |            199 |
| WHIRLWIND SUBSTATION       | KERN            | SCE       |                1365 |          3273 |           2120 |

## Cluster 15 nodes with little recent wreckage (<300 MW withdrawn in 5 years)

| poi_base                                     | county         | utility   |   c15_active_mw |   c15_fcds_req_mw |   wd_recent_mw |   legacy_active_mw | c16_poi_status   |
|:---------------------------------------------|:---------------|:----------|----------------:|------------------:|---------------:|-------------------:|:-----------------|
| DRY LAKE SW STA                              | KINGS          | PGAE      |            2950 |              2050 |              0 |                  0 | AVAILABLE        |
| LOS BANOS - GATES #3                         | FRESNO         | PGAE      |             800 |               800 |              0 |                  0 |                  |
| HASSAYAMPA                                   | MARICOPA       | SDGE      |             700 |                 0 |              0 |                  0 |                  |
| LUGO-PISGAH                                  | SAN BERNARDINO | SCE       |             700 |                 0 |            150 |                  0 |                  |
| MAGUNDEN-PASTORIA                            | KERN           | SCE       |             600 |                 0 |              0 |                  0 |                  |
| NORTH GILA - HOODOO WASH (SDGE PORTION ONLY) | YUMA           | SDGE      |             500 |                 0 |              0 |                  0 |                  |
| QUINTO SW STA                                | MERCED         | PGAE      |             500 |               500 |            100 |                150 |                  |
| RIO OSO SUBSTATION                           | SUTTER         | PGAE      |             400 |                 0 |            100 |                  0 |                  |

## Cluster 15 survival by node (lowest first; >500 MW requested)

| poi_base                       | county         | utility   |   c15_active_mw |   c15_withdrawn_mw |   c15_survival |
|:-------------------------------|:---------------|:----------|----------------:|-------------------:|---------------:|
| MIDWAY - VINCENT               | KERN           | SCE       |               0 |               1150 |           0    |
| VIEJO                          | ORANGE         | SCE       |               0 |               1000 |           0    |
| BEATTY                         | NYE            | GLW       |               0 |               1350 |           0    |
| TROUT CANYON SUBSTATION        | CLARK          | GLW       |               0 |               1500 |           0    |
| SLOAN CANYON SWITCHING STATION | CLARK          | GLW       |               0 |                550 |           0    |
| MOHAVE SUBSTATION              | CLARK          | SCE       |               0 |               1050 |           0    |
| LOS BANOS                      | MERCED         | PGAE      |             400 |               1995 |           0.17 |
| LUGO                           | SAN BERNARDINO | SCE       |            1798 |               4453 |           0.29 |

## Cluster 15 withdrawals by month

| withdrawn_date   |   count |   sum |
|:-----------------|--------:|------:|
| 2025-04          |      11 |  4887 |
| 2025-05          |      14 |  6200 |
| 2025-11          |      10 |  2449 |
| 2025-12          |      27 |  8231 |
| 2026-06          |       8 |  3928 |
| 2026-07          |      14 |  4868 |

## Positions to audit before publishing a map (>500 MW, approximate or missing)

| poi_base                           | county          |   pipeline_mw | geo_method   |   geo_score |
|:-----------------------------------|:----------------|--------------:|:-------------|------------:|
| DELANEY-COLORADO RIVER             | MARICOPA        |          3200 | line-one-end |        0.7  |
| TROUT CANYON SUBSTATION            | CLARK           |          3000 | none         |        0.78 |
| MANNING                            | FRESNO          |          2662 | none         |        0.67 |
| MOSS LANDING                       | MONTEREY        |          2449 | none         |        0.8  |
| TRANQUILITY                        | FRESNO          |          1575 | none         |        0.67 |
| EAST COUNTY SUBSTATION             | BAJA CALIFORNIA |          1573 | none         |        0.8  |
| HOODOO WASH SWITCHYARD             | YUMA            |          1570 | none         |        0.56 |
| CIELO AZUL SUBSTATION              | LA PAZ          |          1350 | none         |        0.53 |
| MANNING-MIDWAY                     | FRESNO          |          1150 | line-one-end |        0.7  |
| COLORADO RIVER - PALO VERDE        | LA PAZ          |          1000 | line-one-end |        0.7  |
| ARCO                               | KERN            |           915 | none         |        0.67 |
| CALCITE SUBSTATION                 | SAN BERNARDINO  |           893 | none         |        0.62 |
| DELANEY SUBSTATION                 | MARICOPA        |           850 | none         |        0.71 |
| LOS BANOS - GATES #3               | FRESNO          |           800 | line-one-end |        0.7  |
| GAMEBIRD SUBSTATION                | NYE             |           744 | none         |        0.62 |
| HASSAYAMPA                         | MARICOPA        |           700 | none         |        0.63 |
| TEHACHAPI CONCEPTUAL SUBSTATION #1 | KERN            |           600 | none         |        0.09 |
| OTAY MESA SWITCHYARD               | SAN DIEGO       |           550 | none         |        0.62 |

## Caveats (say these out loud to any reader)

1. POI strings are free text. `poi_geocode.csv` shows every match, score and method. `line-one-end` means the marker sits at one end of a line, not the tap.
2. Cluster 15 "deliverability" is *requested*, not allocated. TPD allocation is a separate CAISO process.
3. Withdrawal is not failure at the node, and the files give no reason beyond "IC Request". Do not attribute causes.
4. Nothing here is load-side. Data-center load interconnection is a utility process with no public queue.
5. Availability statements are encoded only where a source names the POI. Absence of a row is not availability.
