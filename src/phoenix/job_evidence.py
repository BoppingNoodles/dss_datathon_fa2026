"""Reuse posting-only extraction without caching anyone's qualification answers."""

from functools import lru_cache

from .models import Job
from .qualifications import with_qualification_evidence


@lru_cache(maxsize=2048)
def _posting_evidence(payload: str) -> Job:
    return with_qualification_evidence(Job.model_validate_json(payload))


def prepared_job(job: Job) -> Job:
    # Content, rather than job ID, invalidates extraction when a posting changes.
    # Copies keep a later consumer from mutating the shared posting-only result.
    return _posting_evidence(job.model_dump_json()).model_copy(deep=True)
