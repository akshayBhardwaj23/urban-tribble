"""Focused tests for remaining launch-readiness findings."""

from __future__ import annotations

import unittest

import pandas as pd

from services.file_validation import resolve_reader_ext, sniff_kind
from services.query_plan import QueryPlanError, looks_like_rate_column, validate_plan
from services.daily_metrics import compute_daily_metrics_df
from services.forecaster import Forecaster, NotEnoughHistoryError, MIN_POINTS_FOR_FORECAST


class RateColumnTests(unittest.TestCase):
    def test_rate_names_detected(self):
        self.assertTrue(looks_like_rate_column("conversion_rate"))
        self.assertTrue(looks_like_rate_column("AOV"))
        self.assertTrue(looks_like_rate_column("margin_pct"))
        self.assertFalse(looks_like_rate_column("revenue"))
        self.assertFalse(looks_like_rate_column("order_count"))

    def test_query_plan_rejects_sum_on_rate(self):
        df = pd.DataFrame({"conversion_rate": [0.1, 0.2, 0.3], "region": ["a", "b", "a"]})
        with self.assertRaises(QueryPlanError):
            validate_plan(
                {
                    "aggregate": [
                        {"column": "conversion_rate", "func": "sum", "alias": "total_rate"}
                    ]
                },
                {"main": df},
            )


class OrdersWithoutIdTests(unittest.TestCase):
    def test_no_orders_or_aov_without_order_id(self):
        df = pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]),
                "revenue": [10.0, 20.0, 30.0],
            }
        )
        daily = compute_daily_metrics_df(df, "order_date", "revenue")
        self.assertIsNotNone(daily)
        assert daily is not None
        self.assertNotIn("orders", daily.columns)
        self.assertNotIn("aov", daily.columns)
        self.assertEqual(daily.attrs["orders_basis"]["kind"], "unavailable")


class ForecastFloorTests(unittest.TestCase):
    def test_refuses_thin_history(self):
        n = MIN_POINTS_FOR_FORECAST - 1
        df = pd.DataFrame(
            {
                "d": pd.date_range("2024-01-01", periods=n, freq="D"),
                "v": list(range(n)),
            }
        )
        with self.assertRaises(NotEnoughHistoryError):
            Forecaster().forecast(df, "d", "v", periods=7)


class SniffReaderTests(unittest.TestCase):
    def test_text_sniff(self):
        self.assertEqual(sniff_kind(b"a,b,c\n1,2,3\n"), "text")

    def test_zip_sniff(self):
        self.assertEqual(sniff_kind(b"PK\x03\x04rest"), "zip")


class NumericLocaleTests(unittest.TestCase):
    def test_bare_us_decimal_not_inflated(self):
        from pathlib import Path

        from services.data_cleaner import DataCleaner
        from services.file_processor import FileProcessor

        path = Path(__file__).parent / "fixtures/ingestion/us_decimal.csv"
        df = FileProcessor().read(str(path))
        cleaned, _ = DataCleaner().clean(df)
        # 1.234 must stay ~1.234, never become 1234
        self.assertAlmostEqual(float(cleaned["price"].iloc[0]), 1.234, places=3)

    def test_eu_thousands_with_comma_decimal(self):
        from services.data_cleaner import DataCleaner
        import pandas as pd

        df = pd.DataFrame({"amount": ["1.234,56", "2.000,00"]})
        cleaned, _ = DataCleaner().clean(df)
        self.assertAlmostEqual(float(cleaned["amount"].iloc[0]), 1234.56, places=2)


class SsrfGuardTests(unittest.TestCase):
    def test_blocks_metadata_and_private(self):
        from services.integration_connectors import _assert_safe_export_url, IntegrationFetchError

        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1/admin",
            "http://localhost:8080/x",
            "http://10.0.0.5/secret",
        ):
            with self.assertRaises(IntegrationFetchError):
                _assert_safe_export_url(url)


class ProductionSecretGuardTests(unittest.TestCase):
    def test_empty_jwt_rejected_in_production(self):
        from config import Settings, collect_runtime_setting_errors

        s = Settings(
            APP_ENV="production",
            API_JWT_SECRET="",
            OTP_PEPPER="x" * 32,
            INTERNAL_AUTH_SECRET="y" * 32,
            INTEGRATION_OAUTH_STATE_SECRET="z" * 32,
            DATABASE_URL="postgresql://u:p@localhost/db",
            STORAGE_BACKEND="s3",
            S3_BUCKET="bucket",
            CORS_ORIGINS="https://app.example.com",
            INTEGRATION_CRON_SECRET="cron-secret-value-here",
            RESEND_API_KEY="re_test",
        )
        errors = collect_runtime_setting_errors(s)
        self.assertTrue(any("API_JWT_SECRET" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
