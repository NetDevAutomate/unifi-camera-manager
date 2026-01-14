"""AXIS camera log retrieval via VAPIX API.

This module provides functionality to retrieve system logs, access logs,
and audit logs from AXIS cameras using the VAPIX HTTP API.

The logs are retrieved via the /axis-cgi/serverreport.cgi endpoint
which provides comprehensive system reports including log data.
"""

import io
import re
import tarfile
from collections.abc import AsyncIterator
from datetime import datetime
from enum import Enum

import httpx

from .config import OnvifCameraConfig
from .logging_config import log_debug
from .models import LogEntry, LogLevel, LogReport, LogType


def _parse_log_level(level_str: str) -> LogLevel:
    """Convert a log level string to LogLevel enum.

    Args:
        level_str: Log level string from syslog (e.g., "INFO", "WARNING").

    Returns:
        Matching LogLevel enum value, or LogLevel.INFO as default.
    """
    level_lower = level_str.lower()
    try:
        return LogLevel(level_lower)
    except ValueError:
        # Map common syslog levels to our enum
        mappings = {
            "warn": LogLevel.WARNING,
            "err": LogLevel.ERROR,
            "crit": LogLevel.CRITICAL,
            "emerg": LogLevel.EMERGENCY,
        }
        return mappings.get(level_lower, LogLevel.INFO)


class ServerReportMode(str, Enum):
    """Server report output modes."""

    TEXT = "text"
    TAR_ALL = "tar_all"
    ZIP = "zip"
    ZIP_WITH_IMAGE = "zip_with_image"


# Log file patterns in the server report tarball
LOG_FILE_PATTERNS = {
    LogType.SYSTEM: ["syslog", "messages", "kern.log"],
    LogType.ACCESS: ["access.log", "httpd/access"],
    LogType.AUDIT: ["audit.log", "audit/audit"],
}

# Regex pattern for parsing AXIS syslog format
# Example: 2026-01-11T19:47:42.861+00:00 axis-b8a44f9c81a3 [ INFO    ] systemd[1]: message
SYSLOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)\s+"
    r"(?P<hostname>\S+)\s+"
    r"\[\s*(?P<level>\w+)\s*\]\s+"
    r"(?:(?P<process>[\w\-]+)(?:\[(?P<pid>\d+)\])?:\s*)?"
    r"(?P<message>.*)$"
)

# Alternative pattern for simpler log formats
SIMPLE_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<message>.*)$"
)


def parse_log_line(line: str) -> LogEntry | None:
    """Parse a single log line into a LogEntry.

    Args:
        line: Raw log line string.

    Returns:
        LogEntry if parsing successful, None otherwise.
    """
    line = line.strip()
    if not line:
        return None

    # Try AXIS syslog format first
    match = SYSLOG_PATTERN.match(line)
    if match:
        groups = match.groupdict()
        try:
            timestamp = datetime.fromisoformat(groups["timestamp"])
        except ValueError:
            timestamp = datetime.now()

        return LogEntry(
            timestamp=timestamp,
            hostname=groups["hostname"],
            level=_parse_log_level(groups["level"]),
            process=groups.get("process") or "",
            pid=int(groups["pid"]) if groups.get("pid") else None,
            message=groups["message"],
            raw=line,
        )

    # Try simple format
    match = SIMPLE_LOG_PATTERN.match(line)
    if match:
        groups = match.groupdict()
        try:
            timestamp = datetime.strptime(groups["timestamp"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            timestamp = datetime.now()

        return LogEntry(
            timestamp=timestamp,
            hostname="unknown",
            level=LogLevel.INFO,
            message=groups["message"],
            raw=line,
        )

    # Return as unparsed entry
    return LogEntry(
        timestamp=datetime.now(),
        hostname="unknown",
        level=LogLevel.INFO,
        message=line,
        raw=line,
    )


def parse_log_content(content: str, log_type: LogType = LogType.SYSTEM) -> list[LogEntry]:
    """Parse log content into a list of LogEntry objects.

    Args:
        content: Raw log content string.
        log_type: Type of log being parsed.

    Returns:
        List of parsed LogEntry objects.
    """
    entries: list[LogEntry] = []
    for line in content.splitlines():
        entry = parse_log_line(line)
        if entry:
            entries.append(entry)
    return entries


class AxisLogClient:
    """Client for retrieving logs from AXIS cameras via VAPIX API.

    This client uses the /axis-cgi/serverreport.cgi endpoint to retrieve
    system logs, access logs, and audit logs from AXIS cameras.

    Attributes:
        config: ONVIF camera configuration with credentials.
        timeout: HTTP request timeout in seconds.

    Example:
        >>> config = OnvifCameraConfig(
        ...     address="192.168.1.10", username="admin", password="secret"
        ... )
        >>> async with AxisLogClient(config) as client:
        ...     logs = await client.get_system_logs()
        ...     for entry in logs.entries[:5]:
        ...         print(f"{entry.timestamp}: {entry.message}")
    """

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the AXIS log client.

        Args:
            config: Camera configuration with IP and credentials.
            timeout: HTTP request timeout in seconds.
        """
        self.config = config
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AxisLogClient":
        """Async context manager entry."""
        # Use AXIS admin credentials for VAPIX API access
        # AXIS cameras require Digest authentication
        username, password = self.config.get_axis_credentials()
        is_axis_creds = self.config.axis_username and self.config.axis_password
        log_debug(
            f"AxisLogClient connecting to {self.config.ip_address} "
            f"with username='{username}' "
            f"(using {'axis_username' if is_axis_creds else 'ONVIF username'} credentials)"
        )
        self._client = httpx.AsyncClient(
            auth=httpx.DigestAuth(username, password),
            timeout=self.timeout,
            verify=False,  # AXIS cameras often use self-signed certs
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def base_url(self) -> str:
        """Get the base URL for VAPIX API calls.

        Returns:
            Base URL string for the camera.
        """
        return f"http://{self.config.ip_address}:{self.config.port}"

    def _ensure_connected(self) -> httpx.AsyncClient:
        """Ensure client is connected.

        Returns:
            The HTTP client instance.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._client:
            raise RuntimeError("Client not connected. Use async context manager.")
        return self._client

    async def get_server_report(
        self,
        mode: ServerReportMode = ServerReportMode.TEXT,
    ) -> bytes:
        """Get the server report from the camera.

        Args:
            mode: Output format for the report.

        Returns:
            Raw server report content.

        Raises:
            httpx.HTTPError: If request fails.
        """
        client = self._ensure_connected()
        url = f"{self.base_url}/axis-cgi/serverreport.cgi"

        params = {}
        if mode != ServerReportMode.TEXT:
            params["mode"] = mode.value

        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.content

    async def get_log_files(self) -> dict[str, str]:
        """Get all log files from the server report tarball.

        Returns:
            Dictionary mapping log file names to their content.

        Raises:
            httpx.HTTPError: If request fails.
        """
        content = await self.get_server_report(ServerReportMode.TAR_ALL)

        log_files: dict[str, str] = {}

        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        file_obj = tar.extractfile(member)
                        if file_obj:
                            try:
                                file_content = file_obj.read().decode("utf-8", errors="replace")
                                log_files[member.name] = file_content
                            except Exception:
                                pass
        except tarfile.TarError:
            # If not a valid tar, try to parse as plain text
            log_files["serverreport.txt"] = content.decode("utf-8", errors="replace")

        return log_files

    def _find_log_content(
        self,
        log_files: dict[str, str],
        log_type: LogType,
    ) -> str:
        """Find log content for a specific log type.

        Args:
            log_files: Dictionary of log file names to content.
            log_type: Type of log to find.

        Returns:
            Combined log content for the requested type.
        """
        if log_type == LogType.ALL:
            return "\n".join(log_files.values())

        patterns = LOG_FILE_PATTERNS.get(log_type, [])
        matching_content: list[str] = []

        for filename, content in log_files.items():
            filename_lower = filename.lower()
            for pattern in patterns:
                if pattern.lower() in filename_lower:
                    matching_content.append(content)
                    break

        return "\n".join(matching_content)

    async def get_logs(
        self,
        log_type: LogType = LogType.SYSTEM,
        max_entries: int | None = None,
    ) -> LogReport:
        """Get logs from the camera.

        Args:
            log_type: Type of logs to retrieve.
            max_entries: Maximum number of entries to return.

        Returns:
            LogReport containing parsed log entries.

        Raises:
            httpx.HTTPError: If request fails.
        """
        log_files = await self.get_log_files()
        content = self._find_log_content(log_files, log_type)
        entries = parse_log_content(content, log_type)

        # Sort by timestamp, newest first
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        if max_entries:
            entries = entries[:max_entries]

        return LogReport(
            camera_name=self.config.name or self.config.ip_address,
            camera_address=self.config.ip_address,
            log_type=log_type,
            entries=entries,
        )

    async def get_system_logs(self, max_entries: int | None = None) -> LogReport:
        """Get system logs from the camera.

        Args:
            max_entries: Maximum number of entries to return.

        Returns:
            LogReport containing system log entries.
        """
        return await self.get_logs(LogType.SYSTEM, max_entries)

    async def get_access_logs(self, max_entries: int | None = None) -> LogReport:
        """Get access/request logs from the camera.

        Args:
            max_entries: Maximum number of entries to return.

        Returns:
            LogReport containing access log entries.
        """
        return await self.get_logs(LogType.ACCESS, max_entries)

    async def get_audit_logs(self, max_entries: int | None = None) -> LogReport:
        """Get audit logs from the camera.

        Args:
            max_entries: Maximum number of entries to return.

        Returns:
            LogReport containing audit log entries.
        """
        return await self.get_logs(LogType.AUDIT, max_entries)

    async def stream_logs(
        self,
        log_type: LogType = LogType.SYSTEM,
    ) -> AsyncIterator[LogEntry]:
        """Stream log entries as they are parsed.

        Args:
            log_type: Type of logs to retrieve.

        Yields:
            LogEntry objects as they are parsed.
        """
        log_files = await self.get_log_files()
        content = self._find_log_content(log_files, log_type)

        for line in content.splitlines():
            entry = parse_log_line(line)
            if entry:
                yield entry


async def get_camera_logs(
    config: OnvifCameraConfig,
    log_type: LogType = LogType.SYSTEM,
    max_entries: int | None = 100,
) -> LogReport:
    """Convenience function to get logs from a camera.

    Args:
        config: Camera configuration.
        log_type: Type of logs to retrieve.
        max_entries: Maximum number of entries.

    Returns:
        LogReport with requested logs.

    Example:
        >>> config = OnvifCameraConfig(...)
        >>> logs = await get_camera_logs(config, LogType.AUDIT, max_entries=50)
    """
    async with AxisLogClient(config) as client:
        return await client.get_logs(log_type, max_entries)
