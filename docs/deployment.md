# Local SPHINX service deployment

The `sphinx-s3-local` Compose project runs dcm4chee Archive 5, PostgreSQL,
OpenLDAP and Silo. Assemble it using the base, S3 and deployment files in
that order. The one-shot `bucket-init` and `storage-init` services prepare
the bucket and LDAP descriptor before the archive starts.

## Start

Use a local Docker engine and Compose 2.24.4 or newer. Set up the
[database and LDAP credentials](../README.md#prerequisites-and-setup) and
[local S3 credentials](s3.md#start) in `.env`.

```sh
archive() {
  docker compose -p sphinx-s3-local -f compose.yaml -f compose.s3.yaml -f compose.deploy.yaml "$@"
}
archive up -d --wait
archive ps --all
```

The four persistent services should report healthy. The two initialization
services should exit successfully. Use `archive logs --tail=80 storage-init arc`
if startup fails. `archive stop` stops the stack and preserves named volumes.
Run the same startup command to resume it.

| Interface | Address |
| --- | --- |
| DICOM DIMSE | `127.0.0.1:31112`, called AE `DCM4CHEE` |
| DICOMweb | `http://127.0.0.1:19080/dcm4chee-arc/aets/DCM4CHEE/rs` |
| PostgreSQL, OpenLDAP, Silo API | Compose network only |

The deployed archive accepts synthetic data on the local machine. Local
DICOM and HTTP endpoints are unauthenticated.

## Use the archive directly

Use any DICOM storage client against AE `DCM4CHEE` for C-STORE. A DICOMweb
client can find and retrieve a study from the base URL above. For a known
synthetic Study Instance UID:

```sh
base=http://127.0.0.1:19080/dcm4chee-arc/aets/DCM4CHEE/rs
curl --fail --get -H 'Accept: application/dicom+json' \
  --data-urlencode "StudyInstanceUID=$study_uid" "$base/studies"
curl --fail -H 'Accept: multipart/related; type="application/dicom"; transfer-syntax=*' \
  "$base/studies/$study_uid" -o data/study.multipart
```

The deployment starts and serves these protocols without running the fixture
or recovery harness. The [architecture](architecture.md) and
[recovery drill](recovery-drill.md) describe the persistence and backup paths.

## Verification

On the local native ARM64 Docker VM, both initialization jobs exited with
code 0 and all four services became healthy. Standalone `echoscu` and
`storescu` confirmed C-ECHO and three successful C-STORE responses. Direct
QIDO and WADO requests returned the synthetic study and all three expected
instances. The private bucket contained three objects. QIDO and WADO passed
again after restarting the archive and rerunning Compose startup.
