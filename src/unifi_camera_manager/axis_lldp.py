"""AXIS camera LLDP information retrieval via REST API.

This module provides functionality to retrieve LLDP (Link Layer Discovery Protocol)
information from AXIS cameras using the /config/rest/lldp/v1 REST API endpoint.

LLDP is useful for troubleshooting network connectivity issues by showing
how the camera sees its network neighbors (switches, ports, etc.).
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import OnvifCameraConfig
from .logging_config import log_debug


@dataclass
class LLDPNeighbor:
    """LLDP neighbor information.

    Attributes:
        chassis_id: Chassis ID of the neighbor device.
        port_id: Port ID on the neighbor device.
        port_description: Description of the port.
        system_name: System name of the neighbor.
        system_description: System description.
        capabilities: Device capabilities (router, bridge, etc.).
        management_address: Management IP address.
        ttl: Time to live value.
    """

    chassis_id: str = ""
    port_id: str = ""
    port_description: str = ""
    system_name: str = ""
    system_description: str = ""
    capabilities: list[str] = field(default_factory=list)
    management_address: str = ""
    ttl: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLDPNeighbor":
        """Create LLDPNeighbor from API response dictionary.

        Args:
            data: Dictionary from LLDP API response.

        Returns:
            LLDPNeighbor instance.
        """
        return cls(
            chassis_id=data.get("chassisId", "") or data.get("ChassisId", ""),
            port_id=data.get("portId", "") or data.get("PortId", ""),
            port_description=data.get("portDescription", "") or data.get("PortDescription", ""),
            system_name=data.get("systemName", "") or data.get("SystemName", ""),
            system_description=(
                data.get("systemDescription", "") or data.get("SystemDescription", "")
            ),
            capabilities=data.get("capabilities", []) or data.get("Capabilities", []),
            management_address=(
                data.get("managementAddress", "") or data.get("ManagementAddress", "")
            ),
            ttl=data.get("ttl", 0) or data.get("TTL", 0),
        )


@dataclass
class LLDPStatus:
    """LLDP status information.

    Attributes:
        enabled: Whether LLDP is enabled.
        transmit_interval: LLDP transmit interval in seconds.
        hold_multiplier: Hold multiplier for TTL calculation.
        chassis_id: Local chassis ID.
        port_id: Local port ID.
        system_name: Local system name.
        system_description: Local system description.
    """

    enabled: bool = False
    transmit_interval: int = 30
    hold_multiplier: int = 4
    chassis_id: str = ""
    port_id: str = ""
    system_name: str = ""
    system_description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLDPStatus":
        """Create LLDPStatus from API response dictionary.

        Args:
            data: Dictionary from LLDP API response.

        Returns:
            LLDPStatus instance.
        """
        return cls(
            enabled=data.get("enabled", False) or data.get("Enabled", False),
            transmit_interval=data.get("transmitInterval", 30) or data.get("TransmitInterval", 30),
            hold_multiplier=data.get("holdMultiplier", 4) or data.get("HoldMultiplier", 4),
            chassis_id=data.get("chassisId", "") or data.get("ChassisId", ""),
            port_id=data.get("portId", "") or data.get("PortId", ""),
            system_name=data.get("systemName", "") or data.get("SystemName", ""),
            system_description=(
                data.get("systemDescription", "") or data.get("SystemDescription", "")
            ),
        )


class AxisLLDPClient:
    """Client for retrieving LLDP information from AXIS cameras.

    This client uses the /config/rest/lldp/v1 endpoint to retrieve
    LLDP status and neighbor information.

    Attributes:
        config: ONVIF camera configuration with credentials.
        timeout: HTTP request timeout in seconds.

    Example:
        >>> config = OnvifCameraConfig(
        ...     ip_address="192.168.1.10", username="admin", password="secret"
        ... )
        >>> async with AxisLLDPClient(config) as client:
        ...     neighbors = await client.get_neighbors()
        ...     for n in neighbors:
        ...         print(f"Connected to: {n.system_name} port {n.port_id}")
    """

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the AXIS LLDP client.

        Args:
            config: Camera configuration with IP and credentials.
            timeout: HTTP request timeout in seconds.
        """
        self.config = config
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AxisLLDPClient":
        """Async context manager entry."""
        username, password = self.config.get_axis_credentials()
        is_axis_creds = self.config.axis_username and self.config.axis_password
        log_debug(
            f"AxisLLDPClient connecting to {self.config.ip_address} "
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
        """Get the base URL for LLDP API calls.

        Returns:
            Base URL string for the camera.
        """
        return f"http://{self.config.ip_address}:{self.config.port}/config/rest/lldp/v1"

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
        """
        client = self._ensure_connected()
        url = f"{self.base_url}/{path}" if path else self.base_url

        response = await client.get(url, headers={"accept": "application/json"})
        response.raise_for_status()

        return response.json()

    async def get_status(self) -> LLDPStatus:
        """Get LLDP status from the camera.

        Returns:
            LLDPStatus with current LLDP configuration.

        Raises:
            httpx.HTTPError: If request fails.
        """
        data = await self._get_json()

        # Handle different response formats
        if "data" in data:
            data = data["data"]

        return LLDPStatus.from_dict(data)

    async def get_neighbors(self) -> list[LLDPNeighbor]:
        """Get LLDP neighbors (connected network devices).

        Returns:
            List of LLDPNeighbor objects representing discovered neighbors.

        Raises:
            httpx.HTTPError: If request fails.
        """
        data = await self._get_json("neighbors")

        # Handle different response formats
        if "data" in data:
            data = data["data"]

        neighbors: list[LLDPNeighbor] = []

        # Data might be a list of neighbors or a dict with neighbors key
        if isinstance(data, list):
            for item in data:
                neighbors.append(LLDPNeighbor.from_dict(item))
        elif isinstance(data, dict):
            if "neighbors" in data:
                for item in data["neighbors"]:
                    neighbors.append(LLDPNeighbor.from_dict(item))
            elif "Neighbors" in data:
                for item in data["Neighbors"]:
                    neighbors.append(LLDPNeighbor.from_dict(item))
            else:
                # Single neighbor response
                neighbors.append(LLDPNeighbor.from_dict(data))

        return neighbors

    async def get_raw_status(self) -> dict[str, Any]:
        """Get raw LLDP status response.

        Returns:
            Raw JSON response from the LLDP API.

        Raises:
            httpx.HTTPError: If request fails.
        """
        return await self._get_json()

    async def get_raw_neighbors(self) -> dict[str, Any]:
        """Get raw LLDP neighbors response.

        Returns:
            Raw JSON response from the neighbors endpoint.

        Raises:
            httpx.HTTPError: If request fails.
        """
        return await self._get_json("neighbors")


async def get_lldp_neighbors(config: OnvifCameraConfig) -> list[LLDPNeighbor]:
    """Convenience function to get LLDP neighbors from a camera.

    Args:
        config: Camera configuration.

    Returns:
        List of LLDP neighbors.

    Example:
        >>> config = OnvifCameraConfig(...)
        >>> neighbors = await get_lldp_neighbors(config)
        >>> for n in neighbors:
        ...     print(f"Switch: {n.system_name}, Port: {n.port_description}")
    """
    async with AxisLLDPClient(config) as client:
        return await client.get_neighbors()


async def get_lldp_status(config: OnvifCameraConfig) -> LLDPStatus:
    """Convenience function to get LLDP status from a camera.

    Args:
        config: Camera configuration.

    Returns:
        LLDP status information.

    Example:
        >>> config = OnvifCameraConfig(...)
        >>> status = await get_lldp_status(config)
        >>> print(f"LLDP enabled: {status.enabled}")
    """
    async with AxisLLDPClient(config) as client:
        return await client.get_status()
