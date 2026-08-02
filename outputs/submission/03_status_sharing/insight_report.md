# PM Insight Report — Status Sharing Events (`03_status_sharing`)

**Diagnostic Question:** What is the share rate and referral conversion of status sharing links by channel and destination?  
**Target Table:** `None`  
**Evaluation Timestamp:** 2026-08-02T03:40:11.421783+00:00  
**Public Langfuse Trace URL:** https://us.cloud.langfuse.com/project/cmpwirpg5009oad0esljbiev9/traces/78f2ab89337fa7e6d4cab23f1abc1a05  
**Calibrated Confidence Score:** None

---

## Executive Summary & Diagnostic Breakdown

### I can't answer that from the instrumented tables

**What you asked for:** conversion_rate

**Why it isn't derivable:** The candidate tables track that a sharing event occurred and for which destination, but they lack the 'channel' dimension and the necessary attribution links to measure if those shares resulted in conversions.

- channel column — no dimension exists to distinguish between sharing platforms (e.g., WhatsApp, SMS, Email)
- referral conversion data — these tables track the act of sharing, but do not contain attribution data or the subsequent purchase events of the referred user to calculate conversion

**What I could answer instead:**
- conversion through to purchase_completed, cut by device, geo, destination
- drop-off at any funnel stage present in the event stream
- payment latency at the confirmation step

No query was run and no number was estimated.
🔍 Trace: https://us.cloud.langfuse.com/project/cmpwirpg5009oad0esljbiev9/traces/78f2ab89337fa7e6d4cab23f1abc1a05

---

### ClickHouse Query Execution & Signal Derivation
- **Resolved Table Engine:** `None` (Classification: `raw`)
- **Queries Executed:** 0 ClickHouse Cloud SQL statements
- **Anomalies / Signals Derived:** 0
- **Context Governance:** Synchronized with living `chDB` metadata and registered table semantics.

---
*Generated autonomously by Atlys Product Analyst Agent (CUJ 2) via ClickHouse Cloud.*
