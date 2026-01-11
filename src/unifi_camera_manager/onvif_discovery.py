"""ONVIF camera discovery and verification."""

import asyncio
import os
from dataclasses import dataclass

import onvif
from onvif import ONVIFCamera

from .config import OnvifCameraConfig

# Get the correct WSDL path from the installed onvif package
WSDL_DIR = os.path.join(os.path.dirname(onvif.__file__), "wsdl")


@dataclass
class OnvifCameraInfo:
    """Information retrieved from an ONVIF camera."""

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    is_accessible: bool
    error: str | None = None


async def verify_onvif_camera(config: OnvifCameraConfig) -> OnvifCameraInfo:
    """Verify an ONVIF camera is accessible and get its information.

    Args:
        config: ONVIF camera configuration.

    Returns:
        OnvifCameraInfo with camera details or error information.
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

    Args:
        config: ONVIF camera configuration.

    Returns:
        RTSP stream URI or None if not available.
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

    Args:
        ip_address: Camera IP address.
        port: Port to check (default 80 for HTTP/ONVIF).

    Returns:
        True if camera is reachable.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip_address, port),
            timeout=5.0,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, OSError):
        return False
