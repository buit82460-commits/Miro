-- 0001: bảng render/project tối thiểu khớp contracts/render.json
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    revision   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS renders (
    render_id         TEXT PRIMARY KEY,
    request_id        TEXT NOT NULL UNIQUE,
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    expected_revision INTEGER NOT NULL,
    content_hash      TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'queued'
);

CREATE TABLE IF NOT EXISTS publications (
    publication_id TEXT NOT NULL,
    attempt_id     TEXT NOT NULL,
    render_id      TEXT NOT NULL REFERENCES renders(render_id),
    channel        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued',
    PRIMARY KEY (publication_id, attempt_id)
);
