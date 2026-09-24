-- ============================================================
--  Datalytics — Full Database Schema
-- ============================================================

-- Datasets
CREATE TABLE IF NOT EXISTS datasets (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    filename    VARCHAR(500),
    row_count   INTEGER      DEFAULT 0,
    col_count   INTEGER      DEFAULT 0,
    file_size   BIGINT       DEFAULT 0,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Per-column metadata
CREATE TABLE IF NOT EXISTS dataset_columns (
    id           SERIAL PRIMARY KEY,
    dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    dtype        VARCHAR(50)  NOT NULL,
    missing_pct  FLOAT        DEFAULT 0,
    stats        JSONB        DEFAULT '{}',
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- Analysis results
CREATE TABLE IF NOT EXISTS analysis_results (
    id            SERIAL PRIMARY KEY,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    analysis_type VARCHAR(100) NOT NULL,
    result        JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- Saved charts (legacy)
CREATE TABLE IF NOT EXISTS charts (
    id          SERIAL PRIMARY KEY,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    chart_type  VARCHAR(50)  NOT NULL,
    config      JSONB        NOT NULL,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Reports
CREATE TABLE IF NOT EXISTS reports (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    dataset_id  INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Report pages
CREATE TABLE IF NOT EXISTS report_pages (
    id        SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    name      VARCHAR(255) NOT NULL DEFAULT 'Page 1',
    position  INTEGER      NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Report widgets
CREATE TABLE IF NOT EXISTS report_widgets (
    id          SERIAL PRIMARY KEY,
    page_id     INTEGER NOT NULL REFERENCES report_pages(id) ON DELETE CASCADE,
    widget_type VARCHAR(50)  NOT NULL,
    title       VARCHAR(255),
    config      JSONB        NOT NULL DEFAULT '{}',
    layout      JSONB        NOT NULL DEFAULT '{"x":0,"y":0,"w":6,"h":4}',
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Data-view hierarchy
CREATE TABLE IF NOT EXISTS hierarchy_nodes (
    id          SERIAL PRIMARY KEY,
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    parent_id   INTEGER REFERENCES hierarchy_nodes(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    node_type   VARCHAR(20)  NOT NULL DEFAULT 'folder',
    column_name VARCHAR(255),
    aggregation VARCHAR(50),
    format      VARCHAR(100),
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_columns_dataset   ON dataset_columns(dataset_id);
CREATE INDEX IF NOT EXISTS idx_results_dataset   ON analysis_results(dataset_id);
CREATE INDEX IF NOT EXISTS idx_charts_dataset    ON charts(dataset_id);
CREATE INDEX IF NOT EXISTS idx_pages_report      ON report_pages(report_id);
CREATE INDEX IF NOT EXISTS idx_widgets_page      ON report_widgets(page_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_dataset ON hierarchy_nodes(dataset_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_parent  ON hierarchy_nodes(parent_id);
