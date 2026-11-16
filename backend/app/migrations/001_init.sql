CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE brands(
  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, current_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE brand_versions(
  id TEXT PRIMARY KEY, brand_id TEXT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(brand_id, version));

CREATE TABLE social_accounts(
  id TEXT PRIMARY KEY,
  platform TEXT NOT NULL CHECK(platform IN ('threads','x','instagram','facebook')),
  handle TEXT NOT NULL CHECK(substr(handle,1,5)='demo_'),
  display_name TEXT NOT NULL, brand_id TEXT REFERENCES brands(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL, UNIQUE(platform, handle));

CREATE TABLE projects(
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  brand_id TEXT NOT NULL REFERENCES brands(id), account_id TEXT NOT NULL REFERENCES social_accounts(id),
  purpose TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL, must_terms TEXT NOT NULL DEFAULT '[]',
  exclude_terms TEXT NOT NULL DEFAULT '[]', window_days INTEGER NOT NULL DEFAULT 7 CHECK(window_days BETWEEN 1 AND 90),
  mode TEXT NOT NULL DEFAULT 'manual_review' CHECK(mode IN ('manual_review','observe_only','auto_simulate')),
  daily_limit INTEGER NOT NULL DEFAULT 5 CHECK(daily_limit >= 0),
  schedule_enabled INTEGER NOT NULL DEFAULT 0, interval_seconds INTEGER NOT NULL DEFAULT 3600 CHECK(interval_seconds >= 60),
  next_run_at TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE source_posts(
  id TEXT PRIMARY KEY, platform TEXT NOT NULL, author_handle TEXT NOT NULL, text TEXT NOT NULL,
  created_at TEXT NOT NULL, likes INTEGER NOT NULL DEFAULT 0, replies INTEGER NOT NULL DEFAULT 0,
  is_own INTEGER NOT NULL DEFAULT 0, own_account_id TEXT REFERENCES social_accounts(id), synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX idx_posts_created ON source_posts(created_at);
CREATE TABLE comments(
  id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES source_posts(id) ON DELETE CASCADE,
  author_handle TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 1);
CREATE INDEX idx_comments_post ON comments(post_id);

CREATE TABLE runs(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), brand_version INTEGER NOT NULL,
  params TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
  candidates INTEGER NOT NULL DEFAULT 0, classified INTEGER NOT NULL DEFAULT 0, drafts INTEGER NOT NULL DEFAULT 0,
  error TEXT, trigger TEXT NOT NULL DEFAULT 'manual', started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE evaluations(
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, post_id TEXT NOT NULL REFERENCES source_posts(id),
  project_id TEXT REFERENCES projects(id),
  included INTEGER NOT NULL, inclusion_reason TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '',
  relevant INTEGER, intent TEXT CHECK(intent IN ('seeking','advice','promotion','complaint','other')),
  risk TEXT CHECK(risk IN ('low','medium','high')), reason TEXT, classifier TEXT, flags TEXT NOT NULL DEFAULT '[]',
  classify_error TEXT, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX idx_eval_run_post ON evaluations(run_id, post_id);

CREATE TABLE drafts(
  id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), post_id TEXT NOT NULL REFERENCES source_posts(id),
  evaluation_id TEXT REFERENCES evaluations(id), brand_id TEXT NOT NULL REFERENCES brands(id), brand_version INTEGER NOT NULL,
  body TEXT NOT NULL, content_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','rejected','sent')),
  requires_human INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT 'user',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX idx_draft_post_project ON drafts(project_id, post_id) WHERE status IN ('draft','approved');
CREATE TABLE approvals(
  id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  content_hash TEXT NOT NULL, approved_by TEXT NOT NULL, approved_at TEXT NOT NULL, revoked_at TEXT);

CREATE TABLE automation_rules(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, post_id TEXT NOT NULL REFERENCES source_posts(id),
  keywords TEXT NOT NULL, reply_template TEXT NOT NULL, dm_template TEXT NOT NULL DEFAULT '', send_dm INTEGER NOT NULL DEFAULT 0,
  links TEXT NOT NULL DEFAULT '[]', version INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE events(
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'received' CHECK(status IN ('received','processed','failed')),
  received_at TEXT NOT NULL, processed_at TEXT);

CREATE TABLE jobs(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed','cancelled','unknown')),
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 4,
  run_at TEXT NOT NULL, lease_until TEXT, locked_by TEXT, last_error TEXT, result TEXT,
  side_effect INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT UNIQUE, cancel_requested INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX idx_jobs_claim ON jobs(status, run_at);

CREATE TABLE delivery_attempts(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('draft_reply','public_reply','dm')),
  draft_id TEXT REFERENCES drafts(id), comment_id TEXT REFERENCES comments(id), rule_id TEXT, rule_version INTEGER,
  recipient TEXT, body TEXT NOT NULL DEFAULT '', operation_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK(status IN ('pending','simulated_sent','failed_retryable','failed_terminal','unknown')),
  error TEXT, read_status TEXT NOT NULL DEFAULT 'not_reported', attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE delivery_dedup(dedup_key TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES delivery_attempts(id), created_at TEXT NOT NULL);

CREATE TABLE lead_lists(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE leads(
  id TEXT PRIMARY KEY, platform TEXT NOT NULL, handle TEXT NOT NULL, list_id TEXT NOT NULL REFERENCES lead_lists(id),
  status TEXT NOT NULL DEFAULT 'New' CHECK(status IN ('New','Qualified','Ignored','Converted')),
  note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(platform, handle));
CREATE TABLE lead_sources(
  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE, post_id TEXT REFERENCES source_posts(id),
  reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(lead_id, post_id, reason));
CREATE TABLE lead_activity(
  id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);

CREATE TABLE tracking_links(
  id TEXT PRIMARY KEY, token TEXT NOT NULL UNIQUE, label TEXT NOT NULL, destination TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE click_events(
  id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES tracking_links(id), session_id TEXT NOT NULL,
  is_bot INTEGER NOT NULL DEFAULT 0, device TEXT NOT NULL DEFAULT 'unknown', country TEXT,
  synthetic INTEGER NOT NULL DEFAULT 0, clicked_at TEXT NOT NULL);
CREATE INDEX idx_click_time ON click_events(clicked_at);
CREATE TABLE engagement_snapshots(
  id TEXT PRIMARY KEY, post_id TEXT NOT NULL REFERENCES source_posts(id), day TEXT NOT NULL,
  impressions INTEGER NOT NULL, likes INTEGER NOT NULL, UNIQUE(post_id, day));

CREATE TABLE usage_ledger(
  id TEXT PRIMARY KEY, operation_id TEXT NOT NULL, entry_type TEXT NOT NULL CHECK(entry_type IN ('grant','reserve','settle','release')),
  units INTEGER NOT NULL CHECK(units >= 0), category TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  UNIQUE(operation_id, entry_type));

CREATE TABLE agent_sessions(
  id TEXT PRIMARY KEY, provider TEXT NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle','running','completed','limit_reached','cancelled','error')),
  model_turns INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE agent_messages(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(session_id, seq));
CREATE TABLE tool_calls(
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
  call_id TEXT NOT NULL, name TEXT NOT NULL, args TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('ok','error','rejected')), started_at TEXT NOT NULL, finished_at TEXT);
CREATE TABLE action_proposals(
  id TEXT PRIMARY KEY, session_id TEXT REFERENCES agent_sessions(id), kind TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','rejected','failed')),
  result TEXT, created_at TEXT NOT NULL, decided_at TEXT);

CREATE TABLE idempotency_keys(
  key TEXT NOT NULL, scope TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(key, scope));
