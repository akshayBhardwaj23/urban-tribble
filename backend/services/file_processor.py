from pathlib import Path

import pandas as pd


class FileProcessor:
    READERS = {
        ".csv": lambda p: pd.read_csv(p),
        ".tsv": lambda p: pd.read_csv(p, sep="\t"),
        ".xlsx": lambda p: pd.read_excel(p, engine="openpyxl"),
        ".xls": lambda p: pd.read_excel(p),
    }

    def read(self, file_path: str) -> pd.DataFrame:
        ext = Path(file_path).suffix.lower()
        reader = self.READERS.get(ext)
        if not reader:
            raise ValueError(f"Unsupported file type: {ext}")
        df = reader(file_path)
        if df.empty:
            raise ValueError("File is empty or has no data rows")
        return df

    def preview(self, df: pd.DataFrame, n: int = 20) -> dict:
        preview_df = df.head(n)
        return {
            "columns": list(df.columns),
            "rows": preview_df.where(preview_df.notna(), None)
            .to_dict(orient="records"),
            "total_rows": len(df),
            "total_columns": len(df.columns),
        }
