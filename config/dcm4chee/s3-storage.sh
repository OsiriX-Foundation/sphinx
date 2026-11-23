#!/bin/sh
# Run inside the optional S3 project's ldap service before starting arc.
set -eu

# Keep the interpolated values valid in LDIF and in the demo's mc alias URL.
for value in "$SPHINX_S3_ACCESS_KEY" "$SPHINX_S3_SECRET_KEY"; do
    case "$value" in
        ''|*[!a-zA-Z0-9-]*) echo "The local S3 credentials must be alphanumeric or hyphenated" >&2; exit 1 ;;
    esac
done

ldapmodify -x -H "${LDAP_URL:-ldap://127.0.0.1:389}" -D cn=admin,dc=dcm4che,dc=org -w "$LDAP_ROOTPASS" <<LDIF
dn: dcmStorageID=fs1,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: modify
replace: dcmURI
dcmURI: jclouds:s3:http://s3:9000
-
replace: dcmProperty
dcmProperty: identity=$SPHINX_S3_ACCESS_KEY
dcmProperty: credential=$SPHINX_S3_SECRET_KEY
dcmProperty: container=sphinx-dicom
dcmProperty: containerExists=true
dcmProperty: jclouds.s3.virtual-host-buckets=false
dcmProperty: jclouds.strip-expect-header=true
dcmProperty: pathFormat={now,date,yyyy/MM/dd}/{0020000D,hash}/{0020000E,hash}/{00080018,hash}
LDIF
