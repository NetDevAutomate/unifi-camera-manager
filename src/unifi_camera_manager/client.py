"""UniFi Protect API client wrapper.

This module provides an async client for interacting with UniFi Protect NVRs,
supporting camera management operations like listing, adoption, and control.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from uiprotect import ProtectApiClient
from uiprotect.data import Camera, ModelType

from .config import ProtectConfig
from .models import CameraInfo, NvrInfo


def camera_info_from_protect(camera: Camera) -> CameraInfo:
    """Create CameraInfo from a uiprotect Camera object.

    Args:
        camera: Camera object from uiprotect library.

    Returns:
        CameraInfo with extracted camera data.
    """
    camera_type = str(camera.type) if camera.type else "Unknown"
    is_third_party = not camera_type.startswith("UVC")

    return CameraInfo(
        id=camera.id,
        name=camera.name,
        type=camera_type,
        host=str(camera.host) if hasattr(camera, "host") and camera.host else None,
        is_adopted=camera.is_adopted,
        state=str(camera.state) if camera.state else "Unknown",
        last_seen=camera.last_seen if hasattr(camera, "last_seen") else None,
        is_third_party=is_third_party,
    )


class UnifiProtectClient:
    """Wrapper around uiprotect ProtectApiClient with context management.

    Provides a simplified interface for common UniFi Protect operations
    with proper async context management and error handling.

    Attributes:
        config: UniFi Protect connection configuration.
        include_unadopted: Whether to include unadopted devices in queries.

    Example:
        >>> async with get_protect_client(config) as client:
        ...     cameras = await client.list_cameras()
        ...     for cam in cameras:
        ...         print(f"{cam.name}: {cam.host}")
    """

    def __init__(self, config: ProtectConfig, include_unadopted: bool = True) -> None:
        """Initialize the client.

        Args:
            config: UniFi Protect connection configuration.
            include_unadopted: Whether to include unadopted devices.
        """
        self.config = config
        self.include_unadopted = include_unadopted
        self._client: ProtectApiClient | None = None

    async def connect(self) -> None:
        """Connect to UniFi Protect and initialize the client.

        Raises:
            Exception: If connection fails.
        """
        self._client = ProtectApiClient(
            host=self.config.address,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            verify_ssl=self.config.ssl_verify,
            ignore_unadopted=not self.include_unadopted,
        )
        await self._client.update()

    async def disconnect(self) -> None:
        """Disconnect from UniFi Protect and close the session."""
        if self._client:
            try:
                await self._client.async_disconnect_ws()
            except Exception:
                pass  # Ignore websocket disconnect errors
            try:
                await self._client.close_session()
            except Exception:
                pass  # Ignore session close errors
            self._client = None

    @property
    def client(self) -> ProtectApiClient:
        """Get the underlying client, raising if not connected.

        Returns:
            The connected ProtectApiClient instance.

        Raises:
            RuntimeError: If client is not connected.
        """
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    async def list_cameras(self) -> list[CameraInfo]:
        """List all cameras (adopted and unadopted).

        Returns:
            List of CameraInfo objects for all cameras.
        """
        cameras: list[CameraInfo] = []
        for camera in self.client.bootstrap.cameras.values():
            cameras.append(camera_info_from_protect(camera))
        return cameras

    async def get_camera(self, camera_id: str) -> CameraInfo | None:
        """Get a specific camera by ID.

        Args:
            camera_id: The unique camera identifier.

        Returns:
            CameraInfo if found, None otherwise.
        """
        camera = self.client.bootstrap.cameras.get(camera_id)
        if camera:
            return camera_info_from_protect(camera)
        return None

    async def get_camera_by_ip(self, ip_address: str) -> CameraInfo | None:
        """Get a camera by its IP address.

        Args:
            ip_address: Camera IP address to search for.

        Returns:
            CameraInfo if found, None otherwise.
        """
        for camera in self.client.bootstrap.cameras.values():
            if hasattr(camera, "host") and camera.host == ip_address:
                return camera_info_from_protect(camera)
        return None

    async def adopt_camera(self, camera_id: str) -> bool:
        """Adopt an unadopted camera.

        Args:
            camera_id: The ID of the camera to adopt.

        Returns:
            True if adoption was initiated successfully.

        Raises:
            RuntimeError: If adoption fails.
        """
        try:
            await self.client.adopt_device(ModelType.CAMERA, camera_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to adopt camera: {e}") from e

    async def unadopt_camera(self, camera_id: str) -> bool:
        """Unadopt/remove a camera.

        Args:
            camera_id: The ID of the camera to unadopt.

        Returns:
            True if unadoption was initiated successfully.

        Raises:
            RuntimeError: If unadoption fails.
        """
        try:
            await self.client.unadopt_device(ModelType.CAMERA, camera_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to unadopt camera: {e}") from e

    async def reboot_camera(self, camera_id: str) -> bool:
        """Reboot a camera.

        Args:
            camera_id: The ID of the camera to reboot.

        Returns:
            True if reboot was initiated successfully.

        Raises:
            RuntimeError: If reboot fails.
        """
        try:
            await self.client.reboot_device(ModelType.CAMERA, camera_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to reboot camera: {e}") from e

    async def get_nvr_info(self) -> NvrInfo:
        """Get NVR information.

        Returns:
            NvrInfo with NVR details.
        """
        nvr = self.client.bootstrap.nvr
        return NvrInfo(
            id=nvr.id,
            name=nvr.name,
            model=str(nvr.model) if nvr.model else "Unknown",
            version=str(nvr.version) if nvr.version else None,
            host=str(nvr.host) if hasattr(nvr, "host") and nvr.host else None,
        )


@asynccontextmanager
async def get_protect_client(
    config: ProtectConfig,
    include_unadopted: bool = True,
) -> AsyncIterator[UnifiProtectClient]:
    """Context manager for UniFi Protect client.

    Provides automatic connection management with proper cleanup.

    Args:
        config: UniFi Protect connection configuration.
        include_unadopted: Whether to include unadopted devices.

    Yields:
        Connected UnifiProtectClient instance.

    Example:
        >>> async with get_protect_client(config) as client:
        ...     cameras = await client.list_cameras()
    """
    client = UnifiProtectClient(config, include_unadopted)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()
