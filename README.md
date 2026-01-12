# UniFi Camera Manager

CLI tool to manage UniFi Protect cameras, including third-party ONVIF cameras and AXIS camera log retrieval.

## Installation

```bash
cd unifi-camera-manager
uv sync

# Install shell completions (bash, zsh, fish)
uv run ucam --install-completion
```

## Configuration

### Environment Variables

Create a `.env` file or export environment variables:

```bash
# UniFi Protect NVR
export UFP_USERNAME=your_username
export UFP_PASSWORD=your_password
export UFP_ADDRESS=192.168.x.x
export UFP_PORT=443
export UFP_SSL_VERIFY=false

# For ONVIF camera config interpolation
export AXIS_ADMIN_USERNAME=admin
export AXIS_ADMIN_PASSWORD=your_camera_password
```

### Camera Configuration File

Create `~/.config/ucam/config.yaml` (or `./config.yaml`) with camera definitions:

```yaml
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
```

Environment variables in `${VAR}` syntax are interpolated at load time.

## Usage

### List All Cameras

```bash
uv run ucam list

# Show only third-party cameras
uv run ucam list --third-party

# Exclude unadopted devices
uv run ucam list --include-unadopted false
```

### Get Camera Info

```bash
# By camera ID
uv run ucam info 6961c8c201220503e400d761

# By IP address
uv run ucam info 192.168.10.12
```

### Find Camera by IP

```bash
uv run ucam find 192.168.10.13
```

### Verify ONVIF Camera

Test ONVIF connectivity before adding to Protect:

```bash
uv run ucam verify-onvif 192.168.10.13 -u onvif -p your_password
```

### Adopt/Unadopt Cameras

```bash
# Adopt an unadopted camera
uv run ucam adopt CAMERA_ID

# Remove a camera (with confirmation)
uv run ucam unadopt CAMERA_ID

# Force remove without confirmation
uv run ucam unadopt CAMERA_ID --force
```

### Reboot Camera

```bash
uv run ucam reboot CAMERA_ID
```

### ONVIF Direct Commands

Direct communication with ONVIF cameras (bypassing UniFi Protect):

```bash
# Get camera info
uv run ucam onvif info --camera "Front Door"

# List video profiles
uv run ucam onvif profiles --camera "Front Door"

# Get stream URIs
uv run ucam onvif streams --camera "Front Door"

# Get image settings
uv run ucam onvif image --camera "Front Door"

# PTZ control (if supported)
uv run ucam onvif ptz status --camera "Front Door"
uv run ucam onvif ptz presets --camera "Front Door"

# List available ONVIF services
uv run ucam onvif services --camera "Front Door"
```

### AXIS Camera Logs

Retrieve logs from AXIS cameras via VAPIX API:

```bash
# Get system logs
uv run ucam logs system --camera "Front Door"

# Get access logs
uv run ucam logs access --camera "Front Door"

# Get audit logs
uv run ucam logs audit --camera "Front Door"

# Get all logs combined
uv run ucam logs all --camera "Front Door"

# Limit number of entries
uv run ucam logs system --camera "Front Door" --lines 50
```

## Adding Third-Party ONVIF Cameras

UniFi Protect 5.0+ supports third-party ONVIF cameras. To add one:

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
   - Or via CLI (if camera appears as unadopted):
     ```bash
     uv run ucam adopt CAMERA_ID
     ```

### Limitations of Third-Party Cameras

- **No motion detection** without AI Port device
- **No PTZ control** via Protect (use camera's native interface)
- **No audio** without AI Port
- **Continuous recording only** (no smart detection events)

## Supported Camera Brands

Tested with:
- AXIS (M3216-LVE, I8016-LVE, P3245-LV)
- Any ONVIF-compatible camera should work

## Project Structure

```
unifi-camera-manager/
├── pyproject.toml
├── README.md
├── CLAUDE.md               # Claude Code guidance
├── config.yaml             # Camera configuration (example)
├── src/
│   └── unifi_camera_manager/
│       ├── __init__.py
│       ├── cli.py          # Typer CLI application
│       ├── client.py       # UniFi Protect API wrapper
│       ├── config.py       # XDG-compliant configuration
│       ├── models.py       # Pydantic data models
│       ├── axis_logs.py    # AXIS VAPIX log retrieval
│       ├── onvif_manager.py    # ONVIF camera operations
│       └── onvif_discovery.py  # ONVIF camera verification
└── tests/
    ├── conftest.py         # Shared pytest fixtures
    ├── test_config.py      # Configuration tests
    ├── test_models.py      # Model validation tests
    └── test_axis_logs.py   # Log retrieval tests
```

## Development

```bash
# Install dev dependencies
uv sync

# Run CLI
uv run ucam --help

# Run tests
uv run pytest -v

# Run linting
uv run ruff check src/
uv run ruff format src/

# Run type checking
uv run mypy src/
```

## License

MIT
