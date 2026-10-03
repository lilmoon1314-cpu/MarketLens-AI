"""Export reproducible Draft 2020-12 schemas from Pydantic contracts."""

import argparse
import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from .models import (
    AnalysisRequest,
    AnalystInput,
    AnalystOutput,
    PlannerInput,
    PlannerOutput,
    Review,
    SemanticReview,
    VisualizationInput,
    VisualizationOutput,
)
from .statistics import Statistics

AGENT_MODELS = (
    PlannerInput,
    PlannerOutput,
    AnalystInput,
    AnalystOutput,
    VisualizationInput,
    VisualizationOutput,
)
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"


def schema_documents() -> dict[str, dict]:
    """Return a shared bundle and six independently resolvable entry documents."""
    _, bundle = models_json_schema(
        [
            (model, "validation")
            for model in (*AGENT_MODELS, AnalysisRequest, Review, SemanticReview, Statistics)
        ],
    )
    bundle = {"$schema": SCHEMA_URI, "$id": "urn:marketlens:agent-contracts:1.0", **bundle}
    documents = {"agent-contracts.schema.json": bundle}
    for model in AGENT_MODELS:
        documents[f"{model.__name__}.schema.json"] = {
            "$schema": SCHEMA_URI,
            **model.model_json_schema(),
        }
    return documents


def export_schemas(directory: Path) -> None:
    """Write only known schema filenames; leave other directory content untouched."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, schema in schema_documents().items():
        (directory / name).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/schemas"))
    export_schemas(parser.parse_args().output)


if __name__ == "__main__":
    main()
