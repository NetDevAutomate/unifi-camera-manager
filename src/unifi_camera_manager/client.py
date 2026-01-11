"""UniFi Protect API client wrapper."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

from uiprotect import ProtectApiClient
from uiprotect.data import Camera, ModelType

from .config import ProtectConfig


@dataclass
class CameraInfo:
    """Simplified camera information."""

    id: str
    name: str
    type: str
    host: str | None
    is_adopted: bool
    state: str
    last_seen: datetime | None
    is_third_party: bool

    @classmethod
    def from_camera(cls, camera: Camera) -> "CameraInfo":
        """Create CameraInfo from a uiprotect Camera object."""
        # Determine if it's a third-party camera (non-UVC prefix)
        camera_type = str(camera.type) if camera.type else "Unknown"
        is_third_party = not camera_type.startswith("UVC")

        return cls(
            id=camera.id,
            name=camera.name,
            type=camera_type,
            host=camera.host if hasattr(camera, "host") else None,
            is_adopted=camera.is_adopted,
            state=str(camera.state) if camera.state else "Unknown",
            last_seen=camera.last_seen if hasattr(camera, "last_seen") else None,
            is_third_party=is_third_party,
        )


class UnifiProtectClient:
    """Wrapper around uiprotect ProtectApiClient with context management."""

    def __init__(self, config: ProtectConfig, include_unadopted: bool = True):
        """Initialize the client.

        Args:
            config: UniFi Protect connection configuration.
            include_unadopted: Whether to include unadopted devices.
        """
        self.config = config
        self.include_unadopted = include_unadopted
        self._client: ProtectApiClient | None = None

    async def connect(self) -> None:
        """Connect to UniFi Protect and initialize the client."""
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
        """Disconnect from UniFi Protect."""
        if self._client:
            try:
                await self._client.async_disconnect()
            except Exception:
                pass  # Ignore disconnect errors
            self._client = None

    @property
    def client(self) -> ProtectApiClient:
        """Get the underlying client, raising if not connected."""
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    async def list_cameras(self) -> list[CameraInfo]:
        """List all cameras (adopted and unadopted)."""
        cameras = []
        for camera in self.client.bootstrap.cameras.values():
            cameras.append(CameraInfo.from_camera(camera))
        return cameras

    async def get_camera(self, camera_id: str) -> CameraInfo | None:
        """Get a specific camera by ID."""
        camera = self.client.bootstrap.cameras.get(camera_id)
        if camera:
            return CameraInfo.from_camera(camera)
        return None

    async def get_camera_by_ip(self, ip_address: str) -> CameraInfo | None:
        """Get a camera by its IP address."""
        for camera in self.client.bootstrap.cameras.values():
            if hasattr(camera, "host") and camera.host == ip_address:
                return CameraInfo.from_camera(camera)
        return None

    async def adopt_camera(self, camera_id: str) -> bool:
        """Adopt an unadopted camera.

        Args:
            camera_id: The ID of the camera to adopt.

        Returns:
            True if adoption was initiated successfully.
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
        """
        try:
            await self.client.reboot_device(ModelType.CAMERA, camera_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to reboot camera: {e}") from e

    async def get_nvr_info(self) -> dict:
        """Get NVR information."""
        nvr = self.client.bootstrap.nvr
        return {
            "id": nvr.id,
            "name": nvr.name,
            "model": str(nvr.model) if nvr.model else "Unknown",
            "version": nvr.version,
            "host": nvr.host if hasattr(nvr, "host") else None,
        }


@asynccontextmanager
async def get_protect_client(
    config: ProtectConfig, include_unadopted: bool = True
) -> AsyncIterator[UnifiProtectClient]:
    """Context manager for UniFi Protect client.

    Usage:
        async with get_protect_client(config) as client:
            cameras = await client.list_cameras()
    """
    client = UnifiProtectClient(config, include_unadopted)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()
