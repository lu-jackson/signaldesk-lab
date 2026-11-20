-- 手動匯入的真實貼文：記錄來源網址與來源類型（synthetic=0 代表非合成）。
ALTER TABLE source_posts ADD COLUMN source_url TEXT;
ALTER TABLE source_posts ADD COLUMN origin TEXT NOT NULL DEFAULT 'synthetic';
