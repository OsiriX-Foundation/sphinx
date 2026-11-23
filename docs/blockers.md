# Blockers and open checks

- The [fresh-environment drill](recovery-drill.md) passed on the same local
  Docker host using new containers, volumes and an S3 bucket. Recovery on a
  separate host, loss of the object store or backup media, and restore from
  a backup taken during active ingest remain untested.
- The catalogue-free proof replayed all three objects from a bucket dedicated
  to one synthetic study. It did not demonstrate reconciliation against the
  lost catalogue, inventory at scale, duplicate/rejection handling, or
  restoration of catalogue-only metadata.
- Exoscale SOS, storage versioning, bucket ACLs and credential rotation remain
  untested. The drill reused the local configuration credentials in the fresh
  project.
- Evidence covers one synthetic study across two series of uncompressed,
  single-frame Secondary Capture images. Compressed syntaxes and other IODs
  remain untested. Source dataset bytes matched the S3 payloads after removing
  Part 10 file headers. WADO added Issuer of Patient ID, and exact original
  Part 10 preservation did not pass.
- See [test results](test-results.md) for the artifacts and verified outcomes.
