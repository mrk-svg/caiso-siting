# CAISO Node Watch — draft 2026-09-14

Sources: CAISO Public Queue Report (run date 2026-09-14), CAISO Cluster 15 report (posted 2026-07-16),
CAISO notice "PG&E information on POI availability for Cluster 16" (2026-01-15), OpenStreetMap substations (ODbL).
All MW are net-to-grid as filed. No figure below states a *cause*; the CAISO files carry none.

## The state of the queue in three numbers

- **Legacy pipeline (Cluster 14 and earlier):** 265 active projects, 74,687 MW,
  92% with storage, 214 already under executed IAs.
- **Cluster 15 today:** 86 active projects, 28,449 MW (21,513 MW storage).
  84 projects / 30,564 MW have withdrawn — 52%
  of the 59,013 MW this file records as entering the cluster.
  (CAISO's July 2025 briefing put the studied set at 145 projects / ~68 GW; that is a different population from the
  170 requests in this file, so the two are not differenced here.)
- **Withdrawn 2022–2026 to date, both reports:** 108,198 MW,
  of which 95,683 MW storage.
  (All-time since 2006, both reports: 412,480 MW — a number that mostly describes
  dead wind and solar-era projects.)

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
| WINDHUB SUBSTATION      | KERN           | SCE       |               4050 |             550 |           2268 |           1450 |            0.34 |           0.55 |
| RED BLUFF SUBSTATION    | RIVERSIDE      | SCE       |               2867 |             725 |           1620 |           3025 |            0.84 |           1    |
| VINCENT SUBSTATION      | LOS ANGELES    | SCE       |               2070 |            1450 |            199 |           1950 |            0.53 |           0.54 |
| WHIRLWIND SUBSTATION    | KERN           | SCE       |               2472 |             801 |           2120 |            300 |            0.09 |           1    |
| DELANEY-COLORADO RIVER  | MARICOPA       | DCRT      |               3200 |               0 |            500 |              0 |            0    |         nan    |
| TROUT CANYON SUBSTATION | CLARK          | GLW       |               3000 |               0 |              0 |           1500 |            0.54 |           0    |
| DRY LAKE SW STA         | KINGS          | PGAE      |                  0 |            2950 |              0 |              0 |            0    |           1    |
| MANNING                 | FRESNO         | LSPC      |                  0 |            2662 |              0 |           1782 |            0.67 |           0.6  |
| GATES SUBSTATION        | FRESNO         | PGAE      |               2521 |               0 |            820 |            839 |            0.36 |           0    |
| MOSS LANDING            | MONTEREY       | PGAE      |               2250 |             199 |            932 |              0 |            0    |           1    |
| LUGO                    | SAN BERNARDINO | SCE       |                500 |            1798 |              0 |           4953 |            2.16 |           0.29 |
| TESLA                   | ALAMEDA        | PGAE      |               1280 |            1000 |            436 |           2000 |            0.77 |           0.33 |

## 2025 TPD allocation cycle by node — requested vs allocated vs denied (CAISO results xlsx, posted 2026-05-04)

| poi_base                    | county          | utility   |   tpd25_projects |   tpd25_req_mw |   tpd25_alloc_mw |   tpd25_unalloc_mw |   tpd25_denied_mw |   tpd24_fcdsa_projects |
|:----------------------------|:----------------|:----------|-----------------:|---------------:|-----------------:|-------------------:|------------------:|-----------------------:|
| MOSS LANDING                | MONTEREY        | PGAE      |                1 |           1500 |             1500 |                  0 |                 0 |                      0 |
| GATES SUBSTATION            | FRESNO          | PGAE      |                2 |           1396 |              396 |               1000 |              1000 |                      3 |
| COLORADO RIVER - PALO VERDE | LA PAZ          | SCE       |                1 |           1000 |                0 |               1000 |              1000 |                      0 |
| EAST COUNTY SUBSTATION      | BAJA CALIFORNIA | SDGE      |                1 |            973 |                0 |                973 |               973 |                      1 |
| COLORADO RIVER SUBSTATION   | RIVERSIDE       | SCE       |                3 |            875 |                0 |                875 |               875 |                      1 |
| LAMBIE SWITCHING STATION    | SOLANO          | PGAE      |                2 |            800 |              400 |                400 |               400 |                      0 |
| IMPERIAL VALLEY SUBSTATION  | IMPERIAL        | SDGE      |                3 |            777 |                0 |                777 |               777 |                      2 |
| TROUT CANYON SUBSTATION     | CLARK           | GLW       |                2 |            625 |                0 |                625 |               625 |                      1 |
| RIO HONDO SUBSTATION        | LOS ANGELES     | SCE       |                2 |            600 |              600 |                  0 |                 0 |                      6 |
| WHEELER RIDGE               | KERN            | PGAE      |                1 |            600 |                0 |                600 |               600 |                      0 |
| RECTOR SUBSTATION           | TULARE          | SCE       |                2 |            550 |              350 |                200 |               200 |                      0 |
| CONTRA COSTA SUBSTATION     | CONTRA COSTA    | PGAE      |                2 |            550 |              449 |                101 |                 0 |                      0 |
| OTAY MESA SWITCHYARD        | SAN DIEGO       | SDGE      |                2 |            550 |                0 |                550 |               550 |                      0 |
| MOORPARK SUBSTATION         | VENTURA         | SCE       |                1 |            500 |              462 |                 38 |                 0 |                      1 |
| VACA-DIXON                  | SOLANO          | PGAE      |                2 |            500 |              500 |                  0 |                 0 |                      0 |

"Denied" is MW refused outright (0 %); "unalloc" is requested minus allocated, so it also carries the remainder left by
partial allocations — quote that one for "what the developer did not get". These rows are joined through all three sheets
of the public report, so a node's TPD history can include requests whose project has since withdrawn
(5,505 MW requested / 450 MW allocated in the 2025 cycle across all nodes).
Allocation is CAISO's decision under Appendix DD; the file states no reason and neither does this table.

## Storage churn, 2022–2026 to date (nodes with >300 MW storage surviving and >300 MW storage withdrawn)

| poi_base                   | county         | utility   |   pipeline_storage_mw |   operating_storage_mw |   wd_recent_storage_mw |   storage_churn |
|:---------------------------|:---------------|:----------|----------------------:|-----------------------:|-----------------------:|----------------:|
| ETIWANDA SUBSTATION        | SAN BERNARDINO | SCE       |                   412 |                    100 |                   1850 |            3.61 |
| CIELO AZUL SUBSTATION      | LA PAZ         | DCRT      |                  1350 |                      0 |                   4000 |            2.96 |
| BEATTY                     | NYE            | GLW       |                   500 |                      0 |                   1350 |            2.7  |
| MIRA LOMA SUBSTATION       | SAN BERNARDINO | SCE       |                   660 |                      0 |                   1699 |            2.57 |
| IMPERIAL VALLEY SUBSTATION | IMPERIAL       | SDGE      |                   425 |                    550 |                   2385 |            2.45 |
| LUGO                       | SAN BERNARDINO | SCE       |                  2298 |                      0 |                   4953 |            2.16 |
| GATES-MIDWAY               | KINGS          | PGAE      |                   500 |                      0 |                    950 |            1.9  |
| PITTSBURG                  | CONTRA COSTA   | PGAE      |                   500 |                      0 |                    940 |            1.88 |
| RECTOR SUBSTATION          | TULARE         | SCE       |                   350 |                      0 |                    650 |            1.86 |
| SPRINGVILLE SUBSTATION     | TULARE         | SCE       |                   345 |                      0 |                    630 |            1.83 |

Example of why the window matters — Whirlwind (Kern, SCE): all-time churn 1.32 looks like a graveyard; storage churn since 2022 is 0.09, with 2,120 MW operating and 3,273 MW in pipeline. The old number describes 2008-era wind projects, not today's batteries.

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

## Cluster 15 nodes with little recent wreckage (<300 MW withdrawn since 2022)

| poi_base                                     | county         | utility   |   c15_active_mw |   c15_fcds_req_mw |   wd_recent_mw |   legacy_active_mw | c16_poi_status   |
|:---------------------------------------------|:---------------|:----------|----------------:|------------------:|---------------:|-------------------:|:-----------------|
| DRY LAKE SW STA                              | KINGS          | PGAE      |            2950 |              2050 |              0 |                  0 | AVAILABLE        |
| LOS BANOS - GATES #1                         | FRESNO         | PGAE      |             800 |               800 |              0 |                  0 |                  |
| HASSAYAMPA                                   | MARICOPA       | SDGE      |             700 |                 0 |              0 |                  0 |                  |
| LUGO-PISGAH                                  | SAN BERNARDINO | SCE       |             700 |                 0 |            150 |                  0 |                  |
| CALCITE SUBSTATION                           | SAN BERNARDINO | SCE       |             638 |                 0 |            200 |                255 |                  |
| MAGUNDEN-PASTORIA                            | KERN           | SCE       |             600 |                 0 |              0 |                  0 |                  |
| NORTH GILA - HOODOO WASH (SDGE PORTION ONLY) | YUMA           | SDGE      |             500 |                 0 |              0 |                  0 |                  |
| QUINTO SW STA                                | MERCED         | PGAE      |             500 |               500 |            100 |                150 |                  |

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

| poi_base                           | county          |   pipeline_mw | geo_method      |   geo_score |
|:-----------------------------------|:----------------|--------------:|:----------------|------------:|
| RED BLUFF SUBSTATION               | RIVERSIDE       |          3592 | ambiguous       |        0.5  |
| TROUT CANYON SUBSTATION            | CLARK           |          3000 | county-centroid |        0.3  |
| MANNING                            | FRESNO          |          2662 | county-centroid |        0.3  |
| VALLEY SWITCH                      | NYE             |          2000 | county-centroid |        0.3  |
| TRANQUILITY                        | FRESNO          |          1575 | override-approx |        0.8  |
| EAST COUNTY SUBSTATION             | BAJA CALIFORNIA |          1573 | none            |        0.8  |
| HOODOO WASH SWITCHYARD             | YUMA            |          1570 | county-centroid |        0.3  |
| MIDWAY SUBSTATION                  | KERN            |          1385 | ambiguous       |        0.5  |
| CIELO AZUL SUBSTATION              | LA PAZ          |          1350 | none            |        0.53 |
| MANNING-MIDWAY                     | FRESNO          |          1150 | line-one-end    |        0.7  |
| COLORADO RIVER - PALO VERDE        | LA PAZ          |          1000 | line-one-end    |        0.7  |
| ARCO                               | KERN            |           915 | county-centroid |        0.3  |
| CALCITE SUBSTATION                 | SAN BERNARDINO  |           893 | county-centroid |        0.3  |
| DELANEY SUBSTATION                 | MARICOPA        |           850 | none            |        0.71 |
| HASSAYAMPA                         | MARICOPA        |           700 | none            |        0.63 |
| MIRA LOMA SUBSTATION               | SAN BERNARDINO  |           660 | ambiguous       |        0.5  |
| WALNUT SUBSTATION                  | LOS ANGELES     |           600 | ambiguous       |        0.5  |
| TEHACHAPI CONCEPTUAL SUBSTATION #1 | KERN            |           600 | county-centroid |        0.3  |
| OTAY MESA SWITCHYARD               | SAN DIEGO       |           550 | county-centroid |        0.3  |

## Caveats (say these out loud to any reader)

1. POI strings are free text. `poi_geocode.csv` shows every match, score and method. `line-one-end` means the marker sits at one end of a line, not the tap.
2. Cluster 15 "deliverability" is *requested*, not allocated. TPD allocation is a separate CAISO process.
3. Withdrawal is not failure at the node, and the files give no reason beyond "IC Request". Do not attribute causes.
4. Nothing here is load-side. Data-center load interconnection is a utility process with no public queue.
5. Availability statements are encoded only where a source names the POI. Absence of a row is not availability.
