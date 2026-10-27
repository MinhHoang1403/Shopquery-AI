"""Exercise synthetic tools in owned temporary folders, without Docker or providers."""

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

from docx import Document
from generate_maintenance_demo import generate
from maintenance_oracle import build_oracle
from pypdf import PdfReader


def fonts() -> tuple[Path, Path]:
    """Use installed Unicode fonts; never download files or alter the host."""
    if os.name == "nt":
        root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        pair = root / "arial.ttf", root / "arialbd.ttf"
    else:
        root = Path("/usr/share/fonts/truetype/dejavu")
        pair = root / "DejaVuSans.ttf", root / "DejaVuSans-Bold.ttf"
    if not all(path.is_file() for path in pair):
        raise RuntimeError("Install Arial or DejaVu Sans Unicode fonts before these tests")
    return pair


class MaintenanceToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="shopquery_maintenance_tests_")
        cls.root = Path(cls.temporary.name).resolve()
        # TemporaryDirectory may remove only this newly created, owned temp subtree.
        if cls.root.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError("Unexpected temporary directory root")
        cls.regular, cls.bold = fonts()
        cls.bundle = cls.root / "bundle"
        generate(cls.bundle, cls.regular, cls.bold)
        cls.oracle = build_oracle(cls.bundle)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_generator_requires_new_explicit_output(self) -> None:
        before = {path.name: path.read_bytes() for path in self.bundle.iterdir()}
        with self.assertRaises(FileExistsError):
            generate(self.bundle, self.regular, self.bold)
        with self.assertRaises(ValueError):
            generate(Path("relative-output"), self.regular, self.bold)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.bundle.iterdir()})

    def test_font_failure_leaves_no_output(self) -> None:
        output = self.root / "invalid-font"
        with self.assertRaises(ValueError):
            generate(output, self.root / "missing.ttf", self.bold)
        self.assertFalse(output.exists())

    def test_all_six_files_are_reproducible(self) -> None:
        other = self.root / "repeated"
        generate(other, self.regular, self.bold)
        self.assertEqual(len(list(other.iterdir())), 6)
        for source in self.bundle.iterdir():
            self.assertEqual(source.read_bytes(), (other / source.name).read_bytes(), source.name)

    def test_documents_are_parseable_and_contain_unicode_evidence(self) -> None:
        document = Document(self.bundle / "05_quy_trinh_bao_tri.docx")
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("Điều kiện hoàn thành", text)
        reader = PdfReader(self.bundle / "06_so_tay_dich_vu.pdf")
        self.assertGreaterEqual(len(reader.pages), 4)
        self.assertIn("Phí của phiếu", "\n".join(page.extract_text() for page in reader.pages))

    def test_oracle_recomputes_sums_and_boundary_verdicts_from_csv(self) -> None:
        with (self.bundle / "03_phieu_bao_tri.csv").open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        total = sum((Decimal(row["phi_bao_tri_vnd"]) for row in rows), Decimal(0))
        self.assertEqual(Decimal(self.oracle["total_fee"]), total)
        self.assertEqual(self.oracle["counts"], {"centers": 30, "services": 60, "tickets": 3000})
        self.assertEqual(
            Counter(row["status"] for row in self.oracle["kpi"]),
            {"qualified": 15, "not_qualified": 15},
        )
        self.assertEqual(len(self.oracle["threshold_equal"]), 1)
        by_fee = {row["tong_phi"]: row["status"] for row in self.oracle["kpi"]}
        self.assertEqual(by_fee["7999999.99"], "not_qualified")
        self.assertEqual(by_fee["8000000.00"], "qualified")
        self.assertEqual(by_fee["8000000.01"], "qualified")

    def changed_bundle(self, name: str) -> Path:
        """Copy only generated fixture files into another owned test input, never source."""
        target = self.root / name
        target.mkdir()
        for file in self.bundle.iterdir():
            (target / file.name).write_bytes(file.read_bytes())
        return target

    def change_ticket(self, folder: Path, **values: str) -> None:
        path = folder / "03_phieu_bao_tri.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        rows[0].update(values)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_oracle_uses_actual_rows_instead_of_generator_target_totals(self) -> None:
        folder = self.changed_bundle("changed-fee")
        path = folder / "03_phieu_bao_tri.csv"
        with path.open(encoding="utf-8-sig") as stream:
            row = next(csv.DictReader(stream))
        self.change_ticket(
            folder, phi_bao_tri_vnd=str(Decimal(row["phi_bao_tri_vnd"]) + Decimal("0.01"))
        )
        self.assertEqual(
            Decimal(build_oracle(folder)["total_fee"]),
            Decimal(self.oracle["total_fee"]) + Decimal("0.01"),
        )

    def test_invalid_source_data_is_refused_without_assert_dependency(self) -> None:
        for index, changes in enumerate(
            (
                {"ma_trung_tam": "unknown"},
                {"phi_bao_tri_vnd": "NaN"},
                {"phi_bao_tri_vnd": "-0.01"},
                {"phi_bao_tri_vnd": "1.001"},
                {"ngay_tiep_nhan": "2026-02-30"},
                {"trang_thai": "unknown"},
            )
        ):
            with self.subTest(changes=changes):
                folder = self.changed_bundle(f"invalid-{index}")
                self.change_ticket(folder, **changes)
                with self.assertRaises((ValueError, ArithmeticError)):
                    build_oracle(folder)

    def test_duplicate_keys_and_missing_headers_are_refused(self) -> None:
        folder = self.changed_bundle("duplicate-key")
        path = folder / "03_phieu_bao_tri.csv"
        with path.open(encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
        self.change_ticket(folder, ma_phieu=rows[1]["ma_phieu"])
        with self.assertRaises(ValueError):
            build_oracle(folder)
        folder = self.changed_bundle("missing-header")
        path = folder / "03_phieu_bao_tri.csv"
        path.write_text(
            path.read_text(encoding="utf-8-sig").replace("phi_bao_tri_vnd", "unexpected", 1),
            encoding="utf-8-sig",
        )
        with self.assertRaises(ValueError):
            build_oracle(folder)

    def test_changed_policy_is_refused(self) -> None:
        folder = self.changed_bundle("changed-policy")
        (folder / "04_KPI_trung_tam.md").write_text("Unknown policy", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_oracle(folder)

    def test_cli_requires_paths_and_never_overwrites_existing_json(self) -> None:
        script = Path(__file__).with_name("maintenance_oracle.py")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        missing = subprocess.run([sys.executable, str(script)], capture_output=True, env=env)
        self.assertNotEqual(missing.returncode, 0)
        output = self.root / "answers.json"
        command = [
            sys.executable,
            str(script),
            "--input",
            str(self.bundle),
            "--output",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = output.read_bytes()
        blocked = subprocess.run(command, capture_output=True, env=env)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(output.read_bytes(), payload)
        self.assertEqual(
            json.loads(payload)["source_hashes"]["04_KPI_trung_tam.md"],
            hashlib.sha256((self.bundle / "04_KPI_trung_tam.md").read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
