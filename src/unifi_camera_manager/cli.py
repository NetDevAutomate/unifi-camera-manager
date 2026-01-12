"""CLI for UniFi Camera Manager.

This module provides the command-line interface for managing UniFi Protect
cameras and third-party ONVIF cameras, including camera listing, adoption,
PTZ control, image settings, and log retrieval.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .axis_config import AxisConfigClient
from .axis_diagnostics import AxisDiagnosticsClient
from .axis_lldp import AxisLLDPClient
from .axis_logs import AxisLogClient, get_camera_logs
from .client import get_protect_client
from .config import (
    OnvifCameraConfig,
    ProtectConfig,
    camera_name_completion,
    get_camera_by_ip,
    get_camera_by_name,
    get_default_credentials,
    list_camera_names,
    load_cameras_config,
    protect_camera_id_completion,
    save_protect_cameras_cache,
)
from .logging_config import configure_global_logger, log_debug, log_error, log_info
from .models import LogType, PTZDirection
from .onvif_discovery import (
    check_camera_connectivity,
    get_onvif_stream_uri,
    verify_onvif_camera,
)
from .onvif_manager import OnvifCamera

# Configure root logger to WARNING by default to suppress third-party INFO logs
# This can be overridden with --log-level when --log-file is specified
logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

# Explicitly suppress httpx/httpcore INFO logs which configure their own loggers at import time
# basicConfig doesn't override already-configured loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Console for rich output
console = Console()


def complete_camera_names(incomplete: str) -> list[str]:
    """Provide shell completion for camera names.

    Args:
        incomplete: Partial camera name being typed.

    Returns:
        List of matching camera names from config.yaml.
    """
    names = camera_name_completion()
    return [name for name in names if name.lower().startswith(incomplete.lower())]


def complete_log_types(incomplete: str) -> list[str]:
    """Provide shell completion for log types.

    Args:
        incomplete: Partial log type being typed.

    Returns:
        List of matching log types.
    """
    types = [t.value for t in LogType]
    return [t for t in types if t.startswith(incomplete.lower())]


def complete_ptz_directions(incomplete: str) -> list[str]:
    """Provide shell completion for PTZ directions.

    Args:
        incomplete: Partial direction being typed.

    Returns:
        List of matching PTZ directions.
    """
    directions = ["up", "down", "left", "right", "zoom_in", "zoom_out"]
    return [d for d in directions if d.startswith(incomplete.lower())]


def complete_protect_camera_ids(incomplete: str) -> list[str]:
    """Provide shell completion for UniFi Protect camera IDs.

    Args:
        incomplete: Partial camera ID being typed.

    Returns:
        List of matching camera IDs from cache.

    Note:
        Run `ucam list` first to populate the cache.
    """
    ids = protect_camera_id_completion()
    return [i for i in ids if i.lower().startswith(incomplete.lower())]


# =============================================================================
# Main Application
# =============================================================================

app = typer.Typer(
    name="ucam",
    help="Manage UniFi Protect cameras and third-party ONVIF cameras via CLI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main_callback(
    log_file: Annotated[
        Path | None,
        typer.Option(
            "--log-file",
            "-L",
            help="Log file path. When set, logs are written to file only (not stdout).",
            envvar="UCAM_LOG_FILE",
        ),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Log level for all loggers including httpx (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
            envvar="UCAM_LOG_LEVEL",
        ),
    ] = "WARNING",
) -> None:
    """Configure global options for logging.

    Logs are written only to the specified file, not to stdout.
    The --log-level option controls all loggers including httpx/httpcore.
    """
    # Apply log level to httpx/httpcore loggers (user-configurable)
    level = getattr(logging, log_level.upper(), logging.WARNING)
    logging.getLogger("httpx").setLevel(level)
    logging.getLogger("httpcore").setLevel(level)

    if log_file:
        configure_global_logger(log_file=log_file, log_level=log_level)
        log_info(f"ucam started with log level {log_level}")


def get_config(env_file: Path | None = None) -> ProtectConfig:
    """Get UniFi Protect configuration from environment.

    Args:
        env_file: Optional path to .env file.

    Returns:
        ProtectConfig with NVR connection settings.

    Raises:
        typer.Exit: If configuration is missing or invalid.
    """
    try:
        return ProtectConfig.from_env(env_file)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command("list")
def list_cameras(
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
    show_third_party_only: Annotated[
        bool,
        typer.Option("--third-party", "-t", help="Show only third-party cameras"),
    ] = False,
    show_unadopted: Annotated[
        bool,
        typer.Option("--include-unadopted", "-u", help="Include unadopted devices"),
    ] = True,
) -> None:
    """List all cameras in UniFi Protect.

    Displays a table of all cameras registered with the NVR, including
    their names, types, IP addresses, adoption status, and state.
    """
    config = get_config(env_file)

    async def _list() -> None:
        async with get_protect_client(config, include_unadopted=show_unadopted) as client:
            cameras = await client.list_cameras()
            nvr_info = await client.get_nvr_info()

            console.print(f"\n[bold]NVR:[/bold] {nvr_info.name} ({nvr_info.version})")
            console.print(f"[bold]Model:[/bold] {nvr_info.model}\n")

            if show_third_party_only:
                cameras = [c for c in cameras if c.is_third_party]

            table = Table(title="Cameras")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("IP Address", style="green")
            table.add_column("Adopted", style="yellow")
            table.add_column("State", style="blue")
            table.add_column("ID", style="dim")

            for cam in cameras:
                adopted_str = "\u2713" if cam.is_adopted else "\u2717"
                adopted_style = "green" if cam.is_adopted else "red"
                third_party_marker = " [3P]" if cam.is_third_party else ""

                table.add_row(
                    cam.name,
                    f"{cam.type}{third_party_marker}",
                    str(cam.host) if cam.host else "N/A",
                    f"[{adopted_style}]{adopted_str}[/{adopted_style}]",
                    str(cam.state),
                    cam.id,
                )

            console.print(table)
            console.print(f"\n[bold]Total:[/bold] {len(cameras)} cameras")

            # Save camera IDs to cache for shell completions
            cache_data = [
                {
                    "id": cam.id,
                    "name": cam.name,
                    "host": str(cam.host) if cam.host else "",
                }
                for cam in cameras
            ]
            save_protect_cameras_cache(cache_data)

    asyncio.run(_list())


@app.command("info")
def camera_info(
    camera_id: Annotated[
        str,
        typer.Argument(
            help="Camera ID or IP address",
            autocompletion=complete_protect_camera_ids,
        ),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
) -> None:
    """Get detailed information about a specific camera.

    Retrieves and displays detailed information about a camera
    identified by its ID or IP address.
    """
    config = get_config(env_file)

    async def _info() -> None:
        async with get_protect_client(config) as client:
            # Try to find by ID first, then by IP
            camera = await client.get_camera(camera_id)
            if not camera:
                camera = await client.get_camera_by_ip(camera_id)

            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            console.print(f"\n[bold cyan]Camera: {camera.name}[/bold cyan]")
            console.print(f"  [bold]ID:[/bold] {camera.id}")
            console.print(f"  [bold]Type:[/bold] {camera.type}")
            console.print(
                f"  [bold]IP Address:[/bold] {str(camera.host) if camera.host else 'N/A'}"
            )
            console.print(f"  [bold]Adopted:[/bold] {'Yes' if camera.is_adopted else 'No'}")
            console.print(f"  [bold]State:[/bold] {str(camera.state)}")
            console.print(f"  [bold]Third-Party:[/bold] {'Yes' if camera.is_third_party else 'No'}")
            if camera.last_seen:
                console.print(f"  [bold]Last Seen:[/bold] {camera.last_seen}")

    asyncio.run(_info())


@app.command("adopt")
def adopt_camera(
    camera_id: Annotated[
        str,
        typer.Argument(
            help="Camera ID to adopt",
            autocompletion=complete_protect_camera_ids,
        ),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
) -> None:
    """Adopt an unadopted camera into UniFi Protect.

    Initiates the adoption process for a camera that has been
    discovered but not yet adopted into the NVR.
    """
    config = get_config(env_file)

    async def _adopt() -> None:
        async with get_protect_client(config) as client:
            camera = await client.get_camera(camera_id)
            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            if camera.is_adopted:
                console.print(f"[yellow]Camera already adopted:[/yellow] {camera.name}")
                return

            console.print(f"Adopting camera: [cyan]{camera.name}[/cyan] ({camera_id})...")
            try:
                await client.adopt_camera(camera_id)
                console.print("[green]\u2713[/green] Adoption initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]\u2717[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_adopt())


@app.command("unadopt")
def unadopt_camera(
    camera_id: Annotated[
        str,
        typer.Argument(
            help="Camera ID to unadopt",
            autocompletion=complete_protect_camera_ids,
        ),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Remove/unadopt a camera from UniFi Protect.

    Removes an adopted camera from the NVR. Requires confirmation
    unless --force is specified.
    """
    config = get_config(env_file)

    async def _unadopt() -> None:
        async with get_protect_client(config) as client:
            camera = await client.get_camera(camera_id)
            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            if not force:
                confirm = typer.confirm(f"Are you sure you want to unadopt '{camera.name}'?")
                if not confirm:
                    console.print("[yellow]Cancelled[/yellow]")
                    raise typer.Exit(0)

            console.print(f"Unadopting camera: [cyan]{camera.name}[/cyan]...")
            try:
                await client.unadopt_camera(camera_id)
                console.print("[green]\u2713[/green] Unadoption initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]\u2717[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_unadopt())


@app.command("reboot")
def reboot_camera(
    camera_id: Annotated[
        str,
        typer.Argument(
            help="Camera ID to reboot",
            autocompletion=complete_protect_camera_ids,
        ),
    ],
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
) -> None:
    """Reboot a camera via UniFi Protect.

    Sends a reboot command to the specified camera through the NVR.
    """
    config = get_config(env_file)

    async def _reboot() -> None:
        async with get_protect_client(config) as client:
            camera = await client.get_camera(camera_id)
            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            console.print(f"Rebooting camera: [cyan]{camera.name}[/cyan]...")
            try:
                await client.reboot_camera(camera_id)
                console.print("[green]\u2713[/green] Reboot initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]\u2717[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_reboot())


@app.command("verify-onvif")
def verify_onvif(
    ip_address: Annotated[str, typer.Argument(help="Camera IP address")],
    username: Annotated[str, typer.Option("--user", "-u", help="ONVIF username")],
    password: Annotated[str, typer.Option("--pass", "-p", help="ONVIF password")],
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """Verify ONVIF camera connectivity and get device information.

    Tests network connectivity and ONVIF protocol access to a camera,
    displaying device information if successful.
    """

    async def _verify() -> None:
        console.print(f"\n[bold]Checking camera at {ip_address}:{port}...[/bold]")

        # First check basic connectivity
        console.print("  Checking network connectivity...", end=" ")
        is_reachable = await check_camera_connectivity(ip_address, port)
        if is_reachable:
            console.print("[green]\u2713[/green]")
        else:
            console.print("[red]\u2717[/red] Camera not reachable")
            raise typer.Exit(1)

        # Verify ONVIF
        console.print("  Verifying ONVIF connection...", end=" ")
        config = OnvifCameraConfig(
            ip_address=ip_address,
            username=username,
            password=password,
            port=port,
        )
        info = await verify_onvif_camera(config)

        if info.is_accessible:
            console.print("[green]\u2713[/green]")
            console.print("\n[bold cyan]Camera Information:[/bold cyan]")
            console.print(f"  [bold]Manufacturer:[/bold] {info.manufacturer}")
            console.print(f"  [bold]Model:[/bold] {info.model}")
            console.print(f"  [bold]Firmware:[/bold] {info.firmware_version}")
            console.print(f"  [bold]Serial:[/bold] {info.serial_number}")
            console.print(f"  [bold]Hardware ID:[/bold] {info.hardware_id}")

            # Try to get stream URI
            console.print("\n  Getting RTSP stream URI...", end=" ")
            stream_uri = await get_onvif_stream_uri(config)
            if stream_uri:
                console.print("[green]\u2713[/green]")
                console.print(f"  [bold]Stream URI:[/bold] {stream_uri}")
            else:
                console.print("[yellow]N/A[/yellow]")
        else:
            console.print("[red]\u2717[/red]")
            console.print(f"  [red]Error:[/red] {info.error}")
            raise typer.Exit(1)

    asyncio.run(_verify())


@app.command("find")
def find_camera(
    ip_address: Annotated[str, typer.Argument(help="IP address to search for")],
    env_file: Annotated[
        Path | None,
        typer.Option("--env", "-e", help="Path to .env file"),
    ] = None,
) -> None:
    """Find a camera by IP address in UniFi Protect.

    Searches for a camera in the NVR by its IP address and displays
    basic information if found.
    """
    config = get_config(env_file)

    async def _find() -> None:
        async with get_protect_client(config) as client:
            camera = await client.get_camera_by_ip(ip_address)

            if camera:
                console.print(f"\n[green]\u2713[/green] Camera found at {ip_address}:")
                console.print(f"  [bold]Name:[/bold] {camera.name}")
                console.print(f"  [bold]ID:[/bold] {camera.id}")
                console.print(f"  [bold]Type:[/bold] {camera.type}")
                console.print(f"  [bold]Adopted:[/bold] {'Yes' if camera.is_adopted else 'No'}")
            else:
                console.print(f"\n[yellow]![/yellow] No camera found at {ip_address}")
                console.print("\n[bold]Suggestions:[/bold]")
                console.print(
                    "  1. Ensure 'Discover Third-Party Cameras' is enabled in Protect settings"
                )
                console.print("  2. Verify the camera has ONVIF enabled")
                console.print("  3. Check the camera is on the same network as the NVR")
                console.print("  4. Use 'verify-onvif' command to test ONVIF connectivity")

    asyncio.run(_find())


# =============================================================================
# ONVIF Camera Management Commands
# =============================================================================

onvif_app = typer.Typer(
    name="onvif",
    help="ONVIF camera management commands for direct camera control.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(onvif_app, name="onvif")


def get_onvif_config_from_env() -> OnvifCameraConfig:
    """Get ONVIF configuration from environment variables.

    Returns:
        OnvifCameraConfig from ONVIF_* environment variables.

    Raises:
        ValueError: If required environment variables are missing.
    """
    ip = os.getenv("ONVIF_IP")
    user = os.getenv("ONVIF_USER")
    password = os.getenv("ONVIF_PASSWORD")
    port = int(os.getenv("ONVIF_PORT", "80"))

    if not all([ip, user, password]):
        raise ValueError(
            "Missing ONVIF environment variables. Set ONVIF_IP, ONVIF_USER, ONVIF_PASSWORD"
        )

    return OnvifCameraConfig(
        ip_address=ip,  # type: ignore[arg-type]
        username=user,  # type: ignore[arg-type]
        password=password,  # type: ignore[arg-type]
        port=port,
    )


def get_onvif_config(
    ip: str | None,
    user: str | None,
    password: str | None,
    port: int,
    camera_name: str | None = None,
) -> OnvifCameraConfig:
    """Get ONVIF configuration from multiple sources.

    Priority order:
    1. Explicit --ip, --user, --pass arguments
    2. --ip with default credentials from config.yaml
    3. Camera name from --camera (loads from config.yaml)
    4. Environment variables (ONVIF_IP, ONVIF_USER, ONVIF_PASSWORD)

    Args:
        ip: Camera IP address.
        user: ONVIF username.
        password: ONVIF password.
        port: ONVIF port.
        camera_name: Camera name from config.yaml.

    Returns:
        OnvifCameraConfig with connection settings.

    Raises:
        typer.BadParameter: If no valid configuration source is found.
    """
    # If explicit args provided, use them
    if ip and user and password:
        return OnvifCameraConfig(
            ip_address=ip,
            username=user,
            password=password,
            port=port,
        )

    # If only --ip provided, first try to find camera by IP in config.yaml
    # This enables --ip mode to use device-specific axis credentials
    if ip and not (user and password):
        try:
            # Look up camera by IP address to get device-specific credentials
            camera_config = get_camera_by_ip(ip)
            if camera_config:
                log_debug(
                    f"Found camera '{camera_config.name}' by IP {ip} with "
                    f"axis_username={'set' if camera_config.axis_username else 'not set'}"
                )
                return camera_config
        except (FileNotFoundError, ValueError) as e:
            log_debug(f"Could not lookup camera by IP: {e}")

        # Fall back to default credentials from config
        try:
            defaults = get_default_credentials()
            if defaults:
                return OnvifCameraConfig(
                    ip_address=ip,
                    username=user or defaults.username,
                    password=password or defaults.password,
                    port=port if port != 80 else defaults.port,
                )
        except (FileNotFoundError, ValueError) as e:
            # Config not found or env vars not set - continue to other methods
            console.print(f"[dim]Note: Could not load default credentials: {e}[/dim]")

    # Try camera name from config.yaml
    if camera_name:
        config = get_camera_by_name(camera_name)
        if config:
            return config
        raise typer.BadParameter(
            f"Camera '{camera_name}' not found in config.yaml. "
            f"Available: {', '.join(list_camera_names())}"
        )

    # Try environment
    try:
        return get_onvif_config_from_env()
    except ValueError:
        pass

    # Missing required params
    raise typer.BadParameter(
        "Provide --camera NAME, --ip/--user/--pass, or set ONVIF_* env vars.\n"
        "Tip: Add 'defaults' section to ~/.config/ucam/config.yaml for --ip only access."
    )


@onvif_app.command("list")
def onvif_list() -> None:
    """List all cameras from config.yaml.

    Displays a table of all cameras defined in the configuration file.
    """
    try:
        cameras = load_cameras_config()
    except FileNotFoundError:
        console.print("[yellow]No config.yaml found.[/yellow]")
        console.print("Create a config.yaml file with camera definitions.")
        raise typer.Exit(1) from None
    except ValueError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1) from e

    if not cameras:
        console.print("[yellow]No cameras defined in config.yaml[/yellow]")
        return

    table = Table(title="Configured Cameras")
    table.add_column("Name", style="cyan")
    table.add_column("Vendor", style="magenta")
    table.add_column("Model", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Address", style="yellow")
    table.add_column("Port", style="dim")

    for cam in cameras:
        table.add_row(
            cam.name or "N/A",
            cam.vendor or "N/A",
            cam.model or "N/A",
            cam.device_type or "N/A",
            cam.ip_address,
            str(cam.port),
        )

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {len(cameras)} cameras")
    console.print("\n[dim]Use: ucam onvif info --camera NAME[/dim]")


@onvif_app.command("info")
def onvif_info(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """Get comprehensive ONVIF camera information.

    Displays system information, capabilities, video profiles, and
    stream URIs from the specified camera.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _info() -> None:
        console.print(f"\n[bold]Connecting to {config.ip_address}:{config.port}...[/bold]")

        async with OnvifCamera(config) as cam:
            # System Info
            sys_info = await cam.get_system_info()
            console.print(
                Panel(
                    f"[bold]Manufacturer:[/bold] {sys_info.manufacturer}\n"
                    f"[bold]Model:[/bold] {sys_info.model}\n"
                    f"[bold]Firmware:[/bold] {sys_info.firmware_version}\n"
                    f"[bold]Serial:[/bold] {sys_info.serial_number}\n"
                    f"[bold]Hardware ID:[/bold] {sys_info.hardware_id}"
                    + (
                        f"\n[bold]System Time:[/bold] {sys_info.system_date_time}"
                        if sys_info.system_date_time
                        else ""
                    ),
                    title="[cyan]System Information[/cyan]",
                    expand=False,
                )
            )

            # Capabilities
            caps = await cam.get_capabilities()
            cap_items = []
            if caps.has_ptz:
                cap_items.append("[green]\u2713[/green] PTZ")
            else:
                cap_items.append("[dim]\u2717 PTZ[/dim]")
            if caps.has_audio:
                cap_items.append("[green]\u2713[/green] Audio")
            else:
                cap_items.append("[dim]\u2717 Audio[/dim]")
            if caps.has_events:
                cap_items.append("[green]\u2713[/green] Events")
            else:
                cap_items.append("[dim]\u2717 Events[/dim]")
            if caps.has_analytics:
                cap_items.append("[green]\u2713[/green] Analytics")
            else:
                cap_items.append("[dim]\u2717 Analytics[/dim]")

            console.print(
                Panel(
                    "  ".join(cap_items)
                    + f"\n[bold]Encodings:[/bold] {', '.join(caps.supported_encodings) or 'N/A'}"
                    f"\n[bold]Profiles:[/bold] {caps.max_profiles}",
                    title="[cyan]Capabilities[/cyan]",
                    expand=False,
                )
            )

            # Video Profiles
            profiles = await cam.get_profiles()
            if profiles:
                table = Table(title="Video Profiles", show_header=True)
                table.add_column("Token", style="cyan")
                table.add_column("Name")
                table.add_column("Resolution")
                table.add_column("Encoding")
                table.add_column("FPS")
                table.add_column("Bitrate")

                for p in profiles:
                    table.add_row(
                        p.token,
                        p.name,
                        f"{p.resolution_width}x{p.resolution_height}",
                        p.encoding,
                        str(int(p.frame_rate)),
                        f"{p.bitrate} kbps" if p.bitrate else "N/A",
                    )
                console.print(table)

            # Stream URIs
            streams = await cam.get_all_stream_uris()
            if streams:
                console.print("\n[bold cyan]Stream URIs:[/bold cyan]")
                for stream in streams:
                    console.print(f"  [{stream.profile_token}] {stream.uri}")

            # Snapshot URI
            snapshot = await cam.get_snapshot_uri()
            if snapshot:
                console.print(f"\n[bold cyan]Snapshot URI:[/bold cyan] {snapshot}")

    asyncio.run(_info())


@onvif_app.command("streams")
def onvif_streams(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """List all available RTSP stream URIs.

    Displays stream URIs for each video profile on the camera.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _streams() -> None:
        async with OnvifCamera(config) as cam:
            profiles = await cam.get_profiles()
            streams = await cam.get_all_stream_uris()

            table = Table(title=f"RTSP Streams - {config.ip_address}")
            table.add_column("Profile", style="cyan")
            table.add_column("Resolution", style="green")
            table.add_column("Encoding")
            table.add_column("Stream URI", style="yellow")

            profile_map = {p.token: p for p in profiles}

            for stream in streams:
                profile = profile_map.get(stream.profile_token)
                table.add_row(
                    stream.profile_token,
                    f"{profile.resolution_width}x{profile.resolution_height}" if profile else "N/A",
                    profile.encoding if profile else "N/A",
                    stream.uri,
                )

            console.print(table)

    asyncio.run(_streams())


@onvif_app.command("profiles")
def onvif_profiles(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """List video profiles with detailed configuration.

    Displays detailed information about each video profile including
    resolution, encoding, frame rate, and quality settings.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _profiles() -> None:
        async with OnvifCamera(config) as cam:
            profiles = await cam.get_profiles()

            for p in profiles:
                content = (
                    f"[bold]Resolution:[/bold] {p.resolution_width}x{p.resolution_height}\n"
                    f"[bold]Encoding:[/bold] {p.encoding}\n"
                    f"[bold]Frame Rate:[/bold] {p.frame_rate} fps"
                )
                if p.bitrate:
                    content += f"\n[bold]Bitrate:[/bold] {p.bitrate} kbps"
                if p.quality:
                    content += f"\n[bold]Quality:[/bold] {p.quality}"

                console.print(
                    Panel(
                        content,
                        title=f"[cyan]{p.name}[/cyan] ({p.token})",
                        expand=False,
                    )
                )

    asyncio.run(_profiles())


@onvif_app.command("image")
def onvif_image(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
    brightness: Annotated[
        float | None, typer.Option("--brightness", "-b", help="Set brightness (0-100)")
    ] = None,
    contrast: Annotated[
        float | None, typer.Option("--contrast", "-c", help="Set contrast (0-100)")
    ] = None,
    saturation: Annotated[
        float | None, typer.Option("--saturation", "-s", help="Set saturation (0-100)")
    ] = None,
    sharpness: Annotated[
        float | None, typer.Option("--sharpness", help="Set sharpness (0-100)")
    ] = None,
) -> None:
    """Get or set image settings (brightness, contrast, etc.).

    Without any setting options, displays current image settings.
    With setting options, modifies the specified settings.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _image() -> None:
        async with OnvifCamera(config) as cam:
            # Set values if provided
            settings_changed = False
            if brightness is not None:
                if await cam.set_image_setting("brightness", brightness):
                    console.print(f"[green]\u2713[/green] Brightness set to {brightness}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set brightness")

            if contrast is not None:
                if await cam.set_image_setting("contrast", contrast):
                    console.print(f"[green]\u2713[/green] Contrast set to {contrast}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set contrast")

            if saturation is not None:
                if await cam.set_image_setting("saturation", saturation):
                    console.print(f"[green]\u2713[/green] Saturation set to {saturation}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set saturation")

            if sharpness is not None:
                if await cam.set_image_setting("sharpness", sharpness):
                    console.print(f"[green]\u2713[/green] Sharpness set to {sharpness}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set sharpness")

            # Show current settings
            if not settings_changed:
                settings = await cam.get_image_settings()
                if settings:
                    wdr_str = (
                        "Enabled"
                        if settings.wide_dynamic_range
                        else "Disabled"
                        if settings.wide_dynamic_range is not None
                        else "N/A"
                    )
                    blc_str = (
                        "Enabled"
                        if settings.backlight_compensation
                        else "Disabled"
                        if settings.backlight_compensation is not None
                        else "N/A"
                    )
                    console.print(
                        Panel(
                            f"[bold]Brightness:[/bold] {settings.brightness or 'N/A'}\n"
                            f"[bold]Contrast:[/bold] {settings.contrast or 'N/A'}\n"
                            f"[bold]Saturation:[/bold] {settings.saturation or 'N/A'}\n"
                            f"[bold]Sharpness:[/bold] {settings.sharpness or 'N/A'}\n"
                            f"[bold]IR Cut Filter:[/bold] {settings.ir_cut_filter or 'N/A'}\n"
                            f"[bold]WDR:[/bold] {wdr_str}\n"
                            f"[bold]Backlight Comp:[/bold] {blc_str}",
                            title="[cyan]Image Settings[/cyan]",
                            expand=False,
                        )
                    )
                else:
                    console.print("[yellow]Image settings not available for this camera[/yellow]")

    asyncio.run(_image())


@onvif_app.command("ptz")
def onvif_ptz(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
    move: Annotated[
        str | None,
        typer.Option(
            "--move",
            "-m",
            help="Move direction: up, down, left, right, zoom_in, zoom_out",
            autocompletion=complete_ptz_directions,
        ),
    ] = None,
    speed: Annotated[float, typer.Option("--speed", "-s", help="Movement speed (0.0-1.0)")] = 0.5,
    stop: Annotated[bool, typer.Option("--stop", help="Stop PTZ movement")] = False,
    home: Annotated[bool, typer.Option("--home", help="Move to home position")] = False,
    preset: Annotated[
        str | None, typer.Option("--preset", "-g", help="Go to preset by token")
    ] = None,
    list_presets: Annotated[
        bool, typer.Option("--list-presets", "-l", help="List PTZ presets")
    ] = False,
) -> None:
    """PTZ (Pan/Tilt/Zoom) camera control.

    Without movement options, displays current PTZ status.
    Supports continuous movement, preset positions, and home.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _ptz() -> None:
        async with OnvifCamera(config) as cam:
            if not await cam.has_ptz():
                console.print("[yellow]This camera does not support PTZ[/yellow]")
                return

            # Get current status
            status = await cam.get_ptz_status()
            if status:
                console.print(
                    Panel(
                        f"[bold]Pan:[/bold] {status.pan:.3f}\n"
                        f"[bold]Tilt:[/bold] {status.tilt:.3f}\n"
                        f"[bold]Zoom:[/bold] {status.zoom:.3f}\n"
                        f"[bold]Moving:[/bold] {'Yes' if status.moving else 'No'}",
                        title="[cyan]PTZ Status[/cyan]",
                        expand=False,
                    )
                )

            # List presets
            if list_presets:
                presets = await cam.get_ptz_presets()
                if presets:
                    table = Table(title="PTZ Presets")
                    table.add_column("Token", style="cyan")
                    table.add_column("Name")
                    for p in presets:
                        table.add_row(p.token, p.name)
                    console.print(table)
                else:
                    console.print("[dim]No presets configured[/dim]")
                return

            # Stop movement
            if stop:
                if await cam.ptz_stop():
                    console.print("[green]\u2713[/green] PTZ stopped")
                else:
                    console.print("[red]\u2717[/red] Failed to stop PTZ")
                return

            # Go home
            if home:
                if await cam.ptz_home():
                    console.print("[green]\u2713[/green] Moving to home position")
                else:
                    console.print("[red]\u2717[/red] Failed to move to home")
                return

            # Go to preset
            if preset:
                if await cam.ptz_goto_preset(preset):
                    console.print(f"[green]\u2713[/green] Moving to preset: {preset}")
                else:
                    console.print(f"[red]\u2717[/red] Failed to move to preset: {preset}")
                return

            # Move in direction
            if move:
                direction_map = {
                    "up": PTZDirection.UP,
                    "down": PTZDirection.DOWN,
                    "left": PTZDirection.LEFT,
                    "right": PTZDirection.RIGHT,
                    "zoom_in": PTZDirection.ZOOM_IN,
                    "zoom_out": PTZDirection.ZOOM_OUT,
                }
                direction = direction_map.get(move.lower())
                if not direction:
                    console.print(f"[red]Invalid direction:[/red] {move}")
                    console.print("Valid: up, down, left, right, zoom_in, zoom_out")
                    return

                if await cam.ptz_move(direction, speed):
                    console.print(f"[green]\u2713[/green] Moving {move} at speed {speed}")
                    console.print("[dim]Use --stop to stop movement[/dim]")
                else:
                    console.print(f"[red]\u2717[/red] Failed to move {move}")

    asyncio.run(_ptz())


@onvif_app.command("services")
def onvif_services(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """List available ONVIF services on the camera.

    Displays all ONVIF services exposed by the camera including
    their versions and endpoints.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _services() -> None:
        async with OnvifCamera(config) as cam:
            services = await cam.get_services()

            if services:
                table = Table(title=f"ONVIF Services - {config.ip_address}")
                table.add_column("Service", style="cyan")
                table.add_column("Version", style="green")
                table.add_column("URL", style="dim")

                for s in services:
                    # Extract service name from namespace
                    name = s.namespace.split("/")[-1] if s.namespace else "Unknown"
                    table.add_row(name, s.version, s.xaddr)

                console.print(table)
            else:
                console.print("[yellow]Could not retrieve services[/yellow]")

    asyncio.run(_services())


@onvif_app.command("reboot")
def onvif_reboot(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Reboot the ONVIF camera.

    Sends a reboot command directly to the camera via ONVIF.
    Requires confirmation unless --force is specified.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    if not force:
        confirm = typer.confirm(f"Are you sure you want to reboot {config.ip_address}?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(0)

    async def _reboot() -> None:
        async with OnvifCamera(config) as cam:
            if await cam.reboot():
                console.print(f"[green]\u2713[/green] Reboot initiated for {config.ip_address}")
            else:
                console.print("[red]\u2717[/red] Failed to reboot camera")
                raise typer.Exit(1)

    asyncio.run(_reboot())


@onvif_app.command("scopes")
def onvif_scopes(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="ONVIF username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="ONVIF password")] = None,
    port: Annotated[int, typer.Option("--port", help="ONVIF port")] = 80,
) -> None:
    """List ONVIF device scopes (profile information).

    Displays ONVIF scope URIs that describe the device's
    ONVIF profile compliance and capabilities.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _scopes() -> None:
        async with OnvifCamera(config) as cam:
            scopes = await cam.get_scopes()

            tree = Tree(f"[bold cyan]ONVIF Scopes - {config.ip_address}[/bold cyan]")
            for scope in scopes:
                tree.add(scope)

            console.print(tree)

    asyncio.run(_scopes())


# =============================================================================
# AXIS Camera Logs Commands
# =============================================================================

logs_app = typer.Typer(
    name="logs",
    help="AXIS camera log retrieval via VAPIX API.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(logs_app, name="logs")


@logs_app.command("get")
def logs_get(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    log_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Log type: system, access, audit, all",
            autocompletion=complete_log_types,
        ),
    ] = "system",
    max_entries: Annotated[
        int, typer.Option("--max", "-n", help="Maximum entries to display")
    ] = 50,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw log lines")] = False,
) -> None:
    """Retrieve logs from an AXIS camera.

    Fetches logs from the camera's VAPIX API and displays them
    in a formatted table or raw format.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    # Map log type string to enum
    type_map = {
        "system": LogType.SYSTEM,
        "access": LogType.ACCESS,
        "audit": LogType.AUDIT,
        "all": LogType.ALL,
    }
    lt = type_map.get(log_type.lower())
    if not lt:
        console.print(f"[red]Invalid log type:[/red] {log_type}")
        console.print("Valid types: system, access, audit, all")
        raise typer.Exit(1)

    async def _get_logs() -> None:
        console.print(f"\n[bold]Fetching {log_type} logs from {config.ip_address}...[/bold]")

        try:
            report = await get_camera_logs(config, lt, max_entries)

            console.print(
                f"\n[bold cyan]{report.camera_name}[/bold cyan] - "
                f"{report.log_type.value} logs ({report.total_entries} entries)"
            )

            if raw:
                for entry in report.entries:
                    console.print(entry.raw)
            else:
                table = Table(title=f"{report.log_type.value.title()} Logs")
                table.add_column("Time", style="dim")
                table.add_column("Level", style="cyan")
                table.add_column("Process", style="green")
                table.add_column("Message")

                for entry in report.entries:
                    level_style = (
                        "red"
                        if entry.level.value in ("error", "critical")
                        else ("yellow" if entry.level.value == "warning" else "dim")
                    )
                    table.add_row(
                        entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        f"[{level_style}]{entry.level.value}[/{level_style}]",
                        entry.process or "",
                        entry.message[:80] + ("..." if len(entry.message) > 80 else ""),
                    )

                console.print(table)

        except Exception as e:
            console.print(f"[red]Error retrieving logs:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_logs())


@logs_app.command("system")
def logs_system(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    max_entries: Annotated[
        int, typer.Option("--max", "-n", help="Maximum entries to display")
    ] = 50,
) -> None:
    """Retrieve system logs from an AXIS camera.

    Shortcut for 'logs get --type system'.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_logs() -> None:
        console.print(f"\n[bold]Fetching system logs from {config.ip_address}...[/bold]")

        try:
            async with AxisLogClient(config) as client:
                report = await client.get_system_logs(max_entries)

            console.print(
                f"\n[bold cyan]{report.camera_name}[/bold cyan] - "
                f"System logs ({report.total_entries} entries)"
            )

            table = Table(title="System Logs")
            table.add_column("Time", style="dim")
            table.add_column("Level", style="cyan")
            table.add_column("Process", style="green")
            table.add_column("Message")

            for entry in report.entries:
                level_style = (
                    "red"
                    if entry.level.value in ("error", "critical")
                    else ("yellow" if entry.level.value == "warning" else "dim")
                )
                table.add_row(
                    entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    f"[{level_style}]{entry.level.value}[/{level_style}]",
                    entry.process or "",
                    entry.message[:80] + ("..." if len(entry.message) > 80 else ""),
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error retrieving logs:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_logs())


@logs_app.command("audit")
def logs_audit(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    max_entries: Annotated[
        int, typer.Option("--max", "-n", help="Maximum entries to display")
    ] = 50,
) -> None:
    """Retrieve audit logs from an AXIS camera.

    Shortcut for 'logs get --type audit'.
    Audit logs track configuration changes and administrative actions.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_logs() -> None:
        console.print(f"\n[bold]Fetching audit logs from {config.ip_address}...[/bold]")

        try:
            async with AxisLogClient(config) as client:
                report = await client.get_audit_logs(max_entries)

            console.print(
                f"\n[bold cyan]{report.camera_name}[/bold cyan] - "
                f"Audit logs ({report.total_entries} entries)"
            )

            table = Table(title="Audit Logs")
            table.add_column("Time", style="dim")
            table.add_column("Level", style="cyan")
            table.add_column("Message")

            for entry in report.entries:
                table.add_row(
                    entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    entry.level.value,
                    entry.message,
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error retrieving logs:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_logs())


@logs_app.command("access")
def logs_access(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    max_entries: Annotated[
        int, typer.Option("--max", "-n", help="Maximum entries to display")
    ] = 50,
) -> None:
    """Retrieve access logs from an AXIS camera.

    Shortcut for 'logs get --type access'.
    Access logs track HTTP requests to the camera.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_logs() -> None:
        console.print(f"\n[bold]Fetching access logs from {config.ip_address}...[/bold]")

        try:
            async with AxisLogClient(config) as client:
                report = await client.get_access_logs(max_entries)

            console.print(
                f"\n[bold cyan]{report.camera_name}[/bold cyan] - "
                f"Access logs ({report.total_entries} entries)"
            )

            table = Table(title="Access Logs")
            table.add_column("Time", style="dim")
            table.add_column("Message")

            for entry in report.entries:
                table.add_row(
                    entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    entry.message[:100] + ("..." if len(entry.message) > 100 else ""),
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error retrieving logs:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_logs())


@logs_app.command("files")
def logs_files(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
) -> None:
    """List available log files on an AXIS camera.

    Shows all log files available in the camera's server report.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _list_files() -> None:
        console.print(f"\n[bold]Fetching log files from {config.ip_address}...[/bold]")

        try:
            async with AxisLogClient(config) as client:
                log_files = await client.get_log_files()

            table = Table(title=f"Log Files - {config.ip_address}")
            table.add_column("File", style="cyan")
            table.add_column("Size", style="green")
            table.add_column("Lines", style="yellow")

            for filename, content in sorted(log_files.items()):
                lines = len(content.splitlines())
                size = len(content)
                size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} bytes"
                table.add_row(filename, size_str, str(lines))

            console.print(table)
            console.print(f"\n[bold]Total:[/bold] {len(log_files)} files")

        except Exception as e:
            console.print(f"[red]Error listing files:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_list_files())


# =============================================================================
# AXIS Camera Configuration Commands
# =============================================================================


def _flatten_dict(obj: Any, path: str, result: dict[str, str]) -> None:
    """Recursively flatten a nested dict to dot-notation key=value pairs.

    Args:
        obj: Object to flatten (dict, list, or value).
        path: Current path prefix.
        result: Dictionary to store flattened results.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            _flatten_dict(value, new_path, result)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            _flatten_dict(item, new_path, result)
    else:
        result[path] = str(obj) if obj is not None else ""


def _count_params(obj: Any) -> int:
    """Recursively count leaf parameters in a nested structure.

    Args:
        obj: Object to count (dict, list, or value).

    Returns:
        Number of leaf parameters.
    """
    if isinstance(obj, dict):
        return sum(_count_params(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_params(item) for item in obj)
    return 1


axis_app = typer.Typer(
    name="axis",
    help="AXIS camera configuration via VAPIX API (requires admin credentials).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(axis_app, name="axis")


@axis_app.command("config")
def axis_config(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    group: Annotated[
        str | None, typer.Option("--group", "-g", help="Filter by parameter group")
    ] = None,
    search: Annotated[
        str | None, typer.Option("--search", "-s", help="Search for parameters by name")
    ] = None,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Output as JSON format")] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save JSON output to file (jq-compatible)"),
    ] = None,
) -> None:
    """Get full configuration from an AXIS camera.

    Retrieves all parameters via VAPIX API. Use --group to filter
    by parameter group, or --search to find specific parameters.

    Requires AXIS admin credentials (axis_username/axis_password in config).
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_config() -> None:
        # Suppress status messages when outputting to file
        if not output:
            console.print(f"\n[bold]Fetching configuration from {config.ip_address}...[/bold]")

        try:
            async with AxisConfigClient(config) as client:
                if group:
                    # Get specific group
                    group_data = await client.get_group(group)
                    if not group_data:
                        console.print(f"[yellow]No parameters found in group: {group}[/yellow]")
                        return

                    # File output mode - write JSON only
                    if output:
                        with open(output, "w") as f:
                            json.dump(group_data, f, indent=2)
                        console.print(f"[green]✓[/green] Saved to {output}")
                        return

                    if raw:
                        console.print(json.dumps(group_data, indent=2))
                    else:
                        # Flatten the group data for table display
                        flat_params: dict[str, str] = {}
                        _flatten_dict(group_data, "", flat_params)

                        table = Table(title=f"Parameters - {group}")
                        table.add_column("Parameter", style="cyan")
                        table.add_column("Value", style="green")

                        for key, value in sorted(flat_params.items()):
                            # Truncate long values
                            display_value = value[:60] + "..." if len(value) > 60 else value
                            table.add_row(key, display_value)

                        console.print(table)
                        console.print(f"\n[bold]Total:[/bold] {len(flat_params)} parameters")

                else:
                    # Get all config
                    cfg = await client.get_config()

                    if search:
                        # Search mode
                        matches = cfg.search_params(search)
                        if not matches:
                            console.print(f"[yellow]No parameters matching: {search}[/yellow]")
                            return

                        # File output mode - write JSON only
                        if output:
                            with open(output, "w") as f:
                                json.dump(matches, f, indent=2)
                            console.print(f"[green]✓[/green] Saved to {output}")
                            return

                        if raw:
                            console.print(json.dumps(matches, indent=2))
                        else:
                            table = Table(title=f"Parameters matching '{search}'")
                            table.add_column("Parameter", style="cyan")
                            table.add_column("Value", style="green")

                            for key, value in sorted(matches.items()):
                                val_str = str(value)
                                if len(val_str) > 60:
                                    display_value = val_str[:60] + "..."
                                else:
                                    display_value = val_str
                                table.add_row(key, display_value)

                            console.print(table)
                            console.print(f"\n[bold]Total:[/bold] {len(matches)} parameters")

                    else:
                        # Full config display
                        # File output mode - write JSON only
                        if output:
                            with open(output, "w") as f:
                                json.dump(cfg.data, f, indent=2)
                            console.print(f"[green]✓[/green] Saved to {output}")
                            return

                        console.print(
                            f"\n[bold cyan]{cfg.camera_name}[/bold cyan] - "
                            f"Configuration ({cfg.total_parameters} parameters)"
                        )

                        if raw:
                            console.print(json.dumps(cfg.data, indent=2))
                        else:
                            # Show groups summary
                            table = Table(title="Parameter Groups")
                            table.add_column("Group", style="cyan")
                            table.add_column("Parameters", style="green")

                            for group_name in cfg.groups:
                                group_data = cfg.get_group(group_name)
                                param_count = _count_params(group_data) if group_data else 0
                                table.add_row(group_name, str(param_count))

                            console.print(table)
                            total = cfg.total_parameters
                            console.print(f"\n[bold]Total:[/bold] {total} parameters")
                            console.print("\n[dim]Use --group NAME to see group params[/dim]")
                            console.print("[dim]Use --search PATTERN to find params[/dim]")
                            console.print("[dim]Use --raw for JSON format[/dim]")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                console.print("[red]Error:[/red] Authentication failed (401 Unauthorized)")
                console.print("[dim]Ensure axis credentials are set in config.yaml[/dim]")
            else:
                console.print(f"[red]Error:[/red] HTTP {e.response.status_code}")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error retrieving configuration:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_config())


@axis_app.command("param")
def axis_param(
    name: Annotated[str, typer.Argument(help="Parameter name to retrieve")],
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
) -> None:
    """Get a specific parameter value from an AXIS camera.

    Examples:
        ucam axis param Brand.ProdFullName --camera Front_Of_House
        ucam axis param Network.Bonjour.FriendlyName -c Intercom
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_param() -> None:
        try:
            async with AxisConfigClient(config) as client:
                value = await client.get_parameter(name)

                if value is not None:
                    console.print(f"[cyan]{name}[/cyan] = [green]{value}[/green]")
                else:
                    console.print(f"[yellow]Parameter not found:[/yellow] {name}")
                    raise typer.Exit(1)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                console.print("[red]Error:[/red] Authentication failed (401 Unauthorized)")
            else:
                console.print(f"[red]Error:[/red] HTTP {e.response.status_code}")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_param())


@axis_app.command("groups")
def axis_groups(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
) -> None:
    """List available parameter groups on an AXIS camera.

    Shows all parameter groups and their sizes.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _list_groups() -> None:
        console.print(f"\n[bold]Fetching parameter groups from {config.ip_address}...[/bold]")

        try:
            async with AxisConfigClient(config) as client:
                cfg = await client.get_config()

                table = Table(title=f"Parameter Groups - {cfg.camera_name}")
                table.add_column("Group", style="cyan")
                table.add_column("Parameters", style="green")
                table.add_column("Example Parameter", style="dim")

                for group_name in cfg.groups:
                    group_data = cfg.get_group(group_name)
                    param_count = _count_params(group_data) if group_data else 0
                    # Get first parameter path as example
                    example = ""
                    if group_data and isinstance(group_data, dict):
                        first_key = next(iter(group_data.keys()), "")
                        example = f"{group_name}.{first_key}" if first_key else ""
                    table.add_row(group_name, str(param_count), example)

                console.print(table)
                groups_count = len(cfg.groups)
                params_count = cfg.total_parameters
                console.print(f"\n[bold]Total:[/bold] {groups_count} groups, {params_count} params")
                console.print("\n[dim]Use: ucam axis config --group NAME[/dim]")

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                console.print("[red]Error:[/red] Authentication failed (401 Unauthorized)")
            else:
                console.print(f"[red]Error:[/red] HTTP {e.response.status_code}")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_list_groups())


@axis_app.command("info")
def axis_info(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
) -> None:
    """Get device information from an AXIS camera.

    Shows brand, model, firmware, and other device details
    from the VAPIX parameter API.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _get_info() -> None:
        console.print(f"\n[bold]Fetching device info from {config.ip_address}...[/bold]")

        try:
            async with AxisConfigClient(config) as client:
                brand_data = await client.get_device_info()

                # v2beta API returns nested JSON, so keys are direct (not dot-notation)
                console.print(
                    Panel(
                        f"[bold]Brand:[/bold] {brand_data.get('Brand', 'N/A')}\n"
                        f"[bold]Product:[/bold] {brand_data.get('ProdFullName', 'N/A')}\n"
                        f"[bold]Short Name:[/bold] {brand_data.get('ProdShortName', 'N/A')}\n"
                        f"[bold]Type:[/bold] {brand_data.get('ProdType', 'N/A')}\n"
                        f"[bold]Number:[/bold] {brand_data.get('ProdNbr', 'N/A')}\n"
                        f"[bold]Variant:[/bold] {brand_data.get('ProdVariant', 'N/A')}\n"
                        f"[bold]Web URL:[/bold] {brand_data.get('WebURL', 'N/A')}",
                        title=f"[cyan]AXIS Device Info - {config.ip_address}[/cyan]",
                        expand=False,
                    )
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                console.print("[red]Error:[/red] Authentication failed (401 Unauthorized)")
            else:
                console.print(f"[red]Error:[/red] HTTP {e.response.status_code}")
            raise typer.Exit(1) from e
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from e

    asyncio.run(_get_info())


@axis_app.command("lldp")
def axis_lldp(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON response")] = False,
) -> None:
    """Get LLDP status and neighbors from an AXIS camera.

    Shows LLDP (Link Layer Discovery Protocol) information including
    connected switch ports and network topology data. Useful for
    troubleshooting network connectivity issues.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _lldp() -> None:
        console.print(f"\n[bold]Fetching LLDP info from {config.ip_address}...[/bold]")

        try:
            async with AxisLLDPClient(config) as client:
                if raw:
                    # Show raw JSON
                    status_data = await client.get_raw_status()
                    neighbors_data = await client.get_raw_neighbors()
                    import json

                    console.print("\n[bold cyan]LLDP Status (raw):[/bold cyan]")
                    console.print(json.dumps(status_data, indent=2))
                    console.print("\n[bold cyan]LLDP Neighbors (raw):[/bold cyan]")
                    console.print(json.dumps(neighbors_data, indent=2))
                    return

                # Get structured data
                status = await client.get_status()
                neighbors = await client.get_neighbors()

                # Display status
                enabled_str = "[green]Enabled[/green]" if status.enabled else "[red]Disabled[/red]"
                console.print(
                    Panel(
                        f"[bold]Status:[/bold] {enabled_str}\n"
                        f"[bold]Transmit Interval:[/bold] {status.transmit_interval}s\n"
                        f"[bold]Hold Multiplier:[/bold] {status.hold_multiplier}\n"
                        f"[bold]Chassis ID:[/bold] {status.chassis_id or 'N/A'}\n"
                        f"[bold]Port ID:[/bold] {status.port_id or 'N/A'}\n"
                        f"[bold]System Name:[/bold] {status.system_name or 'N/A'}",
                        title=f"[cyan]LLDP Status - {config.ip_address}[/cyan]",
                        expand=False,
                    )
                )

                # Display neighbors
                if neighbors:
                    table = Table(title="LLDP Neighbors")
                    table.add_column("System Name", style="cyan")
                    table.add_column("Port", style="green")
                    table.add_column("Port Description", style="yellow")
                    table.add_column("Chassis ID", style="dim")
                    table.add_column("Mgmt Address", style="blue")

                    for n in neighbors:
                        table.add_row(
                            n.system_name or "N/A",
                            n.port_id or "N/A",
                            n.port_description or "N/A",
                            n.chassis_id[:20] + "..." if len(n.chassis_id) > 20 else n.chassis_id,
                            n.management_address or "N/A",
                        )

                    console.print(table)
                else:
                    console.print("[yellow]No LLDP neighbors discovered[/yellow]")

        except Exception as e:
            console.print(f"[red]Error retrieving LLDP info:[/red] {e}")
            log_error(f"LLDP retrieval failed: {e}")
            raise typer.Exit(1) from e

    asyncio.run(_lldp())


@axis_app.command("diagnostics")
def axis_diagnostics(
    camera: Annotated[
        str | None,
        typer.Option(
            "--camera",
            "-c",
            help="Camera name from config.yaml",
            autocompletion=complete_camera_names,
        ),
    ] = None,
    ip: Annotated[str | None, typer.Option("--ip", help="Camera IP address")] = None,
    user: Annotated[str | None, typer.Option("--user", "-u", help="Camera username")] = None,
    password: Annotated[str | None, typer.Option("--pass", "-p", help="Camera password")] = None,
    port: Annotated[int, typer.Option("--port", help="HTTP port")] = 80,
) -> None:
    """Get stream and network diagnostics from an AXIS camera.

    Shows RTSP settings, RTP configuration, stream profiles, and network
    configuration. Useful for troubleshooting stream connectivity issues
    such as streams stopping when paired with third-party devices.
    """
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _diagnostics() -> None:
        console.print(f"\n[bold]Fetching diagnostics from {config.ip_address}...[/bold]")

        try:
            async with AxisDiagnosticsClient(config) as client:
                diag = await client.get_full_diagnostics()

                # Show errors if any occurred
                if diag.errors:
                    console.print(
                        Panel(
                            "\n".join(f"[red]\u2717[/red] {err}" for err in diag.errors),
                            title="[red]Errors[/red]",
                            expand=False,
                        )
                    )
                    console.print(
                        "[yellow]Note: Values below may be defaults "
                        "due to retrieval errors.[/yellow]\n"
                    )

                # RTSP Configuration
                rtsp = diag.rtsp
                rtsp_status = "[green]Enabled[/green]" if rtsp.enabled else "[red]Disabled[/red]"
                path_args = "Allowed" if rtsp.allow_path_arguments else "Denied"
                console.print(
                    Panel(
                        f"[bold]Status:[/bold] {rtsp_status}\n"
                        f"[bold]Port:[/bold] {rtsp.port}\n"
                        f"[bold]Authentication:[/bold] {rtsp.authentication}\n"
                        f"[bold]Timeout:[/bold] {rtsp.timeout}s\n"
                        f"[bold]Path Arguments:[/bold] {path_args}",
                        title="[cyan]RTSP Configuration[/cyan]",
                        expand=False,
                    )
                )

                # RTP Configuration
                rtp = diag.rtp
                mcast = "[green]Enabled[/green]" if rtp.multicast_enabled else "[dim]Disabled[/dim]"
                console.print(
                    Panel(
                        f"[bold]Port Range:[/bold] {rtp.start_port} - {rtp.end_port}\n"
                        f"[bold]Multicast:[/bold] {mcast}\n"
                        + (
                            f"[bold]Multicast Address:[/bold] {rtp.multicast_address}"
                            if rtp.multicast_address
                            else ""
                        ),
                        title="[cyan]RTP Configuration[/cyan]",
                        expand=False,
                    )
                )

                # Stream Profiles
                if diag.profiles:
                    table = Table(title="Stream Profiles")
                    table.add_column("Name", style="cyan")
                    table.add_column("Codec", style="green")
                    table.add_column("Resolution")
                    table.add_column("FPS", style="yellow")
                    table.add_column("Bitrate", style="blue")
                    table.add_column("GOP")

                    for p in diag.profiles:
                        bitrate_str = f"{p.bitrate} kbps" if p.bitrate else "Variable"
                        table.add_row(
                            p.name,
                            p.video_codec,
                            p.resolution or "N/A",
                            str(p.fps),
                            bitrate_str,
                            str(p.gop_length),
                        )

                    console.print(table)

                # Network Configuration
                net = diag.network
                dhcp = "[green]DHCP[/green]" if net.dhcp_enabled else "[yellow]Static[/yellow]"
                ipv6 = "[green]Enabled[/green]" if net.ipv6_enabled else "[dim]Disabled[/dim]"
                console.print(
                    Panel(
                        f"[bold]Hostname:[/bold] {net.hostname or 'N/A'}\n"
                        f"[bold]IP Config:[/bold] {dhcp}\n"
                        f"[bold]IP Address:[/bold] {net.ip_address or 'N/A'}\n"
                        f"[bold]Gateway:[/bold] {net.gateway or 'N/A'}\n"
                        f"[bold]MTU:[/bold] {net.mtu}\n"
                        f"[bold]IPv6:[/bold] {ipv6}",
                        title="[cyan]Network Configuration[/cyan]",
                        expand=False,
                    )
                )

                log_debug(f"Diagnostics retrieved for {config.ip_address}")

        except Exception as e:
            console.print(f"[red]Error retrieving diagnostics:[/red] {e}")
            log_error(f"Diagnostics retrieval failed: {e}")
            raise typer.Exit(1) from e

    asyncio.run(_diagnostics())


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
