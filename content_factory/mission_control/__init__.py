"""Local-only review dashboard for generated Shorts Factory jobs."""

from .approvals import ApprovalStore
from .job_index import JobRecord, find_job, scan_jobs

__all__ = ["ApprovalStore", "JobRecord", "create_server", "find_job", "scan_jobs"]


def create_server(*args, **kwargs):
    """Load the HTTP application lazily to keep export helpers independent."""
    from .app import create_server as _create_server

    return _create_server(*args, **kwargs)
