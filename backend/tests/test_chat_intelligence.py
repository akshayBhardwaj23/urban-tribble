"""Tests for workspace chat intelligence (no double-counting shortcuts)."""

import unittest

import pandas as pd

from services.chat_intelligence import (
    build_source_catalog,
    friendly_source_name,
    try_workspace_shortcut,
)


def _pair(name: str, df: pd.DataFrame, revenue_cols: list[str]) -> tuple:
    schema = {"revenue_columns": revenue_cols, "date_columns": []}
    return (name, df, schema, None)


class ChatIntelligenceTests(unittest.TestCase):
    def test_friendly_source_name(self):
        self.assertEqual(
            friendly_source_name("monthly_revenue_and_profit.xlsx"),
            "Monthly Revenue And Profit",
        )

    def test_total_revenue_returns_per_source_not_sum(self):
        orders = pd.DataFrame(
            {"order_id": [1, 2], "revenue_inr": [100.0, 200.0]}
        )
        monthly = pd.DataFrame(
            {"month": ["2024-01"], "channel": ["A"], "net_revenue_inr": [500.0]}
        )
        frames = [
            _pair("recent_orders_detail.xlsx", orders, ["revenue_inr"]),
            _pair(
                "monthly_revenue_and_profit_by_channel.xlsx",
                monthly,
                ["net_revenue_inr"],
            ),
        ]
        out = try_workspace_shortcut(
            "What is total revenue across all sources?", frames
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("no single", out["answer"].lower())
        self.assertNotIn("800", out["answer"])
        self.assertIn("300", out["answer"])
        self.assertIn("500", out["answer"])

    def test_canonical_revenue_picks_monthly_channel(self):
        orders = pd.DataFrame({"order_id": [1], "revenue_inr": [1_000_000.0]})
        monthly = pd.DataFrame(
            {"month": ["2024-01"], "channel": ["Web"], "net_revenue_inr": [50_000.0]}
        )
        frames = [
            _pair("recent_orders_detail.xlsx", orders, ["revenue_inr"]),
            _pair(
                "monthly_revenue_and_profit_by_channel.xlsx",
                monthly,
                ["net_revenue_inr"],
            ),
        ]
        catalog = build_source_catalog(frames)
        canonical = [
            c for c in catalog if "monthly" in c["label"].lower()
        ]
        self.assertTrue(canonical)
        out = try_workspace_shortcut(
            "Which source should I use for company revenue?", frames
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("Monthly Revenue And Profit By Channel", out["answer"])


if __name__ == "__main__":
    unittest.main()
