-- Query timing stats for admin dashboard (database: appdb)
-- Run: mysql -u root -p appdb < db/migrations/002_query_timing.sql

CREATE TABLE IF NOT EXISTS query_timing_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    thread_id CHAR(36) NOT NULL,
    request_id VARCHAR(64) NULL,
    run_id VARCHAR(64) NOT NULL,
    route VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    total_ms INT NOT NULL,
    embedding_ms INT NOT NULL DEFAULT 0,
    embedding_count INT NOT NULL DEFAULT 0,
    chroma_ms INT NOT NULL DEFAULT 0,
    chroma_count INT NOT NULL DEFAULT 0,
    rerank_ms INT NOT NULL DEFAULT 0,
    rerank_count INT NOT NULL DEFAULT 0,
    llm_total_ms INT NOT NULL DEFAULT 0,
    llm_call_count INT NOT NULL DEFAULT 0,
    collection_name VARCHAR(128) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_timing_runs_tenant_created (tenant_id, created_at),
    KEY idx_timing_runs_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS query_timing_llm_calls (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    operation VARCHAR(32) NOT NULL,
    sequence INT NOT NULL,
    duration_ms INT NOT NULL,
    tokens_used INT NULL,
    phase ENUM('main', 'post_turn') NOT NULL DEFAULT 'main',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_timing_llm_tenant_created (tenant_id, created_at),
    KEY idx_timing_llm_run_seq (run_id, sequence),
    CONSTRAINT fk_timing_llm_run
        FOREIGN KEY (run_id) REFERENCES query_timing_runs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
