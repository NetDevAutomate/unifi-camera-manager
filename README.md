# UniFi Camera Manager

CLI tool to manage UniFi Protect cameras, including third-party ONVIF cameras.

## Installation

```bash
cd unifi-camera-manager
uv sync
```

## Configuration

Create a `.env` file with your UniFi Protect credentials:

```bash
export UFP_USERNAME=your_username
export UFP_PASSWORD=your_password
export UFP_ADDRESS=192.168.x.x
export UFP_PORT=443
export UFP_SSL_VERIFY=false
export UFP_API_KEY=your_api_key  # Optional
```

Or use the parent directory's `.env` file (symlinked automatically).

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
- AXIS (M3216-LVE, I8016-LVE)
- Any ONVIF-compatible camera should work

## Project Structure

```
unifi-camera-manager/
├── pyproject.toml
├── README.md
└── src/
    └── unifi_camera_manager/
        ├── __init__.py
        ├── cli.py           # Typer CLI application
        ├── client.py        # UniFi Protect API wrapper
        ├── config.py        # Configuration management
        └── onvif_discovery.py  # ONVIF camera verification
```

## Development

```bash
# Install dev dependencies
uv sync

# Run CLI
uv run ucam --help

# Run with custom .env file
uv run ucam list -e /path/to/.env
```

## License

MIT
