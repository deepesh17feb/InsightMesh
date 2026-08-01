ATTACH TABLE _ UUID '32885174-e385-4f91-bf70-5e45b52aadd9'
(
    `table` String,
    `ddl` String,
    `columns_json` String,
    `spec_id` String,
    `version` UInt16,
    `created_at` DateTime
)
ENGINE = MergeTree
ORDER BY (`table`, version)
SETTINGS index_granularity = 8192
