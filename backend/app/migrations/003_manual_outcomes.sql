-- 人工處理紀錄：你把草稿「真的貼到平台」或「略過」。與模擬投遞（drafts.status='sent'）分開，不混在一起。
-- 每次記錄都留下當時的文字快照；新紀錄會取代舊紀錄（舊的標 undone_at），按錯可復原，歷史保留。
CREATE TABLE manual_outcomes(
  id TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  outcome TEXT NOT NULL CHECK(outcome IN ('posted','skipped')), note TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL, undone_at TEXT);
CREATE INDEX idx_outcomes_draft ON manual_outcomes(draft_id);
