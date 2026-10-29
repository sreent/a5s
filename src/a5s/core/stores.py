"""Locked storage for the ledger's copies, on whichever cloud a5s runs.

A store writes each object once, locked so that nobody, the team that runs a5s
included, can change or delete it until its retention ends. The store belongs
to assurance, in an account, subscription or project that team can't
administer. A folder stands in for development, and locks nothing.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse


class Exists(Exception):
    """The key was written before, and a store never overwrites."""


class Store(Protocol):
    locked: bool  # whether what it holds can't be changed or deleted

    def put(self, key: str, body: bytes) -> None:
        """Write once, locked. Raises Exists if the key is taken."""

    def get(self, key: str) -> bytes:
        """The first version written under the key. Raises KeyError if there's none."""

    def keys(self, prefix: str) -> dict[str, bool]:
        """Every key under the prefix, and whether anyone tried to replace or delete it."""


class FolderStore:
    """For development: a folder, which locks nothing."""

    locked = False

    def __init__(self, path: Path):
        self.path = path

    def put(self, key: str, body: bytes) -> None:
        target = self.path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "xb") as f:
                f.write(body)
        except FileExistsError as exc:
            raise Exists(key) from exc

    def get(self, key: str) -> bytes:
        try:
            return (self.path / key).read_bytes()
        except FileNotFoundError as exc:
            raise KeyError(key) from exc

    def keys(self, prefix: str) -> dict[str, bool]:
        folder = self.path / prefix
        if not folder.is_dir():
            return {}
        return {p.relative_to(self.path).as_posix(): False
                for p in sorted(folder.rglob("*")) if p.is_file()}


class S3Store:
    """Amazon S3, or any store with S3's object lock, in compliance mode.

    The bucket needs object lock. Writing to a key that's taken adds a version
    beside the locked one, so a5s reads the first version, and reports the rest.
    """

    locked = True

    def __init__(self, bucket: str, prefix: str, retain: timedelta, client: Any = None):
        if client is None:
            import boto3

            client = boto3.client("s3")  # credentials and endpoint from the environment
        self.client, self.bucket, self.prefix, self.retain = client, bucket, prefix, retain

    def put(self, key: str, body: bytes) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.put_object(
                Bucket=self.bucket, Key=self.prefix + key, Body=body, IfNoneMatch="*",
                ObjectLockMode="COMPLIANCE", ObjectLockRetainUntilDate=datetime.now(UTC) + self.retain,
                ChecksumAlgorithm="SHA256",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise Exists(key) from exc
            raise

    def _versions(self, prefix: str) -> Iterator[tuple[str, str, bool]]:
        """Each key's versions, newest first as S3 lists them, and whether each deletes."""
        pages = self.client.get_paginator("list_object_versions").paginate(
            Bucket=self.bucket, Prefix=self.prefix + prefix)
        for page in pages:
            for version in page.get("Versions", []):
                yield version["Key"], version["VersionId"], False
            for marker in page.get("DeleteMarkers", []):
                yield marker["Key"], marker["VersionId"], True

    def get(self, key: str) -> bytes:
        name = self.prefix + key
        versions = [v for k, v, deletes in self._versions(key) if k == name and not deletes]
        if not versions:
            raise KeyError(key)
        return self.client.get_object(Bucket=self.bucket, Key=name, VersionId=versions[-1])["Body"].read()

    def keys(self, prefix: str) -> dict[str, bool]:
        seen: dict[str, list[bool]] = {}
        for name, _, deletes in self._versions(prefix):
            seen.setdefault(name.removeprefix(self.prefix), []).append(deletes)
        return {k: len(marks) > 1 or any(marks) for k, marks in seen.items()}


class AzureBlobStore:
    """Azure Blob Storage, in a container with version-level immutability."""

    locked = True

    def __init__(self, container: Any, prefix: str, retain: timedelta):
        self.container, self.prefix, self.retain = container, prefix, retain

    @classmethod
    def connect(cls, account: str, container: str, prefix: str, retain: timedelta) -> AzureBlobStore:
        from azure.storage.blob import BlobServiceClient

        if conn := os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):  # an emulator, or a key
            service = BlobServiceClient.from_connection_string(conn)
        else:  # the workload's own identity, such as a managed identity
            from azure.identity import DefaultAzureCredential

            service = BlobServiceClient(f"https://{account}.blob.core.windows.net",
                                        credential=DefaultAzureCredential())
        return cls(service.get_container_client(container), prefix, retain)

    def put(self, key: str, body: bytes) -> None:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ImmutabilityPolicy

        policy = ImmutabilityPolicy(expiry_time=datetime.now(UTC) + self.retain, policy_mode="Locked")
        try:
            self.container.upload_blob(self.prefix + key, body, overwrite=False,
                                       immutability_policy=policy)
        except ResourceExistsError as exc:
            raise Exists(key) from exc

    def _listing(self, prefix: str) -> Iterator[Any]:
        return self.container.list_blobs(name_starts_with=self.prefix + prefix,
                                          include=["versions", "deleted"])

    def get(self, key: str) -> bytes:
        name = self.prefix + key
        versions = sorted(b.version_id or "" for b in self._listing(key)
                          if b.name == name and not b.deleted)  # version ids are times
        if not versions:
            raise KeyError(key)
        blob = self.container.get_blob_client(name, version_id=versions[0] or None)
        return blob.download_blob().readall()

    def keys(self, prefix: str) -> dict[str, bool]:
        seen: dict[str, list[bool]] = {}
        for blob in self._listing(prefix):
            seen.setdefault(blob.name.removeprefix(self.prefix), []).append(bool(blob.deleted))
        return {k: len(marks) > 1 or any(marks) for k, marks in seen.items()}


class GcsStore:
    """Google Cloud Storage, in a bucket with object retention enabled."""

    locked = True

    def __init__(self, bucket: Any, prefix: str, retain: timedelta):
        self.bucket, self.prefix, self.retain = bucket, prefix, retain

    @classmethod
    def connect(cls, bucket: str, prefix: str, retain: timedelta) -> GcsStore:
        from google.cloud import storage

        if os.environ.get("STORAGE_EMULATOR_HOST"):
            from google.auth.credentials import AnonymousCredentials

            client = storage.Client(credentials=AnonymousCredentials(), project="emulator")
        else:  # the workload's own identity
            client = storage.Client()
        return cls(client.bucket(bucket), prefix, retain)

    def put(self, key: str, body: bytes) -> None:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(self.prefix + key)
        blob.retention.mode = "Locked"
        blob.retention.retain_until_time = datetime.now(UTC) + self.retain
        try:
            blob.upload_from_string(body, if_generation_match=0)
        except PreconditionFailed as exc:
            raise Exists(key) from exc

    def _listing(self, prefix: str) -> Iterator[Any]:
        return self.bucket.client.list_blobs(self.bucket, prefix=self.prefix + prefix, versions=True)

    def get(self, key: str) -> bytes:
        name = self.prefix + key
        generations = sorted(b.generation for b in self._listing(key) if b.name == name)
        if not generations:
            raise KeyError(key)
        return self.bucket.blob(name, generation=generations[0]).download_as_bytes()

    def keys(self, prefix: str) -> dict[str, bool]:
        seen: dict[str, int] = {}
        for blob in self._listing(prefix):
            name = blob.name.removeprefix(self.prefix)
            seen[name] = seen.get(name, 0) + 1
        return {k: n > 1 for k, n in seen.items()}


def store_from_url(url: str, retain: timedelta) -> Store:
    """s3://bucket/prefix, azure://account/container/prefix, gs://bucket/prefix, or file:///folder."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    def prefix(p: str) -> str:
        return f"{p}/" if p else ""

    if parsed.scheme == "file":
        return FolderStore(Path(parsed.path))
    if parsed.scheme == "s3":
        return S3Store(parsed.netloc, prefix(path), retain)
    if parsed.scheme == "azure":
        container, _, rest = path.partition("/")
        return AzureBlobStore.connect(parsed.netloc, container, prefix(rest), retain)
    if parsed.scheme == "gs":
        return GcsStore.connect(parsed.netloc, prefix(path), retain)
    raise ValueError(f"a5s can't keep copies in {url}: use s3://, azure://, gs:// or file://")
