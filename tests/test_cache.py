"""Tests for local file caching utilities.

Covers:
- ``src.data.cache.get_cache_path``: raw vs processed path selection.
- ``src.data.cache.is_cached``: existence and non-empty checks.
- ``src.data.cache.validate_checksum``: MD5 verification.
- ``src.data.cache.ensure_directory``: directory creation.
"""

import hashlib
from pathlib import Path

from src.data.cache import ensure_directory, get_cache_path, is_cached, validate_checksum


# ---------------------------------------------------------------------------
# get_cache_path tests
# ---------------------------------------------------------------------------


class TestGetCachePath:
    """Tests for :func:`src.data.cache.get_cache_path`."""

    def test_pbf_suffix_uses_raw_dir(self) -> None:
        """PBF files should be stored in RAW_DIR."""
        path = get_cache_path("kanto", ".osm.pbf")
        assert "raw" in str(path)
        assert path.name == "kanto-latest.osm.pbf"

    def test_other_suffix_uses_processed_dir(self) -> None:
        """Non-PBF files should be stored in PROCESSED_DIR."""
        path = get_cache_path("kanto", ".parquet")
        assert "processed" in str(path)
        assert path.name == "kanto.parquet"

    def test_returns_path_instance(self) -> None:
        """Return type must be a Path."""
        result = get_cache_path("japan", ".osm.pbf")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# is_cached tests
# ---------------------------------------------------------------------------


class TestIsCached:
    """Tests for :func:`src.data.cache.is_cached`."""

    def test_existing_nonempty_file(self, tmp_path: Path) -> None:
        """Non-empty file should be considered cached."""
        f = tmp_path / "test.pbf"
        f.write_bytes(b"data")
        assert is_cached(f) is True

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file should not be considered cached."""
        f = tmp_path / "missing.pbf"
        assert is_cached(f) is False

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty file (0 bytes) should not be considered cached."""
        f = tmp_path / "empty.pbf"
        f.write_bytes(b"")
        assert is_cached(f) is False

    def test_directory_not_cached(self, tmp_path: Path) -> None:
        """A directory path should not be considered cached."""
        assert is_cached(tmp_path) is False


# ---------------------------------------------------------------------------
# validate_checksum tests
# ---------------------------------------------------------------------------


class TestValidateChecksum:
    """Tests for :func:`src.data.cache.validate_checksum`."""

    def test_valid_checksum(self, tmp_path: Path) -> None:
        """Correct MD5 should return True."""
        content = b"hello world"
        f = tmp_path / "test.dat"
        f.write_bytes(content)
        expected_md5 = hashlib.md5(content).hexdigest()
        assert validate_checksum(f, expected_md5) is True

    def test_invalid_checksum(self, tmp_path: Path) -> None:
        """Incorrect MD5 should return False."""
        f = tmp_path / "test.dat"
        f.write_bytes(b"hello world")
        assert validate_checksum(f, "0000000000000000") is False

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent file should return False."""
        f = tmp_path / "missing.dat"
        assert validate_checksum(f, "abc123") is False

    def test_case_insensitive_md5(self, tmp_path: Path) -> None:
        """MD5 comparison should be case-insensitive."""
        content = b"test data"
        f = tmp_path / "test.dat"
        f.write_bytes(content)
        expected_md5 = hashlib.md5(content).hexdigest().upper()
        assert validate_checksum(f, expected_md5) is True


# ---------------------------------------------------------------------------
# ensure_directory tests
# ---------------------------------------------------------------------------


class TestEnsureDirectory:
    """Tests for :func:`src.data.cache.ensure_directory`."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Should create the directory if it does not exist."""
        new_dir = tmp_path / "subdir" / "nested"
        ensure_directory(new_dir)
        assert new_dir.exists()

    def test_creates_parent_for_file_path(self, tmp_path: Path) -> None:
        """When given a file path, should create the parent directory."""
        file_path = tmp_path / "new_parent" / "test.pbf"
        ensure_directory(file_path)
        assert file_path.parent.exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Should not raise if the directory already exists."""
        ensure_directory(tmp_path)
        ensure_directory(tmp_path)
