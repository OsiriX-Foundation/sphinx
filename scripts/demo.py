#!/usr/bin/env python3
"""Run the synthetic SPHINX C-STORE, DICOMweb and recovery checks."""

import argparse
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydicom import dcmread
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import (
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    SecondaryCaptureImageStorage,
    generate_uid,
)
from pynetdicom import AE
from pynetdicom.sop_class import Verification

DATA = Path(__file__).resolve().parents[1] / "data"
HOST = "127.0.0.1"
ARCHIVE_AE = "DCM4CHEE"
ARCHIVE_PORT = int(os.environ.get("SPHINX_DICOM_PORT", "11112"))
HTTP_PORT = int(os.environ.get("SPHINX_HTTP_PORT", "8080"))
RECEIVER_AE, RECEIVER_PORT = "SPHINX_RESTORE", 11113
DICOMWEB = f"http://{HOST}:{HTTP_PORT}/dcm4chee-arc/aets/{ARCHIVE_AE}/rs"
STUDY_UID, SERIES_UID, SOP_UID = "0020000D", "0020000E", "00080018"
SOURCE_NAMES = {"1.dcm", "2.dcm", "3.dcm"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def files(directory):
    return sorted(path for path in directory.iterdir() if path.is_file())


def make_source(directory, multi_series=False):
    study, series = generate_uid(), generate_uid()
    second_series = generate_uid() if multi_series else series
    for number in range(1, 4):
        path = directory / f"{number}.dcm"
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(path, {}, file_meta=meta, preamble=bytes(128))
        ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
        series_number = 2 if multi_series and number == 3 else 1
        ds.StudyInstanceUID = study
        ds.SeriesInstanceUID = second_series if series_number == 2 else series
        ds.PatientName, ds.PatientID = "SPHINX^Synthetic", f"SYN-{study[-12:]}"
        ds.PatientBirthDate, ds.PatientSex = "", ""
        ds.StudyDate, ds.StudyTime = "20260101", "120000"
        ds.AccessionNumber, ds.ReferringPhysicianName = "", ""
        ds.StudyID, ds.SeriesNumber, ds.InstanceNumber = "SPHINX", series_number, number
        ds.StudyDescription, ds.SeriesDescription = "SPHINX recovery fixture", "Synthetic gradients"
        ds.Modality, ds.ConversionType, ds.Manufacturer = "OT", "SYN", "SPHINX test fixture"
        ds.Laterality = ""
        ds.ImageType, ds.PatientOrientation = ["DERIVED", "SECONDARY"], ["L", "P"]
        ds.ContentDate, ds.ContentTime = ds.StudyDate, ds.StudyTime
        ds.BurnedInAnnotation, ds.LossyImageCompression = "NO", "00"
        ds.Rows, ds.Columns = 32, 32
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
        ds.PixelData = bytes((i + number * 31) % 256 for i in range(ds.Rows * ds.Columns))
        ds.save_as(path, enforce_file_format=True)
    return study


def fingerprint(path):
    raw = path.read_bytes()
    ds = dcmread(path)
    if (ds.SOPClassUID, ds.SOPInstanceUID) != (
        ds.file_meta.MediaStorageSOPClassUID, ds.file_meta.MediaStorageSOPInstanceUID
    ):
        raise ValueError(f"Inconsistent file meta in {path}")
    elements = ds.to_json_dict()
    del elements["7FE00010"]
    return {
        "study": str(ds.StudyInstanceUID),
        "series": str(ds.SeriesInstanceUID),
        "sop": str(ds.SOPInstanceUID),
        "transfer_syntax": str(ds.file_meta.TransferSyntaxUID),
        "file_sha256": digest(raw),
        "pixel_sha256": digest(ds.PixelData),
        "attributes": {
            tag: digest(json.dumps(value, sort_keys=True).encode()) for tag, value in elements.items()
        },
    }


def check_objects(paths, expected, label):
    actual = {}
    for path in paths:
        item = fingerprint(path)
        if item["sop"] in actual:
            raise ValueError(f"{label}: duplicate SOP Instance UID {item['sop']}")
        actual[item["sop"]] = item
    if actual.keys() != expected.keys():
        raise ValueError(f"{label}: unexpected instance UIDs: {sorted(actual)}")
    exact_files, preserved_syntaxes, exact_datasets = 0, 0, 0
    added_tags = set()
    for sop, original in expected.items():
        recovered = actual[sop]
        for field in ("study", "series", "pixel_sha256"):
            if recovered[field] != original[field]:
                raise ValueError(f"{label}: {sop} changed {field}")
        changes = [tag for tag, value in original["attributes"].items()
                   if recovered["attributes"].get(tag) != value]
        if changes:
            raise ValueError(f"{label}: {sop} changed or omitted dataset tags {changes}")
        added_tags.update(recovered["attributes"].keys() - original["attributes"].keys())
        exact_files += recovered["file_sha256"] == original["file_sha256"]
        exact_datasets += recovered["attributes"] == original["attributes"]
        preserved_syntaxes += recovered["transfer_syntax"] == original["transfer_syntax"]
    print(f"{label}: {len(actual)} instances with matching UIDs, original attributes and pixel bytes")
    print(f"  Byte-identical Part 10 files: {exact_files}/{len(actual)}")
    print(f"  Same full dataset attributes and pixel bytes: {exact_datasets}/{len(actual)}")
    print(f"  Original transfer syntax preserved: {preserved_syntaxes}/{len(actual)}")
    print(f"  Observed transfer syntaxes: {sorted({item['transfer_syntax'] for item in actual.values()})}")
    if added_tags:
        print(f"  Added dataset tags: {', '.join(sorted(added_tags))}")
    if preserved_syntaxes != len(expected):
        raise ValueError(f"{label}: transfer syntax changed")


@contextmanager
def association(port, title, contexts, calling_title):
    ae = AE(ae_title=calling_title)
    ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 5
    for uid, syntax in contexts:
        ae.add_requested_context(uid, syntax)
    assoc = ae.associate(HOST, port, ae_title=title)
    if not assoc.is_established:
        raise RuntimeError(f"Association to {title} at {HOST}:{port} failed")
    try:
        yield assoc
    finally:
        if assoc.is_established:
            assoc.release()


def require_success(status, operation):
    if getattr(status, "Status", None) != 0:
        raise RuntimeError(f"{operation} failed: {status!s}")


def echo(port, title):
    with association(port, title, [(Verification, ImplicitVRLittleEndian)], "SPHINX_TEST") as assoc:
        require_success(assoc.send_c_echo(), f"C-ECHO to {title}")


def send(paths, port, title, calling_title):
    datasets = [dcmread(path) for path in paths]
    # Offer the on-disk syntax for each instance. No transcoding in the test client.
    contexts = {(ds.SOPClassUID, ds.file_meta.TransferSyntaxUID) for ds in datasets}
    with association(port, title, contexts, calling_title) as assoc:
        accepted = {(cx.abstract_syntax, cx.transfer_syntax[0]) for cx in assoc.accepted_contexts}
        if not contexts <= accepted:
            raise RuntimeError(f"{title} did not accept the input transfer syntax")
        for ds in datasets:
            require_success(assoc.send_c_store(ds), f"C-STORE of {ds.SOPInstanceUID} to {title}")
    print(f"C-STORE to {title}: {len(datasets)} success responses", file=sys.stderr)


def get(path, accept):
    request = Request(DICOMWEB + path, headers={"Accept": accept})
    return urlopen(request, timeout=15)


def qido(path):
    with get(path, "application/dicom+json") as response:
        if response.status == 204:
            return []
        if response.status != 200 or response.headers.get_content_type() != "application/dicom+json":
            raise RuntimeError(f"Unexpected QIDO response: HTTP {response.status}, {response.headers['Content-Type']}")
        return json.load(response)


def ready():
    echo(ARCHIVE_PORT, ARCHIVE_AE)
    missing = urlencode({"StudyInstanceUID": generate_uid()})
    if qido(f"/studies?{missing}") != []:
        raise ValueError("QIDO returned a study for a newly generated UID")
    print(f"{ARCHIVE_AE} C-ECHO and QIDO-RS passed")


def load_run(run):
    path = Path(run).resolve()
    if path.parent != DATA or not path.name.startswith("run-"):
        raise ValueError(f"Expected a generated run directory under {DATA}")
    with (path / "manifest.json").open() as stream:
        return path, json.load(stream)


def search(manifest):
    study = manifest["study"]
    expected = manifest["instances"]
    rows = qido(f"/studies?{urlencode({'StudyInstanceUID': study})}")
    if [row[STUDY_UID]["Value"][0] for row in rows] != [study]:
        raise ValueError(f"QIDO did not return exactly the requested study {study}")
    instances = qido(f"/studies/{study}/instances")
    actual = {row[SOP_UID]["Value"][0]: row[SERIES_UID]["Value"][0] for row in instances}
    if len(instances) != len(expected) or actual != {sop: item["series"] for sop, item in expected.items()}:
        raise ValueError(f"QIDO returned unexpected instance or series UIDs for {study}: {actual}")
    print(f"QIDO: study {study}, {len(actual)} matching instances", file=sys.stderr)


def ingest(multi_series=False):
    ready()
    path = Path(tempfile.mkdtemp(prefix="run-", dir=DATA))
    directory = path / "source"
    directory.mkdir()
    study = make_source(directory, multi_series)
    instances = {item["sop"]: item for item in map(fingerprint, files(directory))}
    (path / "manifest.json").write_text(json.dumps({"study": study, "instances": instances}, indent=2) + "\n")
    print(f"Run directory: {path}", flush=True)
    send(files(directory), ARCHIVE_PORT, ARCHIVE_AE, "SPHINX_SOURCE")
    search({"study": study, "instances": instances})


def remove_source(path, expected):
    source = path / "source"
    if source.is_symlink():
        raise ValueError("The source directory is a symlink")
    if not source.exists():
        return
    entries = list(source.iterdir())
    expected_hashes = {item["file_sha256"] for item in expected.values()}
    if any(entry.is_symlink() or not entry.is_file() or entry.name not in SOURCE_NAMES
           or digest(entry.read_bytes()) not in expected_hashes for entry in entries):
        raise ValueError("Source contains files outside the generated fixture")
    for entry in entries:
        entry.unlink()
    source.rmdir()
    print("Simulated source loss: deleted only the generated source files")


def retrieve(study, directory):
    accept = 'multipart/related; type="application/dicom"; transfer-syntax=*'
    with get(f"/studies/{study}", accept) as response:
        content_type = response.headers["Content-Type"]
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
            + response.read()
        )
        if response.status != 200 or message.get_content_type() != "multipart/related":
            raise ValueError("WADO did not return a complete multipart study")
    if not message.is_multipart() or message.defects:
        raise ValueError("Malformed WADO multipart response")
    for n, part in enumerate(message.iter_parts(), start=1):
        if part.get_content_type() != "application/dicom" or part.defects:
            raise ValueError(f"Unexpected WADO part {n}: {part.get_content_type()}")
        (directory / f"{n}.dcm").write_bytes(part.get_payload(decode=True))


def restore(path, manifest, keep_source=False):
    search(manifest)
    expected = manifest["instances"]
    if not keep_source:
        remove_source(path, expected)
        search(manifest)
    attempt = Path(tempfile.mkdtemp(prefix="restore-", dir=path))
    exported, received = attempt / "exported", attempt / "received"
    exported.mkdir()
    received.mkdir()
    print(f"Recovery attempt: {attempt}", flush=True)
    retrieve(manifest["study"], exported)
    check_objects(files(exported), expected, "WADO export")

    # Independent Store SCP process with its own output directory and no archive access.
    with (attempt / "receiver.log").open("w") as log:
        with subprocess.Popen(
            [sys.executable, "-m", "pynetdicom", "storescp", "-ba", HOST,
             "-aet", RECEIVER_AE, "-od", str(received), str(RECEIVER_PORT)],
            stdout=log, stderr=subprocess.STDOUT,
        ) as receiver:
            try:
                for _ in range(40):
                    if receiver.poll() is not None:
                        raise RuntimeError(f"Receiver exited. See {log.name}")
                    try:
                        echo(RECEIVER_PORT, RECEIVER_AE)
                        break
                    except RuntimeError:
                        time.sleep(0.25)
                else:
                    raise RuntimeError(f"Receiver did not respond. See {log.name}")
                send(files(exported), RECEIVER_PORT, RECEIVER_AE, "SPHINX_EXPORT")
                check_objects(files(received), expected, "Independent receiver")
            finally:
                if receiver.poll() is None:
                    receiver.terminate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("ready", help="verify archive C-ECHO and a QIDO query")
    ingest_command = actions.add_parser("ingest", help="generate a fresh synthetic study, C-STORE it and check the index")
    ingest_command.add_argument("--multi-series", action="store_true", help="split the fixture across two series")
    actions.add_parser("search", help="find the study and its instances in the archive").add_argument("run")
    restore_command = actions.add_parser("restore", help="retrieve and verify on a separate SCP")
    restore_command.add_argument("run")
    restore_command.add_argument("--keep-source", action="store_true", help="preserve the synthetic source for comparison")
    verify = actions.add_parser("verify", help="compare a directory of recovered objects with the manifest")
    verify.add_argument("run")
    verify.add_argument("directory", type=Path)
    reingest = actions.add_parser("reingest", help="C-STORE verified objects from an existing synthetic run")
    reingest.add_argument("run")
    reingest.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "ready":
            ready()
        elif args.action == "ingest":
            ingest(args.multi_series)
        else:
            path, manifest = load_run(args.run)
            if args.action == "search":
                search(manifest)
            elif args.action in ("verify", "reingest"):
                objects = files(args.directory)
                check_objects(objects, manifest["instances"], "DICOM object verification")
                if args.action == "reingest":
                    send(objects, ARCHIVE_PORT, ARCHIVE_AE, "SPHINX_REPLAY")
                    search(manifest)
            else:
                restore(path, manifest, args.keep_source)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"{args.action} failed: {exc}\n")


if __name__ == "__main__":
    main()
