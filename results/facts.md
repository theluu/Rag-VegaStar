# Đáp án đối chiếu (SQL trực tiếp)

Sinh bởi `scripts/verify_facts.py`. Quãng đường: PostGIS geography trên điểm thô.

## check=vessel, vessel=KOTA GAYA

| shipname | mmsi | imo | callsign | flag | ship_type_summary | ship_type_detail_name | length_m | width_m | dwt | grt | year_built |
|---|---|---|---|---|---|---|---|---|---|---|---|
| KOTA GAYA | 563152500 | 9616802 | 9V7466 | Singapore (Republic of) | Cargo ships, all ships of this type | Container Ship | 222.0 | 30.0 | 39598.0 | 29015.0 | 2012 |

| role | company_name | company_country | start_date |
|---|---|---|---|
| beneficial_owner | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2011-01-25 |
| commercial_manager | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2011-01-25 |
| ism_manager | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2013-03-13 |
| operator | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2012-11-12 |
| registered_owner | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2022-03-17 |
| technical_manager | PACIFIC INTERNATIONAL LINES | SINGAPORE | 2013-03-13 |


## check=owner_fleet, vessel=KOTA GAYA, role=registered_owner

7 tàu khác

| shipname | mmsi | company_name |
|---|---|---|
| KOTA LAYANG | 563137900 | PACIFIC INTERNATIONAL LINES |
| KOTA NAZIM | 565688000 | PACIFIC INTERNATIONAL LINES |
| KOTA NEKAD | 563257300 | PACIFIC INTERNATIONAL LINES |
| KOTA RATU | 564559000 | PACIFIC INTERNATIONAL LINES |
| KOTA SEGAR | 565357000 | PACIFIC INTERNATIONAL LINES |
| KOTA SELAMAT | 566282000 | PACIFIC INTERNATIONAL LINES |
| KOTA SETIA | 564264000 | PACIFIC INTERNATIONAL LINES |


## check=position_at, vessel=KOTA GAYA, ts=2026-09-11T21:00:00Z

| side | event_ts | lat | lon | speed_knots |
|---|---|---|---|---|
| trước | 2026-09-11 19:47:42+00:00 | 21.63939 | 113.88425 | 8.399999618530273 |
| sau | 2026-09-11 21:33:04+00:00 | 21.79336 | 114.08408 | 8.199999809265137 |


## check=daily_distance, mmsi=563240200, days=['2026-09-11', '2026-09-12']

| day | points | first_ts | last_ts | distance_nm | first | last |
|---|---|---|---|---|---|---|
| 2026-09-11 | 107 | 2026-09-11 00:00:00+00:00 | 2026-09-11 23:53:23+00:00 | 447.94 | (6.80919, 106.98844) | (12.9847, 111.21471) |
| 2026-09-12 | 12 | 2026-09-12 00:01:11+00:00 | 2026-09-12 11:48:54+00:00 | 213.65 | (13.01846, 111.2347) | (16.16645, 112.94992) |


## check=gaps, mmsi=563240200

| gap_start_ts | gap_end_ts | hours | start_lat | start_lon | end_lat | end_lon |
|---|---|---|---|---|---|---|
| 2026-09-12 00:14:41+00:00 | 2026-09-12 09:43:42+00:00 | 9.48 | 13.07684326171875 | 111.26851654052734 | 15.576238632202148 | 112.71353149414062 |


## check=last_position, vessel=MSC MANYA

| event_ts | lat | lon | speed_knots | nav_status |
|---|---|---|---|---|
| 2026-09-12 23:50:04+00:00 | 18.46553 | 117.60574 | 15.300000190734863 | Under way |


## check=longest_gap

| shipname | mmsi | gap_start_ts | gap_end_ts | gap_duration_seconds | start_lat | start_lon | end_lat | end_lon |
|---|---|---|---|---|---|---|---|---|
| WORLD SPIRIT | 636011023 | 2026-09-10 00:13:09+00:00 | 2026-09-12 16:01:00+00:00 | 229671 | 9.066532135009766 | 102.82848358154297 | 8.53100872039795 | 103.851318359375 |

Chủ sở hữu/công ty:

| role | company_name |
|---|---|
| technical_manager | FAIRMONT SHIPPING HK LTD |
| registered_owner | MARIGOLD TRANSPORT INC |
| operator | FAIRMONT SHIPPING HK LTD |
| ism_manager | FAIRMONT SHIPPING HK LTD |
| commercial_manager | FAIRMONT SHIPPING HK LTD |
| beneficial_owner | MITSUI OSK LINES LTD |

Điểm AIS cuối trước khi mất:

| event_ts | speed_knots |
|---|---|
| 2026-09-10 00:13:09+00:00 | 11.600000381469727 |


## check=company_tracks, company=EVERGREEN MARINE CORP, role=operator, start=2026-09-10, end=2026-09-13

27 tàu có dữ liệu, tổng 3800 điểm

| shipname | mmsi | points | distance_nm |
|---|---|---|---|
| EVER GLOBE | 354977000 | 220 | 1074.66 |
| EVER BREED | 353800000 | 197 | 1038.71 |
| EVER WISH | 563261900 | 135 | 1007.83 |
| EVER LUNAR | 416497000 | 270 | 850.74 |
| EVER VIVA | 563240200 | 138 | 718.72 |
| EVER ATOP | 563166100 | 95 | 702.35 |
| EVER MACH | 563199600 | 202 | 662.06 |
| MSC UNITE VI | 636024729 | 217 | 657.75 |
| EVER VERT | 563246800 | 85 | 594.46 |
| EVER WIZ | 563243200 | 162 | 586.37 |


## check=type_day, group=cargo, day=2026-09-11

| vessels_in_group | vessels_with_data | points |
|---|---|---|
| 628 | 484 | 35681 |


## check=vessel, vessel=ESL SEATTLE

| shipname | mmsi | imo | callsign | flag | ship_type_summary | ship_type_detail_name | length_m | width_m | dwt | grt | year_built |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ESL SEATTLE | 563300100 | 9848754 | 9V3091 | China (People's Republic of) - Hong Kong (Special Administrative Region of China) | Cargo ships, carrying DG and/or MHB, HS, or MP, IMO hazard or pollutant category OS | Container Ship | 186.0 | 32.0 | 30409.0 | 26971.0 | 2020 |

| role | company_name | company_country | start_date |
|---|---|---|---|
| beneficial_owner | JOHN SWIRE & SONS LTD | UNITED KINGDOM | 2020-01-17 |
| commercial_manager | SWIRE SHIPPING PTE LTD | SINGAPORE | 2020-01-17 |
| ism_manager | SWIRE SHIPPING PTE LTD | SINGAPORE | 2020-01-17 |
| operator | EMIRATES SHIPPING LINES FZE | UNITED ARAB EMIRATES | 2025-08-22 |
| registered_owner | SWIRE SHIPPING PTE LTD | SINGAPORE | 2020-01-17 |
| technical_manager | SWIRE SHIPPING PTE LTD | SINGAPORE | 2020-01-17 |


## check=owner_fleet, vessel=ESL SEATTLE, role=registered_owner

1 tàu khác

| shipname | mmsi | company_name |
|---|---|---|
| RABAUL CHIEF | 477629900 | SWIRE SHIPPING PTE LTD |


## check=position_at, vessel=ESL SEATTLE, ts=2026-09-12T06:30:00Z

| side | event_ts | lat | lon | speed_knots |
|---|---|---|---|---|
| trước | 2026-09-12 06:28:02+00:00 | 11.19527 | 110.21426 | 14.0 |
| sau | 2026-09-12 06:30:27+00:00 | 11.18792 | 110.20974 | 14.100000381469727 |


## check=daily_distance, mmsi=636093181, days=['2026-09-10', '2026-09-11']

| day | points | first_ts | last_ts | distance_nm | first | last |
|---|---|---|---|---|---|---|
| 2026-09-10 | 65 | 2026-09-10 00:00:01+00:00 | 2026-09-10 23:33:36+00:00 | 334.84 | (9.54153, 109.97791) | (13.73461, 113.75172) |
| 2026-09-11 | 101 | 2026-09-11 03:41:41+00:00 | 2026-09-11 21:20:00+00:00 | 221.62 | (14.45216, 114.4054) | (17.49333, 116.56) |


## check=gaps, mmsi=636093181

| gap_start_ts | gap_end_ts | hours | start_lat | start_lon | end_lat | end_lon |
|---|---|---|---|---|---|---|
| 2026-09-10 02:18:44+00:00 | 2026-09-10 05:51:47+00:00 | 3.55 | 9.934782981872559 | 110.35321807861328 | 10.56152629852295 | 110.90693664550781 |
| 2026-09-10 07:15:32+00:00 | 2026-09-10 10:31:32+00:00 | 3.27 | 10.811028480529785 | 111.12960815429688 | 11.403240203857422 | 111.6540298461914 |
| 2026-09-10 13:23:15+00:00 | 2026-09-10 17:46:59+00:00 | 4.40 | 11.924071311950684 | 112.11682891845703 | 12.717677116394043 | 112.82463836669922 |
| 2026-09-10 23:33:36+00:00 | 2026-09-11 03:41:41+00:00 | 4.13 | 13.73460865020752 | 113.75171661376953 | 14.452163696289062 | 114.40540313720703 |
| 2026-09-11 21:20:00+00:00 | 2026-09-12 12:02:00+00:00 | 14.70 | 17.49333381652832 | 116.55999755859375 | 20.062101364135742 | 118.10199737548828 |


## check=company_tracks, company=MAERSK, role=operator, start=2026-09-11, end=2026-09-12

14 tàu có dữ liệu, tổng 818 điểm

| shipname | mmsi | points | distance_nm |
|---|---|---|---|
| A.P. MOLLER | 219677000 | 124 | 406.94 |
| MAERSK STOCKHOLM | 477770200 | 118 | 383.25 |
| GSL ELEFTHERIA | 636017802 | 40 | 349.84 |
| SAN AUGUSTIN MAERSK | 219100000 | 103 | 222.89 |
| GSL DOROTHEA | 636020769 | 86 | 183.74 |
| MAERSK NASSJO | 636024345 | 24 | 178.93 |
| ULSAN | 636022118 | 24 | 167.20 |
| MAERSK LIRQUEN | 219532000 | 61 | 88.44 |
| MARGRETHE MAERSK | 219629000 | 69 | 79.46 |
| NIMTOFTE MAERSK | 219027758 | 24 | 60.40 |


## check=type_day, group=tanker, day=2026-09-12

| vessels_in_group | vessels_with_data | points |
|---|---|---|
| 148 | 126 | 9637 |

