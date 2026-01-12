"""Tests for AXIS camera log retrieval.

This module tests the log parsing functions and AxisLogClient
for retrieving logs from AXIS cameras via the VAPIX API.
"""

import io
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from unifi_camera_manager.axis_logs import (
    LOG_FILE_PATTERNS,
    SIMPLE_LOG_PATTERN,
    SYSLOG_PATTERN,
    AxisLogClient,
    ServerReportMode,
    get_camera_logs,
    parse_log_content,
    parse_log_line,
)
from unifi_camera_manager.config import OnvifCameraConfig
from unifi_camera_manager.models import LogLevel, LogType


class TestSyslogPattern:
    """Tests for SYSLOG_PATTERN regex."""

    def test_matches_full_syslog_format(self) -> None:
        """Test matching a complete AXIS syslog line."""
        line = (
            "2025-01-11T19:47:42.861+00:00 axis-camera "
            "[ INFO    ] systemd[1]: Started Session 42"
        )
        match = SYSLOG_PATTERN.match(line)
        assert match is not None
        groups = match.groupdict()
        assert groups["timestamp"] == "2025-01-11T19:47:42.861+00:00"
        assert groups["hostname"] == "axis-camera"
        assert groups["level"] == "INFO"
        assert groups["process"] == "systemd"
        assert groups["pid"] == "1"
        assert "Started Session 42" in groups["message"]

    def test_matches_without_pid(self) -> None:
        """Test matching syslog line without PID."""
        line = "2025-01-11T19:47:42+00:00 axis-camera [ WARNING ] httpd: Connection timeout"
        match = SYSLOG_PATTERN.match(line)
        assert match is not None
        groups = match.groupdict()
        assert groups["level"] == "WARNING"
        assert groups["process"] == "httpd"
        assert groups["pid"] is None

    def test_matches_various_log_levels(self) -> None:
        """Test matching different log levels."""
        levels = ["INFO", "WARNING", "ERROR", "DEBUG", "NOTICE", "CRITICAL"]
        base = "2025-01-11T12:00:00+00:00 host [ {level}    ] test: message"
        for level in levels:
            line = base.format(level=level)
            match = SYSLOG_PATTERN.match(line)
            assert match is not None
            assert match.groupdict()["level"] == level


class TestSimpleLogPattern:
    """Tests for SIMPLE_LOG_PATTERN regex."""

    def test_matches_simple_format(self) -> None:
        """Test matching a simple log line format."""
        line = "2025-01-11 19:47:42 Simple log message here"
        match = SIMPLE_LOG_PATTERN.match(line)
        assert match is not None
        groups = match.groupdict()
        assert groups["timestamp"] == "2025-01-11 19:47:42"
        assert groups["message"] == "Simple log message here"

    def test_does_not_match_syslog_format(self) -> None:
        """Test that syslog format is not matched by simple pattern."""
        line = "2025-01-11T19:47:42.861+00:00 axis-camera [ INFO    ] test"
        match = SIMPLE_LOG_PATTERN.match(line)
        # Should not match because of ISO timestamp format
        assert match is None


class TestParseLogLine:
    """Tests for parse_log_line function."""

    def test_parse_axis_syslog_format(self) -> None:
        """Test parsing AXIS syslog format."""
        line = "2025-01-11T19:47:42.861+00:00 axis-camera [ INFO    ] httpd[1234]: Request handled"
        entry = parse_log_line(line)
        assert entry is not None
        assert entry.hostname == "axis-camera"
        assert entry.level == LogLevel.INFO
        assert entry.process == "httpd"
        assert entry.pid == 1234
        assert "Request handled" in entry.message
        assert entry.raw == line

    def test_parse_simple_format(self) -> None:
        """Test parsing simple log format."""
        line = "2025-01-11 19:47:42 Simple message"
        entry = parse_log_line(line)
        assert entry is not None
        assert entry.hostname == "unknown"
        assert entry.level == LogLevel.INFO
        assert entry.message == "Simple message"

    def test_parse_empty_line_returns_none(self) -> None:
        """Test that empty lines return None."""
        assert parse_log_line("") is None
        assert parse_log_line("   ") is None

    def test_parse_unparseable_line(self) -> None:
        """Test parsing a line that doesn't match any pattern."""
        line = "random unparseable content"
        entry = parse_log_line(line)
        assert entry is not None
        assert entry.message == line
        assert entry.raw == line
        assert entry.hostname == "unknown"

    def test_parse_warning_level(self) -> None:
        """Test parsing WARNING level."""
        line = "2025-01-11T12:00:00+00:00 host [ WARNING ] proc: warning msg"
        entry = parse_log_line(line)
        assert entry is not None
        assert entry.level == LogLevel.WARNING

    def test_parse_error_level(self) -> None:
        """Test parsing ERROR level."""
        line = "2025-01-11T12:00:00+00:00 host [ ERROR   ] proc: error msg"
        entry = parse_log_line(line)
        assert entry is not None
        assert entry.level == LogLevel.ERROR


class TestParseLogContent:
    """Tests for parse_log_content function."""

    def test_parse_multiple_lines(self, sample_syslog_content: str) -> None:
        """Test parsing multiple log lines."""
        entries = parse_log_content(sample_syslog_content)
        assert len(entries) == 4  # 4 non-empty lines in sample

    def test_parse_empty_content(self) -> None:
        """Test parsing empty content."""
        entries = parse_log_content("")
        assert entries == []

    def test_parse_content_with_empty_lines(self) -> None:
        """Test parsing content with empty lines."""
        content = """2025-01-11 12:00:00 First line

2025-01-11 12:00:01 Second line

"""
        entries = parse_log_content(content)
        assert len(entries) == 2

    def test_parse_preserves_order(self) -> None:
        """Test that parsing preserves line order."""
        content = """2025-01-11 12:00:00 First
2025-01-11 12:00:01 Second
2025-01-11 12:00:02 Third"""
        entries = parse_log_content(content)
        assert entries[0].message == "First"
        assert entries[1].message == "Second"
        assert entries[2].message == "Third"


class TestAxisLogClient:
    """Tests for AxisLogClient class."""

    @pytest.fixture
    def client_config(self) -> OnvifCameraConfig:
        """Create a test configuration."""
        return OnvifCameraConfig(
            address="192.168.1.100",
            username="admin",
            password="secret",
            port=80,
            name="Test Camera",
        )

    def test_base_url(self, client_config: OnvifCameraConfig) -> None:
        """Test base_url property."""
        client = AxisLogClient(client_config)
        assert client.base_url == "http://192.168.1.100:80"

    def test_ensure_connected_raises_when_not_connected(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test _ensure_connected raises when not in context."""
        client = AxisLogClient(client_config)
        with pytest.raises(RuntimeError, match="Client not connected"):
            client._ensure_connected()

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_disconnects(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test async context manager lifecycle."""
        client = AxisLogClient(client_config)
        assert client._client is None

        async with client:
            assert client._client is not None

        assert client._client is None

    def test_find_log_content_system(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test _find_log_content for system logs."""
        client = AxisLogClient(client_config)
        log_files = {
            "syslog": "system log content",
            "access.log": "access content",
            "other.txt": "other content",
        }
        content = client._find_log_content(log_files, LogType.SYSTEM)
        assert "system log content" in content
        assert "access content" not in content

    def test_find_log_content_access(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test _find_log_content for access logs."""
        client = AxisLogClient(client_config)
        log_files = {
            "syslog": "system log content",
            "access.log": "access content",
        }
        content = client._find_log_content(log_files, LogType.ACCESS)
        assert "access content" in content
        assert "system log content" not in content

    def test_find_log_content_all(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test _find_log_content for all logs."""
        client = AxisLogClient(client_config)
        log_files = {
            "syslog": "system content",
            "access.log": "access content",
        }
        content = client._find_log_content(log_files, LogType.ALL)
        assert "system content" in content
        assert "access content" in content

    @pytest.mark.asyncio
    async def test_get_logs_returns_log_report(
        self, client_config: OnvifCameraConfig, sample_syslog_content: str
    ) -> None:
        """Test get_logs returns a LogReport with entries."""
        # Create a tar archive with log content
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
            content_bytes = sample_syslog_content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name="syslog")
            tarinfo.size = len(content_bytes)
            tar.addfile(tarinfo, io.BytesIO(content_bytes))
        tar_content = tar_buffer.getvalue()

        with patch.object(
            AxisLogClient, "get_server_report", new_callable=AsyncMock
        ) as mock_report:
            mock_report.return_value = tar_content

            async with AxisLogClient(client_config) as client:
                report = await client.get_logs(LogType.SYSTEM, max_entries=10)

            assert report.camera_name == "Test Camera"
            assert report.camera_address == "192.168.1.100"
            assert report.log_type == LogType.SYSTEM
            assert len(report.entries) <= 10

    @pytest.mark.asyncio
    async def test_get_system_logs(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test get_system_logs convenience method."""
        with patch.object(AxisLogClient, "get_logs", new_callable=AsyncMock) as mock_logs:
            mock_logs.return_value = MagicMock()

            async with AxisLogClient(client_config) as client:
                await client.get_system_logs(max_entries=50)

            mock_logs.assert_called_once_with(LogType.SYSTEM, 50)

    @pytest.mark.asyncio
    async def test_get_access_logs(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test get_access_logs convenience method."""
        with patch.object(AxisLogClient, "get_logs", new_callable=AsyncMock) as mock_logs:
            mock_logs.return_value = MagicMock()

            async with AxisLogClient(client_config) as client:
                await client.get_access_logs(max_entries=50)

            mock_logs.assert_called_once_with(LogType.ACCESS, 50)

    @pytest.mark.asyncio
    async def test_get_audit_logs(
        self, client_config: OnvifCameraConfig
    ) -> None:
        """Test get_audit_logs convenience method."""
        with patch.object(AxisLogClient, "get_logs", new_callable=AsyncMock) as mock_logs:
            mock_logs.return_value = MagicMock()

            async with AxisLogClient(client_config) as client:
                await client.get_audit_logs(max_entries=50)

            mock_logs.assert_called_once_with(LogType.AUDIT, 50)


class TestGetCameraLogs:
    """Tests for get_camera_logs convenience function."""

    @pytest.mark.asyncio
    async def test_get_camera_logs_uses_context_manager(self) -> None:
        """Test get_camera_logs properly uses AxisLogClient."""
        config = OnvifCameraConfig(
            address="192.168.1.100",
            username="admin",
            password="secret",
        )

        with patch.object(AxisLogClient, "get_logs", new_callable=AsyncMock) as mock_logs:
            mock_logs.return_value = MagicMock()

            with patch.object(AxisLogClient, "__aenter__", new_callable=AsyncMock) as mock_enter:
                mock_enter.return_value = MagicMock(get_logs=mock_logs)
                with patch.object(AxisLogClient, "__aexit__", new_callable=AsyncMock):
                    await get_camera_logs(config, LogType.AUDIT, max_entries=50)


class TestLogFilePatterns:
    """Tests for LOG_FILE_PATTERNS configuration."""

    def test_system_log_patterns(self) -> None:
        """Test system log file patterns."""
        patterns = LOG_FILE_PATTERNS[LogType.SYSTEM]
        assert "syslog" in patterns
        assert "messages" in patterns

    def test_access_log_patterns(self) -> None:
        """Test access log file patterns."""
        patterns = LOG_FILE_PATTERNS[LogType.ACCESS]
        assert "access.log" in patterns

    def test_audit_log_patterns(self) -> None:
        """Test audit log file patterns."""
        patterns = LOG_FILE_PATTERNS[LogType.AUDIT]
        assert "audit.log" in patterns


class TestServerReportMode:
    """Tests for ServerReportMode enum."""

    def test_enum_values(self) -> None:
        """Test ServerReportMode enum values."""
        assert ServerReportMode.TEXT.value == "text"
        assert ServerReportMode.TAR_ALL.value == "tar_all"
        assert ServerReportMode.ZIP.value == "zip"
        assert ServerReportMode.ZIP_WITH_IMAGE.value == "zip_with_image"
