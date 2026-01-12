"""Configuration management for UniFi Camera Manager.

This module provides XDG-compliant configuration paths and Pydantic-based
settings management. Secrets are managed via chezmoi templating, which
injects credentials from secrets.json.age at `chezmoi apply` time.

Configuration priority:
1. ~/.config/ucam/config.yaml (XDG/chezmoi-managed, recommended)
2. Platform-specific config dir (~/Library/Application Support/ucam/ on macOS)
3. ./config.yaml (current directory, for development)

Legacy support for ${VAR} environment variable interpolation is retained
for backward compatibility but chezmoi templating is the recommended approach.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Application identifiers for XDG paths
APP_NAME = "ucam"
APP_AUTHOR = "unifi-camera-manager"


def get_config_dir() -> Path:
    """Get XDG-compliant configuration directory.

    Returns:
        Path to configuration directory (~/.config/ucam on Linux/macOS).

    Note:
        Creates the directory if it doesn't exist.
    """
    config_dir = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_data_dir() -> Path:
    """Get XDG-compliant data directory.

    Returns:
        Path to data directory (~/.local/share/ucam on Linux/macOS).

    Note:
        Creates the directory if it doesn't exist.
    """
    data_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_file() -> Path:
    """Get path to main configuration file.

    Returns:
        Path to config.yaml in XDG config directory.
    """
    return get_config_dir() / "config.yaml"


# =============================================================================
# UniFi Protect Configuration
# =============================================================================


class ProtectConfig(BaseSettings):
    """UniFi Protect NVR connection configuration.

    Loads settings from environment variables with UFP_ prefix.
    Supports loading from .env files.

    Attributes:
        username: UniFi Protect username.
        password: UniFi Protect password.
        address: NVR IP address or hostname.
        port: NVR port (default 443).
        ssl_verify: Whether to verify SSL certificates.
        api_key: Optional API key for authentication.

    Example:
        >>> config = ProtectConfig()  # Load from environment
        >>> config = ProtectConfig(username="admin", password="secret", address="192.168.1.1")
    """

    model_config = SettingsConfigDict(
        env_prefix="UFP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    username: str = Field(..., description="UniFi Protect username")
    password: str = Field(..., description="UniFi Protect password")
    address: str = Field(..., description="NVR IP address or hostname")
    port: int = Field(default=443, ge=1, le=65535, description="NVR port")
    ssl_verify: bool = Field(default=False, description="Verify SSL certificates")
    api_key: str | None = Field(default=None, description="Optional API key")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "ProtectConfig":
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file. If not provided,
                looks in current directory and XDG config directory.

        Returns:
            ProtectConfig instance.

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Determine which env file to use
        if env_file and env_file.exists():
            return cls(_env_file=env_file)

        # Check standard locations
        for path in [Path(".env"), get_config_dir() / ".env"]:
            if path.exists():
                return cls(_env_file=path)

        # Try without env file (use system environment)
        return cls()


# =============================================================================
# ONVIF Camera Configuration
# =============================================================================


class OnvifCameraConfig(BaseModel):
    """ONVIF camera configuration.

    Supports dual credentials for AXIS cameras:
    - username/password: ONVIF protocol access (camera control, streams, PTZ)
    - axis_username/axis_password: VAPIX API access (logs, configuration)

    Attributes:
        ip_address: Camera IP address.
        username: ONVIF username.
        password: ONVIF password.
        port: ONVIF port (default 80).
        name: Optional display name.
        vendor: Camera vendor/manufacturer.
        model: Camera model.
        device_type: Type of device (camera, intercom, etc.).
        axis_username: AXIS admin username for VAPIX API (optional).
        axis_password: AXIS admin password for VAPIX API (optional).
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    ip_address: str = Field(..., alias="address")
    username: str
    password: str
    port: int = Field(default=80, ge=1, le=65535)
    name: str | None = None
    vendor: str | None = None
    model: str | None = None
    device_type: str | None = Field(default=None, alias="type")
    axis_username: str | None = None
    axis_password: str | None = None

    def get_axis_credentials(self) -> tuple[str, str]:
        """Get credentials for AXIS VAPIX API.

        Returns AXIS admin credentials if available, otherwise falls back
        to ONVIF credentials.

        Returns:
            Tuple of (username, password) for VAPIX API access.
        """
        if self.axis_username and self.axis_password:
            return (self.axis_username, self.axis_password)
        return (self.username, self.password)

    @field_validator("ip_address", mode="before")
    @classmethod
    def validate_ip_address(cls, v: Any) -> str:
        """Validate IP address format.

        Args:
            v: Input value for IP address.

        Returns:
            Validated IP address string.
        """
        if not isinstance(v, str):
            v = str(v)
        return v.strip()


class DefaultCredentials(BaseModel):
    """Default credentials for camera access.

    Used when --ip is provided without explicit --user/--pass.
    Credentials are typically injected by chezmoi from secrets.json.age
    at template apply time.

    Attributes:
        username: Default username for AXIS cameras.
        password: Default password for AXIS cameras.
        port: Default HTTP port (default 80).
    """

    model_config = ConfigDict(frozen=True)

    username: str = Field(..., description="Default AXIS username")
    password: str = Field(..., description="Default AXIS password")
    port: int = Field(default=80, ge=1, le=65535, description="Default HTTP port")


class DevicesConfig(BaseModel):
    """Root configuration model for devices config file.

    Attributes:
        devices: List of ONVIF camera configurations.
        defaults: Default credentials for --ip access.
    """

    devices: list[dict[str, Any]] = Field(default_factory=list)
    defaults: dict[str, Any] | None = Field(default=None)


# =============================================================================
# Environment Variable Interpolation
# =============================================================================


def interpolate_env_vars(value: str) -> str:
    """Interpolate environment variables in a string.

    Supports ${VAR_NAME} syntax for referencing environment variables.
    This is commonly used with chezmoi-managed secrets.

    Args:
        value: String potentially containing ${VAR_NAME} references.

    Returns:
        String with environment variables replaced.

    Raises:
        ValueError: If referenced environment variable is not set.

    Example:
        >>> os.environ["MY_SECRET"] = "password123"
        >>> interpolate_env_vars("user:${MY_SECRET}")
        'user:password123'
    """
    if not isinstance(value, str):
        return value

    pattern = r"\$\{([^}]+)\}"

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.getenv(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value

    return re.sub(pattern, replace, value)


def interpolate_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively interpolate environment variables in a dictionary.

    Args:
        data: Dictionary with string values that may contain ${VAR} references.

    Returns:
        Dictionary with all environment variables interpolated.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = interpolate_env_vars(value)
        elif isinstance(value, dict):
            result[key] = interpolate_dict(value)
        elif isinstance(value, list):
            result[key] = [
                interpolate_dict(item) if isinstance(item, dict) else
                interpolate_env_vars(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# =============================================================================
# Configuration Loading Functions
# =============================================================================


def find_config_file(config_file: Path | None = None) -> Path:
    """Find the configuration file.

    Searches in order:
    1. Explicitly provided path
    2. XDG config directory (~/.config/ucam/) - for chezmoi-managed configs
    3. Platform-specific config directory (~/Library/Application Support/ucam/ on macOS)
    4. Current working directory (fallback for development)

    Args:
        config_file: Optional explicit path to config file.

    Returns:
        Path to configuration file.

    Raises:
        FileNotFoundError: If no configuration file is found.
    """
    if config_file is not None:
        if config_file.exists():
            return config_file
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    # XDG config directory (chezmoi standard) - prioritize over platform-specific
    xdg_config_dir = Path.home() / ".config" / APP_NAME

    # Search paths in priority order
    search_paths = [
        xdg_config_dir / "config.yaml",
        xdg_config_dir / "config.yml",
        get_config_dir() / "config.yaml",
        get_config_dir() / "config.yml",
        Path("config.yaml"),
        Path("config.yml"),
    ]

    for path in search_paths:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"Configuration file not found. Searched: {', '.join(str(p) for p in search_paths)}"
    )


@lru_cache(maxsize=1)
def load_raw_config(config_file: Path) -> dict[str, Any]:
    """Load raw YAML configuration (cached).

    Args:
        config_file: Path to YAML configuration file.

    Returns:
        Parsed YAML as dictionary.
    """
    with open(config_file) as f:
        return yaml.safe_load(f) or {}


def load_cameras_config(
    config_file: Path | None = None,
) -> list[OnvifCameraConfig]:
    """Load camera configurations from YAML file.

    Environment variables in the config are interpolated using ${VAR} syntax.
    This integrates with chezmoi's secret management via age encryption.

    Args:
        config_file: Path to config.yaml. If None, searches standard locations.

    Returns:
        List of OnvifCameraConfig objects.

    Raises:
        FileNotFoundError: If config file not found.
        ValueError: If environment variables are missing.

    Example:
        >>> cameras = load_cameras_config()
        >>> for cam in cameras:
        ...     print(f"{cam.name}: {cam.ip_address}")
    """
    config_path = find_config_file(config_file)
    raw_config = load_raw_config(config_path)

    devices = raw_config.get("devices", [])
    cameras: list[OnvifCameraConfig] = []

    for device in devices:
        # Interpolate environment variables in device config
        interpolated = interpolate_dict(device)
        cameras.append(OnvifCameraConfig(**interpolated))

    return cameras


def get_default_credentials(
    config_file: Path | None = None,
) -> DefaultCredentials | None:
    """Get default credentials from config file.

    Loads the 'defaults' section from config.yaml and interpolates
    any ${VAR} environment variable references (for chezmoi secrets).

    Args:
        config_file: Path to config.yaml. If None, searches standard locations.

    Returns:
        DefaultCredentials if defaults section exists, None otherwise.

    Raises:
        ValueError: If environment variables in config are missing.

    Example:
        >>> creds = get_default_credentials()
        >>> if creds:
        ...     print(f"Default user: {creds.username}")
    """
    try:
        config_path = find_config_file(config_file)
    except FileNotFoundError:
        return None

    raw_config = load_raw_config(config_path)
    defaults = raw_config.get("defaults")

    if not defaults:
        return None

    # Interpolate environment variables (for chezmoi secrets)
    interpolated = interpolate_dict(defaults)
    return DefaultCredentials(**interpolated)


def get_camera_by_name(
    name: str,
    config_file: Path | None = None,
) -> OnvifCameraConfig | None:
    """Get a specific camera configuration by name.

    Args:
        name: Camera name (case-insensitive).
        config_file: Path to config.yaml.

    Returns:
        OnvifCameraConfig or None if not found.
    """
    cameras = load_cameras_config(config_file)
    name_lower = name.lower()

    for camera in cameras:
        if camera.name and camera.name.lower() == name_lower:
            return camera

    return None


def get_camera_by_ip(
    ip_address: str,
    config_file: Path | None = None,
) -> OnvifCameraConfig | None:
    """Get a specific camera configuration by IP address.

    This is useful for --ip mode where we want to look up a device's
    axis_username/axis_password credentials by its IP address.

    Args:
        ip_address: Camera IP address.
        config_file: Path to config.yaml.

    Returns:
        OnvifCameraConfig or None if not found.
    """
    cameras = load_cameras_config(config_file)
    ip_normalized = ip_address.strip()

    for camera in cameras:
        if camera.ip_address.strip() == ip_normalized:
            return camera

    return None


def _list_camera_names_raw(config_file: Path | None = None) -> list[str]:
    """Read camera names directly from YAML without env var interpolation.

    This is used as a fallback for shell completion when env vars aren't set.
    Only extracts the 'name' field from each device entry.

    Args:
        config_file: Path to config.yaml.

    Returns:
        List of camera names.
    """
    try:
        config_path = config_file or find_config_file()
        if config_path is None:
            return []

        with open(config_path) as f:
            raw_config = yaml.safe_load(f)

        if not raw_config:
            return []

        devices = raw_config.get("devices", [])
        names: list[str] = []
        for device in devices:
            name = device.get("name")
            if name and isinstance(name, str):
                names.append(name)
        return names
    except (OSError, yaml.YAMLError):
        return []


def list_camera_names(config_file: Path | None = None) -> list[str]:
    """List all camera names from config.

    Args:
        config_file: Path to config.yaml.

    Returns:
        List of camera names.
    """
    try:
        cameras = load_cameras_config(config_file)
        return [c.name for c in cameras if c.name]
    except (FileNotFoundError, ValueError):
        # ValueError occurs when env vars aren't set (e.g., during shell completion)
        # Fall back to reading names directly from YAML without interpolation
        return _list_camera_names_raw(config_file)


def camera_name_completion() -> list[str]:
    """Get camera names for shell completion.

    Returns:
        List of camera names for Typer autocompletion.
    """
    return list_camera_names()


# =============================================================================
# UniFi Protect Camera ID Cache (for shell completions)
# =============================================================================


def _get_protect_cache_file() -> Path:
    """Get path to UniFi Protect camera cache file.

    Returns:
        Path to protect_cameras.json in data directory.
    """
    return get_data_dir() / "protect_cameras.json"


def save_protect_cameras_cache(cameras: list[dict[str, str]]) -> None:
    """Save UniFi Protect camera IDs and names to cache.

    This enables shell completions for camera ID arguments.
    Called by `ucam list` command to update the cache.

    Args:
        cameras: List of dicts with 'id', 'name', and optionally 'host' keys.
    """
    cache_file = _get_protect_cache_file()
    try:
        with open(cache_file, "w") as f:
            json.dump(cameras, f, indent=2)
    except OSError:
        pass  # Silently fail if cache can't be written


def load_protect_cameras_cache() -> list[dict[str, str]]:
    """Load UniFi Protect cameras from cache.

    Returns:
        List of dicts with 'id', 'name', and optionally 'host' keys.
        Returns empty list if cache doesn't exist or is invalid.
    """
    cache_file = _get_protect_cache_file()
    try:
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return []


def protect_camera_id_completion() -> list[str]:
    """Get UniFi Protect camera IDs for shell completion.

    Returns completion options in format "id (name)" or just "id" if no name.
    Run `ucam list` first to populate the cache.

    Returns:
        List of camera ID strings with optional names for display.
    """
    cameras = load_protect_cameras_cache()
    completions: list[str] = []

    for cam in cameras:
        cam_id = cam.get("id", "")
        if cam_id:
            completions.append(cam_id)

    return completions


def protect_camera_completion_with_names() -> list[tuple[str, str]]:
    """Get camera completions with help text for Typer.

    Returns:
        List of (value, help_text) tuples for rich completions.
    """
    cameras = load_protect_cameras_cache()
    completions: list[tuple[str, str]] = []

    for cam in cameras:
        cam_id = cam.get("id", "")
        cam_name = cam.get("name", "")
        cam_host = cam.get("host", "")

        if cam_id:
            help_text = cam_name
            if cam_host:
                help_text = f"{cam_name} ({cam_host})" if cam_name else cam_host
            completions.append((cam_id, help_text))

    return completions
