ATTACH TABLE _ UUID '2fec2198-dd4c-4e35-a3b5-e53adb57c76b'
(
    `ts` DateTime,
    `change_type` String,
    `before` String,
    `after` String,
    `agent` String,
    `trace_id` String
)
ENGINE = MergeTree
ORDER BY ts
SETTINGS index_granularity = 8192
