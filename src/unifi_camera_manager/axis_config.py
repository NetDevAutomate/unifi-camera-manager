"""AXIS camera configuration retrieval via VAPIX v2beta REST API.

This module provides functionality to retrieve and manage configuration
parameters from AXIS cameras using the modern JSON-based REST API.

The configuration is retrieved via the /config/rest/param/v2beta endpoint
which provides structured JSON access to all camera parameters.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import OnvifCameraConfig
from .logging_config import log_debug


@dataclass
class AxisConfig:
    """Complete AXIS camera configuration from v2beta API.

    Attributes:
        camera_name: Display name of the camera.
        camera_address: IP address of the camera.
        data: Raw JSON configuration data with nested structure.
    """

    camera_name: str
    camera_address: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def groups(self) -> list[str]:
        """List of top-level parameter groups."""
        return sorted(self.data.keys())

    @property
    def total_parameters(self) -> int:
        """Estimate total parameters by counting leaf values."""
        return self._count_params(self.data)

    def _count_params(self, obj: Any) -> int:
        """Recursively count leaf parameters."""
        if isinstance(obj, dict):
            return sum(self._count_params(v) for v in obj.values())
        if isinstance(obj, list):
            return sum(self._count_params(item) for item in obj)
        return 1

    def get_group(self, name: str) -> dict[str, Any] | None:
        """Get a parameter group by name.

        Args:
            name: Group name (e.g., "Network", "Image", "PTZ").

        Returns:
            Group data as dict or None if not found.
        """
        return self.data.get(name)

    def get_param(self, path: str) -> Any:
        """Get a parameter value by dot-notation path.

        Args:
            path: Dot-separated path (e.g., "Network.Bonjour.FriendlyName").

        Returns:
            Parameter value or None if not found.
        """
        parts = path.split(".")
        current: Any = self.data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def search_params(self, pattern: str) -> dict[str, Any]:
        """Search for parameters matching a pattern.

        Args:
            pattern: Case-insensitive substring to match in parameter paths.

        Returns:
            Dictionary of matching paths to values.
        """
        matches: dict[str, Any] = {}
        self._search_recursive(self.data, "", pattern.lower(), matches)
        return matches

    def _search_recursive(
        self,
        obj: Any,
        path: str,
        pattern: str,
        matches: dict[str, Any],
    ) -> None:
        """Recursively search for matching parameters."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                if pattern in new_path.lower() and not isinstance(value, (dict, list)):
                    matches[new_path] = value
                self._search_recursive(value, new_path, pattern, matches)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                self._search_recursive(item, new_path, pattern, matches)

    def flatten(self) -> dict[str, str]:
        """Flatten config to dot-notation key=value pairs.

        Returns:
            Dictionary of flattened parameter paths to string values.
        """
        flat: dict[str, str] = {}
        self._flatten_recursive(self.data, "", flat)
        return flat

    def _flatten_recursive(
        self,
        obj: Any,
        path: str,
        flat: dict[str, str],
    ) -> None:
        """Recursively flatten to dot-notation."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                self._flatten_recursive(value, new_path, flat)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{path}[{i}]"
                self._flatten_recursive(item, new_path, flat)
        else:
            flat[path] = str(obj) if obj is not None else ""


class AxisConfigClient:
    """Client for retrieving configuration from AXIS cameras via v2beta REST API.

    This client uses the /config/rest/param/v2beta endpoint to retrieve
    camera parameters and configuration as structured JSON.

    Attributes:
        config: ONVIF camera configuration with credentials.
        timeout: HTTP request timeout in seconds.

    Example:
        >>> config = OnvifCameraConfig(
        ...     address="192.168.1.10", username="admin", password="secret",
        ...     axis_username="root", axis_password="admin_pass"
        ... )
        >>> async with AxisConfigClient(config) as client:
        ...     cfg = await client.get_config()
        ...     print(f"Total parameters: {cfg.total_parameters}")
    """

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the AXIS config client.

        Args:
            config: Camera configuration with IP and credentials.
            timeout: HTTP request timeout in seconds.
        """
        self.config = config
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AxisConfigClient":
        """Async context manager entry."""
        # Use AXIS admin credentials for VAPIX API access
        # AXIS cameras require Digest authentication
        username, password = self.config.get_axis_credentials()
        is_axis_creds = self.config.axis_username and self.config.axis_password
        log_debug(
            f"AxisConfigClient connecting to {self.config.ip_address} "
            f"with username='{username}' "
            f"(using {'axis_username' if is_axis_creds else 'ONVIF username'} credentials)"
        )
        self._client = httpx.AsyncClient(
            auth=httpx.DigestAuth(username, password),
            timeout=self.timeout,
            verify=False,  # AXIS cameras often use self-signed certs
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def base_url(self) -> str:
        """Get the base URL for v2beta API calls.

        Returns:
            Base URL string for the camera.
        """
        return f"http://{self.config.ip_address}:{self.config.port}/config/rest/param/v2beta"

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

    async def _get_json(self, path: str = "") -> dict[str, Any]:
        """Make a GET request and return JSON data.

        Args:
            path: Optional path to append to base URL.

        Returns:
            JSON response data.

        Raises:
            httpx.HTTPError: If request fails.
            ValueError: If response indicates error.
        """
        client = self._ensure_connected()
        url = f"{self.base_url}/{path}" if path else self.base_url

        response = await client.get(url, headers={"accept": "application/json"})
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            error = data.get("error", {})
            raise ValueError(f"API error: {error.get('message', 'Unknown error')}")

        return data.get("data", {})

    async def get_config(self) -> AxisConfig:
        """Get complete camera configuration.

        Returns:
            AxisConfig with all parameters as nested JSON structure.

        Raises:
            httpx.HTTPError: If request fails.
        """
        data = await self._get_json()

        return AxisConfig(
            camera_name=self.config.name or self.config.ip_address,
            camera_address=self.config.ip_address,
            data=data,
        )

    async def get_group(self, group: str) -> dict[str, Any]:
        """Get parameters for a specific group.

        Args:
            group: Group name (e.g., "Network", "Image", "PTZ").

        Returns:
            Group data as nested JSON structure.

        Raises:
            httpx.HTTPError: If request fails.
        """
        return await self._get_json(group)

    async def get_parameter(self, path: str) -> Any:
        """Get a specific parameter value by path.

        Args:
            path: Dot-separated path (e.g., "Brand.ProdFullName").
                  Can use slashes or dots: "Brand/ProdFullName" or "Brand.ProdFullName"

        Returns:
            Parameter value.

        Raises:
            httpx.HTTPError: If request fails.
        """
        # Convert dots to slashes for API path
        api_path = path.replace(".", "/")
        return await self._get_json(api_path)

    async def get_device_info(self) -> dict[str, Any]:
        """Get basic device information from Brand group.

        Returns:
            Dictionary with device info (Brand, ProdFullName, etc.).
        """
        return await self._get_json("Brand")

    async def get_network_config(self) -> dict[str, Any]:
        """Get network configuration parameters.

        Returns:
            Dictionary of network-related parameters.
        """
        return await self._get_json("Network")

    async def get_image_config(self) -> dict[str, Any]:
        """Get image/video configuration parameters.

        Returns:
            Dictionary of image-related parameters.
        """
        return await self._get_json("Image")

    async def get_ptz_config(self) -> dict[str, Any]:
        """Get PTZ configuration parameters.

        Returns:
            Dictionary of PTZ-related parameters.
        """
        return await self._get_json("PTZ")


async def get_axis_config(config: OnvifCameraConfig) -> AxisConfig:
    """Convenience function to get full configuration from a camera.

    Args:
        config: Camera configuration.

    Returns:
        AxisConfig with all parameters.

    Example:
        >>> config = OnvifCameraConfig(...)
        >>> cfg = await get_axis_config(config)
        >>> print(f"Device: {cfg.get_param('Brand.ProdFullName')}")
    """
    async with AxisConfigClient(config) as client:
        return await client.get_config()
