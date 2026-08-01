ATTACH TABLE _ UUID 'e264a96f-79f5-4981-8401-85cca8257eaf'
(
    `spec_id` String,
    `question` String,
    `answer_md` String,
    `confidence` Float32,
    `cuts_json` String,
    `trace_id` String,
    `created_at` DateTime
)
ENGINE = MergeTree
ORDER BY (spec_id, created_at)
SETTINGS index_granularity = 8192
