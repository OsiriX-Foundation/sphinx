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
