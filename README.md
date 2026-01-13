# UniFi Camera Manager

CLI tool (`ucam`) for managing UniFi Protect cameras, with comprehensive support for third-party ONVIF cameras and AXIS camera management via VAPIX API. Built with Python 3.12+, Typer CLI framework, and async/await patterns throughout.

## Features

- **UniFi Protect Integration**: List, adopt, unadopt, and reboot cameras via NVR API
- **ONVIF Direct Control**: PTZ, streams, profiles, image settings for any ONVIF camera
- **AXIS VAPIX Support**: Log retrieval, configuration management, LLDP discovery, diagnostics
- **XDG-Compliant Configuration**: Standard config paths with environment variable interpolation
- **Rich Terminal Output**: Tables, trees, and panels with shell completions

## Installation

### Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

### Install with uv

```bash
cd unifi-camera-manager
uv sync

# Install shell completions (bash, zsh, fish)
uv run ucam --install-completion
```

### Install with pip

```bash
pip install -e .

# Shell completions
ucam --install-completion
```

## Configuration

### Environment Variables

Create a `.env` file or export environment variables:

```bash
# UniFi Protect NVR Connection
export UFP_USERNAME=your_username
export UFP_PASSWORD=your_password
export UFP_ADDRESS=192.168.x.x
export UFP_PORT=443
export UFP_SSL_VERIFY=false

# AXIS Camera Credentials (for config.yaml interpolation)
export AXIS_ADMIN_USERNAME=admin
export AXIS_ADMIN_PASSWORD=your_camera_password

# Direct ONVIF access (optional, for --ip mode)
export ONVIF_IP=192.168.1.100
export ONVIF_USER=onvif_user
export ONVIF_PASSWORD=onvif_pass
```

### Configuration File

Location: `~/.config/ucam/config.yaml` (XDG standard) or `./config.yaml` (local)

```yaml
# Camera definitions with environment variable interpolation
devices:
  - name: Front Door
    address: 192.168.1.100
    username: ${AXIS_ADMIN_USERNAME}
    password: ${AXIS_ADMIN_PASSWORD}
    port: 80
    vendor: AXIS
    model: P3245-LV
    type: camera

  - name: Back Yard
    address: 192.168.1.101
    username: ${AXIS_ADMIN_USERNAME}
    password: ${AXIS_ADMIN_PASSWORD}
    port: 80
    vendor: AXIS
    model: P3247
    type: camera

  - name: Garage
    address: 192.168.1.102
    username: ${ONVIF_USER}
    password: ${ONVIF_PASSWORD}
    port: 80
    vendor: Generic
    type: camera
```

**Features:**
- `${VAR}` syntax interpolates environment variables at load time
- Supports any ONVIF-compatible camera
- Vendor-specific features enabled automatically (e.g., AXIS VAPIX)

## CLI Command Reference

The CLI is organized into four command groups with shell completion support:

```
ucam                    # Main UniFi Protect commands
ucam onvif              # Direct ONVIF camera control
ucam logs               # AXIS log retrieval (VAPIX)
ucam axis               # AXIS configuration management (VAPIX)
```

### Main Commands (`ucam`)

| Command | Description |
|---------|-------------|
| `list` | List all cameras from UniFi Protect NVR |
| `info` | Get detailed camera information by ID or IP |
| `find` | Find camera by IP address |
| `adopt` | Adopt an unadopted camera |
| `unadopt` | Remove a camera (with confirmation) |
| `reboot` | Reboot a camera |
| `verify-onvif` | Test ONVIF connectivity before adoption |

#### Examples

```bash
# List all cameras
uv run ucam list
uv run ucam list --third-party           # Only third-party cameras
uv run ucam list --include-unadopted     # Include unadopted devices

# Get camera info
uv run ucam info CAMERA_ID
uv run ucam info 192.168.10.12           # By IP address

# Find by IP
uv run ucam find 192.168.10.13

# Verify ONVIF before adding
uv run ucam verify-onvif 192.168.10.13 -u onvif -p password

# Adopt/Unadopt
uv run ucam adopt CAMERA_ID
uv run ucam unadopt CAMERA_ID
uv run ucam unadopt CAMERA_ID --force    # Skip confirmation

# Reboot
uv run ucam reboot CAMERA_ID
```

### ONVIF Commands (`ucam onvif`)

Direct communication with ONVIF cameras (bypasses UniFi Protect).

| Command | Description |
|---------|-------------|
| `list` | List all configured ONVIF cameras |
| `info` | Get device information |
| `streams` | Get RTSP stream URIs |
| `profiles` | List video profiles |
| `image` | Get/set image settings (brightness, contrast, etc.) |
| `ptz` | PTZ control (status, presets, move) |
| `services` | List available ONVIF services |
| `scopes` | Get device scopes/metadata |
| `reboot` | Reboot camera via ONVIF |

#### Examples

```bash
# Get camera info (--camera supports tab completion)
uv run ucam onvif info --camera "Front Door"

# Stream URIs for recording
uv run ucam onvif streams --camera "Front Door"

# Video profiles
uv run ucam onvif profiles --camera "Front Door"

# Image settings
uv run ucam onvif image --camera "Front Door"

# PTZ control
uv run ucam onvif ptz status --camera "Front Door"
uv run ucam onvif ptz presets --camera "Front Door"
uv run ucam onvif ptz move --camera "Front Door" --direction up

# Available ONVIF services
uv run ucam onvif services --camera "Front Door"

# Reboot via ONVIF
uv run ucam onvif reboot --camera "Front Door"
```

### AXIS Log Commands (`ucam logs`)

Retrieve logs from AXIS cameras via VAPIX API.

| Command | Description |
|---------|-------------|
| `get` | Get logs by type (system, access, audit) |
| `system` | Get system/syslog entries |
| `access` | Get access control logs |
| `audit` | Get security audit logs |
| `files` | List available log files on device |

#### Examples

```bash
# System logs
uv run ucam logs system --camera "Front Door"
uv run ucam logs system --camera "Front Door" --lines 50

# Access logs
uv run ucam logs access --camera "Front Door"

# Audit logs
uv run ucam logs audit --camera "Front Door"

# Generic log retrieval
uv run ucam logs get --camera "Front Door" --type system

# List available log files
uv run ucam logs files --camera "Front Door"
```

### AXIS Configuration Commands (`ucam axis`)

AXIS camera configuration management via VAPIX API.

| Command | Description |
|---------|-------------|
| `config` | Get/set AXIS camera configuration parameters |
| `param` | Get/set individual parameters |
| `groups` | List parameter groups |
| `info` | Get device information (firmware, serial, etc.) |
| `lldp` | Get LLDP neighbor discovery information |
| `diagnostics` | Run camera diagnostics |

#### Examples

```bash
# Get camera configuration
uv run ucam axis config --camera "Front Door"
uv run ucam axis config --camera "Front Door" --group Network

# Get/set parameters
uv run ucam axis param --camera "Front Door" --name root.Network.Interface.I0.Active
uv run ucam axis param --camera "Front Door" --name root.Brand.Brand

# List parameter groups
uv run ucam axis groups --camera "Front Door"

# Device information
uv run ucam axis info --camera "Front Door"

# LLDP neighbors (discover connected switches)
uv run ucam axis lldp --camera "Front Door"

# Run diagnostics
uv run ucam axis diagnostics --camera "Front Door"
```

## Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--log-file PATH` | Enable logging to file |
| `--log-level LEVEL` | Set log level (DEBUG, INFO, WARNING, ERROR) |

## Shell Completions

Tab completion is available for:
- Camera names (`--camera`)
- Camera IDs (for UniFi Protect commands)
- Log types (`system`, `access`, `audit`)
- PTZ directions (`up`, `down`, `left`, `right`, `zoom-in`, `zoom-out`)

Install completions:

```bash
# Detect shell automatically
uv run ucam --install-completion

# Or specify shell
uv run ucam --install-completion bash
uv run ucam --install-completion zsh
uv run ucam --install-completion fish
```

## Adding Third-Party ONVIF Cameras to UniFi Protect

UniFi Protect 5.0+ supports third-party ONVIF cameras.

### Prerequisites

1. Camera must support ONVIF protocol
2. ONVIF must be enabled on the camera
3. ONVIF credentials configured on camera
4. Camera on same network as NVR (or routable)

### Steps

1. **Enable Discovery in UniFi Protect**
   - Go to Settings → System → Advanced
   - Enable "Discover Third-Party Cameras"

2. **Verify Camera Connectivity**
   ```bash
   uv run ucam verify-onvif CAMERA_IP -u ONVIF_USER -p ONVIF_PASS
   ```

3. **Wait for Discovery**
   - Protect scans the network periodically
   - Camera should appear in Devices list

4. **Adopt the Camera**
   - In Protect UI: Click "Adopt" and enter ONVIF credentials
   - Or via CLI:
     ```bash
     uv run ucam adopt CAMERA_ID
     ```

### Limitations of Third-Party Cameras in Protect

- **No motion detection** without AI Port device
- **No PTZ control** via Protect UI (use `ucam onvif ptz`)
- **No audio** without AI Port
- **Continuous recording only** (no smart detection events)

## Supported Camera Brands

Tested with:
- **AXIS**: M3216-LVE, I8016-LVE, P3245-LV, P3247
- **Any ONVIF-compatible camera** should work for basic operations

AXIS-specific features (logs, config, LLDP, diagnostics) require AXIS firmware.

## Project Structure

```
unifi-camera-manager/
├── pyproject.toml          # Package configuration (uv/pip)
├── README.md               # This file
├── CLAUDE.md               # Claude Code guidance
├── config.yaml             # Local camera config (example)
├── src/
│   └── unifi_camera_manager/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI (4 command groups, 27 commands)
│       ├── client.py           # UniFi Protect API wrapper
│       ├── config.py           # XDG-compliant configuration
│       ├── models.py           # Pydantic data models
│       ├── logging_config.py   # Logging configuration
│       ├── axis_logs.py        # AXIS log retrieval (VAPIX)
│       ├── axis_config.py      # AXIS configuration (VAPIX)
│       ├── axis_lldp.py        # AXIS LLDP discovery (VAPIX)
│       ├── axis_diagnostics.py # AXIS diagnostics (VAPIX)
│       ├── onvif_manager.py    # ONVIF camera operations
│       └── onvif_discovery.py  # ONVIF camera verification
└── tests/
    ├── conftest.py             # Shared pytest fixtures
    ├── test_config.py          # Configuration tests
    ├── test_models.py          # Model validation tests
    └── test_axis_logs.py       # Log retrieval tests
```

## Development

```bash
# Install dev dependencies
uv sync

# Run CLI
uv run ucam --help

# Run tests
uv run pytest -v
uv run pytest --cov=unifi_camera_manager  # With coverage

# Linting
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/
```

## Architecture

### Three API Systems

1. **UniFi Protect API** (`client.py`)
   - Manages cameras through the NVR
   - Uses `uiprotect` library wrapping the UniFi Protect REST API
   - Operations: list/adopt/unadopt/reboot cameras, get NVR info

2. **ONVIF Direct API** (`onvif_manager.py`)
   - Direct camera communication via ONVIF protocol
   - Uses `onvif-zeep-async` for SOAP/WSDL-based ONVIF services
   - Operations: PTZ control, video profiles, image settings, stream URIs

3. **AXIS VAPIX API** (`axis_*.py` modules)
   - Log retrieval, configuration, LLDP discovery via AXIS REST APIs
   - Uses httpx for async HTTP requests
   - Vendor-specific features for AXIS cameras

### Key Design Patterns

- **Async/Await**: All API calls are async; CLI commands use `asyncio.run()` wrapper
- **Pydantic v2 Models**: Strict validation with frozen (immutable) configurations
- **Rich Output**: Tables, panels, trees for terminal display
- **XDG Compliance**: Standard config/data paths via `platformdirs`
- **Environment Interpolation**: `${VAR}` syntax in config files

## License

MIT
