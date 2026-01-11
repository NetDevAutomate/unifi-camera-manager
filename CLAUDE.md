# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CLI tool (`ucam`) for managing UniFi Protect cameras, with extended support for third-party ONVIF cameras. Built with Python 3.12+, Typer for CLI, and async/await patterns throughout.

## Commands

```bash
# Install dependencies
uv sync

# Run CLI
uv run ucam --help
uv run ucam list
uv run ucam onvif info --camera Front_Of_House

# Lint
uv run ruff check src/
uv run ruff format src/
```

## Architecture

### Two API Systems

1. **UniFi Protect API** (`client.py`) - Manages cameras through the NVR
   - Uses `uiprotect` library wrapping the UniFi Protect REST API
   - `UnifiProtectClient` with async context manager `get_protect_client()`
   - Operations: list/adopt/unadopt/reboot cameras, get NVR info

2. **ONVIF Direct API** (`onvif_manager.py`) - Direct camera communication via ONVIF protocol
   - Uses `onvif-zeep-async` for SOAP/WSDL-based ONVIF services
   - `OnvifCameraManager` with async context manager `OnvifCamera`
   - Operations: PTZ control, video profiles, image settings, stream URIs, device info
   - Handles 127.0.0.1/localhost URI fixup for AXIS cameras

### CLI Structure (`cli.py`)

- Main app: `ucam list|info|find|adopt|unadopt|reboot|verify-onvif`
- Sub-app: `ucam onvif list|info|streams|profiles|image|ptz|services|reboot|scopes`

### Configuration (`config.py`)

- `ProtectConfig`: UniFi Protect NVR connection (from `UFP_*` env vars)
- `OnvifCameraConfig`: Individual ONVIF camera settings
- `config.yaml`: Camera definitions with `${ENV_VAR}` interpolation for secrets

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
