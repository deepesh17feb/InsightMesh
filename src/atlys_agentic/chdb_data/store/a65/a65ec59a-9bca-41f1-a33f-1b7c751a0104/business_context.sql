ATTACH TABLE _ UUID '428b73f9-5691-4081-9445-e326a61ed82a'
(
    `id` UInt32,
    `section` String,
    `key` String,
    `definition` String,
    `version` UInt16,
    `valid_from` DateTime,
    `source` String,
    `status` String
)
ENGINE = MergeTree
ORDER BY (section, key, version)
SETTINGS index_granularity = 8192
