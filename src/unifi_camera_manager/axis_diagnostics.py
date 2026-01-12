"""AXIS camera stream and network diagnostics via VAPIX v2beta REST API.

This module provides functionality to retrieve stream configuration, RTSP settings,
RTP configuration, and other network-related parameters useful for troubleshooting
connectivity and streaming issues.

Particularly useful for diagnosing issues like stream stops when paired with
third-party devices (e.g., UniFi AI Port).
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import OnvifCameraConfig
from .logging_config import log_debug


@dataclass
class RTSPConfig:
    """RTSP server configuration.

    Attributes:
        enabled: Whether RTSP server is enabled.
        port: RTSP port number (default 554).
        authentication: Authentication type (none, basic, digest).
        timeout: Session timeout in seconds.
        allow_path_arguments: Whether path arguments are allowed.
    """

    enabled: bool = True
    port: int = 554
    authentication: str = "digest"
    timeout: int = 60
    allow_path_arguments: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RTSPConfig":
        """Create RTSPConfig from API response dictionary."""
        return cls(
            enabled=data.get("Enabled", True),
            port=data.get("Port", 554),
            authentication=data.get("Authentication", "digest"),
            timeout=data.get("Timeout", 60),
            allow_path_arguments=data.get("AllowPathArguments", True),
        )


@dataclass
class RTPConfig:
    """RTP configuration.

    Attributes:
        start_port: Start of RTP port range.
        end_port: End of RTP port range.
        multicast_enabled: Whether multicast is enabled.
        multicast_address: Multicast address if enabled.
    """

    start_port: int = 50000
    end_port: int = 50999
    multicast_enabled: bool = False
    multicast_address: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RTPConfig":
        """Create RTPConfig from API response dictionary."""
        return cls(
            start_port=data.get("StartPort", 50000),
            end_port=data.get("EndPort", 50999),
            multicast_enabled=data.get("Multicast", {}).get("Enabled", False),
            multicast_address=data.get("Multicast", {}).get("Address", ""),
        )


@dataclass
class StreamProfile:
    """Stream profile configuration.

    Attributes:
        name: Profile name (e.g., "Quality", "Balanced", "Bandwidth").
        description: Profile description.
        video_codec: Video codec (H.264, H.265, MJPEG).
        resolution: Resolution string (e.g., "1920x1080").
        fps: Frame rate.
        bitrate: Bitrate in kbps (0 = variable).
        gop_length: GOP length (keyframe interval).
        compression: Compression level (1-100).
        parameters: Additional codec parameters.
    """

    name: str = ""
    description: str = ""
    video_codec: str = "H.264"
    resolution: str = ""
    fps: int = 30
    bitrate: int = 0
    gop_length: int = 32
    compression: int = 30
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "StreamProfile":
        """Create StreamProfile from API response dictionary."""
        return cls(
            name=name,
            description=data.get("Description", ""),
            video_codec=data.get("VideoCodec", "H.264"),
            resolution=data.get("Resolution", ""),
            fps=data.get("Fps", 30),
            bitrate=data.get("Bitrate", 0),
            gop_length=data.get("GOPLength", 32),
            compression=data.get("Compression", 30),
            parameters=data.get("Parameters", {}),
        )


@dataclass
class NetworkDiagnostics:
    """Network configuration diagnostics.

    Attributes:
        hostname: Device hostname.
        dhcp_enabled: Whether DHCP is enabled.
        ip_address: Current IP address.
        subnet_mask: Subnet mask.
        gateway: Default gateway.
        dns_servers: List of DNS servers.
        mtu: MTU size.
        ipv6_enabled: Whether IPv6 is enabled.
    """

    hostname: str = ""
    dhcp_enabled: bool = True
    ip_address: str = ""
    subnet_mask: str = ""
    gateway: str = ""
    dns_servers: list[str] = field(default_factory=list)
    mtu: int = 1500
    ipv6_enabled: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NetworkDiagnostics":
        """Create NetworkDiagnostics from API response dictionary."""
        # Handle nested structure from param/v2beta
        bonjour = data.get("Bonjour", {})
        interface = data.get("Interface", {}).get("I0", {})

        return cls(
            hostname=bonjour.get("FriendlyName", ""),
            dhcp_enabled=interface.get("DHCPEnabled", True),
            ip_address=interface.get("IPAddress", ""),
            subnet_mask=interface.get("SubnetMask", ""),
            gateway=interface.get("Gateway", ""),
            dns_servers=data.get("DNSServers", []),
            mtu=interface.get("MTU", 1500),
            ipv6_enabled=data.get("IPv6", {}).get("Enabled", False),
        )


@dataclass
class StreamDiagnostics:
    """Complete stream diagnostics report.

    Attributes:
        camera_name: Camera name or IP address.
        rtsp: RTSP configuration.
        rtp: RTP configuration.
        profiles: List of stream profiles.
        network: Network configuration.
        raw_data: Raw API response data for debugging.
        errors: List of errors encountered during diagnostics retrieval.
    """

    camera_name: str = ""
    rtsp: RTSPConfig = field(default_factory=RTSPConfig)
    rtp: RTPConfig = field(default_factory=RTPConfig)
    profiles: list[StreamProfile] = field(default_factory=list)
    network: NetworkDiagnostics = field(default_factory=NetworkDiagnostics)
    raw_data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AxisDiagnosticsClient:
    """Client for stream and network diagnostics from AXIS cameras.

    This client uses the /config/rest/param/v2beta endpoint to retrieve
    stream profiles, RTSP settings, RTP configuration, and network
    parameters useful for troubleshooting connectivity issues.

    Attributes:
        config: ONVIF camera configuration with credentials.
        timeout: HTTP request timeout in seconds.

    Example:
        >>> config = OnvifCameraConfig(
        ...     ip_address="192.168.1.10", username="admin", password="secret"
        ... )
        >>> async with AxisDiagnosticsClient(config) as client:
        ...     diagnostics = await client.get_full_diagnostics()
        ...     print(f"RTSP Port: {diagnostics.rtsp.port}")
        ...     for profile in diagnostics.profiles:
        ...         print(f"Profile {profile.name}: {profile.resolution}")
    """

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the diagnostics client.

        Args:
            config: Camera configuration with IP and credentials.
            timeout: HTTP request timeout in seconds.
        """
        self.config = config
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AxisDiagnosticsClient":
        """Async context manager entry."""
        username, password = self.config.get_axis_credentials()
        is_axis_creds = self.config.axis_username and self.config.axis_password
        log_debug(
            f"AxisDiagnosticsClient connecting to {self.config.ip_address} "
            f"with username='{username}' "
            f"(using {'axis_username' if is_axis_creds else 'ONVIF username'} credentials)"
        )
        self._client = httpx.AsyncClient(
            auth=httpx.DigestAuth(username, password),
            timeout=self.timeout,
            verify=False,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def base_url(self) -> str:
        """Get the base URL for param v2beta API calls."""
        return f"http://{self.config.ip_address}:{self.config.port}/config/rest/param/v2beta"

    def _ensure_connected(self) -> httpx.AsyncClient:
        """Ensure client is connected."""
        if not self._client:
            raise RuntimeError("Client not connected. Use async context manager.")
        return self._client

    async def _get_json(self, path: str = "") -> dict[str, Any]:
        """Make a GET request and return JSON data."""
        client = self._ensure_connected()
        url = f"{self.base_url}/{path}" if path else self.base_url

        response = await client.get(url, headers={"accept": "application/json"})
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            error = data.get("error", {})
            raise ValueError(f"API error: {error.get('message', 'Unknown error')}")

        return data.get("data", {})

    async def get_rtsp_config(self) -> RTSPConfig:
        """Get RTSP server configuration.

        Returns:
            RTSPConfig with current RTSP settings.
        """
        data = await self._get_json("Network/RTSP")
        return RTSPConfig.from_dict(data)

    async def get_rtp_config(self) -> RTPConfig:
        """Get RTP configuration.

        Returns:
            RTPConfig with current RTP port settings.
        """
        data = await self._get_json("Network/RTP")
        return RTPConfig.from_dict(data)

    async def get_stream_profiles(self) -> list[StreamProfile]:
        """Get all stream profiles.

        Returns:
            List of StreamProfile objects.
        """
        data = await self._get_json("StreamProfile")

        profiles: list[StreamProfile] = []
        for name, profile_data in data.items():
            if isinstance(profile_data, dict):
                profiles.append(StreamProfile.from_dict(name, profile_data))

        return profiles

    async def get_network_config(self) -> NetworkDiagnostics:
        """Get network configuration.

        Returns:
            NetworkDiagnostics with current network settings.
        """
        data = await self._get_json("Network")
        return NetworkDiagnostics.from_dict(data)

    async def get_full_diagnostics(self) -> StreamDiagnostics:
        """Get complete stream and network diagnostics.

        Returns:
            StreamDiagnostics with all configuration data.
        """
        diagnostics = StreamDiagnostics(
            camera_name=self.config.name or self.config.ip_address,
        )

        # Collect all data, capturing errors for user feedback
        try:
            diagnostics.rtsp = await self.get_rtsp_config()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                diagnostics.errors.append("RTSP config: Authentication failed (401)")
            else:
                diagnostics.errors.append(f"RTSP config: HTTP {e.response.status_code}")
        except Exception as e:
            diagnostics.errors.append(f"RTSP config: {e}")

        try:
            diagnostics.rtp = await self.get_rtp_config()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                diagnostics.errors.append("RTP config: Authentication failed (401)")
            else:
                diagnostics.errors.append(f"RTP config: HTTP {e.response.status_code}")
        except Exception as e:
            diagnostics.errors.append(f"RTP config: {e}")

        try:
            diagnostics.profiles = await self.get_stream_profiles()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                diagnostics.errors.append("Stream profiles: Authentication failed (401)")
            else:
                diagnostics.errors.append(f"Stream profiles: HTTP {e.response.status_code}")
        except Exception as e:
            diagnostics.errors.append(f"Stream profiles: {e}")

        try:
            diagnostics.network = await self.get_network_config()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                diagnostics.errors.append("Network config: Authentication failed (401)")
            else:
                diagnostics.errors.append(f"Network config: HTTP {e.response.status_code}")
        except Exception as e:
            diagnostics.errors.append(f"Network config: {e}")

        return diagnostics

    async def get_image_config(self) -> dict[str, Any]:
        """Get image/video source configuration.

        Returns:
            Raw image configuration data.
        """
        return await self._get_json("Image")

    async def get_stream_cache(self) -> dict[str, Any]:
        """Get stream cache configuration.

        Returns:
            Raw stream cache configuration data.
        """
        return await self._get_json("StreamCache")

    async def get_qos_config(self) -> dict[str, Any]:
        """Get QoS (Quality of Service) configuration.

        Returns:
            Raw QoS configuration data.
        """
        try:
            return await self._get_json("Network/QoS")
        except Exception:
            return {}


async def get_stream_diagnostics(config: OnvifCameraConfig) -> StreamDiagnostics:
    """Convenience function to get full stream diagnostics.

    Args:
        config: Camera configuration.

    Returns:
        StreamDiagnostics with all configuration data.

    Example:
        >>> config = OnvifCameraConfig(...)
        >>> diagnostics = await get_stream_diagnostics(config)
        >>> print(f"RTSP enabled: {diagnostics.rtsp.enabled}")
    """
    async with AxisDiagnosticsClient(config) as client:
        return await client.get_full_diagnostics()
