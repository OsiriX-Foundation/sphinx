# Blockers and open checks

- A coordinated PostgreSQL/LDAP/object restore into a fresh Compose project
  remains untested.
- Direct bucket reads are a prerequisite for catalogue-free recovery. Inventory,
  re-ingest, reconciliation and recoverability at operational scale remain
  untested.
- Exoscale SOS endpoint behavior, credentials and recovery have yet to be tested
  against a dedicated authorized test bucket.
- The fixture covers one study, one series and three single-frame uncompressed
  Secondary Capture images. Compressed syntaxes, multiple series, storage
  policies and external systems remain outside this test. Archive defaults
  can add attributes during ingestion or retrieval. Validate any stricter
  requirement for preserving the exact source dataset or Part 10 file.
- See [test results](test-results.md) for runtime and storage evidence.
