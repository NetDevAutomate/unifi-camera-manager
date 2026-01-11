"""CLI for UniFi Camera Manager."""

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .client import get_protect_client
from .config import (
    OnvifCameraConfig,
    ProtectConfig,
    get_camera_by_name,
    list_camera_names,
    load_cameras_config,
)
from .onvif_discovery import (
    check_camera_connectivity,
    get_onvif_stream_uri,
    verify_onvif_camera,
)
from .onvif_manager import OnvifCamera, PTZDirection

app = typer.Typer(
    name="unifi-camera-manager",
    help="Manage UniFi Protect cameras via CLI",
    no_args_is_help=True,
)
console = Console()


def get_config(env_file: Path | None = None) -> ProtectConfig:
    """Get configuration from environment."""
    try:
        return ProtectConfig.from_env(env_file)
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command("list")
def list_cameras(
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
    show_third_party_only: bool = typer.Option(
        False, "--third-party", "-t", help="Show only third-party cameras"
    ),
    show_unadopted: bool = typer.Option(
        True, "--include-unadopted", "-u", help="Include unadopted devices"
    ),
) -> None:
    """List all cameras in UniFi Protect."""
    config = get_config(env_file)

    async def _list():
        async with get_protect_client(config, include_unadopted=show_unadopted) as client:
            cameras = await client.list_cameras()
            nvr_info = await client.get_nvr_info()

            console.print(f"\n[bold]NVR:[/bold] {nvr_info['name']} ({nvr_info['version']})")
            console.print(f"[bold]Model:[/bold] {nvr_info['model']}\n")

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
                adopted_str = "✓" if cam.is_adopted else "✗"
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

    asyncio.run(_list())


@app.command("info")
def camera_info(
    camera_id: str = typer.Argument(..., help="Camera ID or IP address"),
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
) -> None:
    """Get detailed information about a specific camera."""
    config = get_config(env_file)

    async def _info():
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
            console.print(f"  [bold]IP Address:[/bold] {str(camera.host) if camera.host else 'N/A'}")
            console.print(f"  [bold]Adopted:[/bold] {'Yes' if camera.is_adopted else 'No'}")
            console.print(f"  [bold]State:[/bold] {str(camera.state)}")
            console.print(f"  [bold]Third-Party:[/bold] {'Yes' if camera.is_third_party else 'No'}")
            if camera.last_seen:
                console.print(f"  [bold]Last Seen:[/bold] {camera.last_seen}")

    asyncio.run(_info())


@app.command("adopt")
def adopt_camera(
    camera_id: str = typer.Argument(..., help="Camera ID to adopt"),
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
) -> None:
    """Adopt an unadopted camera into UniFi Protect."""
    config = get_config(env_file)

    async def _adopt():
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
                console.print("[green]✓[/green] Adoption initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]✗[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_adopt())


@app.command("unadopt")
def unadopt_camera(
    camera_id: str = typer.Argument(..., help="Camera ID to unadopt"),
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Remove/unadopt a camera from UniFi Protect."""
    config = get_config(env_file)

    async def _unadopt():
        async with get_protect_client(config) as client:
            camera = await client.get_camera(camera_id)
            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            if not force:
                confirm = typer.confirm(
                    f"Are you sure you want to unadopt '{camera.name}'?"
                )
                if not confirm:
                    console.print("[yellow]Cancelled[/yellow]")
                    raise typer.Exit(0)

            console.print(f"Unadopting camera: [cyan]{camera.name}[/cyan]...")
            try:
                await client.unadopt_camera(camera_id)
                console.print("[green]✓[/green] Unadoption initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]✗[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_unadopt())


@app.command("reboot")
def reboot_camera(
    camera_id: str = typer.Argument(..., help="Camera ID to reboot"),
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
) -> None:
    """Reboot a camera."""
    config = get_config(env_file)

    async def _reboot():
        async with get_protect_client(config) as client:
            camera = await client.get_camera(camera_id)
            if not camera:
                console.print(f"[red]Camera not found:[/red] {camera_id}")
                raise typer.Exit(1)

            console.print(f"Rebooting camera: [cyan]{camera.name}[/cyan]...")
            try:
                await client.reboot_camera(camera_id)
                console.print("[green]✓[/green] Reboot initiated successfully")
            except RuntimeError as e:
                console.print(f"[red]✗[/red] {e}")
                raise typer.Exit(1) from e

    asyncio.run(_reboot())


@app.command("verify-onvif")
def verify_onvif(
    ip_address: str = typer.Argument(..., help="Camera IP address"),
    username: str = typer.Option(..., "--user", "-u", help="ONVIF username"),
    password: str = typer.Option(..., "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port (default: 80)"),
) -> None:
    """Verify ONVIF camera connectivity and get device information."""

    async def _verify():
        console.print(f"\n[bold]Checking camera at {ip_address}:{port}...[/bold]")

        # First check basic connectivity
        console.print("  Checking network connectivity...", end=" ")
        is_reachable = await check_camera_connectivity(ip_address, port)
        if is_reachable:
            console.print("[green]✓[/green]")
        else:
            console.print("[red]✗[/red] Camera not reachable")
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
            console.print("[green]✓[/green]")
            console.print(f"\n[bold cyan]Camera Information:[/bold cyan]")
            console.print(f"  [bold]Manufacturer:[/bold] {info.manufacturer}")
            console.print(f"  [bold]Model:[/bold] {info.model}")
            console.print(f"  [bold]Firmware:[/bold] {info.firmware_version}")
            console.print(f"  [bold]Serial:[/bold] {info.serial_number}")
            console.print(f"  [bold]Hardware ID:[/bold] {info.hardware_id}")

            # Try to get stream URI
            console.print("\n  Getting RTSP stream URI...", end=" ")
            stream_uri = await get_onvif_stream_uri(config)
            if stream_uri:
                console.print("[green]✓[/green]")
                console.print(f"  [bold]Stream URI:[/bold] {stream_uri}")
            else:
                console.print("[yellow]N/A[/yellow]")
        else:
            console.print("[red]✗[/red]")
            console.print(f"  [red]Error:[/red] {info.error}")
            raise typer.Exit(1)

    asyncio.run(_verify())


@app.command("find")
def find_camera(
    ip_address: str = typer.Argument(..., help="IP address to search for"),
    env_file: Path | None = typer.Option(
        None, "--env", "-e", help="Path to .env file"
    ),
) -> None:
    """Find a camera by IP address in UniFi Protect."""
    config = get_config(env_file)

    async def _find():
        async with get_protect_client(config) as client:
            camera = await client.get_camera_by_ip(ip_address)

            if camera:
                console.print(f"\n[green]✓[/green] Camera found at {ip_address}:")
                console.print(f"  [bold]Name:[/bold] {camera.name}")
                console.print(f"  [bold]ID:[/bold] {camera.id}")
                console.print(f"  [bold]Type:[/bold] {camera.type}")
                console.print(f"  [bold]Adopted:[/bold] {'Yes' if camera.is_adopted else 'No'}")
            else:
                console.print(f"\n[yellow]![/yellow] No camera found at {ip_address}")
                console.print("\n[bold]Suggestions:[/bold]")
                console.print("  1. Ensure 'Discover Third-Party Cameras' is enabled in Protect settings")
                console.print("  2. Verify the camera has ONVIF enabled")
                console.print("  3. Check the camera is on the same network as the NVR")
                console.print("  4. Use 'verify-onvif' command to test ONVIF connectivity")

    asyncio.run(_find())


# =============================================================================
# ONVIF Camera Management Commands
# =============================================================================

# Create a sub-app for ONVIF-specific commands
onvif_app = typer.Typer(
    name="onvif",
    help="ONVIF camera management commands",
    no_args_is_help=True,
)
app.add_typer(onvif_app, name="onvif")


def get_onvif_config_from_env() -> OnvifCameraConfig:
    """Get ONVIF config from environment variables."""
    ip = os.getenv("ONVIF_IP")
    user = os.getenv("ONVIF_USER")
    password = os.getenv("ONVIF_PASSWORD")
    port = int(os.getenv("ONVIF_PORT", "80"))

    if not all([ip, user, password]):
        raise ValueError(
            "Missing ONVIF environment variables. Set ONVIF_IP, ONVIF_USER, ONVIF_PASSWORD"
        )

    return OnvifCameraConfig(
        ip_address=ip,
        username=user,
        password=password,
        port=port,
    )


def get_onvif_config(
    ip: str | None,
    user: str | None,
    password: str | None,
    port: int,
    camera_name: str | None = None,
) -> OnvifCameraConfig:
    """Get ONVIF config from args, camera name, or environment.

    Priority:
    1. Explicit --ip, --user, --pass args
    2. Camera name from --camera (loads from config.yaml)
    3. Environment variables (ONVIF_IP, ONVIF_USER, ONVIF_PASSWORD)
    """
    # If explicit args provided, use them
    if ip and user and password:
        return OnvifCameraConfig(
            ip_address=ip,
            username=user,
            password=password,
            port=port,
        )

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
        "Provide --camera NAME, --ip/--user/--pass, or set ONVIF_* env vars"
    )


@onvif_app.command("list")
def onvif_list() -> None:
    """List all cameras from config.yaml."""
    try:
        cameras = load_cameras_config()
    except FileNotFoundError:
        console.print("[yellow]No config.yaml found.[/yellow]")
        console.print("Create a config.yaml file with camera definitions.")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1)

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
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
) -> None:
    """Get comprehensive ONVIF camera information."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _info():
        console.print(f"\n[bold]Connecting to {config.ip_address}:{config.port}...[/bold]")

        async with OnvifCamera(config) as cam:
            # System Info
            sys_info = await cam.get_system_info()
            console.print(Panel(
                f"[bold]Manufacturer:[/bold] {sys_info.manufacturer}\n"
                f"[bold]Model:[/bold] {sys_info.model}\n"
                f"[bold]Firmware:[/bold] {sys_info.firmware_version}\n"
                f"[bold]Serial:[/bold] {sys_info.serial_number}\n"
                f"[bold]Hardware ID:[/bold] {sys_info.hardware_id}"
                + (f"\n[bold]System Time:[/bold] {sys_info.system_date_time}" if sys_info.system_date_time else ""),
                title="[cyan]System Information[/cyan]",
                expand=False,
            ))

            # Capabilities
            caps = await cam.get_capabilities()
            cap_items = []
            if caps.has_ptz:
                cap_items.append("[green]✓[/green] PTZ")
            else:
                cap_items.append("[dim]✗ PTZ[/dim]")
            if caps.has_audio:
                cap_items.append("[green]✓[/green] Audio")
            else:
                cap_items.append("[dim]✗ Audio[/dim]")
            if caps.has_events:
                cap_items.append("[green]✓[/green] Events")
            else:
                cap_items.append("[dim]✗ Events[/dim]")
            if caps.has_analytics:
                cap_items.append("[green]✓[/green] Analytics")
            else:
                cap_items.append("[dim]✗ Analytics[/dim]")

            console.print(Panel(
                "  ".join(cap_items) +
                f"\n[bold]Encodings:[/bold] {', '.join(caps.supported_encodings) or 'N/A'}"
                f"\n[bold]Profiles:[/bold] {caps.max_profiles}",
                title="[cyan]Capabilities[/cyan]",
                expand=False,
            ))

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
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
) -> None:
    """List all available RTSP stream URIs."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _streams():
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
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
) -> None:
    """List video profiles with detailed configuration."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _profiles():
        async with OnvifCamera(config) as cam:
            profiles = await cam.get_profiles()

            for p in profiles:
                console.print(Panel(
                    f"[bold]Resolution:[/bold] {p.resolution_width}x{p.resolution_height}\n"
                    f"[bold]Encoding:[/bold] {p.encoding}\n"
                    f"[bold]Frame Rate:[/bold] {p.frame_rate} fps\n"
                    f"[bold]Bitrate:[/bold] {p.bitrate} kbps" if p.bitrate else "" +
                    f"\n[bold]Quality:[/bold] {p.quality}" if p.quality else "",
                    title=f"[cyan]{p.name}[/cyan] ({p.token})",
                    expand=False,
                ))

    asyncio.run(_profiles())


@onvif_app.command("image")
def onvif_image(
    camera: str | None = typer.Option(None, "--camera", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
    brightness: float | None = typer.Option(None, "--brightness", "-b", help="Set brightness (0-100)"),
    contrast: float | None = typer.Option(None, "--contrast", "-c", help="Set contrast (0-100)"),
    saturation: float | None = typer.Option(None, "--saturation", "-s", help="Set saturation (0-100)"),
    sharpness: float | None = typer.Option(None, "--sharpness", help="Set sharpness (0-100)"),
) -> None:
    """Get or set image settings (brightness, contrast, etc.)."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _image():
        async with OnvifCamera(config) as cam:
            # Set values if provided
            settings_changed = False
            if brightness is not None:
                if await cam.set_image_setting("brightness", brightness):
                    console.print(f"[green]✓[/green] Brightness set to {brightness}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set brightness")

            if contrast is not None:
                if await cam.set_image_setting("contrast", contrast):
                    console.print(f"[green]✓[/green] Contrast set to {contrast}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set contrast")

            if saturation is not None:
                if await cam.set_image_setting("saturation", saturation):
                    console.print(f"[green]✓[/green] Saturation set to {saturation}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set saturation")

            if sharpness is not None:
                if await cam.set_image_setting("sharpness", sharpness):
                    console.print(f"[green]✓[/green] Sharpness set to {sharpness}")
                    settings_changed = True
                else:
                    console.print("[yellow]![/yellow] Could not set sharpness")

            # Show current settings
            if not settings_changed:
                settings = await cam.get_image_settings()
                if settings:
                    console.print(Panel(
                        f"[bold]Brightness:[/bold] {settings.brightness or 'N/A'}\n"
                        f"[bold]Contrast:[/bold] {settings.contrast or 'N/A'}\n"
                        f"[bold]Saturation:[/bold] {settings.saturation or 'N/A'}\n"
                        f"[bold]Sharpness:[/bold] {settings.sharpness or 'N/A'}\n"
                        f"[bold]IR Cut Filter:[/bold] {settings.ir_cut_filter or 'N/A'}\n"
                        f"[bold]WDR:[/bold] {'Enabled' if settings.wide_dynamic_range else 'Disabled' if settings.wide_dynamic_range is not None else 'N/A'}\n"
                        f"[bold]Backlight Comp:[/bold] {'Enabled' if settings.backlight_compensation else 'Disabled' if settings.backlight_compensation is not None else 'N/A'}",
                        title="[cyan]Image Settings[/cyan]",
                        expand=False,
                    ))
                else:
                    console.print("[yellow]Image settings not available for this camera[/yellow]")

    asyncio.run(_image())


@onvif_app.command("ptz")
def onvif_ptz(
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
    move: str | None = typer.Option(None, "--move", "-m", help="Move direction: up, down, left, right, zoom_in, zoom_out"),
    speed: float = typer.Option(0.5, "--speed", "-s", help="Movement speed (0.0-1.0)"),
    stop: bool = typer.Option(False, "--stop", help="Stop PTZ movement"),
    home: bool = typer.Option(False, "--home", help="Move to home position"),
    preset: str | None = typer.Option(None, "--preset", "-g", help="Go to preset by token"),
    list_presets: bool = typer.Option(False, "--list-presets", "-l", help="List PTZ presets"),
) -> None:
    """PTZ (Pan/Tilt/Zoom) camera control."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _ptz():
        async with OnvifCamera(config) as cam:
            if not await cam.has_ptz():
                console.print("[yellow]This camera does not support PTZ[/yellow]")
                return

            # Get current status
            status = await cam.get_ptz_status()
            if status:
                console.print(Panel(
                    f"[bold]Pan:[/bold] {status.pan:.3f}\n"
                    f"[bold]Tilt:[/bold] {status.tilt:.3f}\n"
                    f"[bold]Zoom:[/bold] {status.zoom:.3f}\n"
                    f"[bold]Moving:[/bold] {'Yes' if status.moving else 'No'}",
                    title="[cyan]PTZ Status[/cyan]",
                    expand=False,
                ))

            # List presets
            if list_presets:
                presets = await cam.get_ptz_presets()
                if presets:
                    table = Table(title="PTZ Presets")
                    table.add_column("Token", style="cyan")
                    table.add_column("Name")
                    for p in presets:
                        table.add_row(p["token"], p["name"])
                    console.print(table)
                else:
                    console.print("[dim]No presets configured[/dim]")
                return

            # Stop movement
            if stop:
                if await cam.ptz_stop():
                    console.print("[green]✓[/green] PTZ stopped")
                else:
                    console.print("[red]✗[/red] Failed to stop PTZ")
                return

            # Go home
            if home:
                if await cam.ptz_home():
                    console.print("[green]✓[/green] Moving to home position")
                else:
                    console.print("[red]✗[/red] Failed to move to home")
                return

            # Go to preset
            if preset:
                if await cam.ptz_goto_preset(preset):
                    console.print(f"[green]✓[/green] Moving to preset: {preset}")
                else:
                    console.print(f"[red]✗[/red] Failed to move to preset: {preset}")
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
                    console.print(f"[green]✓[/green] Moving {move} at speed {speed}")
                    console.print("[dim]Use --stop to stop movement[/dim]")
                else:
                    console.print(f"[red]✗[/red] Failed to move {move}")

    asyncio.run(_ptz())


@onvif_app.command("services")
def onvif_services(
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
) -> None:
    """List available ONVIF services on the camera."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _services():
        async with OnvifCamera(config) as cam:
            services = await cam.get_services()

            if services:
                table = Table(title=f"ONVIF Services - {config.ip_address}")
                table.add_column("Service", style="cyan")
                table.add_column("Version", style="green")
                table.add_column("URL", style="dim")

                for s in services:
                    # Extract service name from namespace
                    name = s["namespace"].split("/")[-1] if s["namespace"] else "Unknown"
                    table.add_row(name, s["version"], s["xaddr"])

                console.print(table)
            else:
                console.print("[yellow]Could not retrieve services[/yellow]")

    asyncio.run(_services())


@onvif_app.command("reboot")
def onvif_reboot(
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Reboot the ONVIF camera."""
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

    async def _reboot():
        async with OnvifCamera(config) as cam:
            if await cam.reboot():
                console.print(f"[green]✓[/green] Reboot initiated for {config.ip_address}")
            else:
                console.print("[red]✗[/red] Failed to reboot camera")
                raise typer.Exit(1)

    asyncio.run(_reboot())


@onvif_app.command("scopes")
def onvif_scopes(
    camera: str | None = typer.Option(None, "--camera", "-c", help="Camera name from config.yaml"),
    ip: str | None = typer.Option(None, "--ip", help="Camera IP address"),
    user: str | None = typer.Option(None, "--user", "-u", help="ONVIF username"),
    password: str | None = typer.Option(None, "--pass", "-p", help="ONVIF password"),
    port: int = typer.Option(80, "--port", help="ONVIF port"),
) -> None:
    """List ONVIF device scopes (profile information)."""
    try:
        config = get_onvif_config(ip, user, password, port, camera)
    except (ValueError, typer.BadParameter) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    async def _scopes():
        async with OnvifCamera(config) as cam:
            scopes = await cam.get_scopes()

            tree = Tree(f"[bold cyan]ONVIF Scopes - {config.ip_address}[/bold cyan]")
            for scope in scopes:
                tree.add(scope)

            console.print(tree)

    asyncio.run(_scopes())


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
