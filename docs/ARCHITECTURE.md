# UniFi Camera Manager Architecture

This document provides a comprehensive overview of the UniFi Camera Manager (`ucam`) architecture, including module relationships, data flows, and API integrations.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Module Overview](#module-overview)
- [CLI Command Structure](#cli-command-structure)
- [API Integration Layers](#api-integration-layers)
- [Configuration System](#configuration-system)
- [Authentication Flows](#authentication-flows)
- [Data Models](#data-models)

---

## High-Level Architecture

The UniFi Camera Manager is a CLI tool that integrates with three distinct API systems to provide unified camera management capabilities.

```mermaid
flowchart TB
    subgraph CLI["CLI Layer (cli.py)"]
        APP[Main App<br/>ucam]
        ONVIF_APP[ONVIF Commands<br/>ucam onvif]
        LOGS_APP[Logs Commands<br/>ucam logs]
        AXIS_APP[AXIS Commands<br/>ucam axis]
    end

    subgraph Config["Configuration Layer"]
        ENV[Environment Variables<br/>UFP_*, ONVIF_*, AXIS_*]
        YAML[config.yaml<br/>Device Definitions]
        CREDS[Credential Resolution<br/>ONVIF + AXIS Admin]
    end

    subgraph APIs["API Integration Layer"]
        PROTECT[UniFi Protect API<br/>client.py]
        ONVIF[ONVIF Protocol<br/>onvif_manager.py]
        VAPIX[AXIS VAPIX APIs<br/>axis_*.py modules]
    end

    subgraph External["External Systems"]
        NVR[(UniFi Protect NVR)]
        CAM1[(AXIS Cameras)]
        CAM2[(Third-Party ONVIF)]
    end

    APP --> PROTECT
    ONVIF_APP --> ONVIF
    LOGS_APP --> VAPIX
    AXIS_APP --> VAPIX

    ENV --> Config
    YAML --> Config
    Config --> CREDS

    CREDS --> PROTECT
    CREDS --> ONVIF
    CREDS --> VAPIX

    PROTECT --> NVR
    ONVIF --> CAM1
    ONVIF --> CAM2
    VAPIX --> CAM1
```

---

## Module Overview

The package consists of 12 Python modules organized into functional groups:

```mermaid
flowchart LR
    subgraph Core["Core Modules"]
        CLI[cli.py<br/>2283 lines]
        CONFIG[config.py<br/>638 lines]
        MODELS[models.py<br/>Data Models]
        LOGGING[logging_config.py<br/>Global Logging]
    end

    subgraph UniFi["UniFi Protect"]
        CLIENT[client.py<br/>NVR Client]
    end

    subgraph ONVIF["ONVIF Protocol"]
        MANAGER[onvif_manager.py<br/>Camera Control]
        DISCOVERY[onvif_discovery.py<br/>Network Discovery]
    end

    subgraph AXIS["AXIS VAPIX APIs"]
        LOGS[axis_logs.py<br/>Log Retrieval]
        AXCONFIG[axis_config.py<br/>Parameter API]
        LLDP[axis_lldp.py<br/>Network Discovery]
        DIAG[axis_diagnostics.py<br/>Stream Diagnostics]
    end

    CLI --> CONFIG
    CLI --> CLIENT
    CLI --> MANAGER
    CLI --> LOGS
    CLI --> AXCONFIG
    CLI --> LLDP
    CLI --> DIAG

    CONFIG --> MODELS
    CLIENT --> MODELS
    MANAGER --> MODELS
    LOGS --> MODELS
```

### Module Descriptions

| Module | Lines | Purpose |
|--------|-------|---------|
| `cli.py` | 2283 | Main CLI with Typer, command groups, Rich output |
| `config.py` | 638 | XDG-compliant configuration, credential resolution |
| `models.py` | ~300 | Pydantic v2 data models with validation |
| `logging_config.py` | ~100 | Global logging configuration |
| `client.py` | ~400 | UniFi Protect NVR API client |
| `onvif_manager.py` | ~600 | ONVIF protocol implementation |
| `onvif_discovery.py` | ~200 | ONVIF camera discovery utilities |
| `axis_logs.py` | 409 | VAPIX serverreport.cgi log retrieval |
| `axis_config.py` | ~350 | VAPIX v2beta parameter API |
| `axis_lldp.py` | ~200 | VAPIX LLDP REST API |
| `axis_diagnostics.py` | ~300 | Stream and network diagnostics |

---

## CLI Command Structure

The CLI is built with Typer and organized into four command groups:

```mermaid
flowchart TB
    subgraph Main["ucam (Main App)"]
        LIST[list<br/>List all cameras]
        INFO[info<br/>Camera details]
        FIND[find<br/>Find by IP]
        ADOPT[adopt<br/>Adopt camera]
        UNADOPT[unadopt<br/>Remove camera]
        REBOOT[reboot<br/>Reboot via NVR]
        VERIFY[verify-onvif<br/>Test ONVIF]
    end

    subgraph ONVIF["ucam onvif"]
        O_LIST[list<br/>Config cameras]
        O_INFO[info<br/>ONVIF details]
        O_STREAMS[streams<br/>RTSP URIs]
        O_PROFILES[profiles<br/>Video profiles]
        O_IMAGE[image<br/>Image settings]
        O_PTZ[ptz<br/>PTZ control]
        O_SERVICES[services<br/>ONVIF services]
        O_REBOOT[reboot<br/>Direct reboot]
        O_SCOPES[scopes<br/>Profile info]
    end

    subgraph Logs["ucam logs"]
        L_GET[get<br/>Generic logs]
        L_SYSTEM[system<br/>System logs]
        L_AUDIT[audit<br/>Audit logs]
        L_ACCESS[access<br/>Access logs]
        L_FILES[files<br/>List log files]
    end

    subgraph AXIS["ucam axis"]
        A_CONFIG[config<br/>Full config]
        A_PARAM[param<br/>Single param]
        A_GROUPS[groups<br/>List groups]
        A_INFO[info<br/>Device info]
        A_LLDP[lldp<br/>LLDP status]
        A_DIAG[diagnostics<br/>Stream diag]
    end
```

### Command Options Pattern

All commands follow consistent patterns:

```
--camera, -c     Camera name from config.yaml (with shell completion)
--ip             Direct IP address access
--user, -u       Override username
--pass, -p       Override password
--port           Override port (default: 80)
--env, -e        Path to .env file (UniFi Protect commands)
```

---

## API Integration Layers

### UniFi Protect API

```mermaid
sequenceDiagram
    participant CLI as cli.py
    participant Client as client.py
    participant UIProtect as uiprotect library
    participant NVR as UniFi Protect NVR

    CLI->>Client: get_protect_client(config)
    Client->>UIProtect: ProtectApiClient()
    UIProtect->>NVR: REST API (HTTPS/443)
    NVR-->>UIProtect: JSON Response
    UIProtect-->>Client: Camera objects
    Client-->>CLI: List[CameraInfo]
```

### ONVIF Protocol

```mermaid
sequenceDiagram
    participant CLI as cli.py
    participant Manager as onvif_manager.py
    participant Zeep as onvif-zeep-async
    participant Camera as ONVIF Camera

    CLI->>Manager: OnvifCamera(config)
    Manager->>Zeep: ONVIFCamera()
    Zeep->>Camera: SOAP/WSDL Services
    Camera-->>Zeep: XML Response
    Zeep-->>Manager: Service objects
    Manager-->>CLI: SystemInfo, Profiles, etc.

    Note over Manager,Camera: Services: Device, Media, PTZ, Imaging
```

### AXIS VAPIX APIs

```mermaid
sequenceDiagram
    participant CLI as cli.py
    participant Config as axis_config.py
    participant LLDP as axis_lldp.py
    participant Logs as axis_logs.py
    participant HTTPX as httpx client
    participant Camera as AXIS Camera

    CLI->>Config: AxisConfigClient(config)
    Config->>HTTPX: DigestAuth + GET
    HTTPX->>Camera: /config/rest/param/v2beta
    Camera-->>HTTPX: JSON Parameters
    HTTPX-->>Config: Dict[str, Any]
    Config-->>CLI: AxisConfig model

    CLI->>LLDP: AxisLLDPClient(config)
    LLDP->>HTTPX: DigestAuth + GET
    HTTPX->>Camera: /config/rest/lldp/v1
    Camera-->>HTTPX: JSON LLDP data
    HTTPX-->>LLDP: LLDPStatus, Neighbors
    LLDP-->>CLI: Display tables

    CLI->>Logs: AxisLogClient(config)
    Logs->>HTTPX: DigestAuth + GET
    HTTPX->>Camera: /axis-cgi/serverreport.cgi
    Camera-->>HTTPX: TAR archive
    HTTPX-->>Logs: Parse syslog format
    Logs-->>CLI: LogReport model
```

---

## Configuration System

### Configuration Resolution Priority

```mermaid
flowchart TB
    subgraph Input["User Input"]
        EXPLICIT[Explicit CLI Args<br/>--ip --user --pass]
        CAMERA[--camera NAME<br/>from config.yaml]
        ENV_DIRECT[Environment Variables<br/>ONVIF_IP, etc.]
    end

    subgraph Resolution["get_onvif_config()"]
        CHECK1{Explicit args<br/>provided?}
        CHECK2{--camera<br/>specified?}
        CHECK3{--ip only?}
        CHECK4{Env vars<br/>set?}
    end

    subgraph Sources["Configuration Sources"]
        YAML[(config.yaml<br/>~/.config/ucam/)]
        DEFAULTS[defaults section<br/>in config.yaml]
        IP_LOOKUP[Lookup by IP<br/>in config.yaml]
        ENV_VARS[(Environment<br/>Variables)]
    end

    subgraph Output["OnvifCameraConfig"]
        CONFIG[ip_address<br/>username<br/>password<br/>port<br/>axis_username<br/>axis_password]
    end

    EXPLICIT --> CHECK1
    CAMERA --> CHECK1
    ENV_DIRECT --> CHECK1

    CHECK1 -->|Yes| CONFIG
    CHECK1 -->|No| CHECK2
    CHECK2 -->|Yes| YAML
    CHECK2 -->|No| CHECK3
    CHECK3 -->|Yes| IP_LOOKUP
    IP_LOOKUP -->|Found| CONFIG
    IP_LOOKUP -->|Not Found| DEFAULTS
    CHECK3 -->|No| CHECK4
    CHECK4 -->|Yes| ENV_VARS
    CHECK4 -->|No| ERROR[BadParameter]

    YAML --> CONFIG
    DEFAULTS --> CONFIG
    ENV_VARS --> CONFIG
```

### XDG Directory Structure

```
~/.config/ucam/
├── config.yaml          # Device definitions + defaults
└── .env                  # Optional environment overrides

~/.local/share/ucam/
└── protect_cameras.json  # Cache for shell completions
```

### config.yaml Structure

```yaml
# Default credentials (used with --ip only)
defaults:
  username: "${AXIS_ADMIN_USERNAME}"
  password: "${AXIS_ADMIN_PASSWORD}"
  port: 80

# Device definitions
devices:
  - name: Front_Of_House
    address: 192.168.10.12
    username: onvif_user
    password: onvif_pass
    port: 80
    vendor: AXIS
    model: P3245-V
    type: camera
    # AXIS admin credentials (for VAPIX APIs)
    axis_username: "${AXIS_ADMIN_USERNAME}"
    axis_password: "${AXIS_ADMIN_PASSWORD}"
```

---

## Authentication Flows

### Dual Credential System

AXIS cameras require different credentials for different APIs:

```mermaid
flowchart TB
    subgraph Credentials["OnvifCameraConfig"]
        ONVIF_CREDS[username<br/>password<br/>ONVIF protocol access]
        AXIS_CREDS[axis_username<br/>axis_password<br/>VAPIX admin access]
    end

    subgraph Method["get_axis_credentials()"]
        CHECK{axis_username<br/>set?}
        RETURN_AXIS[Return AXIS creds]
        RETURN_ONVIF[Return ONVIF creds<br/>as fallback]
    end

    subgraph Usage["API Clients"]
        ONVIF_API[ONVIF Protocol<br/>onvif_manager.py]
        VAPIX_API[VAPIX APIs<br/>axis_*.py]
    end

    ONVIF_CREDS --> ONVIF_API
    AXIS_CREDS --> CHECK
    CHECK -->|Yes| RETURN_AXIS
    CHECK -->|No| RETURN_ONVIF
    RETURN_AXIS --> VAPIX_API
    RETURN_ONVIF --> VAPIX_API
```

### HTTP Digest Authentication

All AXIS VAPIX clients use HTTP Digest authentication:

```mermaid
sequenceDiagram
    participant Client as AxisLogClient
    participant HTTPX as httpx.AsyncClient
    participant Camera as AXIS Camera

    Client->>Client: get_axis_credentials()
    Client->>HTTPX: AsyncClient(auth=DigestAuth)
    HTTPX->>Camera: GET /axis-cgi/...
    Camera-->>HTTPX: 401 + WWW-Authenticate
    HTTPX->>HTTPX: Compute Digest response
    HTTPX->>Camera: GET + Authorization header
    Camera-->>HTTPX: 200 OK + Content
    HTTPX-->>Client: Response data
```

---

## Data Models

### Model Hierarchy

```mermaid
classDiagram
    class BaseModel {
        <<Pydantic v2>>
        +model_config: ConfigDict
        +frozen: bool = True
    }

    class ProtectConfig {
        +username: str
        +password: str
        +address: str
        +port: int = 443
        +ssl_verify: bool = False
        +from_env() ProtectConfig
    }

    class OnvifCameraConfig {
        +ip_address: str
        +username: str
        +password: str
        +port: int = 80
        +name: str | None
        +axis_username: str | None
        +axis_password: str | None
        +get_axis_credentials() tuple
    }

    class CameraInfo {
        +id: str
        +name: str
        +host: IPv4Address | None
        +type: str
        +state: str
        +is_adopted: bool
        +is_third_party: bool
    }

    class LogEntry {
        +timestamp: datetime
        +hostname: str
        +level: LogLevel
        +process: str | None
        +message: str
        +raw: str
    }

    class LogReport {
        +camera_name: str
        +camera_address: str
        +log_type: LogType
        +entries: list~LogEntry~
        +total_entries: int
    }

    BaseModel <|-- ProtectConfig
    BaseModel <|-- OnvifCameraConfig
    BaseModel <|-- CameraInfo
    BaseModel <|-- LogEntry
    BaseModel <|-- LogReport

    LogReport *-- LogEntry
```

### Enumerations

```mermaid
classDiagram
    class LogLevel {
        <<Enum>>
        DEBUG
        INFO
        WARNING
        ERROR
        CRITICAL
    }

    class LogType {
        <<Enum>>
        SYSTEM
        ACCESS
        AUDIT
        ALL
    }

    class PTZDirection {
        <<Enum>>
        UP
        DOWN
        LEFT
        RIGHT
        ZOOM_IN
        ZOOM_OUT
    }
```

---

## Async Context Manager Pattern

All API clients follow the async context manager pattern:

```python
async with AxisLogClient(config) as client:
    logs = await client.get_system_logs()
```

```mermaid
sequenceDiagram
    participant CLI as Command Function
    participant CM as Context Manager
    participant Client as API Client
    participant API as External API

    CLI->>CM: async with Client(config)
    CM->>Client: __aenter__()
    Client->>Client: Initialize httpx.AsyncClient
    Client->>Client: Setup DigestAuth
    Client-->>CM: return self

    CM->>Client: await method()
    Client->>API: HTTP Request
    API-->>Client: Response
    Client-->>CM: Parsed Result
    CM-->>CLI: Use result

    CLI->>CM: exit context
    CM->>Client: __aexit__()
    Client->>Client: await client.aclose()
```

---

## Error Handling

### HTTP Status Code Handling

```mermaid
flowchart TB
    REQUEST[HTTP Request] --> RESPONSE{Status Code}

    RESPONSE -->|200| SUCCESS[Parse Response]
    RESPONSE -->|401| AUTH_ERROR[Authentication Failed]
    RESPONSE -->|404| NOT_FOUND[Resource Not Found]
    RESPONSE -->|500| SERVER_ERROR[Server Error]

    AUTH_ERROR --> DISPLAY_401[Display: Check credentials<br/>in config.yaml]
    NOT_FOUND --> DISPLAY_404[Display: Camera not found]
    SERVER_ERROR --> DISPLAY_500[Display: Camera error]

    SUCCESS --> RETURN[Return to CLI]
    DISPLAY_401 --> EXIT[typer.Exit(1)]
    DISPLAY_404 --> EXIT
    DISPLAY_500 --> EXIT
```

### CLI Error Display

All errors are displayed using Rich console with consistent formatting:
- `[red]Error:[/red]` prefix for errors
- `[yellow]Warning:[/yellow]` prefix for warnings
- `[dim]Note:[/dim]` prefix for hints
- Exit code 1 for all error conditions

---

## Testing Architecture

```mermaid
flowchart TB
    subgraph Tests["tests/"]
        CONFTEST[conftest.py<br/>Shared fixtures]
        T_CONFIG[test_config.py<br/>Config loading]
        T_MODELS[test_models.py<br/>Model validation]
        T_LOGS[test_axis_logs.py<br/>Log parsing]
        T_AUTH[test_axis_auth.py<br/>Auth harness]
    end

    subgraph Fixtures["Pytest Fixtures"]
        SAMPLE_CONFIG[sample_config<br/>Mock YAML]
        SAMPLE_LOG[sample_log_content<br/>Mock syslog]
        MOCK_ENV[mock_env_vars<br/>Test env]
    end

    CONFTEST --> SAMPLE_CONFIG
    CONFTEST --> SAMPLE_LOG
    CONFTEST --> MOCK_ENV

    T_CONFIG --> SAMPLE_CONFIG
    T_CONFIG --> MOCK_ENV
    T_MODELS --> SAMPLE_CONFIG
    T_LOGS --> SAMPLE_LOG
```

Run tests with:
```bash
uv run pytest -v              # Verbose output
uv run pytest --cov           # With coverage
uv run pytest -k "test_config"  # Specific tests
```

---

## Future Considerations

### Potential Enhancements

1. **Event Subscription**: ONVIF event polling for motion detection
2. **Firmware Management**: AXIS firmware update via VAPIX
3. **Recording Control**: UniFi Protect recording schedule management
4. **Multi-NVR Support**: Managing cameras across multiple NVRs
5. **Configuration Backup**: Export/import camera settings

### Extension Points

- Add new AXIS VAPIX APIs in `axis_*.py` modules
- Add new CLI commands in command groups
- Add new Pydantic models in `models.py`
- Configuration sources in `config.py`
