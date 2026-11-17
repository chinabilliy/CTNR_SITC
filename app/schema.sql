PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS yards (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name   TEXT NOT NULL,
  short_name  TEXT NOT NULL UNIQUE,
  address     TEXT NOT NULL DEFAULT '',
  phone       TEXT,
  work_hours  TEXT,
  template_key TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lease_batches (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  yard_id     INTEGER NOT NULL REFERENCES yards(id) ON DELETE RESTRICT,
  lease_no    TEXT NOT NULL,
  priority    INTEGER NOT NULL DEFAULT 99,
  remark      TEXT,
  release_image_path TEXT,
  status      TEXT NOT NULL DEFAULT 'active',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  UNIQUE(yard_id, lease_no)
);
CREATE INDEX IF NOT EXISTS ix_batches_lookup ON lease_batches(yard_id, priority, id);

CREATE TABLE IF NOT EXISTS batch_stock (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id    INTEGER NOT NULL REFERENCES lease_batches(id) ON DELETE CASCADE,
  container_type TEXT NOT NULL CHECK(container_type IN ('20GP','40GP','40HC')),
  available   INTEGER NOT NULL DEFAULT 0 CHECK(available >= 0),
  updated_at  TEXT NOT NULL,
  UNIQUE(batch_id, container_type)
);
CREATE INDEX IF NOT EXISTS ix_stock_lookup ON batch_stock(container_type, available);

-- 角色：权限点用 JSON 数组保存，key 与旧角色的 admin/front/printer 兼容。
CREATE TABLE IF NOT EXISTS roles (
  key         TEXT PRIMARY KEY,
  label       TEXT NOT NULL,
  perms       TEXT NOT NULL DEFAULT '[]',
  is_builtin  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  username    TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role        TEXT NOT NULL,
  display_name TEXT,
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL,
  last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS pickups (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  vessel      TEXT NOT NULL DEFAULT '',
  voyage      TEXT NOT NULL DEFAULT '',
  bl_no       TEXT NOT NULL,
  container_type TEXT NOT NULL CHECK(container_type IN ('20GP','40GP','40HC')),
  quantity    INTEGER NOT NULL CHECK(quantity > 0),
  yard_id     INTEGER NOT NULL REFERENCES yards(id) ON DELETE RESTRICT,
  requested_lease_no TEXT,
  eir_print_count INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'pending',
  confirmed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  confirmed_at TEXT,
  created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_pickups_bl ON pickups(bl_no);
CREATE INDEX IF NOT EXISTS ix_pickups_status ON pickups(status);

CREATE TABLE IF NOT EXISTS eir_records (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  eir_no      TEXT NOT NULL UNIQUE,
  pickup_id   INTEGER NOT NULL REFERENCES pickups(id) ON DELETE RESTRICT,
  batch_id    INTEGER NOT NULL REFERENCES lease_batches(id) ON DELETE RESTRICT,
  yard_name_snapshot TEXT,
  yard_address_snapshot TEXT,
  yard_phone_snapshot TEXT,
  work_hours_snapshot TEXT,
  vessel TEXT, voyage TEXT, bl_no TEXT, container_type TEXT,
  lease_no_snapshot TEXT,
  remark_snapshot TEXT,
  image_path_snapshot TEXT,
  print_count INTEGER NOT NULL DEFAULT 0,
  printed_at  TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_eir_pickup ON eir_records(pickup_id);
CREATE INDEX IF NOT EXISTS ix_eir_print ON eir_records(print_count);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT NOT NULL
);
