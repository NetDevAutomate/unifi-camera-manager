"""Comprehensive ONVIF camera management.

This module provides full ONVIF camera control including device information,
video profiles, stream management, PTZ control, image settings, and system
operations through the ONVIF protocol.
"""

import os
from datetime import datetime
from typing import Any

import onvif
from onvif import ONVIFCamera

from .config import OnvifCameraConfig
from .models import (
    CameraCapabilities,
    ImageSettings,
    NetworkConfig,
    OnvifService,
    PTZDirection,
    PTZPreset,
    PTZStatus,
    StreamInfo,
    SystemInfo,
    VideoProfile,
)

# Get the correct WSDL path from the installed onvif package
WSDL_DIR = os.path.join(os.path.dirname(onvif.__file__), "wsdl")


class OnvifCameraManager:
    """Comprehensive ONVIF camera management class.

    Provides a unified interface for interacting with ONVIF-compliant cameras,
    including device management, media services, PTZ control, and imaging.

    Attributes:
        config: ONVIF camera configuration with credentials.
        is_connected: Whether the camera connection is active.

    Example:
        >>> config = OnvifCameraConfig(ip_address="192.168.1.10", username="admin", password="pass")
        >>> async with OnvifCamera(config) as camera:
        ...     info = await camera.get_system_info()
        ...     print(f"Camera: {info.manufacturer} {info.model}")
    """

    def __init__(self, config: OnvifCameraConfig) -> None:
        """Initialize the camera manager.

        Args:
            config: ONVIF camera configuration with connection details.
        """
        self.config = config
        self._camera: ONVIFCamera | None = None
        self._device_service: Any = None
        self._media_service: Any = None
        self._ptz_service: Any = None
        self._imaging_service: Any = None
        self._profiles: list[Any] = []

    async def connect(self) -> None:
        """Connect to the camera and initialize ONVIF services.

        Establishes connection to the camera and initializes core services
        (device management, media). Optional services (PTZ, imaging) are
        initialized if available.

        Raises:
            Exception: If connection or service initialization fails.
        """
        self._camera = ONVIFCamera(
            self.config.ip_address,
            self.config.port,
            self.config.username,
            self.config.password,
            wsdl_dir=WSDL_DIR,
        )
        await self._camera.update_xaddrs()

        # Fix XAddrs if camera returns 127.0.0.1 (common with AXIS cameras)
        # Replace any localhost references with the actual camera IP
        for service_name, xaddr in self._camera.xaddrs.items():
            if "127.0.0.1" in xaddr or "localhost" in xaddr:
                fixed_xaddr = xaddr.replace("127.0.0.1", self.config.ip_address)
                fixed_xaddr = fixed_xaddr.replace("localhost", self.config.ip_address)
                self._camera.xaddrs[service_name] = fixed_xaddr

        # Initialize core services (these are async in onvif-zeep-async)
        self._device_service = await self._camera.create_devicemgmt_service()
        self._media_service = await self._camera.create_media_service()

        # Try to initialize optional services
        try:
            self._ptz_service = await self._camera.create_ptz_service()
        except Exception:
            self._ptz_service = None

        try:
            self._imaging_service = await self._camera.create_imaging_service()
        except Exception:
            self._imaging_service = None

        # Cache profiles
        self._profiles = await self._media_service.GetProfiles()

    async def disconnect(self) -> None:
        """Disconnect from the camera and clean up resources."""
        # Close the ONVIFCamera and its aiohttp sessions
        if self._camera is not None:
            try:
                await self._camera.close()
            except Exception:
                pass  # Best effort cleanup

        self._camera = None
        self._device_service = None
        self._media_service = None
        self._ptz_service = None
        self._imaging_service = None
        self._profiles = []

    @property
    def is_connected(self) -> bool:
        """Check if connected to the camera.

        Returns:
            True if connected, False otherwise.
        """
        return self._camera is not None

    def _ensure_connected(self) -> None:
        """Verify connection is active.

        Raises:
            RuntimeError: If not connected to camera.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to camera. Call connect() first.")

    # =========================================================================
    # Device Information
    # =========================================================================

    async def get_system_info(self) -> SystemInfo:
        """Get comprehensive system information from the camera.

        Returns:
            SystemInfo with manufacturer, model, firmware, and other details.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        device_info = await self._device_service.GetDeviceInformation()

        # Try to get system date/time
        system_datetime = None
        try:
            dt_response = await self._device_service.GetSystemDateAndTime()
            if dt_response.UTCDateTime:
                utc = dt_response.UTCDateTime
                system_datetime = datetime(
                    utc.Date.Year,
                    utc.Date.Month,
                    utc.Date.Day,
                    utc.Time.Hour,
                    utc.Time.Minute,
                    utc.Time.Second,
                )
        except Exception:
            pass

        return SystemInfo(
            manufacturer=device_info.Manufacturer or "Unknown",
            model=device_info.Model or "Unknown",
            firmware_version=device_info.FirmwareVersion or "Unknown",
            serial_number=device_info.SerialNumber or "Unknown",
            hardware_id=device_info.HardwareId or "Unknown",
            system_date_time=system_datetime,
        )

    async def get_capabilities(self) -> CameraCapabilities:
        """Get camera capabilities and supported features.

        Returns:
            CameraCapabilities with feature flags and supported encodings.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        capabilities = CameraCapabilities()

        try:
            caps = await self._device_service.GetCapabilities({"Category": "All"})

            if hasattr(caps, "PTZ") and caps.PTZ:
                capabilities.has_ptz = True

            if hasattr(caps, "Media") and caps.Media:
                if hasattr(caps.Media, "StreamingCapabilities"):
                    stream_caps = caps.Media.StreamingCapabilities
                    if hasattr(stream_caps, "RTPMulticast"):
                        capabilities.has_audio = True

            if hasattr(caps, "Events") and caps.Events:
                capabilities.has_events = True

            if hasattr(caps, "Analytics") and caps.Analytics:
                capabilities.has_analytics = True

        except Exception:
            pass

        # Get supported encodings from profiles
        supported_encodings: list[str] = []
        for profile in self._profiles:
            if hasattr(profile, "VideoEncoderConfiguration"):
                enc = profile.VideoEncoderConfiguration
                if hasattr(enc, "Encoding") and enc.Encoding:
                    encoding = str(enc.Encoding)
                    if encoding not in supported_encodings:
                        supported_encodings.append(encoding)

        return CameraCapabilities(
            has_ptz=capabilities.has_ptz,
            has_audio=capabilities.has_audio,
            has_relay=capabilities.has_relay,
            has_analytics=capabilities.has_analytics,
            has_recording=capabilities.has_recording,
            has_events=capabilities.has_events,
            supported_encodings=supported_encodings,
            max_profiles=len(self._profiles),
        )

    async def get_scopes(self) -> list[str]:
        """Get device scopes (ONVIF profile information).

        Returns:
            List of ONVIF scope URIs describing device capabilities.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()
        scopes = await self._device_service.GetScopes()
        return [str(scope.ScopeItem) for scope in scopes]

    # =========================================================================
    # Video Profiles and Streams
    # =========================================================================

    async def get_profiles(self) -> list[VideoProfile]:
        """Get all video profiles configured on the camera.

        Returns:
            List of VideoProfile objects with encoding and resolution details.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        profiles: list[VideoProfile] = []
        for profile in self._profiles:
            if not hasattr(profile, "VideoEncoderConfiguration"):
                continue

            enc = profile.VideoEncoderConfiguration
            res = enc.Resolution if hasattr(enc, "Resolution") else None

            profiles.append(
                VideoProfile(
                    token=profile.token,
                    name=profile.Name or profile.token,
                    encoding=str(enc.Encoding) if hasattr(enc, "Encoding") else "Unknown",
                    resolution_width=res.Width if res else 0,
                    resolution_height=res.Height if res else 0,
                    frame_rate=float(enc.RateControl.FrameRateLimit)
                    if hasattr(enc, "RateControl")
                    else 0.0,
                    bitrate=int(enc.RateControl.BitrateLimit)
                    if hasattr(enc, "RateControl")
                    else None,
                    quality=float(enc.Quality) if hasattr(enc, "Quality") else None,
                )
            )

        return profiles

    def _fix_uri(self, uri: str) -> str:
        """Fix URIs that contain 127.0.0.1 or localhost.

        Args:
            uri: Original URI that may contain localhost references.

        Returns:
            Fixed URI with actual camera IP address.
        """
        if not uri:
            return uri
        uri = uri.replace("127.0.0.1", self.config.ip_address)
        uri = uri.replace("localhost", self.config.ip_address)
        return uri

    async def get_stream_uri(self, profile_token: str | None = None) -> StreamInfo:
        """Get RTSP stream URI for a video profile.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            StreamInfo with RTSP URI and profile details.

        Raises:
            RuntimeError: If not connected or no profiles available.
        """
        self._ensure_connected()

        if not self._profiles:
            raise RuntimeError("No video profiles available")

        token = profile_token or self._profiles[0].token

        stream_setup = {
            "Stream": "RTP-Unicast",
            "Transport": {"Protocol": "RTSP"},
        }

        uri_response = await self._media_service.GetStreamUri(
            {"StreamSetup": stream_setup, "ProfileToken": token}
        )

        return StreamInfo(
            uri=self._fix_uri(uri_response.Uri),
            profile_token=token,
            transport="RTSP",
        )

    async def get_all_stream_uris(self) -> list[StreamInfo]:
        """Get stream URIs for all video profiles.

        Returns:
            List of StreamInfo for each available profile.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        streams: list[StreamInfo] = []
        for profile in self._profiles:
            try:
                stream = await self.get_stream_uri(profile.token)
                streams.append(stream)
            except Exception:
                pass

        return streams

    async def get_snapshot_uri(self, profile_token: str | None = None) -> str | None:
        """Get snapshot URI for capturing still images.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            Snapshot URI string or None if not available.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        if not self._profiles:
            return None

        token = profile_token or self._profiles[0].token

        try:
            response = await self._media_service.GetSnapshotUri({"ProfileToken": token})
            return self._fix_uri(response.Uri)
        except Exception:
            return None

    # =========================================================================
    # PTZ Control
    # =========================================================================

    async def has_ptz(self) -> bool:
        """Check if camera supports PTZ control.

        Returns:
            True if PTZ service is available.
        """
        return self._ptz_service is not None

    async def get_ptz_status(self, profile_token: str | None = None) -> PTZStatus | None:
        """Get current PTZ position and movement status.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            PTZStatus with position coordinates or None if PTZ unavailable.
        """
        if not self._ptz_service or not self._profiles:
            return None

        token = profile_token or self._profiles[0].token

        try:
            status = await self._ptz_service.GetStatus({"ProfileToken": token})
            pos = status.Position

            return PTZStatus(
                pan=float(pos.PanTilt.x) if hasattr(pos, "PanTilt") else 0.0,
                tilt=float(pos.PanTilt.y) if hasattr(pos, "PanTilt") else 0.0,
                zoom=float(pos.Zoom.x) if hasattr(pos, "Zoom") else 0.0,
                moving=status.MoveStatus is not None,
            )
        except Exception:
            return None

    async def ptz_move(
        self,
        direction: PTZDirection,
        speed: float = 0.5,
        profile_token: str | None = None,
    ) -> bool:
        """Move the camera in a specified direction.

        Args:
            direction: Direction to move (UP, DOWN, LEFT, RIGHT, ZOOM_IN, ZOOM_OUT).
            speed: Movement speed from 0.0 to 1.0.
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            True if movement command was sent successfully.
        """
        if not self._ptz_service or not self._profiles:
            return False

        token = profile_token or self._profiles[0].token
        speed = max(0.0, min(1.0, speed))

        velocity: dict[str, Any] = {"PanTilt": {"x": 0.0, "y": 0.0}, "Zoom": {"x": 0.0}}

        if direction == PTZDirection.UP:
            velocity["PanTilt"]["y"] = speed
        elif direction == PTZDirection.DOWN:
            velocity["PanTilt"]["y"] = -speed
        elif direction == PTZDirection.LEFT:
            velocity["PanTilt"]["x"] = -speed
        elif direction == PTZDirection.RIGHT:
            velocity["PanTilt"]["x"] = speed
        elif direction == PTZDirection.ZOOM_IN:
            velocity["Zoom"]["x"] = speed
        elif direction == PTZDirection.ZOOM_OUT:
            velocity["Zoom"]["x"] = -speed

        try:
            await self._ptz_service.ContinuousMove(
                {"ProfileToken": token, "Velocity": velocity}
            )
            return True
        except Exception:
            return False

    async def ptz_stop(self, profile_token: str | None = None) -> bool:
        """Stop all PTZ movement.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            True if stop command was sent successfully.
        """
        if not self._ptz_service or not self._profiles:
            return False

        token = profile_token or self._profiles[0].token

        try:
            await self._ptz_service.Stop(
                {"ProfileToken": token, "PanTilt": True, "Zoom": True}
            )
            return True
        except Exception:
            return False

    async def ptz_goto_preset(
        self, preset_token: str, profile_token: str | None = None
    ) -> bool:
        """Move camera to a saved PTZ preset position.

        Args:
            preset_token: Token of the preset to move to.
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            True if goto command was sent successfully.
        """
        if not self._ptz_service or not self._profiles:
            return False

        token = profile_token or self._profiles[0].token

        try:
            await self._ptz_service.GotoPreset(
                {"ProfileToken": token, "PresetToken": preset_token}
            )
            return True
        except Exception:
            return False

    async def get_ptz_presets(self, profile_token: str | None = None) -> list[PTZPreset]:
        """Get list of saved PTZ preset positions.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            List of PTZPreset objects with token and name.
        """
        if not self._ptz_service or not self._profiles:
            return []

        token = profile_token or self._profiles[0].token

        try:
            presets = await self._ptz_service.GetPresets({"ProfileToken": token})
            return [
                PTZPreset(token=p.token, name=p.Name or p.token)
                for p in presets
                if hasattr(p, "token")
            ]
        except Exception:
            return []

    async def ptz_home(self, profile_token: str | None = None) -> bool:
        """Move PTZ to home position.

        Args:
            profile_token: Profile token to use. If None, uses the first profile.

        Returns:
            True if home command was sent successfully.
        """
        if not self._ptz_service or not self._profiles:
            return False

        token = profile_token or self._profiles[0].token

        try:
            await self._ptz_service.GotoHomePosition({"ProfileToken": token})
            return True
        except Exception:
            return False

    # =========================================================================
    # Image Settings
    # =========================================================================

    async def get_image_settings(
        self, video_source_token: str | None = None
    ) -> ImageSettings | None:
        """Get current image settings from the camera.

        Args:
            video_source_token: Video source to query. If None, uses first profile.

        Returns:
            ImageSettings with brightness, contrast, etc. or None if unavailable.
        """
        if not self._imaging_service:
            return None

        # Get video source token from first profile if not provided
        if not video_source_token and self._profiles:
            if hasattr(self._profiles[0], "VideoSourceConfiguration"):
                video_source_token = self._profiles[0].VideoSourceConfiguration.SourceToken

        if not video_source_token:
            return None

        try:
            settings = await self._imaging_service.GetImagingSettings(
                {"VideoSourceToken": video_source_token}
            )

            return ImageSettings(
                brightness=float(settings.Brightness)
                if hasattr(settings, "Brightness") and settings.Brightness
                else None,
                contrast=float(settings.Contrast)
                if hasattr(settings, "Contrast") and settings.Contrast
                else None,
                saturation=float(settings.ColorSaturation)
                if hasattr(settings, "ColorSaturation") and settings.ColorSaturation
                else None,
                sharpness=float(settings.Sharpness)
                if hasattr(settings, "Sharpness") and settings.Sharpness
                else None,
                ir_cut_filter=str(settings.IrCutFilter)
                if hasattr(settings, "IrCutFilter") and settings.IrCutFilter
                else None,
                wide_dynamic_range=bool(settings.WideDynamicRange.Mode == "ON")
                if hasattr(settings, "WideDynamicRange") and settings.WideDynamicRange
                else None,
                backlight_compensation=bool(
                    settings.BacklightCompensation.Mode == "ON"
                )
                if hasattr(settings, "BacklightCompensation")
                and settings.BacklightCompensation
                else None,
            )
        except Exception:
            return None

    async def set_image_setting(
        self,
        setting: str,
        value: float | bool,
        video_source_token: str | None = None,
    ) -> bool:
        """Set an image setting on the camera.

        Args:
            setting: Setting name (brightness, contrast, saturation, sharpness).
            value: Value to set (typically 0-100 for most settings).
            video_source_token: Video source to configure. If None, uses first profile.

        Returns:
            True if setting was applied successfully.
        """
        if not self._imaging_service:
            return False

        # Get video source token from first profile if not provided
        if not video_source_token and self._profiles:
            if hasattr(self._profiles[0], "VideoSourceConfiguration"):
                video_source_token = self._profiles[0].VideoSourceConfiguration.SourceToken

        if not video_source_token:
            return False

        setting_map = {
            "brightness": "Brightness",
            "contrast": "Contrast",
            "saturation": "ColorSaturation",
            "sharpness": "Sharpness",
        }

        if setting.lower() not in setting_map:
            return False

        try:
            imaging_settings = {setting_map[setting.lower()]: value}
            await self._imaging_service.SetImagingSettings(
                {
                    "VideoSourceToken": video_source_token,
                    "ImagingSettings": imaging_settings,
                }
            )
            return True
        except Exception:
            return False

    # =========================================================================
    # System Operations
    # =========================================================================

    async def reboot(self) -> bool:
        """Reboot the camera.

        Returns:
            True if reboot command was sent successfully.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        try:
            await self._device_service.SystemReboot()
            return True
        except Exception:
            return False

    async def factory_reset(self, hard_reset: bool = False) -> bool:
        """Factory reset the camera.

        Args:
            hard_reset: If True, performs a hard reset (may not be reversible).

        Returns:
            True if reset command was sent successfully.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        try:
            await self._device_service.SetSystemFactoryDefault(
                {"FactoryDefault": "Hard" if hard_reset else "Soft"}
            )
            return True
        except Exception:
            return False

    async def get_network_config(self) -> NetworkConfig | None:
        """Get network configuration from the camera.

        Returns:
            NetworkConfig with IP address and network settings or None if unavailable.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        try:
            interfaces = await self._device_service.GetNetworkInterfaces()
            if not interfaces:
                return None

            iface = interfaces[0]
            ipv4 = iface.IPv4.Config if hasattr(iface, "IPv4") else None

            if not ipv4:
                return None

            return NetworkConfig(
                ip_address=ipv4.Manual[0].Address if ipv4.Manual else "",
                subnet_mask=str(ipv4.Manual[0].PrefixLength) if ipv4.Manual else "",
                gateway="",  # Not directly available in this response
                dhcp_enabled=ipv4.DHCP if hasattr(ipv4, "DHCP") else False,
            )
        except Exception:
            return None

    async def set_hostname(self, hostname: str) -> bool:
        """Set the camera hostname.

        Args:
            hostname: New hostname for the camera.

        Returns:
            True if hostname was set successfully.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        try:
            await self._device_service.SetHostname({"Name": hostname})
            return True
        except Exception:
            return False

    async def get_services(self) -> list[OnvifService]:
        """Get list of available ONVIF services on the camera.

        Returns:
            List of OnvifService objects with namespace and endpoint details.

        Raises:
            RuntimeError: If not connected to camera.
        """
        self._ensure_connected()

        try:
            services = await self._device_service.GetServices({"IncludeCapability": False})
            return [
                OnvifService(
                    namespace=s.Namespace,
                    xaddr=self._fix_uri(s.XAddr),
                    version=f"{s.Version.Major}.{s.Version.Minor}"
                    if hasattr(s, "Version")
                    else "Unknown",
                )
                for s in services
            ]
        except Exception:
            return []


class OnvifCamera:
    """Async context manager for ONVIF camera connections.

    Provides automatic connection management with proper cleanup.

    Example:
        >>> config = OnvifCameraConfig(ip_address="192.168.1.10", username="admin", password="pass")
        >>> async with OnvifCamera(config) as camera:
        ...     profiles = await camera.get_profiles()
        ...     for p in profiles:
        ...         print(f"{p.name}: {p.resolution_width}x{p.resolution_height}")
    """

    def __init__(self, config: OnvifCameraConfig) -> None:
        """Initialize the context manager.

        Args:
            config: ONVIF camera configuration with connection details.
        """
        self.manager = OnvifCameraManager(config)

    async def __aenter__(self) -> OnvifCameraManager:
        """Connect to camera on context entry.

        Returns:
            Connected OnvifCameraManager instance.
        """
        await self.manager.connect()
        return self.manager

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Disconnect from camera on context exit."""
        await self.manager.disconnect()
