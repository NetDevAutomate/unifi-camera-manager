"""Pytest configuration and shared fixtures.

This module provides fixtures used across test modules for
testing UniFi Camera Manager functionality.
"""

import os
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from unifi_camera_manager.config import OnvifCameraConfig
from unifi_camera_manager.models import (
    CameraCapabilities,
    CameraInfo,
    ImageSettings,
    LogEntry,
    LogLevel,
    LogReport,
    LogType,
    NvrInfo,
    OnvifCameraInfo,
    PTZPreset,
    PTZStatus,
    StreamInfo,
    SystemInfo,
    VideoProfile,
)


@pytest.fixture
def sample_camera_info() -> CameraInfo:
    """Create a sample CameraInfo for testing."""
    return CameraInfo(
        id="camera123",
        name="Front Door",
        type="UVC G4 Bullet",
        host="192.168.1.100",
        is_adopted=True,
        state="CONNECTED",
        last_seen=datetime(2025, 1, 1, 12, 0, 0),
        is_third_party=False,
    )


@pytest.fixture
def sample_third_party_camera() -> CameraInfo:
    """Create a sample third-party CameraInfo for testing."""
    return CameraInfo(
        id="camera456",
        name="AXIS P3245",
        type="AXIS",
        host="192.168.1.101",
        is_adopted=True,
        state="CONNECTED",
        is_third_party=True,
    )


@pytest.fixture
def sample_system_info() -> SystemInfo:
    """Create a sample SystemInfo for testing."""
    return SystemInfo(
        manufacturer="AXIS",
        model="P3245-LV",
        firmware_version="11.8.64",
        serial_number="ACCC8E123456",
        hardware_id="1234",
        system_date_time=datetime(2025, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_onvif_camera_info() -> OnvifCameraInfo:
    """Create a sample OnvifCameraInfo for testing."""
    return OnvifCameraInfo(
        manufacturer="AXIS",
        model="P3245-LV",
        firmware_version="11.8.64",
        serial_number="ACCC8E123456",
        hardware_id="1234",
        is_accessible=True,
    )


@pytest.fixture
def sample_video_profile() -> VideoProfile:
    """Create a sample VideoProfile for testing."""
    return VideoProfile(
        token="profile_1",
        name="MainStream",
        encoding="H264",
        resolution_width=1920,
        resolution_height=1080,
        frame_rate=30.0,
        bitrate=4096,
        quality=80.0,
    )


@pytest.fixture
def sample_stream_info() -> StreamInfo:
    """Create a sample StreamInfo for testing."""
    return StreamInfo(
        uri="rtsp://192.168.1.100:554/stream1",
        profile_token="profile_1",
        transport="RTSP",
    )


@pytest.fixture
def sample_ptz_status() -> PTZStatus:
    """Create a sample PTZStatus for testing."""
    return PTZStatus(
        pan=0.5,
        tilt=-0.25,
        zoom=0.0,
        moving=False,
    )


@pytest.fixture
def sample_ptz_preset() -> PTZPreset:
    """Create a sample PTZPreset for testing."""
    return PTZPreset(
        token="preset_1",
        name="Home",
    )


@pytest.fixture
def sample_image_settings() -> ImageSettings:
    """Create a sample ImageSettings for testing."""
    return ImageSettings(
        brightness=50.0,
        contrast=50.0,
        saturation=50.0,
        sharpness=50.0,
        ir_cut_filter="AUTO",
        wide_dynamic_range=True,
        backlight_compensation=False,
    )


@pytest.fixture
def sample_capabilities() -> CameraCapabilities:
    """Create a sample CameraCapabilities for testing."""
    return CameraCapabilities(
        has_ptz=True,
        has_audio=True,
        has_relay=False,
        has_analytics=True,
        has_recording=False,
        has_events=True,
        supported_encodings=["H264", "H265", "JPEG"],
        max_profiles=4,
    )


@pytest.fixture
def sample_nvr_info() -> NvrInfo:
    """Create a sample NvrInfo for testing."""
    return NvrInfo(
        id="nvr123",
        name="Home NVR",
        model="UNVR",
        version="3.0.0",
        host="192.168.1.1",
    )


@pytest.fixture
def sample_log_entry() -> LogEntry:
    """Create a sample LogEntry for testing."""
    return LogEntry(
        timestamp=datetime(2025, 1, 1, 12, 0, 0),
        hostname="axis-camera",
        level=LogLevel.INFO,
        process="httpd",
        pid=1234,
        message="HTTP request handled successfully",
        raw=(
            "2025-01-01T12:00:00+00:00 axis-camera [ INFO    ] "
            "httpd[1234]: HTTP request handled successfully"
        ),
    )


@pytest.fixture
def sample_log_report(sample_log_entry: LogEntry) -> LogReport:
    """Create a sample LogReport for testing."""
    return LogReport(
        camera_name="Front Door",
        camera_address="192.168.1.100",
        log_type=LogType.SYSTEM,
        entries=[sample_log_entry],
    )


@pytest.fixture
def sample_onvif_config() -> OnvifCameraConfig:
    """Create a sample OnvifCameraConfig for testing."""
    return OnvifCameraConfig(
        address="192.168.1.100",
        username="admin",
        password="password123",
        port=80,
        name="Front Door",
        vendor="AXIS",
        model="P3245-LV",
    )


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary config directory with sample config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    yield config_dir


@pytest.fixture
def sample_config_yaml(temp_config_dir: Path) -> Path:
    """Create a sample config.yaml file for testing."""
    config_file = temp_config_dir / "config.yaml"
    config_content = """
devices:
  - name: Front Door
    address: 192.168.1.100
    username: admin
    password: secret123
    port: 80
    vendor: AXIS
    model: P3245-LV
    type: camera

  - name: Back Yard
    address: 192.168.1.101
    username: admin
    password: secret456
    port: 80
    vendor: AXIS
    model: P3247
    type: camera
"""
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def sample_config_yaml_with_env_vars(temp_config_dir: Path) -> Path:
    """Create a config.yaml with environment variable interpolation."""
    config_file = temp_config_dir / "config.yaml"
    config_content = """
devices:
  - name: Front Door
    address: 192.168.1.100
    username: ${CAMERA_USER}
    password: ${CAMERA_PASS}
    port: 80
"""
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def env_vars_for_config() -> Generator[None, None, None]:
    """Set up environment variables for config testing."""
    original_env = os.environ.copy()
    os.environ["CAMERA_USER"] = "test_admin"
    os.environ["CAMERA_PASS"] = "test_password"
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def sample_syslog_content() -> str:
    """Create sample AXIS syslog content for testing."""
    return """2025-01-11T19:47:42.861+00:00 axis-camera [ INFO    ] systemd[1]: Started Session 42
2025-01-11T19:47:43.123+00:00 axis-camera [ WARNING ] httpd[1234]: Connection timeout
2025-01-11T19:47:44.456+00:00 axis-camera [ ERROR   ] ptzd[5678]: PTZ motor error detected
2025-01-11T19:47:45.789+00:00 axis-camera [ INFO    ] eventd[9012]: Motion detected
"""


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Create a mock httpx client for testing."""
    client = MagicMock()
    return client
