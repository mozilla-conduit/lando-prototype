from __future__ import annotations

import datetime
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Optional,
)

from django.db import models
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy

from lando import settings
from lando.utils import GitPatchHelper, build_patch_for_revision

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = int(os.environ.get("DEFAULT_GRACE_SECONDS", 60 * 2))


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LandingJobStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", gettext_lazy("Submitted")
    IN_PROGRESS = "IN_PROGRESS", gettext_lazy("In progress")
    DEFERRED = "DEFERRED", gettext_lazy("Deferred")
    FAILED = "FAILED", gettext_lazy("Failed")
    LANDED = "LANDED", gettext_lazy("Landed")
    CANCELLED = "CANCELLED", gettext_lazy("Cancelled")


class Revision(BaseModel):
    """
    A representation of a revision in the database.

    Includes a reference to the related Phabricator revision and diff ID if one exists.
    """

    # revision_id and diff_id map to Phabricator IDs (integers).
    revision_id = models.IntegerField(blank=True, null=True, unique=True)

    # diff_id is that of the latest diff on the revision at landing request time. It
    # does not track all diffs.
    diff_id = models.IntegerField(blank=True, null=True)

    # The actual patch.
    patch = models.TextField(blank=True, default="")

    # Patch metadata, such as author, timestamp, etc...
    patch_data = models.JSONField(blank=True, default=dict)

    # A general purpose data field to store arbitrary information about this revision.
    data = models.JSONField(blank=True, default=dict)

    # The commit ID generated by the landing worker, before pushing to remote repo.
    commit_id = models.CharField(max_length=40, null=True, blank=True)

    def __repr__(self) -> str:
        """Return a human-readable representation of the instance."""
        # Add an identifier for the Phabricator revision if it exists.
        phab_identifier = (
            f" [D{self.revision_id}-{self.diff_id}]>" if self.revision_id else ""
        )
        return f"<{self.__class__.__name__}: {self.id}{phab_identifier}>"

    @property
    def patch_string(self) -> str:
        """Return the patch as a UTF-8 encoded string."""
        return self.patch_bytes.decode("utf-8")

    def set_patch(self, raw_diff: str, patch_data: dict[str, str]):
        """Given a raw_diff and patch data, build the patch and store it."""
        self.patch_data = patch_data
        patch = build_patch_for_revision(raw_diff, **self.patch_data)
        self.patch_bytes = patch.encode("utf-8")


class LandingJob(BaseModel):
    status = models.CharField(
        max_length=12,
        choices=LandingJobStatus,
        default=None,
        null=True,  # TODO: should change this to not-nullable
        blank=True,
    )

    # Text describing errors when status != LANDED.
    error = models.TextField(default="", blank=True)

    # Error details in a dictionary format, listing failed merges, etc...
    # E.g. {
    #    "failed_paths": [{"path": "...", "url": "..."}],
    #    "reject_paths": [{"path": "...", "content": "..."}]
    # }
    error_breakdown = models.JSONField(null=True, blank=True, default=dict)

    # LDAP email of the user who requested transplant.
    requester_email = models.CharField(blank=True, default="", max_length=255)

    # Identifier for the most descendent commit created by this landing.
    landed_commit_id = models.TextField(blank=True, default="")

    # Number of attempts made to complete the job.
    attempts = models.IntegerField(default=0)

    # Priority of the job. Higher values are processed first.
    priority = models.IntegerField(default=0)

    # Duration of job from start to finish
    duration_seconds = models.IntegerField(default=0)

    # Identifier of the published commit which this job should land on top of.
    target_commit_hash = models.TextField(blank=True, default="")

    revisions = models.ManyToManyField(Revision)  # TODO: order by index

    target_repo = models.ForeignKey("Repo", on_delete=models.SET_NULL, null=True)

    @classmethod
    def job_queue_query(
        cls,
        repositories: Optional[Iterable[str]] = None,
        grace_seconds: int = DEFAULT_GRACE_SECONDS,
    ) -> QuerySet:
        """Return a query which selects the queued jobs.

        Args:
            repositories (iterable): A list of repository names to use when filtering
                the landing job search query.
            grace_seconds (int): Ignore landing jobs that were submitted after this
                many seconds ago.
        """
        applicable_statuses = (
            LandingJobStatus.SUBMITTED,
            LandingJobStatus.IN_PROGRESS,
            LandingJobStatus.DEFERRED,
        )
        q = cls.objects.filter(status__in=applicable_statuses)

        if repositories:
            q = q.filter(target_repo__in=repositories)

        if grace_seconds:
            now = datetime.datetime.now(datetime.timezone.utc)
            grace_cutoff = now - datetime.timedelta(seconds=grace_seconds)
            q = q.filter(created_at__lt=grace_cutoff)

        # Any `LandingJobStatus.IN_PROGRESS` job is first and there should
        # be a maximum of one (per repository). For
        # `LandingJobStatus.SUBMITTED` jobs, higher priority items come first
        # and then we order by creation time (older first).
        q = q.order_by("-status", "-priority", "created_at")

        return q

    @classmethod
    def next_job(cls, repositories: Optional[Iterable[str]] = None) -> QuerySet:
        """Return a query which selects the next job and locks the row."""
        query = cls.job_queue_query(repositories=repositories)

        # Returned rows should be locked for updating, this ensures the next
        # job can be claimed.
        return query.select_for_update()


def add_job_with_revisions(revisions: list[Revision], **params: Any) -> LandingJob:
    """Creates a new job and associates provided revisions with it."""
    job = LandingJob(**params)
    job.save()
    for revision in revisions:
        job.revisions.add(revision)
    return job


class Repo(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    default_branch = models.CharField(max_length=255, default="main")
    url = models.CharField(max_length=255)
    push_path = models.CharField(max_length=255)
    pull_path = models.CharField(max_length=255)
    is_initialized = models.BooleanField(default=False)

    system_path = models.FilePathField(
        path=settings.REPO_ROOT,
        max_length=255,
        allow_folders=True,
        blank=True,
        default="",
    )

    def _run(self, *args, cwd=None):
        cwd = cwd or self.system_path
        command = ["git"] + list(args)
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        return result

    def initialize(self):
        self.refresh_from_db()

        if self.is_initialized:
            raise

        self.system_path = str(Path(settings.REPO_ROOT) / self.name)
        result = self._run("clone", self.pull_path, self.name, cwd=settings.REPO_ROOT)
        if result.returncode == 0:
            self.is_initialized = True
            self.save()
        else:
            raise Exception(f"{result.returncode}: {result.stderr}")

    def pull(self):
        self._run("pull", "--all", "--prune")

    def reset(self, branch=None):
        self._run("reset", "--hard", branch or self.default_branch)
        self._run("clean", "--force")

    def apply_patch(self, patch_buffer: str):
        patch_helper = GitPatchHelper(patch_buffer)
        self.patch_header = patch_helper.get_header

        # Import the diff to apply the changes then commit separately to
        # ensure correct parsing of the commit message.
        f_msg = tempfile.NamedTemporaryFile(encoding="utf-8", mode="w+")
        f_diff = tempfile.NamedTemporaryFile(encoding="utf-8", mode="w+")
        with f_msg, f_diff:
            patch_helper.write_commit_description(f_msg)
            f_msg.flush()
            patch_helper.write_diff(f_diff)
            f_diff.flush()

            self._run("apply", f_diff.name)

            # Commit using the extracted date, user, and commit desc.
            # --landing_system is provided by the set_landing_system hgext.
            date = patch_helper.get_header("Date")
            user = patch_helper.get_header("From")

            self._run("add", "-A")
            self._run("commit", "--date", date, "--author", user, "--file", f_msg.name)

    def last_commit_id(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def push(self):
        self._run("push")


class Worker(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    is_paused = models.BooleanField(default=False)
    is_stopped = models.BooleanField(default=False)
    ssh_private_key = models.TextField(null=True, blank=True)
    applicable_repos = models.ManyToManyField(Repo)

    throttle_seconds = models.IntegerField(default=10)
    sleep_seconds = models.IntegerField(default=10)

    @property
    def enabled_repos(self) -> list[Repo]:
        return self.applicable_repos.all()
