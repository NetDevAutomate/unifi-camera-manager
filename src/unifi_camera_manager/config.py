"""Configuration management for UniFi Protect connection."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class ProtectConfig:
    """UniFi Protect connection configuration."""

    username: str
    password: str
    address: str
    port: int = 443
    ssl_verify: bool = False
    api_key: str | None = None

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "ProtectConfig":
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file. If not provided,
                     looks in current directory and parent directories.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            # Try current directory first, then parent
            if Path(".env").exists():
                load_dotenv(".env")
            elif Path("../.env").exists():
                load_dotenv("../.env")

        username = os.getenv("UFP_USERNAME")
        password = os.getenv("UFP_PASSWORD")
        address = os.getenv("UFP_ADDRESS")

        if not all([username, password, address]):
            raise ValueError(
                "Missing required environment variables: "
                "UFP_USERNAME, UFP_PASSWORD, UFP_ADDRESS"
            )

        return cls(
            username=username,
            password=password,
            address=address,
            port=int(os.getenv("UFP_PORT", "443")),
            ssl_verify=os.getenv("UFP_SSL_VERIFY", "false").lower() == "true",
            api_key=os.getenv("UFP_API_KEY"),
        )


@dataclass
class OnvifCameraConfig:
    """ONVIF camera configuration for adding third-party cameras."""

    ip_address: str
    username: str
    password: str
    port: int = 80
    name: str | None = None
    vendor: str | None = None
    model: str | None = None
    device_type: str | None = None


def _interpolate_env_vars(value: str) -> str:
    """Interpolate environment variables in a string.

    Supports ${VAR_NAME} syntax.
    """
    if not isinstance(value, str):
        return value

    pattern = r"\$\{([^}]+)\}"

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.getenv(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value

    return re.sub(pattern, replace, value)


def load_cameras_config(
    config_file: Path | None = None,
    env_file: Path | None = None,
) -> list[OnvifCameraConfig]:
    """Load camera configurations from YAML file.

    Args:
        config_file: Path to config.yaml. Defaults to ./config.yaml.
        env_file: Path to .env file for secrets.

    Returns:
        List of OnvifCameraConfig objects.
    """
    # Load environment variables first
    if env_file:
        load_dotenv(env_file)
    else:
        if Path(".env").exists():
            load_dotenv(".env")
        elif Path("../.env").exists():
            load_dotenv("../.env")

    # Find config file
    if config_file is None:
        config_file = Path("config.yaml")
        if not config_file.exists():
            config_file = Path("../config.yaml")

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_file) as f:
        config_data = yaml.safe_load(f)

    devices = config_data.get("devices", [])
    cameras = []

    for device in devices:
        cameras.append(
            OnvifCameraConfig(
                ip_address=device["address"],
                username=_interpolate_env_vars(device["username"]),
                password=_interpolate_env_vars(device["password"]),
                port=device.get("port", 80),
                name=device.get("name"),
                vendor=device.get("vendor"),
                model=device.get("model"),
                device_type=device.get("type"),
            )
        )

    return cameras


def get_camera_by_name(
    name: str,
    config_file: Path | None = None,
    env_file: Path | None = None,
) -> OnvifCameraConfig | None:
    """Get a specific camera configuration by name.

    Args:
        name: Camera name (case-insensitive).
        config_file: Path to config.yaml.
        env_file: Path to .env file.

    Returns:
        OnvifCameraConfig or None if not found.
    """
    cameras = load_cameras_config(config_file, env_file)
    name_lower = name.lower()

    for camera in cameras:
        if camera.name and camera.name.lower() == name_lower:
            return camera

    return None


def list_camera_names(
    config_file: Path | None = None,
    env_file: Path | None = None,
) -> list[str]:
    """List all camera names from config.

    Args:
        config_file: Path to config.yaml.
        env_file: Path to .env file.

    Returns:
        List of camera names.
    """
    cameras = load_cameras_config(config_file, env_file)
    return [c.name for c in cameras if c.name]
