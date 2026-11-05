-- University Pass Generator schema.
-- Phase 1 uses `students`; `passes` and `verifications` are created now so
-- later phases (card generation, QR verification) need no migration.

CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_number   TEXT    NOT NULL UNIQUE,
    full_name     TEXT    NOT NULL,
    program       TEXT    NOT NULL,
    department    TEXT,
    year_of_study INTEGER,
    email         TEXT,
    phone         TEXT,
    blood_group   TEXT,
    valid_until   TEXT,
    photo_path    TEXT,
    status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','suspended')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS passes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    pass_code   TEXT    NOT NULL UNIQUE,
    qr_token    TEXT    NOT NULL UNIQUE,
    issued_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT,
    status      TEXT    NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','revoked','expired')),
    qr_mode     TEXT    NOT NULL DEFAULT 'online' CHECK (qr_mode IN ('online','offline'))
);

CREATE TABLE IF NOT EXISTS verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pass_id     INTEGER REFERENCES passes(id) ON DELETE SET NULL,
    result      TEXT    NOT NULL,
    method      TEXT    NOT NULL DEFAULT 'online',
    checked_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_students_name ON students(full_name);
CREATE INDEX IF NOT EXISTS idx_passes_student ON passes(student_id);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Phase 4A: admin-managed list of buggy pickup points.
-- Student columns added in this phase live in db._migrate() so old and new
-- databases are upgraded the same way.
CREATE TABLE IF NOT EXISTS pickup_points (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Phase 4B: card wording and branding (key/value, edited on the Settings page).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
