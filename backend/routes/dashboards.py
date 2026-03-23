import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Dataset, Upload

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _load_cleaned_df(upload: Upload) -> pd.DataFrame:
    parquet_path = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
    if not parquet_path.exists():
        raise HTTPException(404, "Cleaned data file not found")
    return pd.read_parquet(str(parquet_path))


@router.get("/dataset/{dataset_id}")
def get_dashboard_data(dataset_id: str, db: Session = Depends(get_db)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    upload = db.query(Upload).filter(Upload.id == dataset.upload_id).first()
    if not upload:
        raise HTTPException(404, "Upload not found")

    df = _load_cleaned_df(upload)
    metadata = json.loads(dataset.schema_json) if dataset.schema_json else {}

    charts = []

    date_cols = metadata.get("date_columns", [])
    revenue_cols = metadata.get("revenue_columns", [])
    category_cols = metadata.get("category_columns", [])
    numeric_cols = metadata.get("numeric_columns", [])

    for date_col in date_cols:
        for rev_col in revenue_cols:
            if date_col in df.columns and rev_col in df.columns:
                grouped = df.groupby(date_col)[rev_col].sum().reset_index()
                grouped = grouped.sort_values(date_col)
                chart_data = []
                for _, row in grouped.iterrows():
                    val = row[date_col]
                    if pd.api.types.is_datetime64_any_dtype(type(val)):
                        val = val.strftime("%Y-%m-%d")
                    chart_data.append({"x": str(val), "y": float(row[rev_col])})

                charts.append({
                    "id": f"{rev_col}_over_{date_col}",
                    "title": f"{rev_col.replace('_', ' ').title()} Over Time",
                    "type": "line",
                    "x_label": date_col,
                    "y_label": rev_col,
                    "data": chart_data,
                })

    for cat_col in category_cols:
        for rev_col in revenue_cols:
            if cat_col in df.columns and rev_col in df.columns:
                grouped = df.groupby(cat_col)[rev_col].sum().reset_index()
                grouped = grouped.sort_values(rev_col, ascending=False)
                chart_data = [
                    {"name": str(row[cat_col]), "value": float(row[rev_col])}
                    for _, row in grouped.iterrows()
                ]
                charts.append({
                    "id": f"{rev_col}_by_{cat_col}",
                    "title": f"{rev_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                    "type": "bar",
                    "data": chart_data,
                })

    for cat_col in category_cols[:1]:
        if cat_col in df.columns:
            counts = df[cat_col].value_counts().head(10)
            chart_data = [
                {"name": str(name), "value": int(count)}
                for name, count in counts.items()
            ]
            charts.append({
                "id": f"{cat_col}_distribution",
                "title": f"{cat_col.replace('_', ' ').title()} Distribution",
                "type": "pie",
                "data": chart_data,
            })

    for date_col in date_cols:
        for num_col in numeric_cols:
            if date_col in df.columns and num_col in df.columns:
                grouped = df.groupby(date_col)[num_col].sum().reset_index()
                grouped = grouped.sort_values(date_col)
                chart_data = []
                for _, row in grouped.iterrows():
                    val = row[date_col]
                    if pd.api.types.is_datetime64_any_dtype(type(val)):
                        val = val.strftime("%Y-%m-%d")
                    chart_data.append({"x": str(val), "y": float(row[num_col])})

                charts.append({
                    "id": f"{num_col}_over_{date_col}",
                    "title": f"{num_col.replace('_', ' ').title()} Over Time",
                    "type": "area",
                    "x_label": date_col,
                    "y_label": num_col,
                    "data": chart_data,
                })

    return {"dataset_id": dataset_id, "charts": charts}
