# ADR-001 · Stand-alone dcm4chee Archive 5

**Status** · Provisional. Synthetic source-loss validation covers the local
recovery path. Archive-host and catalogue loss remain separate acceptance tests.

Use stand-alone dcm4chee Archive 5 with its release-matched OpenLDAP schema and
PostgreSQL image. It provides mature DIMSE and DICOMweb interfaces and a
documented S3 integration. Nicolas Cordonnier's prior KHEOPS deployment and S3
experience reduce implementation and troubleshooting time.

Docker Compose replaces the cluster deployment machinery for this local
demonstrator. The filesystem store provides a recovery baseline with fewer
dependencies than S3. A separate pynetdicom `storescp` process gives the
recovery test a real DICOM destination without operating a second archive.
The test client requests the input transfer syntax on both C-STORE hops.

The optional S3 variant uses Silo, the maintained MinIO fork, after the
upstream MinIO Community image proved unavailable. A separate Compose project
keeps its catalogue, LDAP storage descriptor and bucket independent of the
filesystem baseline. [Silo upstream](https://github.com/pgsty/silo)

The test uses a pinned 5.35.2 set from the upstream release. All three images
publish native ARM64 manifests. An unauthenticated archive with loopback-only
ports is sufficient for disposable synthetic data. The catalogue and LDAP
configuration remain recovery dependencies. [Upstream release](https://github.com/dcm4che/dcm4chee-arc-light/releases/tag/5.35.2)
