#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Render with explicit non-secret values. Ignore any local .env file.
export POSTGRES_PASSWORD=ci-postgres-placeholder
export LDAP_ROOTPASS=ci-ldap-root-placeholder
export LDAP_CONFIGPASS=ci-ldap-config-placeholder
export SPHINX_S3_ACCESS_KEY=ci0000000000
export SPHINX_S3_SECRET_KEY=ci1111111111

check() {
    local http_port=$1 dicom_port=$2
    shift 2
    docker compose --env-file /dev/null "$@" config --format json |
        jq -e --arg http "$http_port" --arg dicom "$dicom_port" '
            all(.services[]; .network_mode != "host") and
            ([.services | to_entries[] | .key as $service | .value.ports[]? |
                [$service, .host_ip, (.published | tostring), .target, .protocol]
            ] | sort) == ([
                ["arc", "127.0.0.1", $dicom, 11112, "tcp"],
                ["arc", "127.0.0.1", $http, 8080, "tcp"]
            ] | sort)
        ' >/dev/null
    printf 'Validated archive-only loopback ports for %s\n' "$*"
}

check 8080 11112 -f compose.yaml
check 8080 11112 -f compose.yaml -f compose.s3.yaml
check 18080 21112 -f compose.yaml -f compose.recovery.yaml
check 18080 21112 -f compose.yaml -f compose.recovery.yaml -f compose.s3.yaml
check 19080 31112 -f compose.yaml -f compose.s3.yaml -f compose.deploy.yaml
