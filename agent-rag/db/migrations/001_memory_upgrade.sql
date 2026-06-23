-- Memory upgrade: conversation summary + tenant profiles
-- Run on existing databases: mysql -u root -p appdb < db/migrations/001_memory_upgrade.sql

ALTER TABLE conversations
    ADD COLUMN summary TEXT NULL,
    ADD COLUMN summary_up_to_sequence INT NOT NULL DEFAULT 0,
    ADD COLUMN summary_updated_at DATETIME(3) NULL;

CREATE TABLE IF NOT EXISTS tenant_profiles (
    tenant_id VARCHAR(64) PRIMARY KEY,
    profile_json JSON NOT NULL,
    profile_summary TEXT NULL,
    source ENUM('auto', 'manual') NOT NULL DEFAULT 'auto',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
