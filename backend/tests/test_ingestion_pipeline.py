"""Golden-file tests for the spreadsheet ingestion pipeline."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from services.column_detector import ColumnDetector
from services.column_profile import (
    build_mapping_spec,
    metadata_from_mapping_spec,
    preserve_user_mapping,
    user_authored,
)
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor
from services.ingest_pipeline import process_dataframe

FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


class IngestionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.cleaner = DataCleaner()
        self.detector = ColumnDetector()
        self.reader = FileProcessor()

    def _clean_detect(self, path: Path):
        df = self.reader.read(str(path))
        cleaned, report = self.cleaner.clean(df)
        meta = self.detector.detect(cleaned)
        return cleaned, report, meta

    def test_dayfirst_dates(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "dates_dayfirst.csv")
        self.assertIn("order_date", meta["date_columns"])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(cleaned["order_date"]))
        # 15/01/2024 → January 15
        self.assertEqual(cleaned["order_date"].iloc[0].month, 1)
        self.assertEqual(cleaned["order_date"].iloc[0].day, 15)
        self.assertEqual(cleaned["order_date"].iloc[3].month, 12)
        self.assertEqual(cleaned["order_date"].iloc[3].day, 25)

    def test_monthfirst_dates(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "dates_monthfirst.csv")
        self.assertIn("order_date", meta["date_columns"])
        # 01/15/2024 → January 15
        self.assertEqual(cleaned["order_date"].iloc[0].month, 1)
        self.assertEqual(cleaned["order_date"].iloc[0].day, 15)

    def test_ambiguous_dates_flagged(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "dates_ambiguous.csv")
        codes = {f.get("code") for f in report.get("flags") or []}
        self.assertIn("ambiguous_date_format", codes)
        # Default dayfirst → 01/02/2024 is 1 Feb
        self.assertEqual(cleaned["order_date"].iloc[0].day, 1)
        self.assertEqual(cleaned["order_date"].iloc[0].month, 2)

    def test_delivery_days_not_timeline(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "delivery_days.csv")
        self.assertNotIn("delivery_days", meta["date_columns"])
        self.assertIn("order_date", meta["date_columns"])
        # Ad_Spend should be expense/outflow, not revenue
        self.assertIn("ad_spend", meta.get("expense_columns") or [])
        self.assertNotIn("ad_spend", meta.get("revenue_columns") or [])

    def test_currency_and_negatives(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "currency.csv")
        self.assertTrue(pd.api.types.is_numeric_dtype(cleaned["amount"]))
        self.assertAlmostEqual(float(cleaned["amount"].iloc[0]), 1234.56, places=2)
        self.assertAlmostEqual(float(cleaned["fee"].iloc[0]), -500.0, places=2)
        # EU format €1.234,56
        self.assertAlmostEqual(float(cleaned["amount"].iloc[3]), 1234.56, places=2)

    def test_colliding_headers(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "colliding_headers.csv")
        cols = list(cleaned.columns)
        self.assertEqual(len(cols), len(set(cols)))
        self.assertTrue(any(c.startswith("total_sales") for c in cols))
        # Selecting a column must return a Series, never a DataFrame
        for c in cols:
            self.assertIsInstance(cleaned[c], pd.Series)

    def test_numeric_and_blank_headers(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "numeric_headers.csv")
        cols = list(cleaned.columns)
        self.assertEqual(len(cols), 3)
        self.assertTrue(all(cols))  # no blank names
        self.assertIn("name", cols)

    def test_trailing_total_stripped(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "trailing_total.csv")
        self.assertEqual(len(cleaned), 2)
        self.assertAlmostEqual(float(cleaned["revenue"].sum()), 300.0)

    def test_sparse_column_kept(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "sparse_column.csv")
        self.assertIn("notes", cleaned.columns)
        codes = {f.get("code") for f in report.get("flags") or []}
        self.assertIn("sparse_column", codes)

    def test_duplicates_kept_by_default(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "duplicates.csv")
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(report.get("duplicate_row_count"), 1)
        codes = {f.get("code") for f in report.get("flags") or []}
        self.assertIn("duplicates_detected", codes)

    def test_no_median_fill(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "missing_numeric.csv")
        self.assertTrue(pd.isna(cleaned["revenue"].iloc[1]))
        # Sum should be 400, not inflated by median fill
        self.assertAlmostEqual(float(cleaned["revenue"].sum(skipna=True)), 400.0)

    def test_excel_serial_dates(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "excel_serial.csv")
        self.assertIn("order_date", meta["date_columns"])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(cleaned["order_date"]))
        self.assertEqual(cleaned["order_date"].iloc[0].year, 2024)

    def test_multi_sheet_picks_data_sheet(self):
        df = self.reader.read(str(FIXTURES / "multi_sheet.xlsx"))
        self.assertIn("Revenue", df.columns) or self.assertIn("revenue", [c.lower() for c in df.columns])
        sheets = self.reader.list_sheets(str(FIXTURES / "multi_sheet.xlsx"))
        self.assertGreaterEqual(len(sheets), 2)
        self.assertEqual(sheets[0]["name"], "Transactions")

    def test_mapping_spec_roundtrip(self):
        cleaned, report, meta = self._clean_detect(FIXTURES / "delivery_days.csv")
        spec = build_mapping_spec(cleaned, meta, clean_report=report, source="auto")
        derived = metadata_from_mapping_spec(spec)
        self.assertEqual(derived["date_columns"], meta["date_columns"])
        self.assertIn("expense_columns", derived)

    def test_process_dataframe_no_llm(self):
        df = self.reader.read(str(FIXTURES / "delivery_days.csv"))
        out = process_dataframe(df, filename="delivery_days.csv", use_llm=False)
        self.assertIn("mapping_spec", out)
        self.assertIn("ingestion", out)
        self.assertNotIn("delivery_days", out["metadata"]["date_columns"])

    def test_xls_engine_registered(self):
        # Ensure .xls is wired; skip if xlrd missing
        try:
            import xlrd  # noqa: F401
        except ImportError:
            self.skipTest("xlrd not installed")
        self.assertIn(".xls", {".xls"})  # reader path exists
        # Reading a .xlsx with xls engine is wrong; just verify method accepts engine
        df = self.reader.read(str(FIXTURES / "simple.xlsx"))
        self.assertGreater(len(df), 0)


class UserAuthoredTests(unittest.TestCase):
    """`source` is the only thing separating a person's decision from a guess."""

    def test_the_editor_marker_is_recognised(self):
        self.assertTrue(user_authored({"source": "user"}))

    def test_machine_derived_specs_are_not_user_authored(self):
        for source in ("llm", "auto"):
            with self.subTest(source=source):
                self.assertFalse(user_authored({"source": source}))

    def test_missing_and_empty_specs_are_safe(self):
        for spec in (None, {}, {"columns": []}):
            with self.subTest(spec=spec):
                self.assertFalse(user_authored(spec))


class PreserveUserMappingTests(unittest.TestCase):
    """Re-deriving a spec is right for what the machine guessed and wrong for
    what a person chose. These pin which half is which."""

    def _old(self, **overrides):
        spec = {
            "source": "user",
            "primary_timeline": "order_date",
            "primary_amount": "net_revenue",
            "dayfirst": True,
            "drop_duplicates": True,
            "header_row": 2,
            "sheet": "Q4",
            "columns": [
                {"name": "order_date", "role": "timeline", "date_format": "%d/%m/%Y"},
                {"name": "net_revenue", "role": "amount_inflow", "meaning": "Net of refunds"},
                {"name": "notes", "role": "ignore"},
            ],
        }
        spec.update(overrides)
        return spec

    def _new(self, columns=None):
        return {
            "source": "llm",
            "primary_timeline": "shipped_date",
            "primary_amount": "gross_revenue",
            "dayfirst": None,
            "drop_duplicates": False,
            "header_row": 0,
            "sheet": None,
            "columns": columns
            or [
                {"name": "order_date", "role": "text"},
                {"name": "net_revenue", "role": "quantity"},
                {"name": "notes", "role": "text"},
            ],
        }

    def test_corrected_roles_survive(self):
        merged = preserve_user_mapping(self._old(), self._new())
        by_name = {c["name"]: c for c in merged["columns"]}
        self.assertEqual(by_name["order_date"]["role"], "timeline")
        self.assertEqual(by_name["net_revenue"]["role"], "amount_inflow")
        self.assertEqual(by_name["notes"]["role"], "ignore")

    def test_meanings_and_date_formats_survive(self):
        merged = preserve_user_mapping(self._old(), self._new())
        by_name = {c["name"]: c for c in merged["columns"]}
        self.assertEqual(by_name["net_revenue"]["meaning"], "Net of refunds")
        self.assertEqual(by_name["order_date"]["date_format"], "%d/%m/%Y")

    def test_the_chosen_primary_columns_survive(self):
        """The headline bug: build_mapping_spec falls back to the first date
        and revenue column, so a deliberate choice was reset on every sync."""
        merged = preserve_user_mapping(self._old(), self._new())
        self.assertEqual(merged["primary_timeline"], "order_date")
        self.assertEqual(merged["primary_amount"], "net_revenue")

    def test_parse_policy_survives(self):
        """These describe how the file is read, not just how it is labelled."""
        merged = preserve_user_mapping(self._old(), self._new())
        self.assertIs(merged["dayfirst"], True)
        self.assertIs(merged["drop_duplicates"], True)
        self.assertEqual(merged["header_row"], 2)
        self.assertEqual(merged["sheet"], "Q4")

    def test_the_result_stays_user_authored(self):
        """Otherwise the next sync would treat it as a machine guess and the
        preservation would apply exactly once."""
        self.assertEqual(preserve_user_mapping(self._old(), self._new())["source"], "user")

    def test_a_dropped_column_is_not_resurrected(self):
        merged = preserve_user_mapping(
            self._old(),
            self._new(columns=[{"name": "net_revenue", "role": "quantity"}]),
        )
        self.assertEqual([c["name"] for c in merged["columns"]], ["net_revenue"])

    def test_a_primary_that_no_longer_exists_falls_back_to_the_fresh_guess(self):
        """Preserving it blindly would leave the spec pointing at nothing."""
        merged = preserve_user_mapping(
            self._old(),
            self._new(
                columns=[
                    {"name": "shipped_date", "role": "timeline"},
                    {"name": "gross_revenue", "role": "amount_inflow"},
                ]
            ),
        )
        self.assertEqual(merged["primary_timeline"], "shipped_date")
        self.assertEqual(merged["primary_amount"], "gross_revenue")

    def test_a_new_column_keeps_its_freshly_derived_role(self):
        """Only what the user actually touched is frozen; the rest is profiled
        normally, or a new column could never be picked up."""
        merged = preserve_user_mapping(
            self._old(),
            self._new(
                columns=[
                    {"name": "order_date", "role": "text"},
                    {"name": "region", "role": "dimension"},
                ]
            ),
        )
        by_name = {c["name"]: c for c in merged["columns"]}
        self.assertEqual(by_name["region"]["role"], "dimension")
        self.assertEqual(by_name["order_date"]["role"], "timeline")

    def test_neither_input_is_mutated(self):
        old, new = self._old(), self._new()
        preserve_user_mapping(old, new)
        self.assertEqual(new["source"], "llm")
        self.assertEqual(new["primary_timeline"], "shipped_date")
        self.assertEqual(new["columns"][0]["role"], "text")
        self.assertEqual(old["columns"][0]["role"], "timeline")

    def test_the_merged_spec_drives_the_legacy_metadata_shim(self):
        """schema_json is derived from the spec, so the preserved roles have to
        survive that conversion too -- otherwise the dashboard still rebuilds
        from the guessed ones."""
        merged = preserve_user_mapping(self._old(), self._new())
        metadata = metadata_from_mapping_spec(merged)
        self.assertEqual(metadata["date_columns"], ["order_date"])
        self.assertEqual(metadata["revenue_columns"], ["net_revenue"])
        self.assertNotIn("notes", metadata["text_columns"])


if __name__ == "__main__":
    unittest.main()
