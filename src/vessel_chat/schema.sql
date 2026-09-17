-- Schema idempotent. {embedding_dim} được thay từ cấu hình EMBEDDING_DIM.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ======================= Dữ liệu tàu =======================
CREATE TABLE IF NOT EXISTS vessels (
    vessel_id             uuid PRIMARY KEY,
    mmsi                  bigint,
    imo                   bigint,
    shipname              text,
    shipname_norm         text NOT NULL DEFAULT '',
    callsign              text,
    flag_code             text,
    flag                  text,
    ship_type_summary     text,
    ship_type_group       text NOT NULL DEFAULT 'unknown',
    ship_type_detail_name text,
    length_m              double precision,
    width_m               double precision,
    dwt                   double precision,
    grt                   double precision,
    year_built            integer
);
CREATE INDEX IF NOT EXISTS vessels_mmsi_idx ON vessels (mmsi);
CREATE INDEX IF NOT EXISTS vessels_imo_idx ON vessels (imo);
CREATE INDEX IF NOT EXISTS vessels_callsign_idx ON vessels (upper(callsign));
CREATE INDEX IF NOT EXISTS vessels_type_group_idx ON vessels (ship_type_group);
CREATE INDEX IF NOT EXISTS vessels_name_trgm_idx ON vessels USING gin (shipname_norm gin_trgm_ops);

CREATE TABLE IF NOT EXISTS ais_positions (
    vessel_id     uuid NOT NULL,
    mmsi          bigint,
    event_ts      timestamptz NOT NULL,
    lat           double precision NOT NULL,
    lon           double precision NOT NULL,
    geom          geometry(Point, 4326) NOT NULL,
    speed_knots   double precision,
    course_deg    double precision,
    heading_deg   double precision,
    nav_status    text,
    reported_dest text,
    draught_m     double precision
);
CREATE INDEX IF NOT EXISTS ais_vessel_ts_idx ON ais_positions (vessel_id, event_ts);
CREATE INDEX IF NOT EXISTS ais_ts_idx ON ais_positions (event_ts);
CREATE INDEX IF NOT EXISTS ais_geom_idx ON ais_positions USING gist (geom);

CREATE TABLE IF NOT EXISTS dark_gaps (
    gap_id               uuid PRIMARY KEY,
    vessel_id            uuid NOT NULL,
    mmsi                 bigint,
    gap_start_ts         timestamptz NOT NULL,
    gap_end_ts           timestamptz NOT NULL,
    gap_duration_seconds bigint NOT NULL,
    distance_nm          double precision,
    implied_speed_knots  double precision,
    start_lat            double precision,
    start_lon            double precision,
    end_lat              double precision,
    end_lon              double precision,
    start_geom           geometry(Point, 4326),
    end_geom             geometry(Point, 4326),
    path                 geometry(LineString, 4326)
);
CREATE INDEX IF NOT EXISTS gaps_vessel_idx ON dark_gaps (vessel_id, gap_start_ts);
CREATE INDEX IF NOT EXISTS gaps_duration_idx ON dark_gaps (gap_duration_seconds DESC);
CREATE INDEX IF NOT EXISTS gaps_path_idx ON dark_gaps USING gist (path);

CREATE TABLE IF NOT EXISTS ownership (
    id              bigserial PRIMARY KEY,
    vessel_id       uuid NOT NULL,
    role            text NOT NULL,
    company_name    text NOT NULL,
    company_norm    text NOT NULL,
    company_country text,
    start_date      date
);
CREATE INDEX IF NOT EXISTS ownership_vessel_idx ON ownership (vessel_id);
CREATE INDEX IF NOT EXISTS ownership_norm_idx ON ownership (company_norm, role);
CREATE INDEX IF NOT EXISTS ownership_norm_trgm_idx ON ownership USING gin (company_norm gin_trgm_ops);

-- ======================= Hội thoại & bộ nhớ =======================
CREATE TABLE IF NOT EXISTS conversations (
    id                uuid PRIMARY KEY,
    title             text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    summary           text NOT NULL DEFAULT '',
    summary_upto_turn integer NOT NULL DEFAULT 0,
    focus_state       jsonb NOT NULL DEFAULT '{{}}'::jsonb
);

CREATE TABLE IF NOT EXISTS messages (
    id              bigserial PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_no         integer NOT NULL,
    role            text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         text NOT NULL DEFAULT '',
    tool_calls      jsonb,
    tool_call_id    text,
    tool_name       text,
    meta            jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conv_idx ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS memory_chunks (
    id              bigserial PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_no         integer NOT NULL,
    text            text NOT NULL,
    embedding       vector({embedding_dim}) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, turn_no)
);
-- Truy xuất luôn lọc theo một hội thoại → quét chính xác trên tập nhỏ (xem docs/architecture.md).
-- Khi cần tìm ký ức xuyên hội thoại ở quy mô lớn: thêm HNSW (vector_cosine_ops) + hnsw.iterative_scan.
DROP INDEX IF EXISTS memory_embedding_idx;

CREATE TABLE IF NOT EXISTS map_data (
    id              uuid PRIMARY KEY,
    conversation_id uuid REFERENCES conversations(id) ON DELETE CASCADE,
    kind            text NOT NULL,
    summary         jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    bbox            jsonb,
    geojson         jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS map_data_conv_idx ON map_data (conversation_id, created_at);

-- ======================= Kho tri thức (RAG) =======================
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id           bigserial PRIMARY KEY,
    source       text NOT NULL,
    section      text NOT NULL,
    ordinal      integer NOT NULL,
    content      text NOT NULL,
    content_hash text NOT NULL UNIQUE,
    embedding    vector({embedding_dim}) NOT NULL,
    tsv          tsvector NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
-- Kho tri thức dùng chung cho mọi hội thoại → index ANN phù hợp
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx ON kb_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx ON kb_chunks USING gin (tsv);
