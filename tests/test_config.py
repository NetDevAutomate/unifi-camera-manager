"""Tests for configuration management.

This module tests the configuration loading, environment variable
interpolation, and XDG path handling in unifi_camera_manager.config.
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from unifi_camera_manager.config import (
    APP_NAME,
    OnvifCameraConfig,
    ProtectConfig,
    find_config_file,
    get_camera_by_name,
    get_config_dir,
    get_config_file,
    get_data_dir,
    interpolate_dict,
    interpolate_env_vars,
    list_camera_names,
    load_cameras_config,
    load_raw_config,
)


class TestXDGPaths:
    """Tests for XDG Base Directory Specification compliance."""

    def test_app_name_is_ucam(self) -> None:
        """Test that APP_NAME is set correctly."""
        assert APP_NAME == "ucam"

    def test_get_config_dir_returns_path(self) -> None:
        """Test that get_config_dir returns a Path object."""
        config_dir = get_config_dir()
        assert isinstance(config_dir, Path)
        assert config_dir.exists()

    def test_get_data_dir_returns_path(self) -> None:
        """Test that get_data_dir returns a Path object."""
        data_dir = get_data_dir()
        assert isinstance(data_dir, Path)
        assert data_dir.exists()

    def test_get_config_file_returns_yaml_path(self) -> None:
        """Test that get_config_file returns config.yaml path."""
        config_file = get_config_file()
        assert config_file.name == "config.yaml"
        assert config_file.parent == get_config_dir()


class TestEnvironmentVariableInterpolation:
    """Tests for ${VAR} environment variable interpolation."""

    @pytest.fixture(autouse=True)
    def setup_env(self) -> Generator[None, None, None]:
        """Set up test environment variables."""
        original_env = os.environ.copy()
        os.environ["TEST_VAR"] = "test_value"
        os.environ["TEST_USER"] = "admin"
        os.environ["TEST_PASS"] = "secret123"
        yield
        os.environ.clear()
        os.environ.update(original_env)

    def test_interpolate_simple_variable(self) -> None:
        """Test interpolating a simple ${VAR} reference."""
        result = interpolate_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

    def test_interpolate_multiple_variables(self) -> None:
        """Test interpolating multiple ${VAR} references."""
        result = interpolate_env_vars("${TEST_USER}:${TEST_PASS}")
        assert result == "admin:secret123"

    def test_interpolate_no_variables(self) -> None:
        """Test string without ${VAR} is unchanged."""
        result = interpolate_env_vars("no variables here")
        assert result == "no variables here"

    def test_interpolate_missing_variable_raises(self) -> None:
        """Test that missing environment variable raises ValueError."""
        with pytest.raises(ValueError, match="Environment variable 'NONEXISTENT'"):
            interpolate_env_vars("${NONEXISTENT}")

    def test_interpolate_non_string_returns_unchanged(self) -> None:
        """Test that non-string values are returned unchanged."""
        assert interpolate_env_vars(123) == 123  # type: ignore[arg-type]
        assert interpolate_env_vars(None) is None  # type: ignore[arg-type]

    def test_interpolate_dict_nested(self) -> None:
        """Test recursive dictionary interpolation."""
        data = {
            "user": "${TEST_USER}",
            "nested": {
                "password": "${TEST_PASS}",
            },
            "list": ["${TEST_VAR}"],
            "number": 42,
        }
        result = interpolate_dict(data)
        assert result["user"] == "admin"
        assert result["nested"]["password"] == "secret123"
        assert result["list"][0] == "test_value"
        assert result["number"] == 42


class TestOnvifCameraConfig:
    """Tests for OnvifCameraConfig model."""

    def test_create_valid_config(self, sample_onvif_config: OnvifCameraConfig) -> None:
        """Test creating a valid OnvifCameraConfig."""
        assert sample_onvif_config.ip_address == "192.168.1.100"
        assert sample_onvif_config.username == "admin"
        assert sample_onvif_config.port == 80

    def test_config_with_alias(self) -> None:
        """Test OnvifCameraConfig accepts 'address' alias."""
        config = OnvifCameraConfig(
            address="192.168.1.200",
            username="user",
            password="pass",
        )
        assert config.ip_address == "192.168.1.200"

    def test_config_default_port(self) -> None:
        """Test OnvifCameraConfig default port is 80."""
        config = OnvifCameraConfig(
            address="192.168.1.100",
            username="user",
            password="pass",
        )
        assert config.port == 80

    def test_config_optional_fields(self) -> None:
        """Test OnvifCameraConfig optional fields."""
        config = OnvifCameraConfig(
            address="192.168.1.100",
            username="user",
            password="pass",
        )
        assert config.name is None
        assert config.vendor is None
        assert config.model is None
        assert config.device_type is None

    def test_config_ip_address_validation(self) -> None:
        """Test IP address is trimmed."""
        config = OnvifCameraConfig(
            address="  192.168.1.100  ",
            username="user",
            password="pass",
        )
        assert config.ip_address == "192.168.1.100"

    def test_config_frozen(self, sample_onvif_config: OnvifCameraConfig) -> None:
        """Test OnvifCameraConfig is immutable."""
        with pytest.raises(ValidationError):
            sample_onvif_config.ip_address = "192.168.1.200"  # type: ignore[misc]


class TestProtectConfig:
    """Tests for ProtectConfig settings."""

    @pytest.fixture(autouse=True)
    def setup_env(self) -> Generator[None, None, None]:
        """Set up test environment variables."""
        original_env = os.environ.copy()
        os.environ["UFP_USERNAME"] = "protect_user"
        os.environ["UFP_PASSWORD"] = "protect_pass"
        os.environ["UFP_ADDRESS"] = "192.168.1.1"
        yield
        os.environ.clear()
        os.environ.update(original_env)

    def test_load_from_env(self) -> None:
        """Test ProtectConfig loads from UFP_ environment variables."""
        config = ProtectConfig()
        assert config.username == "protect_user"
        assert config.password == "protect_pass"
        assert config.address == "192.168.1.1"

    def test_default_port(self) -> None:
        """Test ProtectConfig default port is 443."""
        config = ProtectConfig()
        assert config.port == 443

    def test_default_ssl_verify(self) -> None:
        """Test ProtectConfig default ssl_verify is False."""
        config = ProtectConfig()
        assert config.ssl_verify is False


class TestConfigFileLoading:
    """Tests for configuration file loading functions."""

    def test_find_config_file_explicit_path(
        self, sample_config_yaml: Path
    ) -> None:
        """Test find_config_file with explicit path."""
        found = find_config_file(sample_config_yaml)
        assert found == sample_config_yaml

    def test_find_config_file_not_found(self, tmp_path: Path) -> None:
        """Test find_config_file raises when file not found."""
        nonexistent = tmp_path / "nonexistent.yaml"
        with patch(
            "unifi_camera_manager.config.get_config_dir", return_value=tmp_path
        ), pytest.raises(FileNotFoundError):
            find_config_file(nonexistent)

    def test_load_raw_config(self, sample_config_yaml: Path) -> None:
        """Test loading raw YAML configuration."""
        # Clear the lru_cache to ensure fresh load
        load_raw_config.cache_clear()
        config = load_raw_config(sample_config_yaml)
        assert "devices" in config
        assert len(config["devices"]) == 2

    def test_load_cameras_config(self, sample_config_yaml: Path) -> None:
        """Test loading camera configurations from YAML."""
        load_raw_config.cache_clear()
        cameras = load_cameras_config(sample_config_yaml)
        assert len(cameras) == 2
        assert cameras[0].name == "Front Door"
        assert cameras[0].ip_address == "192.168.1.100"
        assert cameras[1].name == "Back Yard"

    def test_load_cameras_config_with_env_interpolation(
        self,
        sample_config_yaml_with_env_vars: Path,
        env_vars_for_config: None,
    ) -> None:
        """Test loading config with environment variable interpolation."""
        load_raw_config.cache_clear()
        cameras = load_cameras_config(sample_config_yaml_with_env_vars)
        assert len(cameras) == 1
        assert cameras[0].username == "test_admin"
        assert cameras[0].password == "test_password"


class TestCameraLookup:
    """Tests for camera lookup functions."""

    def test_get_camera_by_name_found(self, sample_config_yaml: Path) -> None:
        """Test finding a camera by name."""
        load_raw_config.cache_clear()
        camera = get_camera_by_name("Front Door", sample_config_yaml)
        assert camera is not None
        assert camera.ip_address == "192.168.1.100"

    def test_get_camera_by_name_case_insensitive(
        self, sample_config_yaml: Path
    ) -> None:
        """Test camera lookup is case-insensitive."""
        load_raw_config.cache_clear()
        camera = get_camera_by_name("front door", sample_config_yaml)
        assert camera is not None
        assert camera.name == "Front Door"

    def test_get_camera_by_name_not_found(self, sample_config_yaml: Path) -> None:
        """Test camera lookup returns None when not found."""
        load_raw_config.cache_clear()
        camera = get_camera_by_name("Nonexistent Camera", sample_config_yaml)
        assert camera is None

    def test_list_camera_names(self, sample_config_yaml: Path) -> None:
        """Test listing all camera names."""
        load_raw_config.cache_clear()
        names = list_camera_names(sample_config_yaml)
        assert "Front Door" in names
        assert "Back Yard" in names
        assert len(names) == 2

    def test_list_camera_names_no_config(self, tmp_path: Path) -> None:
        """Test listing camera names when config doesn't exist."""
        with patch(
            "unifi_camera_manager.config.find_config_file",
            side_effect=FileNotFoundError,
        ):
            names = list_camera_names(tmp_path / "nonexistent.yaml")
            assert names == []
