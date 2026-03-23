from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.models import Dataset, DatasetRelation, Upload
from services.relation_detector import RelationDetector

router = APIRouter(prefix="/api/relations", tags=["relations"])

detector = RelationDetector()


@router.get("/detect")
def detect_relations(db: Session = Depends(get_db)):
    """Auto-detect relations across all datasets."""
    datasets_with_meta = []

    datasets = db.query(Dataset).all()
    for ds in datasets:
        schema = json.loads(ds.schema_json) if ds.schema_json else {}
        all_cols = []
        for key in ["date_columns", "revenue_columns", "category_columns", "numeric_columns", "text_columns"]:
            all_cols.extend(schema.get(key, []))

        datasets_with_meta.append({
            "id": ds.id,
            "name": ds.name,
            "columns": all_cols,
            "schema": schema,
        })

    relations = detector.detect_relations(datasets_with_meta)

    db.query(DatasetRelation).filter(
        DatasetRelation.relation_type == "auto_detected"
    ).delete()

    for rel in relations:
        db.add(DatasetRelation(
            source_dataset_id=rel["source_dataset_id"],
            target_dataset_id=rel["target_dataset_id"],
            source_column=rel["source_column"],
            target_column=rel["target_column"],
            relation_type="auto_detected",
        ))

    db.commit()

    return {"relations": relations, "total": len(relations)}


@router.get("/")
def list_relations(db: Session = Depends(get_db)):
    """List all detected and user-defined relations."""
    relations = db.query(DatasetRelation).all()

    result = []
    for rel in relations:
        source = db.query(Dataset).filter(Dataset.id == rel.source_dataset_id).first()
        target = db.query(Dataset).filter(Dataset.id == rel.target_dataset_id).first()
        result.append({
            "id": rel.id,
            "source_dataset_id": rel.source_dataset_id,
            "source_dataset_name": source.name if source else "Unknown",
            "target_dataset_id": rel.target_dataset_id,
            "target_dataset_name": target.name if target else "Unknown",
            "source_column": rel.source_column,
            "target_column": rel.target_column,
            "relation_type": rel.relation_type,
            "created_at": rel.created_at.isoformat(),
        })

    return result
