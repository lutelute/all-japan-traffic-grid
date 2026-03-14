"""Tests for Geofabrik PBF download manager.

Covers:
- ``src.data.downloader.download_pbf``: region validation, caching, retry
  logic, and successful download flow.
- ``src.data.downloader.fetch_md5``: MD5 checksum retrieval.

All network I/O is mocked — no actual HTTP requests are made.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.data.downloader import _stream_download, download_pbf, fetch_md5


# ---------------------------------------------------------------------------
# download_pbf tests
# ---------------------------------------------------------------------------


class TestDownloadPbf:
    """Tests for :func:`src.data.downloader.download_pbf`."""

    def test_unknown_region_raises(self) -> None:
        """Unknown region must raise ValueError."""
        with pytest.raises(ValueError, match="Unknown region"):
            download_pbf(region="nonexistent")

    def test_cached_file_skips_download(self, tmp_path: Path) -> None:
        """When cached file exists, download should be skipped."""
        with (
            patch("src.data.downloader.get_cache_path") as mock_cache_path,
            patch("src.data.downloader.is_cached", return_value=True),
        ):
            cached = tmp_path / "kanto-latest.osm.pbf"
            cached.write_bytes(b"fake pbf data")
            mock_cache_path.return_value = cached

            result = download_pbf(region="kanto", force=False)
            assert result == cached

    def test_force_redownload(self, tmp_path: Path) -> None:
        """When force=True, should download even if cached."""
        with (
            patch("src.data.downloader.get_cache_path") as mock_cache_path,
            patch("src.data.downloader.is_cached", return_value=True),
            patch("src.data.downloader.ensure_directory"),
            patch("src.data.downloader._stream_download") as mock_stream,
        ):
            dest = tmp_path / "kanto-latest.osm.pbf"
            mock_cache_path.return_value = dest

            download_pbf(region="kanto", force=True)
            mock_stream.assert_called_once()

    def test_download_failure_raises_runtime_error(self, tmp_path: Path) -> None:
        """After exhausting retries, RuntimeError must be raised."""
        import requests

        with (
            patch("src.data.downloader.get_cache_path") as mock_cache_path,
            patch("src.data.downloader.is_cached", return_value=False),
            patch("src.data.downloader.ensure_directory"),
            patch(
                "src.data.downloader._stream_download",
                side_effect=requests.RequestException("timeout"),
            ),
            patch("src.data.downloader.time.sleep"),
        ):
            mock_cache_path.return_value = tmp_path / "kanto-latest.osm.pbf"

            with pytest.raises(RuntimeError, match="Failed to download"):
                download_pbf(region="kanto")


# ---------------------------------------------------------------------------
# fetch_md5 tests
# ---------------------------------------------------------------------------


class TestFetchMd5:
    """Tests for :func:`src.data.downloader.fetch_md5`."""

    def test_successful_fetch(self) -> None:
        """Should parse MD5 from Geofabrik .md5 format."""
        mock_response = MagicMock()
        mock_response.text = "abc123def456  kanto-latest.osm.pbf\n"
        mock_response.raise_for_status = MagicMock()

        with patch("src.data.downloader.requests.get", return_value=mock_response):
            result = fetch_md5("https://download.geofabrik.de/test.osm.pbf")
            assert result == "abc123def456"

    def test_network_failure_returns_none(self) -> None:
        """Network errors should return None, not raise."""
        import requests

        with patch(
            "src.data.downloader.requests.get",
            side_effect=requests.RequestException("fail"),
        ):
            result = fetch_md5("https://download.geofabrik.de/test.osm.pbf")
            assert result is None


# ---------------------------------------------------------------------------
# _stream_download tests
# ---------------------------------------------------------------------------


class TestStreamDownload:
    """Tests for :func:`src.data.downloader._stream_download`."""

    def test_writes_content_to_dest(self, tmp_path: Path) -> None:
        """Should write streamed content to destination file."""
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "5"}
        mock_response.iter_content.return_value = [b"hello"]
        mock_response.raise_for_status = MagicMock()

        dest = tmp_path / "test.osm.pbf"

        with patch("src.data.downloader.requests.get", return_value=mock_response):
            _stream_download(
                "https://example.com/test.osm.pbf",
                dest,
                attempt=1,
            )

        assert dest.exists()
        assert dest.read_bytes() == b"hello"
