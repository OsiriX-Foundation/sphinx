# SPHINX Phase 1 demonstrator

Fondation OsiriX · Sponsor Prof. Osman Ratib · Consultant Nicolas Cordonnier

Test whether a stand-alone DICOM backup can accept a synthetic study, find and
export it after simulated loss at the source, and restore it into a separate
DICOM system. This local environment accepts synthetic images only.

## Prerequisites and setup

- A local Docker Engine 28 or newer with Docker Compose v2 or newer.
  On macOS, Docker runs in a Linux VM such as Docker Desktop or Lima.
  The pinned archive, database and LDAP images publish both Linux ARM64 and
  AMD64 builds. See the [verification record](docs/test-results.md) for tested versions.
- Python 3.10 or newer, with a virtual environment. The test tooling uses
  pydicom and pynetdicom.
- Free local TCP ports 8080 and 11112 for the archive and 11113 for the test
  receiver. Run commands from the repository root.

Create the local credentials once. OpenSSL prints the random passwords into
`.env` only. Keep that file with its corresponding database and LDAP volumes.

```sh
if [ ! -e .env ]; then
  (umask 077
   {
     printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
     printf 'LDAP_ROOTPASS=%s\n' "$(openssl rand -hex 24)"
     printf 'LDAP_CONFIGPASS=%s\n' "$(openssl rand -hex 24)"
   } > .env)
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`POSTGRES_PASSWORD` is shared by `db` and `arc`.
`LDAP_ROOTPASS` is shared by `ldap` and `arc`. `LDAP_CONFIGPASS` protects
OpenLDAP's configuration database. Compose reads the passwords from
`.env`. Compose, the archive and the test client use fixed local ports.
Changing a password in `.env` alone does not rotate a previously initialized
service password.

## Start and check readiness

```sh
docker compose config --quiet
docker compose up -d --wait
docker compose ps
.venv/bin/python scripts/demo.py ready
```

Compose waits for an LDAP bind and archive device lookup, a TCP PostgreSQL
query against the archive schema, and an archive QIDO query inside the
container. The host-side readiness test checks both C-ECHO and QIDO.
Use `docker compose logs --tail=80 arc` for container startup and
`docker compose exec -T arc tail -80 /opt/wildfly/standalone/log/server.log`
for archive application logs.

| Service | Local endpoint | Persistent storage inside service |
| --- | --- | --- |
| `arc` dcm4chee Archive 5 | DICOM `DCM4CHEE` at `127.0.0.1:11112`, DICOMweb at `http://127.0.0.1:8080/dcm4chee-arc/aets/DCM4CHEE/rs` | `archive-data` at `/storage` (DICOM under `/storage/fs1`), `wildfly-data` at `/opt/wildfly/standalone` |
| `db` PostgreSQL | Internal `db:5432`, database `pacsdb`, user `pacs` | `postgres-data` at `/var/lib/postgresql/data` |
| `ldap` OpenLDAP | Internal `ldap:389` | `ldap-data` and `ldap-config` at `/var/lib/openldap/openldap-data` and `/etc/openldap/slapd.d` |
| Host `storescp` | DICOM `SPHINX_RESTORE` at `127.0.0.1:11113` during recovery | `data/run-*/restore-*/received/` |

The archive's local test endpoints are unauthenticated. WildFly management, LDAP,
PostgreSQL and the archive's other listeners have no published host port.

## Ingest, search and restore

```sh
.venv/bin/python scripts/demo.py ingest
```

`ingest` prints a new run directory, generates three uncompressed Secondary
Capture instances in a single study and series, sends them via C-STORE with
calling AE `SPHINX_SOURCE`, and checks the study and instance index. Use the
printed run directory in the commands below.

```sh
.venv/bin/python scripts/demo.py search data/run-REPLACE_ME
.venv/bin/python scripts/demo.py restore data/run-REPLACE_ME
```

`restore` confirms the study exists, removes the disposable generated source
files after verifying their hashes, repeats the QIDO query, and retrieves the
study over WADO-RS. It starts a separate `storescp` process, sends the
exported objects via C-STORE as `SPHINX_EXPORT`, and checks its output against
the pre-loss manifest. It stops the receiver when the check ends. Each retry
writes a new `restore-*` directory. The run directory contains only synthetic
test evidence and is ignored by Git.

The check requires the expected study, series and instance UIDs, original
dataset attributes and exact pixel bytes for this uncompressed fixture. It
reports added dataset tags, complete file SHA-256 matches and transfer syntax
preservation separately. Part 10 file meta can be regenerated during C-STORE.

## Optional local S3 test

The [S3 procedure](docs/s3.md) uses a second Compose project and a private
Silo bucket. Both variants use the same loopback ports, so run one at a time.

## Stop

```sh
docker compose down
```

This preserves the project's named volumes. Run the startup commands again to
reuse them.

## Scope

The [architecture](docs/architecture.md) explains the storage and catalogue
dependencies. See [test results](docs/test-results.md) for the observed
recovery evidence, [blockers](docs/blockers.md) for open checks and
[ADR-001](docs/decisions.md) for the archive choice.
