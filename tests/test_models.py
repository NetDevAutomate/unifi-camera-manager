"""Tests for Pydantic models.

This module tests the data models in unifi_camera_manager.models,
ensuring proper validation, serialization, and field constraints.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from unifi_camera_manager.models import (
    CameraCapabilities,
    CameraInfo,
    ImageSettings,
    LogEntry,
    LogLevel,
    LogReport,
    LogType,
    NetworkConfig,
    NvrInfo,
    OnvifCameraInfo,
    OnvifService,
    PTZDirection,
    PTZPreset,
    PTZStatus,
    StreamInfo,
    SystemInfo,
    VideoProfile,
)


class TestCameraInfo:
    """Tests for CameraInfo model."""

    def test_create_valid_camera_info(self, sample_camera_info: CameraInfo) -> None:
        """Test creating a valid CameraInfo instance."""
        assert sample_camera_info.id == "camera123"
        assert sample_camera_info.name == "Front Door"
        assert sample_camera_info.host == "192.168.1.100"
        assert sample_camera_info.is_adopted is True
        assert sample_camera_info.is_third_party is False

    def test_camera_info_optional_fields(self) -> None:
        """Test CameraInfo with optional fields as None."""
        camera = CameraInfo(
            id="test",
            name="Test Camera",
            type="Unknown",
            is_adopted=False,
            state="DISCONNECTED",
        )
        assert camera.host is None
        assert camera.last_seen is None
        assert camera.is_third_party is False

    def test_camera_info_frozen(self, sample_camera_info: CameraInfo) -> None:
        """Test that CameraInfo is immutable."""
        with pytest.raises(ValidationError):
            sample_camera_info.name = "New Name"  # type: ignore[misc]


class TestSystemInfo:
    """Tests for SystemInfo model."""

    def test_create_valid_system_info(self, sample_system_info: SystemInfo) -> None:
        """Test creating a valid SystemInfo instance."""
        assert sample_system_info.manufacturer == "AXIS"
        assert sample_system_info.model == "P3245-LV"
        assert sample_system_info.firmware_version == "11.8.64"

    def test_system_info_optional_fields(self) -> None:
        """Test SystemInfo with optional fields as None."""
        info = SystemInfo(
            manufacturer="Test",
            model="Test Model",
            firmware_version="1.0",
            serial_number="12345",
            hardware_id="hw1",
        )
        assert info.system_date_time is None
        assert info.uptime_seconds is None


class TestOnvifCameraInfo:
    """Tests for OnvifCameraInfo model."""

    def test_create_accessible_camera(
        self, sample_onvif_camera_info: OnvifCameraInfo
    ) -> None:
        """Test creating an accessible OnvifCameraInfo."""
        assert sample_onvif_camera_info.is_accessible is True
        assert sample_onvif_camera_info.error is None

    def test_create_inaccessible_camera(self) -> None:
        """Test creating an inaccessible OnvifCameraInfo with error."""
        info = OnvifCameraInfo(
            is_accessible=False,
            error="Connection timeout",
        )
        assert info.is_accessible is False
        assert info.error == "Connection timeout"
        assert info.manufacturer == ""

    def test_default_values(self) -> None:
        """Test OnvifCameraInfo default values."""
        info = OnvifCameraInfo()
        assert info.manufacturer == ""
        assert info.is_accessible is False


class TestVideoProfile:
    """Tests for VideoProfile model."""

    def test_create_valid_profile(self, sample_video_profile: VideoProfile) -> None:
        """Test creating a valid VideoProfile."""
        assert sample_video_profile.token == "profile_1"
        assert sample_video_profile.resolution_width == 1920
        assert sample_video_profile.resolution_height == 1080
        assert sample_video_profile.frame_rate == 30.0

    def test_profile_validation_negative_resolution(self) -> None:
        """Test that negative resolution values are rejected."""
        with pytest.raises(ValidationError):
            VideoProfile(
                token="test",
                name="Test",
                encoding="H264",
                resolution_width=-1,
                resolution_height=1080,
                frame_rate=30.0,
            )

    def test_profile_validation_negative_frame_rate(self) -> None:
        """Test that negative frame rate is rejected."""
        with pytest.raises(ValidationError):
            VideoProfile(
                token="test",
                name="Test",
                encoding="H264",
                resolution_width=1920,
                resolution_height=1080,
                frame_rate=-1.0,
            )

    def test_profile_optional_bitrate_quality(self) -> None:
        """Test VideoProfile with optional bitrate and quality."""
        profile = VideoProfile(
            token="test",
            name="Test",
            encoding="H264",
            resolution_width=1920,
            resolution_height=1080,
            frame_rate=30.0,
        )
        assert profile.bitrate is None
        assert profile.quality is None


class TestStreamInfo:
    """Tests for StreamInfo model."""

    def test_create_valid_stream_info(self, sample_stream_info: StreamInfo) -> None:
        """Test creating a valid StreamInfo."""
        assert sample_stream_info.uri == "rtsp://192.168.1.100:554/stream1"
        assert sample_stream_info.profile_token == "profile_1"
        assert sample_stream_info.transport == "RTSP"

    def test_stream_info_default_transport(self) -> None:
        """Test StreamInfo default transport value."""
        stream = StreamInfo(uri="rtsp://test:554/stream", profile_token="test")
        assert stream.transport == "RTSP"


class TestPTZStatus:
    """Tests for PTZStatus model."""

    def test_create_valid_ptz_status(self, sample_ptz_status: PTZStatus) -> None:
        """Test creating a valid PTZStatus."""
        assert sample_ptz_status.pan == 0.5
        assert sample_ptz_status.tilt == -0.25
        assert sample_ptz_status.zoom == 0.0
        assert sample_ptz_status.moving is False

    def test_ptz_status_validation_pan_range(self) -> None:
        """Test PTZStatus pan value must be in range."""
        with pytest.raises(ValidationError):
            PTZStatus(pan=1.5, tilt=0.0, zoom=0.0)

    def test_ptz_status_validation_tilt_range(self) -> None:
        """Test PTZStatus tilt value must be in range."""
        with pytest.raises(ValidationError):
            PTZStatus(pan=0.0, tilt=-1.5, zoom=0.0)

    def test_ptz_status_validation_zoom_range(self) -> None:
        """Test PTZStatus zoom value must be in range."""
        with pytest.raises(ValidationError):
            PTZStatus(pan=0.0, tilt=0.0, zoom=1.5)


class TestPTZPreset:
    """Tests for PTZPreset model."""

    def test_create_valid_preset(self, sample_ptz_preset: PTZPreset) -> None:
        """Test creating a valid PTZPreset."""
        assert sample_ptz_preset.token == "preset_1"
        assert sample_ptz_preset.name == "Home"


class TestImageSettings:
    """Tests for ImageSettings model."""

    def test_create_valid_image_settings(
        self, sample_image_settings: ImageSettings
    ) -> None:
        """Test creating valid ImageSettings."""
        assert sample_image_settings.brightness == 50.0
        assert sample_image_settings.contrast == 50.0
        assert sample_image_settings.wide_dynamic_range is True

    def test_image_settings_validation_brightness_range(self) -> None:
        """Test ImageSettings brightness must be 0-100."""
        with pytest.raises(ValidationError):
            ImageSettings(brightness=150.0)

    def test_image_settings_validation_contrast_range(self) -> None:
        """Test ImageSettings contrast must be 0-100."""
        with pytest.raises(ValidationError):
            ImageSettings(contrast=-10.0)

    def test_image_settings_all_optional(self) -> None:
        """Test ImageSettings with all optional fields."""
        settings = ImageSettings()
        assert settings.brightness is None
        assert settings.contrast is None
        assert settings.ir_cut_filter is None


class TestCameraCapabilities:
    """Tests for CameraCapabilities model."""

    def test_create_valid_capabilities(
        self, sample_capabilities: CameraCapabilities
    ) -> None:
        """Test creating valid CameraCapabilities."""
        assert sample_capabilities.has_ptz is True
        assert sample_capabilities.has_audio is True
        assert "H264" in sample_capabilities.supported_encodings

    def test_capabilities_defaults(self) -> None:
        """Test CameraCapabilities default values."""
        caps = CameraCapabilities()
        assert caps.has_ptz is False
        assert caps.has_audio is False
        assert caps.supported_encodings == []
        assert caps.max_profiles == 0


class TestNetworkConfig:
    """Tests for NetworkConfig model."""

    def test_create_valid_network_config(self) -> None:
        """Test creating a valid NetworkConfig."""
        config = NetworkConfig(
            ip_address="192.168.1.100",
            subnet_mask="255.255.255.0",
            gateway="192.168.1.1",
            dhcp_enabled=False,
        )
        assert config.ip_address == "192.168.1.100"
        assert config.dhcp_enabled is False

    def test_network_config_optional_dns(self) -> None:
        """Test NetworkConfig with optional DNS fields."""
        config = NetworkConfig(
            ip_address="192.168.1.100",
            subnet_mask="255.255.255.0",
            gateway="192.168.1.1",
        )
        assert config.dns_primary is None
        assert config.dns_secondary is None


class TestOnvifService:
    """Tests for OnvifService model."""

    def test_create_valid_service(self) -> None:
        """Test creating a valid OnvifService."""
        service = OnvifService(
            namespace="http://www.onvif.org/ver10/device/wsdl",
            xaddr="http://192.168.1.100/onvif/device_service",
            version="2.0",
        )
        assert "device" in service.namespace
        assert service.version == "2.0"

    def test_service_default_version(self) -> None:
        """Test OnvifService default version."""
        service = OnvifService(
            namespace="http://www.onvif.org/ver10/media/wsdl",
            xaddr="http://192.168.1.100/onvif/media_service",
        )
        assert service.version == "Unknown"


class TestLogEntry:
    """Tests for LogEntry model."""

    def test_create_valid_log_entry(self, sample_log_entry: LogEntry) -> None:
        """Test creating a valid LogEntry."""
        assert sample_log_entry.hostname == "axis-camera"
        assert sample_log_entry.level == LogLevel.INFO
        assert sample_log_entry.process == "httpd"
        assert sample_log_entry.pid == 1234

    def test_log_entry_level_normalization(self) -> None:
        """Test LogEntry level normalization from string."""
        entry = LogEntry(
            timestamp=datetime.now(),
            hostname="test",
            level="warn",  # type: ignore[arg-type]
            message="Test message",
            raw="raw log line",
        )
        assert entry.level == LogLevel.WARNING

    def test_log_entry_level_normalization_error(self) -> None:
        """Test LogEntry level normalization for error variant."""
        entry = LogEntry(
            timestamp=datetime.now(),
            hostname="test",
            level="err",  # type: ignore[arg-type]
            message="Error message",
            raw="raw log line",
        )
        assert entry.level == LogLevel.ERROR

    def test_log_entry_unknown_level_defaults_to_info(self) -> None:
        """Test LogEntry with unknown level defaults to INFO."""
        entry = LogEntry(
            timestamp=datetime.now(),
            hostname="test",
            level="unknown_level",  # type: ignore[arg-type]
            message="Message",
            raw="raw",
        )
        assert entry.level == LogLevel.INFO


class TestLogReport:
    """Tests for LogReport model."""

    def test_create_valid_log_report(self, sample_log_report: LogReport) -> None:
        """Test creating a valid LogReport."""
        assert sample_log_report.camera_name == "Front Door"
        assert sample_log_report.log_type == LogType.SYSTEM
        assert len(sample_log_report.entries) == 1
        assert sample_log_report.total_entries == 1

    def test_log_report_auto_total_entries(self) -> None:
        """Test LogReport automatically sets total_entries."""
        entries = [
            LogEntry(
                timestamp=datetime.now(),
                hostname="test",
                level=LogLevel.INFO,
                message=f"Message {i}",
                raw=f"raw {i}",
            )
            for i in range(5)
        ]
        report = LogReport(
            camera_name="Test",
            camera_address="192.168.1.1",
            log_type=LogType.ALL,
            entries=entries,
        )
        assert report.total_entries == 5


class TestNvrInfo:
    """Tests for NvrInfo model."""

    def test_create_valid_nvr_info(self, sample_nvr_info: NvrInfo) -> None:
        """Test creating a valid NvrInfo."""
        assert sample_nvr_info.id == "nvr123"
        assert sample_nvr_info.name == "Home NVR"
        assert sample_nvr_info.model == "UNVR"

    def test_nvr_info_optional_host(self) -> None:
        """Test NvrInfo with optional host."""
        nvr = NvrInfo(
            id="test",
            name="Test NVR",
            model="UNVR",
            version="3.0.0",
        )
        assert nvr.host is None


class TestEnums:
    """Tests for enum types."""

    def test_ptz_direction_values(self) -> None:
        """Test PTZDirection enum values."""
        assert PTZDirection.UP.value == "up"
        assert PTZDirection.DOWN.value == "down"
        assert PTZDirection.LEFT.value == "left"
        assert PTZDirection.RIGHT.value == "right"
        assert PTZDirection.ZOOM_IN.value == "zoom_in"
        assert PTZDirection.ZOOM_OUT.value == "zoom_out"

    def test_log_level_values(self) -> None:
        """Test LogLevel enum values."""
        assert LogLevel.EMERGENCY.value == "emergency"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.DEBUG.value == "debug"

    def test_log_type_values(self) -> None:
        """Test LogType enum values."""
        assert LogType.SYSTEM.value == "system"
        assert LogType.ACCESS.value == "access"
        assert LogType.AUDIT.value == "audit"
        assert LogType.ALL.value == "all"
