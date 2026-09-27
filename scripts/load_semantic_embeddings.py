from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.search.semantic import (
    EMBEDDINGS_PATH,
    METADATA_PATH,
)
from tendergraph.search.vector import (
    VectorIndexMetadata,
    load_vector_index,
)

EXPECTED_MODEL = (
    "intfloat/multilingual-e5-small"
)


def main() -> None:
    metadata_payload: dict[
        str,
        Any,
    ] = json.loads(
        Path(
            METADATA_PATH
        ).read_text()
    )

    run_ids = metadata_payload[
        "ingestion_run_ids"
    ]

    if len(run_ids) != 1:
        raise RuntimeError(
            "Expected exactly one "
            "ingestion run"
        )

    if metadata_payload["model"] != (
        EXPECTED_MODEL
    ):
        raise RuntimeError(
            "Unexpected embedding model"
        )

    payload = np.load(
        EMBEDDINGS_PATH
    )

    publication_numbers = payload[
        "publication_numbers"
    ]

    embeddings = payload[
        "embeddings"
    ].astype(
        np.float32,
        copy=False,
    )

    metadata = VectorIndexMetadata(
        model_name=metadata_payload[
            "model"
        ],
        ingestion_run_id=run_ids[0],
        dimensions=int(
            metadata_payload[
                "dimensions"
            ]
        ),
        normalized=bool(
            metadata_payload[
                "normalized"
            ]
        ),
        rows=int(
            metadata_payload[
                "rows"
            ]
        ),
    )

    print(
        "=== PGVECTOR EMBEDDING LOAD ==="
    )
    print(
        f"Model:      "
        f"{metadata.model_name}"
    )
    print(
        f"Run ID:     "
        f"{metadata.ingestion_run_id}"
    )
    print(
        f"Rows:       "
        f"{metadata.rows}"
    )
    print(
        f"Dimensions: "
        f"{metadata.dimensions}"
    )

    settings = DatabaseSettings()

    summary = load_vector_index(
        settings,
        publication_numbers=(
            publication_numbers
        ),
        embeddings=embeddings,
        metadata=metadata,
    )

    print()
    print(
        f"Batch rows:  "
        f"{summary.batch_rows}"
    )
    print(
        f"Inserted:    "
        f"{summary.inserted_rows}"
    )
    print(
        f"Updated:     "
        f"{summary.updated_rows}"
    )
    print(
        f"Database:    "
        f"{summary.database_rows}"
    )
    print(
        "Status:      complete"
    )


if __name__ == "__main__":
    main()
