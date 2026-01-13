# API Reference

This document provides detailed reference information for interfaces, data models, and configuration options in UniFi Camera Manager.

## Configuration Models

### ProtectConfig

Configuration for UniFi Protect NVR connection.

```python
class ProtectConfig(BaseSettings):
    """UniFi Protect NVR connection settings."""

    username: str          # UFP_USERNAME env var
    password: str          # UFP_PASSWORD env var
    address: str           # UFP_ADDRESS env var
    port: int = 443        # UFP_PORT env var
    ssl_verify: bool = False  # UFP_SSL_VERIFY env var
```

**Environment Variables:**
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UFP_USERNAME` | Yes | - | NVR admin username |
| `UFP_PASSWORD` | Yes | - | NVR admin password |
| `UFP_ADDRESS` | Yes | - | NVR IP address or hostname |
| `UFP_PORT` | No | 443 | HTTPS port |
| `UFP_SSL_VERIFY` | No | false | Verify SSL certificates |

### OnvifCameraConfig

Configuration for individual ONVIF camera connections.

```python
class OnvifCameraConfig(BaseModel):
    """ONVIF camera connection settings."""

    model_config = ConfigDict(frozen=True)

    ip_address: str        # Camera IP (alias: address)
    username: str          # ONVIF username
    password: str          # ONVIF password
    port: int = 80         # ONVIF service port
    name: str | None = None     # Camera display name
    vendor: str | None = None   # Camera vendor (e.g., AXIS)
    model: str | None = None    # Camera model

    # AXIS-specific credentials for VAPIX APIs
    axis_username: str | None = None
    axis_password: str | None = None
```

**Methods:**
| Method | Returns | Description |
|--------|---------|-------------|
| `get_axis_credentials()` | `tuple[str, str]` | Returns (username, password) for VAPIX APIs |

---

## Data Models

### CameraInfo

Represents a camera from UniFi Protect NVR.

```python
class CameraInfo(BaseModel):
    """Camera information from UniFi Protect."""

    id: str                    # Unique camera ID
    name: str                  # Display name
    type: str                  # Camera type
    state: str                 # Current state
    ip_address: str | None     # IP address
    mac: str | None            # MAC address
    firmware_version: str | None
    model: str | None
    is_adopted: bool = False
    is_connected: bool = False
    is_third_party: bool = False
```

### OnvifCameraInfo

Camera information retrieved via ONVIF protocol.

```python
class OnvifCameraInfo(BaseModel):
    """ONVIF GetDeviceInformation response."""

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    is_accessible: bool = False
    error: str | None = None
```

### SystemInfo

Extended system information from ONVIF.

```python
class SystemInfo(BaseModel):
    """Extended ONVIF device information."""

    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    onvif_version: str | None = None
```

### VideoProfile

ONVIF video profile configuration.

```python
class VideoProfile(BaseModel):
    """ONVIF video profile settings."""

    token: str                 # Profile token
    name: str                  # Profile name
    encoding: str              # Video encoding (H.264, H.265, etc.)
    resolution_width: int
    resolution_height: int
    frame_rate: float
    bitrate: int | None = None
    quality: float | None = None
```

### StreamInfo

RTSP stream information.

```python
class StreamInfo(BaseModel):
    """ONVIF stream URI information."""

    profile_token: str
    uri: str                   # RTSP URI
    transport: str             # Transport protocol
    is_multicast: bool = False
```

### PTZStatus

Pan/Tilt/Zoom position and state.

```python
class PTZStatus(BaseModel):
    """PTZ current status."""

    pan: float                 # Pan position
    tilt: float                # Tilt position
    zoom: float                # Zoom level
    is_moving: bool = False
```

### ImageSettings

Camera image settings.

```python
class ImageSettings(BaseModel):
    """Camera image settings."""

    brightness: float          # 0.0 - 1.0
    contrast: float            # 0.0 - 1.0
    saturation: float          # 0.0 - 1.0
    sharpness: float           # 0.0 - 1.0
```

### LogEntry

Single log entry from AXIS camera.

```python
class LogEntry(BaseModel):
    """Parsed syslog entry."""

    timestamp: str             # ISO format timestamp
    level: LogLevel            # Log severity
    source: str                # Source process/hostname
    message: str               # Log message
```

### LogReport

Collection of log entries with metadata.

```python
class LogReport(BaseModel):
    """Log retrieval report."""

    camera_name: str
    camera_address: str
    log_type: LogType
    entries: list[LogEntry]
    raw_content: str
    retrieved_at: str
```

---

## Enumerations

### LogLevel

```python
class LogLevel(str, Enum):
    """Syslog severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

### LogType

```python
class LogType(str, Enum):
    """AXIS log types."""

    SYSTEM = "system"      # System/syslog
    ACCESS = "access"      # Access control logs
    AUDIT = "audit"        # Security audit logs
    ALL = "all"            # All available logs
```

### PTZDirection

```python
class PTZDirection(str, Enum):
    """PTZ movement directions."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    ZOOM_IN = "zoom-in"
    ZOOM_OUT = "zoom-out"
```

---

## API Clients

### UnifiProtectClient

Client for UniFi Protect NVR API operations.

```python
class UnifiProtectClient:
    """UniFi Protect NVR API wrapper."""

    def __init__(self, config: ProtectConfig): ...

    async def list_cameras(
        self,
        include_unadopted: bool = False,
        third_party_only: bool = False,
    ) -> list[CameraInfo]: ...

    async def get_camera(self, camera_id: str) -> CameraInfo | None: ...

    async def adopt_camera(self, camera_id: str) -> bool: ...

    async def unadopt_camera(self, camera_id: str) -> bool: ...

    async def reboot_camera(self, camera_id: str) -> bool: ...

    async def get_nvr_info(self) -> NvrInfo: ...
```

**Context Manager:**
```python
async with get_protect_client(config) as client:
    cameras = await client.list_cameras()
```

### OnvifCameraManager

Direct ONVIF camera communication.

```python
class OnvifCameraManager:
    """ONVIF camera operations."""

    def __init__(self, config: OnvifCameraConfig): ...

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...

    # Device operations
    async def get_system_info(self) -> SystemInfo: ...
    async def get_capabilities(self) -> CameraCapabilities: ...
    async def reboot(self) -> None: ...

    # Media operations
    async def get_profiles(self) -> list[VideoProfile]: ...
    async def get_stream_uris(self) -> list[StreamInfo]: ...
    async def get_services(self) -> list[OnvifService]: ...
    async def get_scopes(self) -> list[str]: ...

    # PTZ operations (if supported)
    async def get_ptz_status(self) -> PTZStatus: ...
    async def get_ptz_presets(self) -> list[PTZPreset]: ...
    async def ptz_move(
        self,
        direction: PTZDirection,
        speed: float = 0.5,
        duration: float = 0.5,
    ) -> None: ...
    async def ptz_go_to_preset(self, preset_token: str) -> None: ...

    # Imaging operations (if supported)
    async def get_image_settings(self) -> ImageSettings: ...
    async def set_brightness(self, value: float) -> None: ...
    async def set_contrast(self, value: float) -> None: ...
```

**Context Manager:**
```python
async with OnvifCamera(config) as manager:
    info = await manager.get_system_info()
```

### AxisLogClient

AXIS camera log retrieval via VAPIX.

```python
class AxisLogClient:
    """AXIS VAPIX log retrieval."""

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ): ...

    async def get_server_report(
        self,
        mode: ServerReportMode = ServerReportMode.TAR_ALL,
    ) -> bytes: ...

    async def get_log_files(self) -> list[str]: ...

    async def get_logs(
        self,
        log_type: LogType = LogType.SYSTEM,
        max_lines: int | None = None,
    ) -> LogReport: ...

    async def get_system_logs(
        self,
        max_lines: int | None = None,
    ) -> LogReport: ...
```

### AxisConfigClient

AXIS camera parameter configuration via VAPIX v2beta.

```python
class AxisConfigClient:
    """AXIS VAPIX parameter API."""

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ): ...

    async def get_config(self) -> AxisConfig: ...

    async def get_group(self, group: str) -> dict[str, Any]: ...

    async def get_parameter(self, path: str) -> Any: ...

    async def get_device_info(self) -> dict[str, Any]: ...

    async def get_network_config(self) -> dict[str, Any]: ...

    async def get_image_config(self) -> dict[str, Any]: ...

    async def get_ptz_config(self) -> dict[str, Any]: ...
```

### AxisLLDPClient

AXIS LLDP neighbor discovery.

```python
class AxisLLDPClient:
    """AXIS VAPIX LLDP API."""

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ): ...

    async def get_status(self) -> LLDPStatus: ...

    async def get_neighbors(self) -> list[LLDPNeighbor]: ...
```

### AxisDiagnosticsClient

Stream and network diagnostics.

```python
class AxisDiagnosticsClient:
    """AXIS stream diagnostics."""

    def __init__(
        self,
        config: OnvifCameraConfig,
        timeout: float = 30.0,
    ): ...

    async def get_rtsp_config(self) -> RTSPConfig: ...

    async def get_rtp_config(self) -> RTPConfig: ...

    async def get_stream_profiles(self) -> list[StreamProfile]: ...

    async def get_network_config(self) -> NetworkDiagnostics: ...

    async def get_full_diagnostics(self) -> StreamDiagnostics: ...
```

---

## Configuration File Format

### config.yaml Schema

```yaml
# Default credentials (used with --ip only)
defaults:
  username: "${AXIS_ADMIN_USERNAME}"
  password: "${AXIS_ADMIN_PASSWORD}"
  port: 80

# Device definitions
devices:
  - name: string              # Required: Camera display name
    address: string           # Required: IP address
    username: string          # Required: ONVIF username
    password: string          # Required: ONVIF password
    port: int                 # Optional: Port (default: 80)
    vendor: string            # Optional: Vendor name
    model: string             # Optional: Model name
    type: string              # Optional: Device type
    axis_username: string     # Optional: AXIS admin username
    axis_password: string     # Optional: AXIS admin password
```

### Environment Variable Interpolation

The `${VAR}` syntax in config.yaml is replaced with environment variable values:

```yaml
# In config.yaml
password: "${MY_PASSWORD}"

# With MY_PASSWORD=secret123 in environment
# Resolves to: password: "secret123"
```

---

## CLI Options Reference

### Global Options

| Option | Type | Description |
|--------|------|-------------|
| `--help` | flag | Show help message |
| `--log-file PATH` | path | Enable logging to file |
| `--log-level LEVEL` | choice | Log level (DEBUG, INFO, WARNING, ERROR) |

### Camera Selection Options

| Option | Short | Type | Description |
|--------|-------|------|-------------|
| `--camera` | `-c` | string | Camera name from config.yaml |
| `--ip` | - | string | Direct IP address |
| `--user` | `-u` | string | Override username |
| `--pass` | `-p` | string | Override password |
| `--port` | - | int | Override port |

### Log Retrieval Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--lines` | `-n` | int | None | Limit number of entries |
| `--level` | `-l` | choice | None | Filter by log level |

### PTZ Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--direction` | `-d` | choice | - | Movement direction |
| `--speed` | `-s` | float | 0.5 | Movement speed (0.0-1.0) |
| `--duration` | `-t` | float | 0.5 | Movement duration in seconds |
