================================================================================
🧠 INSTRUMENTATION ENGINEER ARCHITECTURAL DECISION & RATIONALE
================================================================================
• Target Table: express_checkout
• Executive Summary: Proposes dedicated table for `express_checkout`.

--- 1. Table Strategy Decision ---
  Strategy: CREATE_NEW
  Recommendation: Dedicated table created for express_checkout.

--- 2. Primary Sorting Key (ORDER BY) ---
  ORDER BY (timestamp, user_id)

--- 3. Partitioning Strategy (PARTITION BY) ---
  PARTITION BY toYYYYMM(timestamp)

--- 4. Encodings & Data Types ---
  LowCardinality(String) applied to bounded categorical dimensions to optimize memory and disk compression.

--- 5. Materialized View Rollup ---
  Materialized view `express_checkout_daily_mv` pre-aggregates daily metrics via SummingMergeTree.

--- 6. Data Lifecycle Retention (TTL) ---
  

--- Proposed ClickHouse DDL ---
CREATE TABLE IF NOT EXISTS express_checkout (
    event LowCardinality(String),
    id String,
    timestamp DateTime,
    device_type LowCardinality(String),
    os LowCardinality(String),
    app_version LowCardinality(String),
    geoip_country_code LowCardinality(String),
    city LowCardinality(String),
    client_lib LowCardinality(String),
    user_id String,
    application_id String,
    destination String,
    eligible UInt8,
    shown_amount Nullable(Float64),
    currency LowCardinality(String),
    saved_method_type LowCardinality(String),
    otp_attempts Nullable(Int64),
    otp_success UInt8,
    payment_amount Nullable(Float64),
    payment_currency LowCardinality(String),
    payment_latency_ms Nullable(Int64)
) ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
PRIMARY KEY (timestamp, user_id)
ORDER BY (timestamp, user_id)
TTL timestamp + INTERVAL 12 MONTH
SETTINGS index_granularity = 8192;

--- Proposed Materialized View (SummingMergeTree) ---
-- justification: daily segment rollup for accelerated dashboard query execution
CREATE MATERIALIZED VIEW IF NOT EXISTS express_checkout_daily_mv
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(date)
ORDER BY (device_type, os, geoip_country_code, destination, date, event)
AS SELECT
    toYYYYMMDD(timestamp) AS date,
    device_type, os, geoip_country_code, destination, event,
    count() AS total_events,
    uniqState(user_id) AS unique_users
FROM express_checkout
GROUP BY device_type, os, geoip_country_code, destination, date, event;

--- Context Diff Audit (Context Librarian) ---
  • New Attributes to Sync (21): express_checkout.event, express_checkout.id, express_checkout.timestamp, express_checkout.device_type, express_checkout.os, express_checkout.app_version, express_checkout.geoip_country_code, express_checkout.city, express_checkout.client_lib, express_checkout.user_id, express_checkout.application_id, express_checkout.destination, express_checkout.eligible, express_checkout.shown_amount, express_checkout.currency, express_checkout.saved_method_type, express_checkout.otp_attempts, express_checkout.otp_success, express_checkout.payment_amount, express_checkout.payment_currency, express_checkout.payment_latency_ms
  • Metric Conflicts Detected: Denominator definition conflict in 3. The eight raw event tables#1: | Table | Kind | Emitted when | Key event-specific columns |
|-------|------|--------------|----------------------------|
| `destination_card_clicked` | funnel | user taps a destination card | `destination`, `visa_type`, `card_type`, `flow` |
| `application_started` | funnel | user starts an application | `purpose`, `eta_shown`, `co_travelers`, `destination` |
| `document_uploaded` | funnel | passport image submitted | `doc_type`, `capture_mode`, `retry_count`, `is_crossed_failed_attempt_threshold` |
| `purchase_completed` | funnel | payment succeeds (**conversion**) | `value` (revenue), `currency`, `insurance_amount`, `coupon_applied` |
| `search_typed` | supporting | user types a destination search | `search_term`, `results_count`, `source` |
| `landing_page_scrolled` | supporting | user scrolls a landing page | `scroll_depth_pct`, `time_on_page_s`, `page_version` |
| `auth_completed` | supporting | user finishes login/signup | `auth_method`, `is_new_user`, `attempts` |
| `pay_now_clicked` | supporting | user taps Pay Now at checkout | `payment_method`, `amount`, `currency`, `coupon_applied` |, Denominator definition conflict in 4. Metric definitions#0: **Conversion rate** = completed purchases ÷ **sessions**. A session is a single
app-open / web visit. This is the headline number reported to leadership., Denominator definition conflict in 4. Metric definitions#6: > Note on funnel conversion: within the funnel, we treat **conversion as
> `purchase_completed` users ÷ users who started an application**
> (`application_started`). This is the denominator used in the drop-off dashboards.
  • Undocumented Gaps Flagged: Undocumented column `app_version` in express_checkout, Undocumented column `client_lib` in express_checkout, Undocumented column `eligible` in express_checkout, Undocumented column `shown_amount` in express_checkout, Undocumented column `saved_method_type` in express_checkout, Undocumented column `otp_attempts` in express_checkout, Undocumented column `otp_success` in express_checkout, Undocumented column `payment_amount` in express_checkout, Undocumented column `payment_currency` in express_checkout, Undocumented column `payment_latency_ms` in express_checkout
================================================================================

<!-- atlys:proposal spec_id=01_express_checkout table=express_checkout trace=3908c60204de1edd75d01d4e66e8d7af -->