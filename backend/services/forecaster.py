from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class Forecaster:
    def forecast(
        self,
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
        periods: int = 30,
    ) -> Dict[str, Any]:
        """Simple linear regression forecast."""
        if date_col not in df.columns or value_col not in df.columns:
            raise ValueError(f"Columns {date_col} or {value_col} not found")

        ts = df[[date_col, value_col]].copy()
        ts[date_col] = pd.to_datetime(ts[date_col])
        ts = ts.groupby(date_col)[value_col].sum().reset_index()
        ts = ts.sort_values(date_col)

        if len(ts) < 3:
            raise ValueError("Need at least 3 data points for forecasting")

        x = np.arange(len(ts)).astype(float)
        y = ts[value_col].values.astype(float)

        slope, intercept = np.polyfit(x, y, 1)
        y_pred_historical = slope * x + intercept

        residuals = y - y_pred_historical
        std_error = np.std(residuals)

        freq = self._infer_frequency(ts[date_col])
        last_date = ts[date_col].max()
        future_dates = pd.date_range(
            start=last_date + freq, periods=periods, freq=freq
        )
        future_x = np.arange(len(ts), len(ts) + periods).astype(float)
        future_y = slope * future_x + intercept

        historical = [
            {
                "date": row[date_col].strftime("%Y-%m-%d"),
                "actual": float(row[value_col]),
                "predicted": float(y_pred_historical[i]),
            }
            for i, (_, row) in enumerate(ts.iterrows())
        ]

        forecast_data = [
            {
                "date": d.strftime("%Y-%m-%d"),
                "predicted": float(future_y[i]),
                "lower": float(future_y[i] - 1.96 * std_error),
                "upper": float(future_y[i] + 1.96 * std_error),
            }
            for i, d in enumerate(future_dates)
        ]

        trend = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
        daily_change = float(slope)
        period_label = self._freq_label(freq)

        return {
            "historical": historical,
            "forecast": forecast_data,
            "stats": {
                "trend": trend,
                "slope_per_period": round(daily_change, 2),
                "period_type": period_label,
                "r_squared": round(float(1 - np.sum(residuals**2) / np.sum((y - np.mean(y))**2)), 4) if np.sum((y - np.mean(y))**2) > 0 else 0,
                "std_error": round(float(std_error), 2),
                "forecast_periods": periods,
            },
        }

    def _infer_frequency(self, dates: pd.Series) -> pd.DateOffset:
        if len(dates) < 2:
            return pd.DateOffset(days=1)
        diffs = dates.diff().dropna()
        median_days = diffs.dt.days.median()
        if median_days >= 28:
            return pd.DateOffset(months=1)
        elif median_days >= 7:
            return pd.DateOffset(weeks=1)
        return pd.DateOffset(days=max(1, int(median_days)))

    def _freq_label(self, freq: pd.DateOffset) -> str:
        if hasattr(freq, 'months') and freq.months:
            return "month"
        elif hasattr(freq, 'weeks') and freq.weeks:
            return "week"
        return "day"
