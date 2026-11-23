# Fresh-environment recovery drill

Run this only against a local Docker runtime with synthetic data. Set up the
Python environment and local credentials as described in the [README](../README.md)
and [S3 procedure](s3.md). The drill requires Docker Compose 2.24.4 or newer
for the recovery port override. It uses loopback ports 18080 for DICOMweb,
21112 for archive DICOM and 11113 for the temporary receiver.

From the repository root, run:

```sh
scripts/recovery-drill.sh
```

If Docker runs inside Lima, make a Docker CLI wrapper available on `PATH`
that forwards arguments and standard input to the guest's Docker CLI. The
Python test client still runs on the host.

The script prints three unique Compose project names and a Git-ignored
`data/archive-dr-*` evidence directory. It creates a two-series study,
records the original manifest, and tests the source archive. It moves the
generated fixture out of its original source directory for later byte
comparison. It stops the archive before exporting a PostgreSQL dump and
both LDAP LDIFs. With the source catalogue stopped, it lists the private
S3 bucket, downloads the objects by key, and validates each DICOM payload.

The second project imports those dumps and writes the saved S3 objects to
a new bucket on a separate local S3 service. The script compares the key
list and each object's bytes against the export and then checks QIDO,
WADO and independent C-STORE recovery. The third project starts with an
empty catalogue and ingests the enumerated S3 payloads via C-STORE while
the other projects are stopped. It repeats the query, export and receiver
checks.

Keep the matching local `.env` and backup set together for recovery.
The database restore needs the `pacs` role provisioned by the pinned
PostgreSQL image. The LDAP config and data exports preserve schemas, AEs,
the storage endpoint and bucket mapping, and local credential material.
The S3 copy preserves keys and payload bytes. Object-store ACLs, versions
and other provider-specific metadata are outside the drill.

On success, all three drill projects are stopped and their named volumes
are retained. On failure, inspect the reported project's services and
evidence before retrying. A retry makes new projects. The database restore
replaces the image-seeded schema in its fresh target only. The script
removes its one-off LDAP import containers and never removes named volumes.
