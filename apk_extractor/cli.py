import sys
from pathlib import Path
from typing import Optional, Tuple

# Pastikan output stream di Windows menggunakan UTF-8
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import questionary
import typer
from rich.status import Status

from apk_extractor.adb import ADBError, ADBManager
from apk_extractor.app_names import AppInfo, resolve_apps
from apk_extractor.packager import APKPackager, sanitize_filename
from apk_extractor.tui import run_tui_selector
from apk_extractor.ui import (
    console,
    print_banner,
    select_device,
    select_package_interactive,
    show_devices_table,
    show_error,
    show_no_device_help,
    show_package_table,
    show_success_summary,
    show_unauthorized_device_help,
    show_warning,
)

app = typer.Typer(
    name="apkx",
    help="apkx: Android APK & Split-APK Extractor CLI",
    add_completion=False,
)


@app.command()
def main(
    query: Optional[str] = typer.Argument(
        None,
        help="Nama atau potongan nama package aplikasi (opsional, jika kosong akan membuka pencarian interaktif)",
    ),
    all_apps: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Sertakan semua aplikasi sistem (default: hanya aplikasi pihak ketiga)",
    ),
    output_dir: Path = typer.Option(
        Path("./output"),
        "--output",
        "-o",
        help="Direktori utama penyimpanan (default: ./output)",
    ),
    device_id: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Serial ID perangkat spesifik jika ada lebih dari satu HP terhubung",
    ),
    list_only: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="Hanya tampilkan daftar aplikasi tanpa melakukan ekstraksi",
    ),
    show_devices: bool = typer.Option(
        False,
        "--devices",
        help="Tampilkan daftar perangkat Android yang terhubung ke komputer",
    ),
) -> None:
    """
    Ekstrak file APK dari HP Android ke komputer dengan cepat dan rapi.
    """
    adb = ADBManager()
    packager = APKPackager(adb)

    # 1. Periksa ketersediaan ADB binary (auto-download jika belum ada)
    if not adb.is_installed():
        print_banner()
        with Status("[bold cyan]ADB tidak ditemukan di sistem. Mengunduh Android Platform-Tools resmi dari Google...", console=console):
            installed = adb.ensure_installed()

        if not installed:
            show_error(
                "Gagal mengunduh atau menginisialisasi ADB otomatis.\n"
                "Pastikan koneksi internet aktif atau pasang Android SDK Platform-Tools secara manual."
            )
            raise typer.Exit(code=1)
        console.print("[green][V] Android Platform-Tools resmi dari Google berhasil dipasang![/green]\n")

    # 1.5 Cek perintah melihat perangkat (apkx devices / apkx --devices)
    if query == "devices" or show_devices:
        print_banner()
        try:
            device_list = adb.get_devices_with_details()
        except ADBError as e:
            show_error(str(e))
            raise typer.Exit(code=1)

        if not device_list:
            show_no_device_help()
            raise typer.Exit(code=0)

        show_devices_table(device_list)
        raise typer.Exit(code=0)

    # 2. Periksa perangkat terhubung
    try:
        devices = adb.get_connected_devices()
    except ADBError as e:
        print_banner()
        show_error(str(e))
        raise typer.Exit(code=1)

    if not devices:
        print_banner()
        show_no_device_help()
        raise typer.Exit(code=1)

    authorized = [d for d in devices if d[1] == "device"]
    unauthorized = [d for d in devices if d[1] == "unauthorized"]

    if not authorized:
        print_banner()
        if unauthorized:
            show_unauthorized_device_help(unauthorized[0][0])
        else:
            show_no_device_help()
        raise typer.Exit(code=1)

    # Pilih device jika ada beberapa
    target_device = device_id
    if not target_device:
        if len(authorized) == 1:
            target_device = authorized[0][0]
        else:
            target_device = select_device(authorized)
            if not target_device:
                console.print("[dim]Pemilihan perangkat dibatalkan.[/dim]")
                raise typer.Exit(code=0)

    # 3. Ambil daftar package dan nama aplikasi dari perangkat
    with console.status("[bold cyan]Mengambil daftar aplikasi dari perangkat...[/bold cyan]"):
        try:
            packages = adb.list_packages(device_id=target_device, third_party_only=not all_apps)
            apps = resolve_apps(adb, packages, device_id=target_device)
        except ADBError as e:
            print_banner()
            show_error(str(e))
            raise typer.Exit(code=1)

    if not apps:
        print_banner()
        app_type = "pihak ketiga" if not all_apps else "sistem"
        show_warning(f"Tidak ada aplikasi {app_type} yang ditemukan di perangkat.")
        raise typer.Exit(code=0)

    # Jika hanya ingin menampilkan daftar (mode --list)
    if list_only:
        print_banner()
        show_package_table(
            apps,
            title=f"Daftar Aplikasi ({len(apps)} terpasang, Device: {target_device})",
        )
        raise typer.Exit(code=0)

    # 4. Tentukan aplikasi dan tindakan yang dipilih
    selected_app: Optional[AppInfo] = None
    selected_action: Optional[str] = None

    if query:
        print_banner()
        query_clean = query.strip().lower()
        exact_matches = [
            a for a in apps
            if a.package_name.lower() == query_clean or a.app_name.lower() == query_clean
        ]

        if exact_matches:
            selected_app = exact_matches[0]
            console.print(f"[bold green][V] Ditemukan exact match:[/bold green] [bold green]{selected_app.app_name}[/bold green] [white]({selected_app.package_name})[/white]")
        else:
            partial_matches = [
                a for a in apps
                if query_clean in a.package_name.lower() or query_clean in a.app_name.lower()
            ]
            if len(partial_matches) == 1:
                selected_app = partial_matches[0]
                console.print(f"[bold green][V] Ditemukan 1 aplikasi yang cocok:[/bold green] [bold green]{selected_app.app_name}[/bold green] [white]({selected_app.package_name})[/white]")
            elif len(partial_matches) > 1:
                try:
                    tui_res = run_tui_selector(partial_matches, device_id=target_device)
                    if tui_res:
                        selected_app, selected_action = tui_res
                except Exception:
                    pkg = select_package_interactive(partial_matches, prefilter_query=query)
                    if pkg:
                        selected_app = next((a for a in apps if a.package_name == pkg), None)
            else:
                show_warning(f"Tidak ada aplikasi yang cocok dengan kata kunci '{query}'.")
                confirm = questionary.confirm("Apakah Anda ingin mencari dari seluruh daftar aplikasi?").ask()
                if confirm:
                    try:
                        tui_res = run_tui_selector(apps, device_id=target_device)
                        if tui_res:
                            selected_app, selected_action = tui_res
                    except Exception:
                        pkg = select_package_interactive(apps)
                        if pkg:
                            selected_app = next((a for a in apps if a.package_name == pkg), None)
                else:
                    raise typer.Exit(code=0)

        # Jika terpilih lewat query tanpa TUI modal, tanyakan tindakan
        if selected_app and not selected_action:
            action_choice = questionary.select(
                f"Pilih tindakan untuk {selected_app.app_name}:",
                choices=[
                    questionary.Choice("📦 [1] Ambil File APK Saja (ke output/apks/)", value="apk_only"),
                    questionary.Choice("📂 [2] Ambil & Ekstrak Isi APK (ke output/extracted/)", value="extract_only"),
                    questionary.Choice("⚡ [3] Keduanya (Simpan APK + Ekstrak Isi)", value="both"),
                ],
            ).ask()
            if not action_choice:
                console.print("[dim]Operasi dibatalkan.[/dim]")
                raise typer.Exit(code=0)
            selected_action = action_choice
    else:
        # Mode interaktif default: TUI dengan Action Modal
        try:
            tui_res = run_tui_selector(apps, device_id=target_device)
            if tui_res:
                selected_app, selected_action = tui_res
        except Exception:
            pkg = select_package_interactive(apps)
            if pkg:
                selected_app = next((a for a in apps if a.package_name == pkg), None)

    if not selected_app:
        console.print("[dim]Operasi dibatalkan.[/dim]")
        raise typer.Exit(code=0)

    if not selected_action:
        selected_action = "both"

    # Siapkan direktori output terpisah yang rapi
    apks_dir = output_dir / "apks"
    extracted_dir = output_dir / "extracted"
    apks_dir.mkdir(parents=True, exist_ok=True)
    if selected_action in ("extract_only", "both"):
        extracted_dir.mkdir(parents=True, exist_ok=True)

    # 5. Dapatkan lokasi path APK di HP
    try:
        with console.status(f"[bold cyan]Mencari lokasi APK untuk {selected_app.app_name}...[/bold cyan]"):
            apk_paths = adb.get_package_apk_paths(selected_app.package_name, device_id=target_device)
    except ADBError as e:
        show_error(str(e))
        raise typer.Exit(code=1)

    if not apk_paths:
        show_error(f"Tidak dapat menemukan path APK untuk '{selected_app.app_name}' ({selected_app.package_name}).")
        raise typer.Exit(code=1)

    # 6. Tarik file APK dari HP
    try:
        with console.status(f"[bold cyan]Menarik APK untuk {selected_app.app_name}...[/bold cyan]") as status:
            def update_progress(msg: str, current: int, total: int):
                status.update(f"[bold cyan]{msg}[/bold cyan]")

            extract_res = packager.extract(
                package_name=selected_app.package_name,
                remote_paths=apk_paths,
                output_dir=apks_dir,
                app_name=selected_app.app_name,
                device_id=target_device,
                progress_callback=update_progress,
            )

        app_folder_name = sanitize_filename(selected_app.app_name)
        app_extracted_folder: Optional[Path] = None
        fw_info: Optional[dict] = None

        # 7. Bongkar isi APK jika dipilih
        if selected_action in ("extract_only", "both"):
            app_extracted_folder = extracted_dir / app_folder_name
            with console.status(f"[bold cyan]Mengekstrak isi APK ke {app_extracted_folder}...[/bold cyan]"):
                packager.unpack(extract_res.output_path, app_extracted_folder)
                fw_info = packager.generate_analysis_summary(
                    app_extracted_folder, selected_app.app_name, selected_app.package_name
                )

        # Jika aksi adalah extract_only, hapus file installer APK dari apks_dir agar bersih
        final_apk_path: Optional[Path] = extract_res.output_path
        if selected_action == "extract_only":
            try:
                extract_res.output_path.unlink()
                final_apk_path = None
            except Exception:
                pass

        # 8. Tampilkan hasil ringkasan
        show_success_summary(
            package_name=selected_app.package_name,
            app_name=selected_app.app_name,
            output_path=final_apk_path,
            is_split=extract_res.is_split,
            total_parts=extract_res.total_parts,
            size_str=extract_res.formatted_size if final_apk_path else None,
            extracted_folder=app_extracted_folder,
            framework_info=fw_info,
        )

    except (ADBError, ValueError, IOError) as e:
        show_error(f"Terjadi kesalahan saat memproses APK:\n{str(e)}")
        raise typer.Exit(code=1)


def query_matches_handled(action: str) -> bool:
    """Helper untuk memeriksa apakah action sudah terisi dari modal TUI."""
    return action in ("apk_only", "extract_only", "both")


if __name__ == "__main__":
    app()
