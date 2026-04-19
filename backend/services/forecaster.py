from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


class Forecaster:
    def forecast(
        self,
        df: pd.DataFrame,
        date_col: str,
        value_col: str,
        periods: int = 30,
    ) -> Dict[str, Any]:
        """Forecast with Prophet when enough history, else linear regression."""
        ts, freq, period_label = self._prepare_series(df, date_col, value_col)
        if len(ts) < 3:
            raise ValueError("Need at least 3 data points for forecasting")

        engine = (getattr(settings, "FORECAST_ENGINE", "prophet") or "prophet").strip().lower()
        min_p = max(3, int(getattr(settings, "FORECAST_PROPHET_MIN_POINTS", 24)))

        if engine == "linear" or len(ts) < min_p:
            return self._forecast_linear(ts, date_col, value_col, periods, freq, period_label)

        try:
            return self._forecast_prophet(ts, date_col, value_col, periods, freq, period_label)
        except Exception as e:
            logger.warning("Prophet forecast failed, using linear fallback: %s", e)
            return self._forecast_linear(ts, date_col, value_col, periods, freq, period_label)

    def _prepare_series(
        self, df: pd.DataFrame, date_col: str, value_col: str
    ) -> Tuple[pd.DataFrame, pd.DateOffset, str]:
        if date_col not in df.columns or value_col not in df.columns:
            raise ValueError(f"Columns {date_col} or {value_col} not found")

        ts = df[[date_col, value_col]].copy()
        ts[date_col] = pd.to_datetime(ts[date_col])
        ts = ts.groupby(date_col, as_index=False)[value_col].sum()
        ts = ts.sort_values(date_col).reset_index(drop=True)
        ts = ts.replace([np.inf, -np.inf], np.nan).dropna(subset=[value_col])
        if len(ts) < 3:
            raise ValueError("Need at least 3 data points for forecasting")

        freq = self._infer_frequency(ts[date_col])
        period_label = self._freq_label(freq)
        return ts, freq, period_label

    def _dateoffset_to_prophet_freq(self, freq: pd.DateOffset) -> str:
        if hasattr(freq, "months") and getattr(freq, "months", None):
            return "MS"
        if hasattr(freq, "weeks") and getattr(freq, "weeks", None):
            return "W-SUN"
        return "D"

    def _forecast_prophet(
        self,
        ts: pd.DataFrame,
        date_col: str,
        value_col: str,
        periods: int,
        freq: pd.DateOffset,
        period_label: str,
    ) -> Dict[str, Any]:
        from prophet import Prophet

        max_rows = int(getattr(settings, "FORECAST_PROPHET_MAX_HISTORY_ROWS", 4000))
        train = ts.rename(columns={date_col: "ds", value_col: "y"}).copy()
        train["ds"] = pd.to_datetime(train["ds"])
        if (train["y"] <= 0).any():
            raise ValueError("Prophet path requires positive y; use linear for non-positive series")
        if len(train) > max_rows:
            train = train.tail(max_rows).reset_index(drop=True)

        pfreq = self._dateoffset_to_prophet_freq(freq)
        m = Prophet(
            interval_width=0.95,
            daily_seasonality="auto",
            weekly_seasonality="auto",
            yearly_seasonality="auto",
        )
        m.fit(train)

        future_df = m.make_future_dataframe(periods=periods, freq=pfreq)
        fc_all = m.predict(future_df)

        last_train = train["ds"].max()
        future_part = fc_all[fc_all["ds"] > last_train].head(periods)
        if len(future_part) < periods:
            future_part = fc_all.tail(periods)

        in_sample = m.predict(train[["ds"]].sort_values("ds")).reset_index(drop=True)
        train_sorted = train.sort_values("ds").reset_index(drop=True)
        if len(in_sample) != len(train_sorted):
            raise RuntimeError("Prophet in-sample length mismatch")

        y = train_sorted["y"].astype(float).values
        yhat = in_sample["yhat"].astype(float).values
        residuals = y - yhat
        std_error = float(np.std(residuals)) if len(residuals) else 0.0
        ss_tot = float(np.sum((y - np.mean(y)) ** 2)) if len(y) else 0.0
        r_squared = (
            float(1.0 - np.sum(residuals**2) / ss_tot) if ss_tot > 1e-12 else 0.0
        )

        yhat_first, yhat_last = float(yhat[0]), float(yhat[-1])
        if yhat_last > yhat_first + 1e-9 * max(1.0, abs(yhat_first)):
            trend = "increasing"
        elif yhat_last < yhat_first - 1e-9 * max(1.0, abs(yhat_first)):
            trend = "decreasing"
        else:
            trend = "flat"
        slope_pp = (yhat_last - yhat_first) / max(1, len(yhat) - 1)

        historical = [
            {
                "date": row["ds"].strftime("%Y-%m-%d"),
                "actual": float(row["y"]),
                "predicted": float(in_sample["yhat"].iloc[i]),
            }
            for i, (_, row) in enumerate(train_sorted.iterrows())
        ]

        forecast_data = [
            {
                "date": row["ds"].strftime("%Y-%m-%d"),
                "predicted": float(row["yhat"]),
                "lower": float(row["yhat_lower"]),
                "upper": float(row["yhat_upper"]),
            }
            for _, row in future_part.iterrows()
        ]

        return {
            "historical": historical,
            "forecast": forecast_data,
            "stats": {
                "trend": trend,
                "slope_per_period": round(float(slope_pp), 4),
                "period_type": period_label,
                "r_squared": round(float(r_squared), 4),
                "std_error": round(std_error, 4),
                "forecast_periods": periods,
            },
        }

    def _forecast_linear(
        self,
        ts: pd.DataFrame,
        date_col: str,
        value_col: str,
        periods: int,
        freq: pd.DateOffset,
        period_label: str,
    ) -> Dict[str, Any]:
        """Simple linear regression forecast (original implementation)."""
        x = np.arange(len(ts)).astype(float)
        y = ts[value_col].values.astype(float)

        slope, intercept = np.polyfit(x, y, 1)
        y_pred_historical = slope * x + intercept

        residuals = y - y_pred_historical
        std_error = float(np.std(residuals))

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

        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = (
            round(float(1 - np.sum(residuals**2) / ss_tot), 4) if ss_tot > 0 else 0.0
        )

        return {
            "historical": historical,
            "forecast": forecast_data,
            "stats": {
                "trend": trend,
                "slope_per_period": round(daily_change, 2),
                "period_type": period_label,
                "r_squared": r_squared,
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
        if median_days >= 7:
            return pd.DateOffset(weeks=1)
        return pd.DateOffset(days=max(1, int(median_days)))

    def _freq_label(self, freq: pd.DateOffset) -> str:
        if hasattr(freq, "months") and freq.months:
            return "month"
        if hasattr(freq, "weeks") and freq.weeks:
            return "week"
        return "day"
