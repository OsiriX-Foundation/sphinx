# Quality baseline

The [quality workflow](../.github/workflows/quality.yml) runs for pull requests
and pushes to `main`. It uses read-only repository permissions and runs
without deployment credentials. Checks can also be run locally from the
repository root with the development Python environment, a Docker CLI with
Compose 2.24.4 or newer, `jq`, and Gitleaks.

```sh
.venv/bin/python -m compileall -q scripts tests
.venv/bin/python -m unittest discover -s tests -v
bash -n scripts/recovery-drill.sh
bash -n tests/check-compose.sh
sh -n config/dcm4chee/s3-storage.sh
bash tests/check-compose.sh
gitleaks git --log-opts=--all --redact --no-banner
```

Compose validation renders the five supported file combinations with test
placeholders. It checks that only the archive publishes ports and that those
ports bind explicitly to IPv4 loopback. These checks start no services.

## What recovery verification measures

- The verifier requires a nonempty manifest, a unique SOP Instance UID per
  object, and an exact match of the expected study, series, and instance
  identifiers. It checks file-meta SOP identifiers, original dataset attribute
  values, pixel bytes, and transfer syntax. QIDO requires one matching study
  and the expected instance count and SOP-to-series mapping.
- The verifier reports added tags and whole-file SHA-256 matches separately.
  The live test observed a regenerated Part 10 header in S3 and an added
  Issuer of Patient ID in WADO. Semantic recovery passes with those
  differences. [Recorded integrity checks](test-results.md#assertion-and-dicom-audit)
- CI exercises synthetic files and mocked QIDO and WADO responses, including
  missing or duplicate instances, changed attributes, pixel bytes and
  transfer syntax, and safe fixture cleanup. It does not perform live DICOM
  transfers or restore the archive. Use the [recovery drill](recovery-drill.md)
  for that test.
- Live evidence covers three uncompressed Secondary Capture instances across
  up to two series on one Docker host. The backup drill stops ingest before
  copying data. A separate-host restore, active-ingest consistency,
  compressed syntax coverage, independent backup-media survival, and replay of
  catalogue-only metadata remain unproven. [Open checks](blockers.md)

## Security and cleanup review

- Compose requires development credentials through `.env` or the environment.
  Keep `.env` and backup artifacts private and outside Git. The database,
  LDAP, and S3 API stay on the Compose network. Credentials are available
  to Docker administrators via container configuration. LDAP data exports
  contain the S3 credential and configuration exports contain credential
  material. Treat both as secrets.
- Published DICOM and DICOMweb endpoints and the temporary DICOM receiver bind
  to loopback. The archive uses unauthenticated local test interfaces. The
  internal LDAP and S3 traffic uses plaintext. Use synthetic data only on a
  trusted local Docker host.
- `demo.py restore` removes generated source files by default only after
  checking their names, file types, and manifest hashes. Use `--keep-source`
  to retain them. The recovery drill refuses existing test project
  containers or volumes and aborts if the inventory commands fail.
- The drill's `pg_restore --clean` replaces the seeded schema in its fresh
  target database. It removes only its one-off LDAP import containers and
  stops its projects on success. A failed run can leave its own containers
  running and evidence on disk. The ordinary shutdown instructions retain
  volumes. Apply the S3 bootstrap only to the dedicated S3 project because
  it changes the LDAP storage descriptor that resolves existing catalogue
  locations.
