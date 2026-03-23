from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd


class RelationDetector:
    def detect_relations(
        self,
        datasets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find shared column names across multiple datasets."""
        if len(datasets) < 2:
            return []

        relations = []

        for i in range(len(datasets)):
            for j in range(i + 1, len(datasets)):
                ds_a = datasets[i]
                ds_b = datasets[j]

                schema_a = ds_a.get("schema", {})
                schema_b = ds_b.get("schema", {})

                cols_a = set(ds_a.get("columns", []))
                cols_b = set(ds_b.get("columns", []))

                shared = cols_a & cols_b

                for col in shared:
                    relation = {
                        "source_dataset_id": ds_a["id"],
                        "source_dataset_name": ds_a["name"],
                        "target_dataset_id": ds_b["id"],
                        "target_dataset_name": ds_b["name"],
                        "source_column": col,
                        "target_column": col,
                        "relation_type": "auto_detected",
                        "column_type": self._get_column_type(col, schema_a),
                    }
                    relations.append(relation)

        return relations

    def _get_column_type(self, col: str, schema: Dict) -> str:
        for type_key in ["date_columns", "revenue_columns", "category_columns", "numeric_columns"]:
            if col in schema.get(type_key, []):
                return type_key.replace("_columns", "")
        return "unknown"
