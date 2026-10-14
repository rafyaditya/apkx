import sys
from pathlib import Path
from typing import List, Optional, Tuple

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

# Pastikan output stream di Windows menggunakan UTF-8
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "bold magenta",
})

console = Console(theme=custom_theme)
console_err = Console(theme=custom_theme, stderr=True)


def print_banner() -> None:
    """Displays the app banner."""
    console.print(
        Panel.fit(
            "[bold cyan]>> apkx[/bold cyan] - [bold white]Android APK & Split-APK Extractor[/bold white]\n"
            "[dim]Tarik file APK dari HP Android langsung ke komputermu dengan cepat[/dim]",
            border_style="cyan",
        )
    )


def show_error(message: str, title: str = "Error") -> None:
    """Displays an error panel."""
    console.print(Panel(f"[error]{message}[/error]", title=f"[bold red]{title}[/bold red]", border_style="red"))


def show_warning(message: str, title: str = "Peringatan") -> None:
    """Displays a warning panel."""
    console.print(Panel(f"[warning]{message}[/warning]", title=f"[bold yellow]{title}[/bold yellow]", border_style="yellow"))


def show_no_device_help() -> None:
    """Displays comprehensive troubleshooting when no device is detected."""
    help_text = (
        "[bold red]Tidak ada perangkat Android yang terdeteksi via ADB![/bold red]\n\n"
        "[bold white]Langkah penyelesaian:[/bold white]\n"
        "  1. Pastikan HP terhubung ke komputer menggunakan kabel USB.\n"
        "  2. Pastikan [bold cyan]USB Debugging[/bold cyan] sudah aktif di menu Developer Options.\n"
        "  3. Cek notifikasi di layar HP dan pilih [bold cyan]Allow / Izinkan USB debugging[/bold cyan].\n"
        "  4. Cek koneksi di terminal dengan perintah: [bold green]apkx devices[/bold green]\n"
    )
    console.print(Panel(help_text, title="[bold red]Perangkat Tidak Ditemukan[/bold red]", border_style="red"))


def show_devices_table(devices: List[dict]) -> None:
    """Displays connected Android devices in a styled Rich table."""
    table = Table(title="Daftar Perangkat Android Terhubung", border_style="cyan")
    table.add_column("No", justify="right", style="cyan", no_wrap=True)
    table.add_column("Serial ID", style="bold white")
    table.add_column("Merk & Model", style="bold yellow")
    table.add_column("Versi OS", style="cyan")
    table.add_column("Status", justify="center")

    has_unauthorized = False

    for idx, d in enumerate(devices, start=1):
        status_raw = d.get("status", "")
        if status_raw == "device":
            status_display = "[bold green][V] Siap Digunakan[/bold green]"
        elif status_raw == "unauthorized":
            status_display = "[bold yellow][!] Perlu Izin HP[/bold yellow]"
            has_unauthorized = True
        elif status_raw == "offline":
            status_display = "[bold red][X] Offline[/bold red]"
        else:
            status_display = f"[dim]{status_raw}[/dim]"

        brand = d.get("brand", "-")
        model = d.get("model", "-")
        if brand != "-" and model != "-":
            device_label = f"{brand} {model}"
        elif model != "-":
            device_label = model
        else:
            device_label = brand

        table.add_row(
            str(idx),
            d.get("serial", "-"),
            device_label,
            d.get("android_version", "-"),
            status_display,
        )

    console.print(table)

    if has_unauthorized:
        console.print(
            "\n[bold yellow]Catatan:[/bold yellow] Terdapat perangkat berstatus '[!] Perlu Izin HP'.\n"
            "Buka kunci layar HP Anda dan pilih '[bold cyan]Allow / Izinkan USB debugging[/bold cyan]' agar dapat diakses.\n"
        )


def show_unauthorized_device_help(serial: str) -> None:
    """Displays help when a device is connected but unauthorized."""
    help_text = (
        f"[bold yellow]Perangkat '{serial}' terhubung namun belum diizinkan (Unauthorized)![/bold yellow]\n\n"
        "[bold white]Silakan cek layar HP Anda sekarang:[/bold white]\n"
        "  1. Buka kunci layar (unlock screen) HP Anda.\n"
        "  2. Akan muncul pop-up izin [italic]'Allow USB debugging?'[/italic].\n"
        "  3. Centang [bold cyan]'Always allow from this computer'[/bold cyan] lalu tekan [bold green]Allow/OK[/bold green].\n"
    )
    console.print(Panel(help_text, title="[bold yellow]Izin USB Debugging Diperlukan[/bold yellow]", border_style="yellow"))


def select_devices(device_details: List[dict]) -> Optional[List[dict]]:
    """
    If multiple authorized devices are connected, prompts user to select one or all.
    Returns:
      - None if user cancels (KeyboardInterrupt).
      - List containing all device dicts if '[Semua Perangkat]' chosen.
      - List containing single chosen device dict if specific device chosen.
    """
    authorized = [d for d in device_details if d.get("status") == "device"]
    if not authorized:
        return None
    if len(authorized) == 1:
        return authorized

    choices = [
        questionary.Choice(
            title=f"[Semua Perangkat] (Ekstrak dari seluruh {len(authorized)} HP terhubung)",
            value="ALL",
        )
    ]
    for idx, d in enumerate(authorized, start=1):
        serial = d.get("serial", "")
        brand = d.get("brand", "")
        model = d.get("model", "")
        version = d.get("android_version", "")
        if brand != "-" and model != "-":
            label = f"{brand} {model}"
        elif model != "-":
            label = model
        else:
            label = serial

        ver_str = f" - {version}" if version and version != "-" else ""
        title = f"{idx}. {label} ({serial}){ver_str}"
        choices.append(questionary.Choice(title=title, value=serial))

    try:
        selected_val = questionary.select(
            f"Ditemukan {len(authorized)} perangkat Android terhubung. Pilih target:",
            choices=choices,
        ).ask()
    except KeyboardInterrupt:
        return None

    if selected_val == "ALL":
        return authorized
    elif selected_val:
        for d in authorized:
            if d.get("serial") == selected_val:
                return [d]

    return None


def select_device(devices: List[Tuple[str, str]]) -> Optional[str]:
    """If multiple authorized devices are connected, prompts user to select one."""
    if len(devices) == 1:
        return devices[0][0]

    choices = [f"{serial} ({status})" for serial, status in devices if status == "device"]
    if not choices:
        return None

    choice = questionary.select(
        "Ditemukan beberapa perangkat. Pilih perangkat yang ingin digunakan:",
        choices=choices,
    ).ask()

    if choice:
        return choice.split()[0]
    return None


def select_package_interactive(apps: list, prefilter_query: Optional[str] = None) -> Optional[str]:
    """
    Prompts the user to pick a package with live fuzzy search.
    """
    if not apps:
        return None

    message = (
        f"Pilih aplikasi yang cocok dengan '{prefilter_query}' (ketik untuk menyaring):"
        if prefilter_query
        else "Pilih aplikasi yang ingin diekstrak (ketik langsung untuk mencari/filter):"
    )

    choices = []
    for item in apps:
        if hasattr(item, "app_name") and hasattr(item, "package_name"):
            choices.append(questionary.Choice(title=f"{item.app_name}  ({item.package_name})", value=item.package_name))
        else:
            choices.append(str(item))

    try:
        selected = questionary.select(
            message,
            choices=choices,
            use_search_filter=True,
            use_jk_keys=False,
            use_indicator=True,
        ).ask()
        return selected
    except KeyboardInterrupt:
        return None


def show_package_table(apps: list, title: str = "Daftar Aplikasi") -> None:
    """Displays installed packages in a neat multi-column or numbered table."""
    table = Table(title=title, border_style="dim")
    table.add_column("No", justify="right", style="cyan", no_wrap=True)
    table.add_column("Nama Aplikasi", style="bold green")
    table.add_column("Package ID", style="white")

    for idx, item in enumerate(apps, start=1):
        if hasattr(item, "app_name") and hasattr(item, "package_name"):
            table.add_row(str(idx), item.app_name, item.package_name)
        else:
            table.add_row(str(idx), "-", str(item))

    console.print(table)


def show_success_summary(
    package_name: str,
    output_path: Optional[Path] = None,
    is_split: bool = False,
    total_parts: int = 1,
    size_str: Optional[str] = None,
    app_name: Optional[str] = None,
    extracted_folder: Optional[Path] = None,
    framework_info: Optional[dict] = None,
) -> None:
    """Displays a clean summary table of the extracted APK/APKS and unpacked folder."""
    table = Table(title="[bold green][V] Operasi Berhasil![/bold green]", border_style="green", show_header=False)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Nama Aplikasi", f"[bold green]{app_name or package_name}[/bold green]")
    table.add_row("Package ID", package_name)

    if output_path:
        table.add_row("Format APK", f"[bold yellow]Split APK ({total_parts} part / .apks)[/bold yellow]" if is_split else "[bold green]Single APK (.apk)[/bold green]")
        if size_str:
            table.add_row("Ukuran File", size_str)
        table.add_row("File APK", f"[cyan]{output_path.resolve()}[/cyan]")

    if extracted_folder:
        table.add_row("Folder Ekstrak", f"[bold green]{extracted_folder.resolve()}[/bold green]")

    if framework_info:
        table.add_row("Teknologi", f"[bold magenta]{framework_info.get('framework', '-')}[/bold magenta]")
        table.add_row("Lokasi Kode", f"[white]{framework_info.get('code_path', '-')}[/white]")
        table.add_row("Keterangan", f"[dim]{framework_info.get('description', '-')}[/dim]")

    console.print()
    console.print(table)
    console.print()


def show_app_info(info: dict) -> None:
    """Menampilkan tabel informasi teknis dan audit aplikasi."""
    app_name = info.get("app_name", info.get("package_name", "-"))
    table = Table(title=f"[bold cyan]Informasi & Audit Aplikasi: {app_name}[/bold cyan]", border_style="cyan", show_header=False)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")

    table.add_row("Nama Aplikasi", f"[bold green]{app_name}[/bold green]")
    table.add_row("Package ID", info.get("package_name", "-"))
    table.add_row("Versi Aplikasi", f"{info.get('version_name', '-')} (VersionCode: {info.get('version_code', '-')})")
    table.add_row("Target / Min SDK", f"Target: {info.get('target_sdk', '-')} | Min: {info.get('min_sdk', '-')}")

    if info.get("installed_time") and info.get("installed_time") != "-":
        table.add_row("Waktu Install", str(info.get("installed_time")))
    if info.get("updated_time") and info.get("updated_time") != "-":
        table.add_row("Waktu Update", str(info.get("updated_time")))

    table.add_row("Format APK", info.get("apk_format", "-"))
    paths = info.get("apk_paths", [])
    if paths:
        table.add_row("Lokasi APK di HP", "\n".join(paths))

    if info.get("launcher_activity") and info.get("launcher_activity") != "-":
        table.add_row("Launcher Activity", info.get("launcher_activity"))

    if info.get("framework") and info.get("framework") != "-":
        table.add_row("Teknologi/Framework", f"[bold magenta]{info.get('framework')}[/bold magenta]")

    perms = info.get("permissions", [])
    if perms:
        perm_display = "\n".join(f"• {p}" for p in perms[:10])
        if len(perms) > 10:
            perm_display += f"\n... dan {len(perms) - 10} izin lainnya"
        table.add_row("Izin (Permissions)", perm_display)

    console.print()
    console.print(table)
    console.print()
