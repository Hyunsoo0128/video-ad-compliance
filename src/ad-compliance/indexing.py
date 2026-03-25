"""Step 0 – Index creation (§3).

Creates a dual-model index (Marengo 3.0 + Pegasus 1.2) with visual+audio.
Index creation is idempotent: returns existing index if name matches.
"""

from __future__ import annotations

import logging

from twelvelabs.indexes.types import IndexesCreateRequestModelsItem

from .client import get_client, retry_call
from .config import INDEX_NAME

log = logging.getLogger(__name__)


def get_or_create_index(client=None, index_name: str = INDEX_NAME) -> str:
    """Return index_id, creating the index if it doesn't exist."""
    client = client or get_client()

    # Check existing indexes
    indexes = retry_call(client.indexes.list)
    for idx in indexes:
        if idx.index_name == index_name:
            log.info("Using existing index %s (%s)", index_name, idx.id)
            return idx.id

    # Create new dual-model index
    index = retry_call(
        client.indexes.create,
        index_name=index_name,
        models=[
            IndexesCreateRequestModelsItem(
                model_name="marengo3.0",
                model_options=["visual", "audio"],
            ),
            IndexesCreateRequestModelsItem(
                model_name="pegasus1.2",
                model_options=["visual", "audio"],
            ),
        ],
    )
    log.info("Created index %s (%s)", index_name, index.id)
    return index.id
