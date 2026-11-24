#!/usr/bin/env bash
# Rebuild a synthetic S3 archive from exported backups, then replay its objects
# into a second clean archive. Projects and backup artifacts are retained.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

evidence=$(mktemp -d data/archive-dr-XXXXXXXX)
suffix=$(basename "$evidence" | tr '[:upper:]' '[:lower:]')
source_project="sphinx-$suffix-source"
target_project="sphinx-$suffix-restored"
replay_project="sphinx-$suffix-replay"
bucket_root=sphinx/sphinx-dicom
export SPHINX_HTTP_PORT=18080 SPHINX_DICOM_PORT=21112

echo "Evidence: $evidence"
echo "Projects: $source_project $target_project $replay_project"
compose() {
    docker compose --project-name "$1" -f compose.yaml -f compose.recovery.yaml "${@:2}"
}
src() { compose "$source_project" -f compose.s3.yaml "$@"; }
dst() { compose "$target_project" -f compose.s3.yaml "$@"; }
replay() { compose "$replay_project" "$@"; }
demo() { "${SPHINX_PYTHON:-.venv/bin/python}" scripts/demo.py "$@"; }

bucket() {
    local project=$1
    shift
    "$project" exec -T s3 sh -ec '
        export MC_HOST_sphinx="http://$MINIO_ROOT_USER:$MINIO_ROOT_PASSWORD@127.0.0.1:9000"
        exec mc "$@"
    ' sh "$@"
}

src config --quiet
dst config --quiet
replay config --quiet
for project in "$source_project" "$target_project" "$replay_project"; do
    label="label=com.docker.compose.project=$project"
    containers=$(docker ps -aq --filter "$label")
    volumes=$(docker volume ls -q --filter "$label")
    if [[ -n "$containers" || -n "$volumes" ]]; then
        echo "Refusing to reuse project $project" >&2
        exit 1
    fi
done
src up -d --wait ldap db s3
bucket src mb "$bucket_root"
src exec -T ldap sh -s < config/dcm4chee/s3-storage.sh
src up -d --wait
demo ingest --multi-series | tee "$evidence/ingest.txt"
run=$(sed -n 's/^Run directory: //p' "$evidence/ingest.txt")
demo restore "$run" --keep-source | tee "$evidence/baseline.txt"
cp "$run/manifest.json" "$evidence/manifest.json"
mv "$run/source" "$evidence/source-fixture"

# Quiesce the only writer before capturing the catalogue, directory and objects.
src stop arc
src exec -T db pg_dump -U pacs -d pacsdb -Fc > "$evidence/pacsdb.dump"
src exec -T ldap slapcat -n 0 > "$evidence/ldap-config.ldif"
src exec -T ldap slapcat -b dc=dcm4che,dc=org > "$evidence/ldap-data.ldif"
src stop db ldap

# This inventory and export run with the source catalogue stopped.
mkdir "$evidence/objects"
bucket src find "$bucket_root" </dev/null | LC_ALL=C sort > "$evidence/s3-keys.txt"
test -s "$evidence/s3-keys.txt"
while IFS= read -r object; do
    key=${object#"$bucket_root"/}
    if ! [[ "$key" =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}/[0-9A-F]+/[0-9A-F]+/[0-9A-F]+$ ]]; then
        echo "Unexpected synthetic object key: $object" >&2
        exit 1
    fi
    mkdir -p "$evidence/objects/$(dirname "$key")"
    bucket src cat "$object" </dev/null > "$evidence/objects/$key"
done < "$evidence/s3-keys.txt"

# Flatten names for the fixture verifier while retaining the key-based backup.
mkdir "$evidence/replay-input"
n=0
while IFS= read -r object; do
    n=$((n + 1))
    ln "$evidence/objects/${object#"$bucket_root"/}" "$evidence/replay-input/$n.dcm"
done < "$evidence/s3-keys.txt"
demo verify "$run" "$evidence/replay-input"
src stop s3

# Restore to separate, newly created volumes and a separate S3 endpoint.
dst up -d --wait db s3
bucket dst mb "$bucket_root"
while IFS= read -r object; do
    archived="$evidence/objects/${object#"$bucket_root"/}"
    bucket dst pipe "$object" < "$archived"
    bucket dst cat "$object" </dev/null | cmp - "$archived"
done < "$evidence/s3-keys.txt"
bucket dst find "$bucket_root" </dev/null | LC_ALL=C sort | cmp - "$evidence/s3-keys.txt"
echo "Restored S3 objects have the same keys and exact bytes"

# Replace the image-seeded schema in this fresh, dedicated target database.
dst exec -T db pg_restore -U pacs -d pacsdb --clean --if-exists \
    --single-transaction --exit-on-error < "$evidence/pacsdb.dump"
# Preload the initially empty LDAP volumes before the entrypoint can seed them.
dst run --rm --no-deps -T --entrypoint sh ldap -ec '
    test ! -e /etc/openldap/slapd.d/cn=config.ldif
    slapadd -F /etc/openldap/slapd.d -n 0
    chown -R "$LDAP_USER_ID:$LDAP_GROUP_ID" /etc/openldap/slapd.d
' < "$evidence/ldap-config.ldif"
dst run --rm --no-deps -T --entrypoint sh ldap -ec '
    test ! -e /var/lib/openldap/openldap-data/data.mdb
    slapadd -F /etc/openldap/slapd.d -b dc=dcm4che,dc=org
    chown -R "$LDAP_USER_ID:$LDAP_GROUP_ID" /var/lib/openldap/openldap-data
' < "$evidence/ldap-data.ldif"
dst up -d --wait
demo ready
demo restore "$run" --keep-source | tee "$evidence/restored.txt"
dst stop

# The original and reconstructed catalogues stay stopped during replay.
replay up -d --wait
demo ready
demo reingest "$run" "$evidence/replay-input"
demo restore "$run" --keep-source | tee "$evidence/replayed.txt"
replay stop
echo "Recovery drill passed. Projects are stopped and all volumes are retained."
