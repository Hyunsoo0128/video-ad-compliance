"""Step 1 – Ingestion: upload & index a video (§4).

Submits a video to TwelveLabs for indexing and waits for completion.
Skips re-indexing if a video with the same filename already exists.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .client import get_client, retry_call

log = logging.getLogger(__name__)


def ingest_video(
    index_id: str,
    *,
    url: str | None = None,
    file_path: str | None = None,
    client=None,
) -> str:
    """Index a video and return its video_id.

    Provide either *url* (S3 presigned URL) or *file_path* (local file).
    Skips re-indexing if a video with the same filename already exists.
    """
    client = client or get_client()

    # 중복 체크: 같은 filename이면 기존 video_id 재사용
    source_name = (Path(file_path).name if file_path
                   else url.rstrip("/").split("/")[-1] if url
                   else None)
    if source_name:
        for v in client.indexes.videos.list(index_id=index_id):
            meta = getattr(v, "system_metadata", None)
            if meta and getattr(meta, "filename", None) == source_name:
                log.info("Video already indexed (filename=%s) – video_id=%s",
                         source_name, v.id)
                return v.id

    kwargs: dict = {"index_id": index_id}
    if url:
        kwargs["video_url"] = url
    elif file_path:
        kwargs["video_file"] = open(file_path, "rb")
    else:
        raise ValueError("Provide url or file_path")

    log.info("Submitting video for indexing (index=%s)", index_id)
    task = retry_call(client.tasks.create, **kwargs)
    log.info("Task %s created – waiting for indexing…", task.id)

    result = client.tasks.wait_for_done(task.id, sleep_interval=5)

    if result.status != "ready":
        raise RuntimeError(f"Indexing failed: {result.status}")

    video_id = result.video_id
    log.info("Indexing complete – video_id=%s", video_id)
    return video_id
