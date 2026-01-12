# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CLI tool (`ucam`) for managing UniFi Protect cameras, with extended support for third-party ONVIF cameras and AXIS camera log retrieval. Built with Python 3.12+, Typer for CLI, and async/await patterns throughout.

## Commands

```bash
# Install dependencies
uv sync

# Run CLI
uv run ucam --help
uv run ucam list
uv run ucam onvif info --camera Front_Of_House
uv run ucam logs system --camera Front_Of_House

# Install shell completions
uv run ucam --install-completion

# Lint
uv run ruff check src/
uv run ruff format src/

# Run tests
uv run pytest
uv run pytest -v  # verbose
uv run pytest --cov=unifi_camera_manager  # with coverage
```

## Architecture

### Three API Systems

1. **UniFi Protect API** (`client.py`) - Manages cameras through the NVR
   - Uses `uiprotect` library wrapping the UniFi Protect REST API
   - `UnifiProtectClient` with async context manager `get_protect_client()`
   - Operations: list/adopt/unadopt/reboot cameras, get NVR info

2. **ONVIF Direct API** (`onvif_manager.py`) - Direct camera communication via ONVIF protocol
   - Uses `onvif-zeep-async` for SOAP/WSDL-based ONVIF services
   - `OnvifCameraManager` with async context manager `OnvifCamera`
   - Operations: PTZ control, video profiles, image settings, stream URIs, device info
   - Handles 127.0.0.1/localhost URI fixup for AXIS cameras

3. **AXIS Log API** (`axis_logs.py`) - Log retrieval from AXIS cameras via VAPIX
   - Uses httpx for async HTTP requests
   - `AxisLogClient` with async context manager
   - Retrieves system logs, access logs, audit logs via /axis-cgi/serverreport.cgi
   - Parses syslog format with regex patterns

### CLI Structure (`cli.py`)

Main app with subcommands:
- `ucam list|info|find|adopt|unadopt|reboot|verify-onvif`
- `ucam onvif list|info|streams|profiles|image|ptz|services|reboot|scopes`
- `ucam logs system|access|audit|all --camera NAME [--lines N]`

Shell completions available for:
- Camera names (`--camera`)
- Log types (`system|access|audit|all`)
- PTZ directions

### Configuration (`config.py`)

XDG-compliant paths using `platformdirs` (APP_NAME="ucam"):
- Config: `~/.config/ucam/config.yaml`
- Data: `~/.local/share/ucam/`

Models:
- `ProtectConfig`: UniFi Protect NVR connection (from `UFP_*` env vars)
- `OnvifCameraConfig`: Individual ONVIF camera settings (Pydantic v2 with validation)

Config file: `config.yaml` with `${ENV_VAR}` interpolation for secrets

### Data Models (`models.py`)

All models use Pydantic v2 BaseModel with:
- Frozen (immutable) configurations
- Field validation (ranges, constraints)
- Type safety with runtime validation

Key models:
- `CameraInfo`, `NvrInfo` - UniFi Protect entities
- `SystemInfo`, `OnvifCameraInfo` - ONVIF device info
- `VideoProfile`, `StreamInfo` - Media configuration
- `PTZStatus`, `PTZPreset` - PTZ control
- `ImageSettings`, `CameraCapabilities` - Camera features
- `LogEntry`, `LogReport` - AXIS log data
- Enums: `LogLevel`, `LogType`, `PTZDirection`

## Environment Variables

```bash
# UniFi Protect NVR
UFP_USERNAME=...
UFP_PASSWORD=...
UFP_ADDRESS=192.168.x.x
UFP_PORT=443
UFP_SSL_VERIFY=false

# ONVIF direct (optional, for --ip mode)
ONVIF_IP=...
ONVIF_USER=...
ONVIF_PASSWORD=...

# For config.yaml interpolation
AXIS_ADMIN_USERNAME=...
AXIS_ADMIN_PASSWORD=...
```

## Key Patterns

- All API calls are async; CLI commands use `asyncio.run()` wrapper pattern
- Rich library for terminal output (tables, panels, trees)
- ONVIF services initialized lazily (PTZ/imaging may not exist on all cameras)
- WSDL files loaded from installed `onvif` package directory
- Pydantic v2 models with aliases (e.g., `ip_address` accepts `address` in YAML)
- LRU caching for config file loading
- Regex parsing for syslog format logs

## Testing

Tests in `tests/` directory:
- `test_config.py` - Configuration loading, env var interpolation, XDG paths
- `test_models.py` - Pydantic model validation and constraints
- `test_axis_logs.py` - Log parsing and AxisLogClient functionality
- `conftest.py` - Shared pytest fixtures

Run with: `uv run pytest -v`
