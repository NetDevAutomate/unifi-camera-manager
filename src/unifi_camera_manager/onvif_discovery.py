"""ONVIF camera discovery and verification.

This module provides functions for verifying ONVIF camera accessibility,
retrieving device information, and checking network connectivity.
"""

import asyncio
import os

import onvif
from onvif import ONVIFCamera

from .config import OnvifCameraConfig
from .models import OnvifCameraInfo

# Get the correct WSDL path from the installed onvif package
WSDL_DIR = os.path.join(os.path.dirname(onvif.__file__), "wsdl")


async def verify_onvif_camera(config: OnvifCameraConfig) -> OnvifCameraInfo:
    """Verify an ONVIF camera is accessible and retrieve its information.

    Connects to an ONVIF camera using the provided configuration and
    retrieves basic device information including manufacturer, model,
    firmware version, and serial number.

    Args:
        config: ONVIF camera configuration with IP address and credentials.

    Returns:
        OnvifCameraInfo with camera details if accessible, or error
        information if connection failed.

    Example:
        >>> config = OnvifCameraConfig(ip_address="192.168.1.10", username="admin", password="pass")
        >>> info = await verify_onvif_camera(config)
        >>> if info.is_accessible:
        ...     print(f"Found: {info.manufacturer} {info.model}")
        ... else:
        ...     print(f"Error: {info.error}")
    """
    try:
        # Create ONVIF camera instance with correct WSDL path
        camera = ONVIFCamera(
            config.ip_address,
            config.port,
            config.username,
            config.password,
            wsdl_dir=WSDL_DIR,
        )

        # Initialize and get device information
        await camera.update_xaddrs()
        device_service = await camera.create_devicemgmt_service()

        # Get device information
        device_info = await device_service.GetDeviceInformation()

        return OnvifCameraInfo(
            manufacturer=device_info.Manufacturer or "Unknown",
            model=device_info.Model or "Unknown",
            firmware_version=device_info.FirmwareVersion or "Unknown",
            serial_number=device_info.SerialNumber or "Unknown",
            hardware_id=device_info.HardwareId or "Unknown",
            is_accessible=True,
        )
    except Exception as e:
        return OnvifCameraInfo(
            manufacturer="",
            model="",
            firmware_version="",
            serial_number="",
            hardware_id="",
            is_accessible=False,
            error=str(e),
        )


async def get_onvif_stream_uri(config: OnvifCameraConfig) -> str | None:
    """Get the RTSP stream URI from an ONVIF camera.

    Connects to the camera and retrieves the RTSP stream URI for
    the first available video profile.

    Args:
        config: ONVIF camera configuration with IP address and credentials.

    Returns:
        RTSP stream URI string or None if unavailable.

    Example:
        >>> config = OnvifCameraConfig(ip_address="192.168.1.10", username="admin", password="pass")
        >>> uri = await get_onvif_stream_uri(config)
        >>> if uri:
        ...     print(f"Stream: {uri}")
    """
    try:
        camera = ONVIFCamera(
            config.ip_address,
            config.port,
            config.username,
            config.password,
            wsdl_dir=WSDL_DIR,
        )

        await camera.update_xaddrs()
        media_service = await camera.create_media_service()

        # Get profiles
        profiles = await media_service.GetProfiles()
        if not profiles:
            return None

        # Get stream URI for first profile
        stream_setup = {
            "Stream": "RTP-Unicast",
            "Transport": {"Protocol": "RTSP"},
        }
        uri_response = await media_service.GetStreamUri(
            {"StreamSetup": stream_setup, "ProfileToken": profiles[0].token}
        )

        return uri_response.Uri
    except Exception:
        return None


async def check_camera_connectivity(ip_address: str, port: int = 80) -> bool:
    """Check if a camera is reachable on the network.

    Attempts to establish a TCP connection to the camera on the
    specified port to verify network connectivity.

    Args:
        ip_address: Camera IP address to check.
        port: Port to check (default 80 for HTTP/ONVIF).

    Returns:
        True if camera is reachable, False otherwise.

    Example:
        >>> is_online = await check_camera_connectivity("192.168.1.10")
        >>> if is_online:
        ...     print("Camera is online")
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_address, port),
            timeout=5.0,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (TimeoutError, OSError):
        return False
