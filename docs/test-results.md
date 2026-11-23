# Test results · 23 November 2026

## Environment

Apple Silicon macOS (ARM64). The workspace started with IntelliJ metadata and
no Git repository. TCP ports 8080, 11112 and 11113 were free. No Docker CLI,
Compose plugin, daemon socket or desktop runtime was present on the host.
The test used Lima 2.3.0 with Virtualization.framework, Ubuntu 26.04 ARM64,
Docker Engine 29.10.0 rootless and Compose v5.8.0. The VM had four vCPUs, 6 GiB
of memory and a 25 GiB virtual disk. The published archive, LDAP and database
manifests included Linux AMD64 and ARM64. These runs used native ARM64 images
with no emulation.

The shell sandbox initially could not resolve public hosts. Upstream browsing
and the approved public downloads succeeded. The temporary VM's Ubuntu
package source had to be switched from HTTP to HTTPS to finish Docker
provisioning. No production endpoints or KHEOPS configuration were used.

## Commands and results

Commands below are shown using a local Docker CLI. During this session Docker
ran inside Lima. See [the S3 procedure](s3.md) for exact LDAP, bucket and SQL
commands.

| Command or check | Observed result |
| --- | --- |
| `docker compose config --quiet` and `docker compose up -d --wait --wait-timeout 180` | LDAP seed entry, PostgreSQL archive schema and archive QIDO health checks passed |
| `.venv/bin/python scripts/demo.py ready` | C-ECHO and study QIDO-RS passed through host loopback |
| `demo.py ingest`, `search`, `restore` on the filesystem project | Three successful C-STORE responses, one study and three indexed instances, three filesystem objects, source files deleted, three WADO parts and three successful C-STORE responses from the separate SCP |
| `dciodvfy <file>` on all three instances in the final S3 fixture | Recognized the Secondary Capture IOD, exited successfully with no errors. Warned about empty Laterality, which is unknown for these synthetic test patterns |
| `docker compose -f compose.yaml -f compose.s3.yaml config --quiet` and `up -d --wait` | S3 project healthy, private bucket created and jclouds descriptor applied |
| S3 catalogue query, `mc cat`, then `demo.py verify` | Three PostgreSQL location keys each resolved to a DICOM object in `sphinx-dicom`. The objects passed manifest verification. The S3 project's filesystem storage volume contained its setup marker and no DICOM files |
| S3 `restart arc`, `up -d --wait`, `demo.py ready`, `demo.py restore` | After readiness returned, source files were deleted. QIDO found the same study and three instances, WADO returned three objects and the independent SCP accepted all three |
| `docker compose down` for filesystem and S3 projects | Reproducible container/network teardown with the named volumes retained |
| `docker compose up -d --wait` and `demo.py search data/run-gr6rq77t` after filesystem shutdown | The original filesystem study and all three indexed instances survived Compose teardown. A fresh study also passed source-loss recovery |
| Host listener check after the final recovery | Only `127.0.0.1:8080` and `127.0.0.1:11112` remained published for SPHINX. The temporary SCP exited |

Each command above using `demo.py` ran through `.venv/bin/python scripts/demo.py`.
Recovery artifacts are under Git-ignored `data/`. Final filesystem run
`run-xaimi34o` and S3 run `run-m68c8m13` retain manifests and receiver output.
The S3 run also retains the three catalogue keys and direct S3 downloads.

| Object comparison | Study, series and SOP UIDs, original attributes and pixel bytes | Full dataset attributes and pixel bytes | Original transfer syntax | Identical Part 10 file SHA-256 |
| --- | ---: | ---: | ---: | ---: |
| Filesystem WADO and receiver (each) | 3/3 | 0/3 | 3/3 | 0/3 |
| Direct S3 downloads | 3/3 | 3/3 | 3/3 | 0/3 |
| S3 WADO and receiver (each) | 3/3 | 0/3 | 3/3 | 0/3 |

The transfer syntax was Explicit VR Little Endian (`1.2.840.10008.1.2.1`).
WADO added Issuer of Patient ID (`0010,0021`) under the default archive
configuration. The receiver preserved that additional attribute. File
identity and dataset equality were measured separately.

## Failures encountered and corrected

- The first DICOM smoke test assumed pynetdicom associations were context
  managers. The runner now releases the association explicitly. The rerun
  obtained three C-STORE success responses and verified all three outputs.
- The initial C-ECHO offered Explicit VR Little Endian only. The archive's
  verification context accepted Implicit VR Little Endian. The corrected
  C-ECHO passed on the archive and separate SCP. Compose now waits on a QIDO
  check as well.
- The first fixture missed Laterality. The validator diagnosed it and the
  final fixture encodes an empty value for unknown laterality.
- The first S3 download loop consumed its key list via Docker/SSH stdin after
  one object. Redirecting each `mc cat` call from `/dev/null` retrieved all
  three objects on the rerun.
- The former upstream MinIO binary returned HTTP 410 and image registry
  requests failed. The pinned Silo image pulled and ran successfully.
  [MinIO distribution note](https://github.com/minio/minio) · [Silo image](https://hub.docker.com/r/pgsty/silo/tags)

## Replay on this workstation

While the temporary VM exists, use the following in the repository root to
run Compose in the VM. Run the Python test commands on macOS. Only the
repository is mounted in the VM, read-only.

```sh
export LIMA_HOME=/tmp/sphinx-local-tools/vm
limactl=/tmp/sphinx-local-tools/lima/bin/limactl
docker() { "$limactl" shell sphinx-demo docker "$@"; }
docker compose ps
.venv/bin/python scripts/demo.py ready
```

The VM and its Docker volumes live under `/tmp/sphinx-local-tools`.
The filesystem project was left healthy and running. The S3 project was shut
down with its named volumes retained. The Compose files and instructions are
the reproducible deliverable.

## Fresh-environment recovery and catalogue-free replay

The archive disaster recovery drill ran on the same native ARM64 Docker
runtime. `scripts/recovery-drill.sh` used a one-study, two-series synthetic
fixture with three instances and three unique Compose projects. The filesystem
baseline stayed running on its existing ports. The drill used ports 18080 and
21112 on loopback and stopped only its own services.

| Command or check | Observed result |
| --- | --- |
| `demo.py ingest --multi-series` and baseline `restore --keep-source` | Three successful C-STORE responses, exact study/series/SOP UID coverage, three WADO objects and three receiver objects |
| `stop arc`, `pg_dump -Fc`, `slapcat -n 0` and `slapcat -b dc=dcm4che,dc=org` | Archive writes quiesced before the PostgreSQL and LDAP exports. Both LDAP configuration and directory data were captured |
| Source `stop db ldap`, then `mc find` and `mc cat` | Enumerated three keys and read three usable DICOM Part 10 objects without querying PostgreSQL |
| Fresh S3 bucket, `mc pipe` and `cmp` | All three restored keys and payloads matched the source bucket exactly |
| `pg_restore` and offline `slapadd` in the fresh project | Imported the catalogue, LDAP config and LDAP data into separate volumes. The fresh archive started with new WildFly and archive volumes |
| Rebuilt archive `ready` and `restore --keep-source` | C-ECHO passed. QIDO, WADO and the receiver each covered all three SOP Instance UIDs. All three WADO Part 10 files matched their pre-loss WADO files byte for byte |
| Clean project `reingest` and `restore --keep-source` | With the source and rebuilt projects stopped, three objects discovered by S3 listing produced three successful C-STORE responses. QIDO, WADO and independent receiver verification passed |
| Existing filesystem `ready`, `search`, and `restore --keep-source` | The earlier synthetic filesystem fixture remained discoverable and recoverable |

The final drill retained its artifacts in Git-ignored `data/archive-dr-qH5NdWO1`
and `data/run-wbd_y_7d`. The three drill projects were stopped with their
volumes intact. The first LDAP import failed without an explicit
`-F /etc/openldap/slapd.d`. The next attempt imported the LDIFs but slapd
could not read `cn=config.ldif` under its runtime UID. The successful run
applied the LDAP image's configured numeric UID/GID to both restored volumes.

### Assertion and DICOM audit

- QIDO checks the exact study match, instance count and SOP-to-series mapping.
  WADO and receiver verification reject missing, unexpected and duplicate SOP
  Instance UIDs. They also check the study and series UIDs, the consistency
  of the file-meta SOP identifiers, original dataset attribute values, and
  the SHA-256 of the pixel bytes. The drill requires transfer syntax to match
  and separately reports added tags, full dataset equality and file SHA-256
  equality.
- Direct S3 downloads kept all three source **encoded datasets** byte for
  byte. Comparing each Part 10 file by SOP UID showed differences in the
  file-meta group length, Implementation Class UID and Implementation Version
  Name. C-STORE sends the DICOM dataset, and the archive writes its own Part 10
  file meta. The source file and its stored representation therefore had
  different whole-file SHA-256 values for all three instances.
- For WADO and independent C-STORE recovery, all source attributes and pixel
  bytes matched and all three instances kept Explicit VR Little Endian.
  WADO added Issuer of Patient ID (`0010,0021`) which the receiver retained.
  Neither output matched the original source Part 10 files byte for byte.
- The default `demo.py restore` deletes files only under the generated run's
  `source/` directory. It checks accepted filenames, file types and manifest
  hashes and rejects symlinks. The new drill uses `--keep-source` and moves
  its own fixture into the evidence directory for comparison. The S3 LDAP
  setup overwrites the test project's `fs1` descriptor, so the script runs it
  only before the fresh source archive starts. The fresh target
  `pg_restore --clean` replaces the image-seeded catalogue schema in that
  target alone.

### Dependency outage checks

In a disposable S3 project holding the pilot synthetic study, `curl`
queried the study by UID and requested the WADO multipart DICOM study. The
filesystem baseline stayed available.

| Condition | QIDO | WADO |
| --- | --- | --- |
| All dependencies up | HTTP 200 | HTTP 200 |
| PostgreSQL stopped while archive running | HTTP 500 | HTTP 500 |
| PostgreSQL restarted | HTTP 200 | HTTP 200 |
| LDAP stopped while archive already initialized | HTTP 200 | HTTP 200 |
| Archive restarted with LDAP still stopped | HTTP 500 | HTTP 500 |
| LDAP restored, then archive restarted | HTTP 200 | HTTP 200 |

The cold LDAP outage logged `CommunicationException: ldap:389` and WildFly
service deployment failures. Warm LDAP outage results cover these two
requests only.

`dciodvfy` accepted all three final synthetic files. It warned about the
empty Laterality field for the test patterns, as in the original fixture.
Shell syntax checks, Python compilation and `git diff --check` also passed.
