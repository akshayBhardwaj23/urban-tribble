"""Read spreadsheet/CSV files with format coverage and sheet helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class FileProcessor:
    def read(
        self,
        file_path: str,
        *,
        sheet_name: str | int | None = None,
        header_row: int | None = None,
        declared_ext: str | None = None,
    ) -> pd.DataFrame:
        path = Path(file_path)
        declared = (declared_ext or path.suffix).lower()
        try:
            from services.file_validation import resolve_reader_ext

            ext = resolve_reader_ext(path, declared)
        except Exception:
            ext = declared
        if ext == ".csv":
            df = pd.read_csv(file_path, index_col=False, header=header_row if header_row is not None else 0)
        elif ext == ".tsv":
            df = pd.read_csv(
                file_path,
                sep="\t",
                index_col=False,
                header=header_row if header_row is not None else 0,
            )
        elif ext in (".xlsx", ".xlsm"):
            df = self._read_excel(
                file_path, engine="openpyxl", sheet_name=sheet_name, header_row=header_row
            )
        elif ext == ".xls":
            df = self._read_excel(
                file_path, engine="xlrd", sheet_name=sheet_name, header_row=header_row
            )
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        if df.empty:
            raise ValueError("File is empty or has no data rows")
        df = self._strip_trailing_total_rows(df)
        return df

    def _read_excel(
        self,
        file_path: str,
        *,
        engine: str,
        sheet_name: str | int | None,
        header_row: int | None,
    ) -> pd.DataFrame:
        header = header_row if header_row is not None else 0
        if sheet_name is not None:
            return pd.read_excel(file_path, engine=engine, sheet_name=sheet_name, header=header)

        # Auto-pick the best data sheet when multiple exist
        sheets = pd.read_excel(file_path, engine=engine, sheet_name=None, header=None)
        if not isinstance(sheets, dict):
            df = pd.read_excel(file_path, engine=engine, header=header)
            return df
        if len(sheets) == 1:
            name = next(iter(sheets))
            if header_row is not None:
                return pd.read_excel(file_path, engine=engine, sheet_name=name, header=header)
            best_header = self.detect_header_row(sheets[name])
            return pd.read_excel(
                file_path, engine=engine, sheet_name=name, header=best_header
            )

        scored = []
        for name, raw in sheets.items():
            score = self.score_sheet_as_table(raw)
            hdr = header_row if header_row is not None else self.detect_header_row(raw)
            scored.append((score, name, hdr))
        scored.sort(key=lambda x: -x[0])
        _, best_name, best_hdr = scored[0]
        return pd.read_excel(
            file_path, engine=engine, sheet_name=best_name, header=best_hdr
        )

    def list_sheets(self, file_path: str) -> list[dict[str, Any]]:
        ext = Path(file_path).suffix.lower()
        if ext not in (".xlsx", ".xls"):
            return []
        engine = "openpyxl" if ext == ".xlsx" else "xlrd"
        sheets = pd.read_excel(file_path, engine=engine, sheet_name=None, header=None)
        if not isinstance(sheets, dict):
            return []
        out = []
        for name, raw in sheets.items():
            out.append(
                {
                    "name": str(name),
                    "score": self.score_sheet_as_table(raw),
                    "rows": int(len(raw)),
                    "cols": int(raw.shape[1]) if len(raw) else 0,
                    "suggested_header_row": self.detect_header_row(raw),
                }
            )
        out.sort(key=lambda x: -x["score"])
        return out

    def score_sheet_as_table(self, raw: pd.DataFrame) -> float:
        """Higher score = more likely a real data table vs cover page."""
        if raw is None or raw.empty:
            return 0.0
        rows, cols = raw.shape
        if rows < 2 or cols < 2:
            return 0.0
        # Prefer sheets with many non-null cells and mixed types in body
        non_null = float(raw.notna().sum().sum())
        density = non_null / max(rows * cols, 1)
        score = density * 10 + min(rows, 500) / 50 + min(cols, 40) / 4
        # Penalize sheets whose first cell looks like a title-only cover
        first = raw.iloc[0].dropna().astype(str).tolist()
        if len(first) <= 1 and rows < 5:
            score *= 0.3
        return float(score)

    def detect_header_row(self, raw: pd.DataFrame, max_scan: int = 10) -> int:
        """Pick the row most likely to be column headers among the first N."""
        if raw is None or raw.empty:
            return 0
        best_i = 0
        best_score = -1.0
        scan = min(max_scan, len(raw))
        for i in range(scan):
            row = raw.iloc[i]
            vals = [str(v).strip() for v in row.tolist() if pd.notna(v) and str(v).strip()]
            if len(vals) < 2:
                continue
            # Headers are usually unique strings, not mostly numeric
            unique_ratio = len(set(vals)) / len(vals)
            numericish = sum(1 for v in vals if self._looks_numeric(v)) / len(vals)
            score = unique_ratio * 2 - numericish + len(vals) / 20
            if score > best_score:
                best_score = score
                best_i = i
        return best_i

    def _looks_numeric(self, v: str) -> bool:
        s = v.replace(",", "").replace("$", "").replace("%", "").strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1]
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _strip_trailing_total_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop trailing GRAND TOTAL / Total / Subtotal summary rows."""
        if df.empty:
            return df
        total_pat = re_total()
        drop_idx = []
        # Scan last 5 rows
        for idx in list(df.index)[-5:]:
            row = df.loc[idx]
            text_vals = [
                str(v).strip().lower()
                for v in row.tolist()
                if pd.notna(v) and str(v).strip()
            ]
            if not text_vals:
                continue
            # If first non-null cell matches total label, drop
            first = text_vals[0]
            if total_pat.match(first) or first in ("total", "grand total", "subtotal", "sum"):
                drop_idx.append(idx)
                continue
            # Or any cell is exactly a total label and most others numeric
            if any(total_pat.match(t) for t in text_vals):
                drop_idx.append(idx)
        if drop_idx:
            df = df.drop(index=drop_idx)
        return df

    def preview(self, df: pd.DataFrame, n: int = 20) -> dict:
        preview_df = df.head(n)
        return {
            "columns": list(df.columns),
            "rows": preview_df.where(preview_df.notna(), None).to_dict(orient="records"),
            "total_rows": len(df),
            "total_columns": len(df.columns),
        }


def re_total():
    import re

    return re.compile(r"^(grand\s*)?total$|^subtotal$|^sum$", re.I)
