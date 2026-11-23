from email.message import Message
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pydicom import dcmread
from pydicom.uid import ImplicitVRLittleEndian

from scripts import demo


class SyntheticFixtureTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run_dir = Path(temporary.name)
        self.source = self.run_dir / "source"
        self.source.mkdir()
        self.study = demo.make_source(self.source, multi_series=True)
        self.paths = demo.files(self.source)
        self.expected = {item["sop"]: item for item in map(demo.fingerprint, self.paths)}
        self.manifest = {"study": self.study, "instances": self.expected}
        self.output = StringIO()
        capture = patch("sys.stdout", self.output)
        capture.start()
        self.addCleanup(capture.stop)

    def test_fixture_round_trip(self):
        self.assertEqual(len(self.expected), 3)
        self.assertEqual(len({item["series"] for item in self.expected.values()}), 2)
        self.assertEqual({item["study"] for item in self.expected.values()}, {self.study})
        demo.check_objects(self.paths, self.expected, "fixture")
        self.assertIn("Byte-identical Part 10 files: 3/3", self.output.getvalue())

    def test_rejects_empty_manifest(self):
        with self.assertRaisesRegex(ValueError, "manifest has no instances"):
            demo.check_objects([], {}, "empty")
        with patch.object(demo, "qido") as query:
            with self.assertRaisesRegex(ValueError, "manifest has no instances"):
                demo.search({"study": self.study, "instances": {}})
            query.assert_not_called()

    def test_rejects_missing_extra_duplicate_instances(self):
        extra_dir = self.run_dir / "extra"
        extra_dir.mkdir()
        demo.make_source(extra_dir)
        cases = [
            ("missing", self.paths[1:], "missing SOP Instance UIDs"),
            ("extra", self.paths + [extra_dir / "1.dcm"], r"unexpected \['"),
            ("duplicate", self.paths + [self.paths[0]], "duplicate SOP Instance UID"),
        ]
        for label, paths, error in cases:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, error):
                demo.check_objects(paths, self.expected, label)

    def test_audits_added_tags_and_changed_file_meta(self):
        ds = dcmread(self.paths[0])
        ds.IssuerOfPatientID = "TEST"
        ds.file_meta.ImplementationVersionName = "TEST_META"
        ds.save_as(self.paths[0], enforce_file_format=True)
        demo.check_objects(self.paths, self.expected, "allowed differences")
        output = self.output.getvalue()
        self.assertIn("Added dataset tags: 00100021", output)
        self.assertIn("Same full dataset attributes and pixel bytes: 2/3", output)
        self.assertIn("Byte-identical Part 10 files: 2/3", output)

    def test_rejects_changed_original_attributes(self):
        ds = dcmread(self.paths[0])
        ds.PatientID = "DIFFERENT"
        ds.save_as(self.paths[0], enforce_file_format=True)
        with self.assertRaisesRegex(ValueError, "changed or omitted dataset tags"):
            demo.check_objects(self.paths, self.expected, "changed Patient ID")

    def test_rejects_changed_pixel_bytes(self):
        ds = dcmread(self.paths[0])
        ds.PixelData = bytes(len(ds.PixelData))
        ds.save_as(self.paths[0], enforce_file_format=True)
        with self.assertRaisesRegex(ValueError, "changed pixel_sha256"):
            demo.check_objects(self.paths, self.expected, "changed pixels")

    def test_rejects_changed_transfer_syntax(self):
        ds = dcmread(self.paths[0])
        ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
        ds.save_as(self.paths[0], enforce_file_format=True)
        with self.assertRaisesRegex(ValueError, "transfer syntax changed"):
            demo.check_objects(self.paths, self.expected, "changed syntax")

    def test_rejects_file_meta_uid_mismatch(self):
        ds = dcmread(self.paths[0])
        ds.file_meta.MediaStorageSOPInstanceUID = demo.generate_uid()
        # Write the mismatch as-is. Enforcing the Part 10 format repairs it.
        ds.save_as(self.paths[0])
        with self.assertRaisesRegex(ValueError, "Inconsistent file meta"):
            demo.check_objects(self.paths, self.expected, "changed file meta UID")

    def test_qido_matches_exact_sop_to_series_mapping(self):
        rows = [{demo.SOP_UID: {"Value": [sop]}, demo.SERIES_UID: {"Value": [item["series"]]}}
                for sop, item in self.expected.items()]
        studies = [{demo.STUDY_UID: {"Value": [self.study]}}]
        with patch.object(demo, "qido", side_effect=[studies, rows]):
            demo.search(self.manifest)
        with patch.object(demo, "qido", side_effect=[studies, [rows[0], rows[0], rows[2]]]):
            with self.assertRaisesRegex(ValueError, "unexpected instance or series UIDs"):
                demo.search(self.manifest)

    def test_wado_preserves_part_bytes(self):
        boundary = b"fixture-boundary"
        body = b"".join(
            b"--" + boundary + b"\r\nContent-Type: application/dicom\r\n\r\n" + p.read_bytes() + b"\r\n"
            for p in self.paths
        ) + b"--" + boundary + b"--\r\n"
        exported = self.run_dir / "exported"
        exported.mkdir()
        with patch.object(demo, "get", return_value=self.wado_response(body)):
            demo.retrieve(self.study, exported)
        self.assertEqual([p.read_bytes() for p in demo.files(exported)], [p.read_bytes() for p in self.paths])

    def test_wado_rejects_partial_response(self):
        with patch.object(demo, "get", return_value=self.wado_response(b"", status=206)):
            with self.assertRaisesRegex(ValueError, "complete multipart study"):
                demo.retrieve(self.study, self.run_dir)

    @staticmethod
    def wado_response(body, status=200):
        response = BytesIO(body)
        response.status = status
        response.headers = Message()
        response.headers["Content-Type"] = 'multipart/related; type="application/dicom"; boundary=fixture-boundary'
        return response

    def test_source_cleanup_refuses_edited_files(self):
        self.paths[0].write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "outside the generated fixture"):
            demo.remove_source(self.run_dir, self.expected)
        self.assertTrue(all(path.exists() for path in self.paths))

    def test_source_cleanup_refuses_symlinks(self):
        external = self.run_dir / "external.dcm"
        self.paths[0].rename(external)
        self.paths[0].symlink_to(external)
        with self.assertRaisesRegex(ValueError, "outside the generated fixture"):
            demo.remove_source(self.run_dir, self.expected)
        self.assertTrue(external.is_file())
        self.assertTrue(self.paths[0].is_symlink())

    def test_source_cleanup_only_removes_fixture(self):
        manifest = self.run_dir / "manifest.json"
        manifest.touch()
        demo.remove_source(self.run_dir, self.expected)
        self.assertFalse(self.source.exists())
        self.assertTrue(manifest.exists())
