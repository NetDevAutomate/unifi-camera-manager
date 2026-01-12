"""Pydantic models for UniFi Camera Manager.

This module contains all data models used throughout the application,
providing validation, serialization, and type safety.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PTZDirection(str, Enum):
    """PTZ movement directions."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"


class LogLevel(str, Enum):
    """Log severity levels per RFC5424."""

    EMERGENCY = "emergency"
    ALERT = "alert"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"
    INFO = "info"
    DEBUG = "debug"


class LogType(str, Enum):
    """Types of logs available from AXIS cameras."""

    SYSTEM = "system"
    ACCESS = "access"
    AUDIT = "audit"
    ALL = "all"


# =============================================================================
# Camera Information Models
# =============================================================================


class CameraInfo(BaseModel):
    """Simplified camera information from UniFi Protect.

    Attributes:
        id: Unique camera identifier.
        name: Display name of the camera.
        type: Camera type/model string.
        host: IP address of the camera.
        is_adopted: Whether camera is adopted into Protect.
        state: Current camera state.
        last_seen: Last time camera was seen online.
        is_third_party: Whether this is a third-party (non-UniFi) camera.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    host: str | None = None
    is_adopted: bool
    state: str
    last_seen: datetime | None = None
    is_third_party: bool = False


class SystemInfo(BaseModel):
    """Extended system information from ONVIF camera.

    Attributes:
        manufacturer: Camera manufacturer name.
        model: Camera model identifier.
        firmware_version: Current firmware version.
        serial_number: Device serial number.
        hardware_id: Hardware identifier.
        system_date_time: Current camera system time.
        uptime_seconds: Device uptime in seconds.
    """

    model_config = ConfigDict(frozen=True)

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    system_date_time: datetime | None = None
    uptime_seconds: int | None = None


class OnvifCameraInfo(BaseModel):
    """Information retrieved from an ONVIF camera during verification.

    Attributes:
        manufacturer: Camera manufacturer name.
        model: Camera model identifier.
        firmware_version: Current firmware version.
        serial_number: Device serial number.
        hardware_id: Hardware identifier.
        is_accessible: Whether camera was successfully accessed.
        error: Error message if access failed.
    """

    model_config = ConfigDict(frozen=True)

    manufacturer: str = ""
    model: str = ""
    firmware_version: str = ""
    serial_number: str = ""
    hardware_id: str = ""
    is_accessible: bool = False
    error: str | None = None


# =============================================================================
# Video and Stream Models
# =============================================================================


class VideoProfile(BaseModel):
    """Video profile configuration.

    Attributes:
        token: Unique profile token.
        name: Human-readable profile name.
        encoding: Video encoding type (H264, H265, etc.).
        resolution_width: Video width in pixels.
        resolution_height: Video height in pixels.
        frame_rate: Frames per second.
        bitrate: Video bitrate in kbps.
        quality: Quality setting (0-100).
    """

    model_config = ConfigDict(frozen=True)

    token: str
    name: str
    encoding: str
    resolution_width: int = Field(ge=0)
    resolution_height: int = Field(ge=0)
    frame_rate: float = Field(ge=0)
    bitrate: int | None = Field(default=None, ge=0)
    quality: float | None = Field(default=None, ge=0, le=100)


class StreamInfo(BaseModel):
    """Stream information.

    Attributes:
        uri: RTSP stream URI.
        profile_token: Associated profile token.
        transport: Transport protocol (RTSP, HTTP, etc.).
    """

    model_config = ConfigDict(frozen=True)

    uri: str
    profile_token: str
    transport: str = "RTSP"


# =============================================================================
# Camera Settings Models
# =============================================================================


class ImageSettings(BaseModel):
    """Image settings for a camera.

    Attributes:
        brightness: Brightness level (0-100).
        contrast: Contrast level (0-100).
        saturation: Color saturation level (0-100).
        sharpness: Sharpness level (0-100).
        ir_cut_filter: IR cut filter mode.
        wide_dynamic_range: WDR enabled state.
        backlight_compensation: Backlight compensation enabled.
    """

    brightness: float | None = Field(default=None, ge=0, le=100)
    contrast: float | None = Field(default=None, ge=0, le=100)
    saturation: float | None = Field(default=None, ge=0, le=100)
    sharpness: float | None = Field(default=None, ge=0, le=100)
    ir_cut_filter: str | None = None
    wide_dynamic_range: bool | None = None
    backlight_compensation: bool | None = None


class PTZStatus(BaseModel):
    """PTZ position and status.

    Attributes:
        pan: Pan position (-1.0 to 1.0).
        tilt: Tilt position (-1.0 to 1.0).
        zoom: Zoom position (0.0 to 1.0).
        moving: Whether PTZ is currently moving.
    """

    model_config = ConfigDict(frozen=True)

    pan: float = Field(ge=-1.0, le=1.0)
    tilt: float = Field(ge=-1.0, le=1.0)
    zoom: float = Field(ge=0.0, le=1.0)
    moving: bool = False


class PTZPreset(BaseModel):
    """PTZ preset position.

    Attributes:
        token: Preset token identifier.
        name: Human-readable preset name.
    """

    model_config = ConfigDict(frozen=True)

    token: str
    name: str


# =============================================================================
# Capability Models
# =============================================================================


class CameraCapabilities(BaseModel):
    """Camera capabilities and features.

    Attributes:
        has_ptz: Camera supports PTZ control.
        has_audio: Camera supports audio.
        has_relay: Camera has relay outputs.
        has_analytics: Camera supports analytics.
        has_recording: Camera supports local recording.
        has_events: Camera supports event system.
        supported_encodings: List of supported video encodings.
        max_profiles: Maximum number of video profiles.
    """

    has_ptz: bool = False
    has_audio: bool = False
    has_relay: bool = False
    has_analytics: bool = False
    has_recording: bool = False
    has_events: bool = False
    supported_encodings: list[str] = Field(default_factory=list)
    max_profiles: int = Field(default=0, ge=0)


# =============================================================================
# Network Models
# =============================================================================


class NetworkConfig(BaseModel):
    """Camera network configuration.

    Attributes:
        ip_address: Camera IP address.
        subnet_mask: Network subnet mask.
        gateway: Default gateway.
        dns_primary: Primary DNS server.
        dns_secondary: Secondary DNS server.
        dhcp_enabled: Whether DHCP is enabled.
        ntp_servers: List of NTP server addresses.
    """

    ip_address: str
    subnet_mask: str
    gateway: str
    dns_primary: str | None = None
    dns_secondary: str | None = None
    dhcp_enabled: bool = False
    ntp_servers: list[str] = Field(default_factory=list)


class OnvifService(BaseModel):
    """ONVIF service information.

    Attributes:
        namespace: Service namespace URI.
        xaddr: Service endpoint address.
        version: Service version string.
    """

    model_config = ConfigDict(frozen=True)

    namespace: str
    xaddr: str
    version: str = "Unknown"


# =============================================================================
# Log Models
# =============================================================================


class LogEntry(BaseModel):
    """A single log entry from AXIS camera.

    Attributes:
        timestamp: Log entry timestamp.
        hostname: Device hostname.
        level: Log severity level.
        process: Process name that generated the log.
        pid: Process ID.
        message: Log message content.
        raw: Original raw log line.
    """

    timestamp: datetime
    hostname: str
    level: LogLevel = LogLevel.INFO
    process: str = ""
    pid: int | None = None
    message: str
    raw: str

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, v: Any) -> LogLevel:
        """Normalize log level string to enum.

        Args:
            v: Input value for level field.

        Returns:
            Normalized LogLevel enum value.
        """
        if isinstance(v, LogLevel):
            return v
        if isinstance(v, str):
            level_map = {
                "emerg": LogLevel.EMERGENCY,
                "alert": LogLevel.ALERT,
                "crit": LogLevel.CRITICAL,
                "err": LogLevel.ERROR,
                "error": LogLevel.ERROR,
                "warn": LogLevel.WARNING,
                "warning": LogLevel.WARNING,
                "notice": LogLevel.NOTICE,
                "info": LogLevel.INFO,
                "debug": LogLevel.DEBUG,
            }
            return level_map.get(v.lower(), LogLevel.INFO)
        return LogLevel.INFO


class LogReport(BaseModel):
    """Collection of log entries with metadata.

    Attributes:
        camera_name: Name of the camera.
        camera_address: IP address of the camera.
        log_type: Type of logs retrieved.
        entries: List of log entries.
        retrieved_at: When the logs were retrieved.
        total_entries: Total number of entries.
    """

    camera_name: str
    camera_address: str
    log_type: LogType
    entries: list[LogEntry] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=datetime.now)
    total_entries: int = 0

    def model_post_init(self, __context: Any) -> None:
        """Update total_entries after initialization."""
        if not self.total_entries:
            object.__setattr__(self, "total_entries", len(self.entries))


# =============================================================================
# NVR Models
# =============================================================================


class NvrInfo(BaseModel):
    """UniFi Protect NVR information.

    Attributes:
        id: NVR unique identifier.
        name: NVR display name.
        model: NVR model.
        version: Firmware version.
        host: NVR IP address.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    model: str
    version: str
    host: str | None = None
