# Core Workflows

This document describes the core operational workflows in UniFi Camera Manager, including data flows, process sequences, and integration patterns.

## Camera Discovery and Adoption

### Workflow: Adding a Third-Party ONVIF Camera to UniFi Protect

```mermaid
sequenceDiagram
    participant User
    participant CLI as ucam CLI
    participant ONVIF as ONVIF Discovery
    participant NVR as UniFi Protect NVR

    User->>CLI: ucam verify-onvif 192.168.1.10 -u admin -p pass
    CLI->>ONVIF: verify_onvif_camera(config)
    ONVIF->>ONVIF: ONVIFCamera(host, port, user, pass)
    ONVIF->>ONVIF: GetDeviceInformation()
    ONVIF-->>CLI: OnvifCameraInfo

    alt Camera Accessible
        CLI-->>User: ✅ Found: AXIS P3245-V
        User->>CLI: ucam list --include-unadopted
        CLI->>NVR: list_cameras()
        NVR-->>CLI: Cameras (including unadopted)
        CLI-->>User: Shows discovered camera

        User->>CLI: ucam adopt CAMERA_ID
        CLI->>NVR: adopt_camera(id)
        NVR-->>CLI: Success
        CLI-->>User: ✅ Camera adopted
    else Camera Not Accessible
        CLI-->>User: ❌ Error: Connection failed
    end
```

### Workflow: Configuration Resolution

When a CLI command is executed, the configuration is resolved through multiple sources:

```mermaid
flowchart TB
    subgraph Input["Command Input"]
        A1[--camera NAME]
        A2[--ip ADDRESS]
        A3[--user/--pass]
    end

    subgraph Resolution["Configuration Resolution"]
        B1{Camera name<br/>provided?}
        B2{IP address<br/>provided?}
        B3{Credentials<br/>provided?}
        B4[Load from config.yaml]
        B5[Search by IP in config]
        B6[Use defaults section]
        B7[Use env vars]
    end

    subgraph Output["OnvifCameraConfig"]
        C1[ip_address]
        C2[username]
        C3[password]
        C4[port]
        C5[axis_username]
        C6[axis_password]
    end

    A1 --> B1
    A2 --> B2
    A3 --> B3

    B1 -->|Yes| B4
    B1 -->|No| B2
    B2 -->|Yes| B5
    B2 -->|No| B7
    B5 -->|Found| C1
    B5 -->|Not Found| B6
    B3 -->|Yes| C2
    B3 -->|No| B6
    B4 --> C1
    B4 --> C2
    B4 --> C5
    B6 --> C2
    B6 --> C6
    B7 --> C1
```

## Log Retrieval Workflow

### Workflow: Retrieving AXIS System Logs

```mermaid
sequenceDiagram
    participant User
    participant CLI as ucam CLI
    participant Client as AxisLogClient
    participant Camera as AXIS Camera

    User->>CLI: ucam logs system --camera Front_Door
    CLI->>CLI: get_camera_by_name("Front_Door")
    CLI->>Client: AxisLogClient(config)

    activate Client
    Client->>Client: get_axis_credentials()
    Client->>Client: httpx.AsyncClient(DigestAuth)
    Client->>Camera: GET /axis-cgi/serverreport.cgi?mode=tar
    Camera-->>Client: TAR archive with logs

    Client->>Client: Extract syslog.log from TAR
    Client->>Client: Parse syslog format
    Client-->>CLI: LogReport(entries=[...])
    deactivate Client

    CLI->>CLI: Filter by level if --level
    CLI->>CLI: Limit entries if --lines
    CLI->>CLI: Display with Rich Table
    CLI-->>User: Formatted log output
```

### Syslog Parsing Process

```mermaid
flowchart TB
    subgraph Input["Raw Log Data"]
        A1["Jan 13 10:23:45 axis-1234 process[123]: Message"]
    end

    subgraph Parsing["SYSLOG_PATTERN Regex"]
        B1["(?P<timestamp>...)<br/>(?P<hostname>...)<br/>(?P<process>...)<br/>(?P<message>...)"]
    end

    subgraph Processing["Log Entry Creation"]
        C1[Parse timestamp]
        C2[Extract hostname]
        C3[Determine LogLevel]
        C4[Extract message]
    end

    subgraph Output["LogEntry Model"]
        D1[timestamp: datetime]
        D2[hostname: str]
        D3[level: LogLevel]
        D4[process: str]
        D5[message: str]
    end

    A1 --> B1
    B1 --> C1
    B1 --> C2
    B1 --> C3
    B1 --> C4
    C1 --> D1
    C2 --> D2
    C3 --> D3
    C4 --> D4
    C4 --> D5
```

## ONVIF Operations Workflow

### Workflow: PTZ Control

```mermaid
sequenceDiagram
    participant User
    participant CLI as ucam CLI
    participant Manager as OnvifCameraManager
    participant Camera as ONVIF Camera

    User->>CLI: ucam onvif ptz move --camera Front --direction up
    CLI->>Manager: OnvifCamera(config)

    activate Manager
    Manager->>Camera: Create PTZ Service
    Camera-->>Manager: PTZ Service Ready

    Manager->>Camera: GetStatus()
    Camera-->>Manager: Current position

    Manager->>Camera: ContinuousMove(velocity)
    Note over Camera: Camera moves
    Manager->>Manager: asyncio.sleep(duration)
    Manager->>Camera: Stop()
    Camera-->>Manager: Stopped

    Manager->>Camera: GetStatus()
    Camera-->>Manager: New position
    Manager-->>CLI: PTZStatus
    deactivate Manager

    CLI-->>User: Movement complete
```

### Workflow: Retrieving Stream URIs

```mermaid
sequenceDiagram
    participant User
    participant CLI as ucam CLI
    participant Manager as OnvifCameraManager
    participant Camera as ONVIF Camera

    User->>CLI: ucam onvif streams --camera Front_Door
    CLI->>Manager: OnvifCamera(config)

    activate Manager
    Manager->>Camera: Create Media Service
    Manager->>Camera: GetProfiles()
    Camera-->>Manager: List[VideoProfile]

    loop For each profile
        Manager->>Camera: GetStreamUri(profile_token)
        Camera-->>Manager: RTSP URI
        Manager->>Manager: Fix localhost/127.0.0.1 URIs
    end

    Manager-->>CLI: List[StreamInfo]
    deactivate Manager

    CLI->>CLI: Display as Rich Table
    CLI-->>User: Stream URIs table
```

## AXIS VAPIX Operations

### Workflow: LLDP Neighbor Discovery

```mermaid
sequenceDiagram
    participant User
    participant CLI as ucam CLI
    participant Client as AxisLLDPClient
    participant Camera as AXIS Camera

    User->>CLI: ucam axis lldp --camera Front_Door
    CLI->>Client: AxisLLDPClient(config)

    activate Client
    Client->>Camera: GET /config/rest/lldp/v1
    Camera-->>Client: LLDP Status JSON

    Client->>Camera: GET /config/rest/lldp/v1/neighbors
    Camera-->>Client: LLDP Neighbors JSON

    Client->>Client: Parse to LLDPStatus
    Client->>Client: Parse to List[LLDPNeighbor]
    Client-->>CLI: Status + Neighbors
    deactivate Client

    CLI->>CLI: Display LLDP info table
    CLI-->>User: Connected switch/port info
```

### Workflow: Stream Diagnostics

```mermaid
flowchart TB
    subgraph Request["User Request"]
        A1["ucam axis diagnostics<br/>--camera Front_Door"]
    end

    subgraph Client["AxisDiagnosticsClient"]
        B1[Get RTSP Config]
        B2[Get RTP Config]
        B3[Get Stream Profiles]
        B4[Get Network Config]
    end

    subgraph Endpoints["VAPIX Endpoints"]
        C1["/config/rest/param/v2beta/Network/RTSP"]
        C2["/config/rest/param/v2beta/Network/RTP"]
        C3["/config/rest/param/v2beta/StreamProfile"]
        C4["/config/rest/param/v2beta/Network"]
    end

    subgraph Output["StreamDiagnostics"]
        D1[RTSPConfig]
        D2[RTPConfig]
        D3["List[StreamProfile]"]
        D4[NetworkDiagnostics]
        D5[errors: List]
    end

    A1 --> B1
    A1 --> B2
    A1 --> B3
    A1 --> B4

    B1 --> C1
    B2 --> C2
    B3 --> C3
    B4 --> C4

    C1 --> D1
    C2 --> D2
    C3 --> D3
    C4 --> D4
```

## Error Handling Workflows

### Workflow: Authentication Error Recovery

```mermaid
flowchart TB
    subgraph Request["API Request"]
        A1[HTTP Request with DigestAuth]
    end

    subgraph Response["Response Handling"]
        B1{Status Code}
        B2[200 OK]
        B3[401 Unauthorized]
        B4[404 Not Found]
        B5[Other Error]
    end

    subgraph Actions["Error Actions"]
        C1[Parse & Return Data]
        C2["Display: Authentication failed"]
        C3["Display: Endpoint not available"]
        C4["Display: HTTP error details"]
    end

    subgraph Hints["User Hints"]
        D1["Check credentials in config.yaml"]
        D2["Verify camera supports this feature"]
        D3["Check camera connectivity"]
    end

    A1 --> B1
    B1 -->|200| B2 --> C1
    B1 -->|401| B3 --> C2 --> D1
    B1 -->|404| B4 --> C3 --> D2
    B1 -->|5xx| B5 --> C4 --> D3
```

### Workflow: Graceful Degradation in Diagnostics

```mermaid
flowchart TB
    subgraph Requests["Diagnostic Requests"]
        A1[RTSP Config]
        A2[RTP Config]
        A3[Stream Profiles]
        A4[Network Config]
    end

    subgraph Handling["Per-Request Handling"]
        B1{Request Success?}
        B2[Add to diagnostics]
        B3[Add error to errors list]
        B4[Continue to next request]
    end

    subgraph Output["Final Output"]
        C1[StreamDiagnostics<br/>with partial data]
        C2[Display available info]
        C3[Show error summary]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B1

    B1 -->|Yes| B2
    B1 -->|No| B3
    B2 --> B4
    B3 --> B4
    B4 --> C1
    C1 --> C2
    C1 --> C3
```

## Shell Completion Workflow

### Workflow: Camera Name Completion

```mermaid
sequenceDiagram
    participant Shell as Shell (bash/zsh)
    participant Typer as Typer Framework
    participant Completion as camera_name_completion()
    participant Config as config.py

    Shell->>Typer: TAB key pressed
    Typer->>Completion: Get completions
    Completion->>Config: list_camera_names()
    Config->>Config: load_cameras_config()
    Config-->>Completion: ["Front_Door", "Back_Yard", ...]
    Completion-->>Typer: CompletionItem list
    Typer-->>Shell: Display completions

    Note over Shell: User selects "Front_Door"
    Shell->>Typer: Complete command
```

### Workflow: Protect Camera ID Completion

```mermaid
sequenceDiagram
    participant Shell as Shell
    participant Typer as Typer
    participant Completion as protect_camera_id_completion()
    participant Cache as protect_cameras.json
    participant NVR as UniFi Protect NVR

    Shell->>Typer: TAB for camera ID
    Typer->>Completion: Get completions

    Completion->>Cache: Check cache exists?

    alt Cache exists and fresh
        Cache-->>Completion: Cached camera list
    else Cache missing or stale
        Completion->>NVR: Fetch camera list
        NVR-->>Completion: Camera data
        Completion->>Cache: Save to cache
    end

    Completion-->>Typer: Camera IDs with names
    Typer-->>Shell: Display completions
```

## Data Transformation Flows

### Flow: UniFi Protect Camera to CameraInfo

```mermaid
flowchart LR
    subgraph Input["uiprotect Camera Object"]
        A1[id]
        A2[name]
        A3[host]
        A4[type]
        A5[state]
        A6[is_adopted]
        A7[firmware_version]
        A8[model]
    end

    subgraph Transform["to_camera_info()"]
        B1[Map fields]
        B2[Handle None values]
        B3[Convert types]
    end

    subgraph Output["CameraInfo Model"]
        C1["id: str"]
        C2["name: str"]
        C3["ip_address: str | None"]
        C4["type: str"]
        C5["state: str"]
        C6["is_adopted: bool"]
        C7["firmware_version: str"]
        C8["model: str"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B2
    A4 --> B1
    A5 --> B1
    A6 --> B1
    A7 --> B2
    A8 --> B2
    B1 --> B3
    B2 --> B3
    B3 --> C1
    B3 --> C2
    B3 --> C3
    B3 --> C4
    B3 --> C5
    B3 --> C6
    B3 --> C7
    B3 --> C8
```

### Flow: Environment Variable Interpolation

```mermaid
flowchart TB
    subgraph Input["config.yaml with Variables"]
        A1["username: '${AXIS_USERNAME}'"]
        A2["password: '${AXIS_PASSWORD}'"]
    end

    subgraph Process["interpolate_env_vars()"]
        B1[Find ${VAR} patterns]
        B2[Lookup in os.environ]
        B3[Replace with values]
    end

    subgraph Output["Resolved Config"]
        C1["username: 'admin'"]
        C2["password: 'secret123'"]
    end

    A1 --> B1
    A2 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> C1
    B3 --> C2
```
