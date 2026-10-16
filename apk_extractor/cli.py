import sys
from contextlib import nullcontext
from pathlib import Path
from typing import List, Optional, Tuple

# Pastikan output stream dan console di Windows menggunakan UTF-8
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
        h_out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
    except Exception:
        pass
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import questionary
import typer
from rich.panel import Panel
from rich.status import Status

from apk_extractor import __version__
from apk_extractor.adb import ADBError, ADBManager
from apk_extractor.app_names import AppInfo, resolve_apps
from apk_extractor.packager import APKPackager, sanitize_filename
from apk_extractor.tui import run_tui_selector
from apk_extractor.ui import (
    console,
    console_err,
    print_banner,
    select_device,
    select_devices,
    select_package_interactive,
    show_app_info,
    show_devices_table,
    show_error,
    show_no_device_help,
    show_package_table,
    show_success_summary,
    show_unauthorized_device_help,
    show_warning,
)


def version_callback(value: bool):
    if value:
        if "--json" in sys.argv:
            print(json.dumps({"version": __version__}))
        else:
            console.print(f"[bold cyan]apkx[/bold cyan] versi [bold green]{__version__}[/bold green]")
        raise typer.Exit()


class APKXTyper(typer.Typer):
    """Custom Typer subclass providing clear, user-friendly error messages."""

    def __call__(self, *args, **kwargs):
        try:
            return super().__call__(*args, standalone_mode=False, **kwargs)
        except Exception as e:
            if type(e).__name__ == "BadOptionUsage":
                opt = getattr(e, "option_name", "opsi")
                msg = f"[bold red]Kesalahan Argumen:[/] Opsi [cyan]{opt}[/] membutuhkan nilai argumen.\n\n"
                if opt in ["-d", "--device"]:
                    msg += (
                        "[bold white]Penjelasan:[/]\n"
                        "  Anda harus memasukkan Serial ID perangkat setelah opsi [cyan]-d[/].\n\n"
                        "[bold white]Contoh Penggunaan:[/]\n"
                        "  [green]apkx -d EU99MJMVKREIWCDY[/]\n\n"
                        "[bold yellow]Tips:[/] Jalankan [bold green]apkx devices[/] untuk melihat daftar Serial ID perangkat yang terhubung."
                    )
                elif opt in ["-o", "--output"]:
                    msg += (
                        "[bold white]Penjelasan:[/]\n"
                        "  Anda harus memasukkan path folder tujuan setelah opsi [cyan]-o[/].\n\n"
                        "[bold white]Contoh Penggunaan:[/]\n"
                        "  [green]apkx -o ./output[/] atau [green]apkx -o D:\\HasilEkstrak[/]"
                    )
                else:
                    msg += f"Silakan jalankan [bold green]apkx --help[/] untuk melihat format penggunaan opsi [cyan]{opt}[/]."

                console.print(Panel(msg, title="[bold red]Argumen Tidak Lengkap[/]", border_style="red"))
                raise SystemExit(2)
            elif type(e).__name__ == "NoSuchOption":
                opt = getattr(e, "option_name", "opsi")
                console.print(Panel(
                    f"Opsi [cyan]{opt}[/] tidak dikenal.\n\n"
                    "Silakan jalankan [bold green]apkx --help[/] untuk melihat daftar opsi yang valid.",
                    title="[bold red]Opsi Tidak Dikenal[/]",
                    border_style="red",
                ))
                raise SystemExit(2)
            elif type(e).__name__ in ["Exit", "Abort"]:
                raise SystemExit(getattr(e, "exit_code", 0))
            elif any("ClickException" in base.__name__ for base in type(e).__mro__):
                console.print(Panel(str(e), title="[bold red]Kesalahan Perintah[/]", border_style="red"))
                raise SystemExit(getattr(e, "exit_code", 1))
            raise e


app = APKXTyper(
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
    system_only: bool = typer.Option(
        False,
        "--system",
        "-s",
        help="Hanya sertakan aplikasi bawaan sistem (system apps)",
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
    apk_only: bool = typer.Option(
        False,
        "--apk-only",
        "-k",
        help="Hanya simpan installer APK (.apk/.apks) tanpa mengekstrak isinya",
    ),
    extract_only: bool = typer.Option(
        False,
        "--extract-only",
        "-x",
        help="Hanya ekstrak isi APK (dex, res, assets) tanpa menyimpan file installer APK",
    ),
    both: bool = typer.Option(
        False,
        "--both",
        "-b",
        help="Simpan installer APK sekaligus ekstrak isinya (default)",
    ),
    info_only: bool = typer.Option(
        False,
        "--info",
        "--analyze",
        help="Tampilkan audit dan informasi teknis aplikasi tanpa ekstraksi",
    ),
    recent: bool = typer.Option(
        False,
        "--recent",
        "-r",
        help="Urutkan aplikasi berdasarkan waktu instalasi atau pembaruan terbaru",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Keluarkan output dalam format JSON (machine-readable)",
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Tampilkan versi apkx dan keluar",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """
    Ekstrak file APK dari HP Android ke komputer dengan cepat dan rapi.
    """
    # Validasi opsi yang berkonflik
    if all_apps and system_only:
        show_error("Opsi --all (-a) dan --system (-s) tidak dapat digunakan bersamaan.")
        raise typer.Exit(code=2)

    actions_specified = [k for k, v in [("apk_only", apk_only), ("extract_only", extract_only), ("both", both)] if v]
    if len(actions_specified) > 1:
        show_error("Hanya boleh memilih satu di antara --apk-only (-k), --extract-only (-x), atau --both (-b).")
        raise typer.Exit(code=2)

    default_action: Optional[str] = None
    if apk_only:
        default_action = "apk_only"
    elif extract_only:
        default_action = "extract_only"
    elif both:
        default_action = "both"

    adb = ADBManager()
    packager = APKPackager(adb)

    # 1. Periksa ketersediaan ADB binary (auto-download jika belum ada)
    if not adb.is_installed():
        if not as_json:
            print_banner()
            with Status("[bold cyan]ADB tidak ditemukan di sistem. Mengunduh Android Platform-Tools resmi dari Google...", console=console):
                installed = adb.ensure_installed()
        else:
            installed = adb.ensure_installed()

        if not installed:
            if as_json:
                print(json.dumps({"status": "error", "message": "Gagal mengunduh atau menginisialisasi ADB otomatis."}))
            else:
                show_error(
                    "Gagal mengunduh atau menginisialisasi ADB otomatis.\n"
                    "Pastikan koneksi internet aktif atau pasang Android SDK Platform-Tools secara manual."
                )
            raise typer.Exit(code=1)
        if not as_json:
            console.print("[green][V] Android Platform-Tools resmi dari Google berhasil dipasang![/green]\n")

    # 1.5 Cek perintah melihat perangkat (apkx devices / apkx --devices)
    if query == "devices" or show_devices:
        if not as_json:
            print_banner()
        try:
            device_list = adb.get_devices_with_details()
        except ADBError as e:
            if as_json:
                print(json.dumps({"status": "error", "message": str(e)}))
            else:
                show_error(str(e))
            raise typer.Exit(code=1)

        if as_json:
            print(json.dumps(device_list, indent=2, ensure_ascii=False))
            raise typer.Exit(code=0)

        if not device_list:
            show_no_device_help()
            raise typer.Exit(code=0)

        show_devices_table(device_list)
        raise typer.Exit(code=0)

    # 2. Periksa perangkat terhubung
    try:
        devices = adb.get_connected_devices()
    except ADBError as e:
        if as_json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print_banner()
            show_error(str(e))
        raise typer.Exit(code=1)

    if not devices:
        if as_json:
            print(json.dumps({"status": "error", "message": "Tidak ada perangkat Android yang terdeteksi via USB debugging."}))
        else:
            print_banner()
            show_no_device_help()
        raise typer.Exit(code=1)

    authorized = [d for d in devices if d[1] == "device"]
    unauthorized = [d for d in devices if d[1] == "unauthorized"]

    if not authorized:
        if as_json:
            print(json.dumps({"status": "error", "message": "Perangkat Android belum diotorisasi (cek dialog USB debugging di HP)."}))
        else:
            print_banner()
            if unauthorized:
                show_unauthorized_device_help(unauthorized[0][0])
            else:
                show_no_device_help()
        raise typer.Exit(code=1)

    # Tentukan perangkat yang akan diproses
    if device_id:
        target_devices = [{"serial": device_id, "brand": "-", "model": "-", "android_version": "-", "status": "device"}]
    elif len(authorized) == 1:
        target_devices = [adb.get_device_details(authorized[0][0], "device")]
    else:
        if as_json:
            target_devices = [adb.get_device_details(authorized[0][0], "device")]
        else:
            print_banner()
            all_details = adb.get_devices_with_details()
            selected_devs = select_devices(all_details)
            if not selected_devs:
                console.print("[dim]Pemilihan perangkat dibatalkan.[/dim]")
                raise typer.Exit(code=0)
            target_devices = selected_devs

    is_multi = len(target_devices) > 1
    for dev_idx, dev_info in enumerate(target_devices, start=1):
        target_device = dev_info["serial"]
        brand = dev_info.get("brand", "")
        model = dev_info.get("model", "")
        if brand != "-" and model != "-":
            device_label = f"{brand} {model}"
        elif model != "-":
            device_label = model
        else:
            device_label = target_device

        if is_multi:
            if not as_json:
                console.print(Panel(
                    f"[bold cyan]Memproses Perangkat {dev_idx}/{len(target_devices)}:[/] [bold green]{device_label}[/] [dim]({target_device})[/dim]",
                    border_style="cyan",
                ))
            cur_output_dir = output_dir / sanitize_filename(device_label)
        else:
            cur_output_dir = output_dir

        process_single_device(
            adb=adb,
            packager=packager,
            target_device=target_device,
            device_label=device_label,
            query=query,
            all_apps=all_apps,
            system_only=system_only,
            list_only=list_only,
            info_only=info_only,
            recent=recent,
            as_json=as_json,
            default_action=default_action,
            output_dir=cur_output_dir,
            is_multi=is_multi,
        )

        if is_multi and dev_idx < len(target_devices) and not as_json:
            console.print(f"\n[dim]Selesai memproses {device_label}. Lanjut ke perangkat berikutnya...[/dim]\n")


def process_single_device(
    adb: ADBManager,
    packager: APKPackager,
    target_device: str,
    device_label: str,
    query: Optional[str],
    all_apps: bool,
    system_only: bool,
    list_only: bool,
    info_only: bool,
    recent: bool,
    as_json: bool,
    default_action: Optional[str],
    output_dir: Path,
    is_multi: bool,
) -> None:
    """Processes package listing, selection, and extraction for a specific device."""
    # Gunakan console_err saat --json aktif agar spinner/progress tampil di stderr
    # sementara stdout tetap berisi JSON murni tanpa polusi tampilan.
    active_console = console_err if as_json else console

    # 3. Ambil daftar package dan nama aplikasi dari perangkat
    status_ctx = active_console.status(f"[bold cyan]Mengambil daftar aplikasi dari {device_label}...[/bold cyan]")
    with status_ctx:
        try:
            packages = adb.list_packages(
                device_id=target_device,
                third_party_only=(not all_apps) and (not system_only),
                system_only=system_only,
            )
            apps = resolve_apps(adb, packages, device_id=target_device)
        except ADBError as e:
            if as_json:
                print(json.dumps({"status": "error", "message": str(e)}))
                raise typer.Exit(code=1)
            else:
                if not is_multi:
                    print_banner()
                show_error(str(e))
            return

    # Urutkan berdasarkan waktu instalasi/update jika opsi --recent aktif
    if recent:
        recent_order = adb.get_package_recent_order(device_id=target_device)
        if recent_order:
            order_map = {pkg: idx for idx, pkg in enumerate(recent_order)}
            apps.sort(key=lambda a: order_map.get(a.package_name, 999999))

    if not apps:
        if as_json:
            print(json.dumps({"status": "error", "message": f"Tidak ada aplikasi ditemukan di {device_label}.", "apps": []}))
            raise typer.Exit(code=1)
        if not is_multi:
            print_banner()
        app_type = "sistem" if system_only else ("semua" if all_apps else "pihak ketiga")
        show_warning(f"Tidak ada aplikasi {app_type} yang ditemukan di perangkat {device_label}.")
        return

    # Jika hanya ingin menampilkan daftar (mode --list)
    if list_only:
        if as_json:
            app_data = [{"app_name": a.app_name, "package_name": a.package_name} for a in apps]
            print(json.dumps(app_data, indent=2, ensure_ascii=False))
            return
        if not is_multi:
            print_banner()
        show_package_table(
            apps,
            title=f"Daftar Aplikasi ({len(apps)} terpasang, Device: {device_label})",
        )
        return

    # 4. Tentukan aplikasi dan tindakan yang dipilih
    selected_app: Optional[AppInfo] = None
    selected_action: Optional[str] = default_action
    effective_default_action: Optional[str] = "info" if info_only else default_action

    if query:
        if not is_multi and not as_json:
            print_banner()
        query_clean = query.strip().lower()
        exact_matches = [
            a for a in apps
            if a.package_name.lower() == query_clean or a.app_name.lower() == query_clean
        ]

        if exact_matches:
            selected_app = exact_matches[0]
            if not as_json:
                console.print(f"[bold green][V] Ditemukan exact match:[/bold green] [bold green]{selected_app.app_name}[/bold green] [white]({selected_app.package_name})[/white]")
        else:
            partial_matches = [
                a for a in apps
                if query_clean in a.package_name.lower() or query_clean in a.app_name.lower()
            ]
            if len(partial_matches) == 1:
                selected_app = partial_matches[0]
                if not as_json:
                    console.print(f"[bold green][V] Ditemukan 1 aplikasi yang cocok:[/bold green] [bold green]{selected_app.app_name}[/bold green] [white]({selected_app.package_name})[/white]")
            elif len(partial_matches) > 1:
                if as_json:
                    # Ambil kecocokan pertama di mode non-interaktif JSON
                    selected_app = partial_matches[0]
                else:
                    try:
                        tui_res = run_tui_selector(partial_matches, device_id=target_device, default_action=effective_default_action)
                        if tui_res:
                            selected_app, act = tui_res
                            if act != "info":
                                selected_action = act
                    except Exception:
                        pkg = select_package_interactive(partial_matches, prefilter_query=query)
                        if pkg:
                            selected_app = next((a for a in apps if a.package_name == pkg), None)
            else:
                if as_json:
                    print(json.dumps({"status": "error", "message": f"Tidak ada aplikasi yang cocok dengan kata kunci '{query}' di {device_label}."}))
                    raise typer.Exit(code=1)
                show_warning(f"Tidak ada aplikasi yang cocok dengan kata kunci '{query}' di {device_label}.")
                confirm = questionary.confirm(f"Apakah Anda ingin mencari dari seluruh daftar aplikasi di {device_label}?").ask()
                if confirm:
                    try:
                        tui_res = run_tui_selector(apps, device_id=target_device, default_action=effective_default_action)
                        if tui_res:
                            selected_app, act = tui_res
                            if act != "info":
                                selected_action = act
                    except Exception:
                        pkg = select_package_interactive(apps)
                        if pkg:
                            selected_app = next((a for a in apps if a.package_name == pkg), None)
                else:
                    return

    else:
        # Mode tanpa query
        if as_json:
            # Jika user menjalankan `apkx --json` tanpa query, otomatis tampilkan daftar aplikasi dalam format JSON
            app_data = [{"app_name": a.app_name, "package_name": a.package_name} for a in apps]
            print(json.dumps(app_data, indent=2, ensure_ascii=False))
            return
        try:
            tui_res = run_tui_selector(apps, device_id=target_device, default_action=effective_default_action)
            if tui_res:
                selected_app, act = tui_res
                if act != "info":
                    selected_action = act
        except Exception:
            pkg = select_package_interactive(apps)
            if pkg:
                selected_app = next((a for a in apps if a.package_name == pkg), None)

    if not selected_app:
        if not as_json:
            if is_multi:
                console.print(f"[dim]Pemilihan aplikasi untuk {device_label} dilewati.[/dim]\n")
            else:
                console.print("[dim]Operasi dibatalkan.[/dim]")
        return

    # Jika hanya meminta informasi teknis (--info / --analyze)
    if info_only:
        with active_console.status(f"[bold cyan]Mengambil informasi teknis untuk {selected_app.app_name}...[/bold cyan]"):
            quick_info = adb.get_package_quick_info(selected_app.package_name, device_id=target_device)
            quick_info["app_name"] = selected_app.app_name

        if as_json:
            print(json.dumps(quick_info, indent=2, ensure_ascii=False))
        else:
            if not is_multi:
                print_banner()
            show_app_info(quick_info)
        return

    # Jika terpilih lewat query atau selector tanpa action eksplisit, tanyakan tindakan jika belum ada default
    if not selected_action:
        if as_json:
            selected_action = "both"
        else:
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
                return
            selected_action = action_choice

    # Siapkan direktori output terpisah yang rapi
    apks_dir = output_dir / "apks"
    extracted_dir = output_dir / "extracted"
    apks_dir.mkdir(parents=True, exist_ok=True)
    if selected_action in ("extract_only", "both"):
        extracted_dir.mkdir(parents=True, exist_ok=True)

    # 5. Dapatkan lokasi path APK di HP
    try:
        with active_console.status(f"[bold cyan][1/4] Mencari lokasi APK untuk {selected_app.app_name}...[/bold cyan]"):
            apk_paths = adb.get_package_apk_paths(selected_app.package_name, device_id=target_device)
    except ADBError as e:
        if as_json:
            print(json.dumps({"status": "error", "message": str(e)}))
            raise typer.Exit(code=1)
        else:
            show_error(str(e))
        return

    if not apk_paths:
        err_msg = f"Tidak dapat menemukan path APK untuk '{selected_app.app_name}' ({selected_app.package_name})."
        if as_json:
            print(json.dumps({"status": "error", "message": err_msg}))
            raise typer.Exit(code=1)
        else:
            show_error(err_msg)
        return

    if not as_json:
        part_desc = f"{len(apk_paths)} file split APK" if len(apk_paths) > 1 else "1 file APK"
        console.print(f"[bold green][V][/bold green] Lokasi APK terdeteksi [dim]({part_desc})[/dim]")

    # 6. Tarik file APK dari HP
    try:
        with active_console.status(f"[bold cyan][2/4] Menarik APK untuk {selected_app.app_name}...[/bold cyan]") as pull_status:
            def update_pull_progress(msg: str, current: int, total: int):
                if hasattr(pull_status, "update"):
                    pull_status.update(f"[bold cyan][2/4] {msg}[/bold cyan]")

            extract_res = packager.extract(
                package_name=selected_app.package_name,
                remote_paths=apk_paths,
                output_dir=apks_dir,
                app_name=selected_app.app_name,
                device_id=target_device,
                progress_callback=update_pull_progress,
            )

        if not as_json:
            console.print(f"[bold green][V][/bold green] File APK berhasil ditarik [dim]({extract_res.formatted_size})[/dim]")

        # Gunakan nama resmi hasil ekstraksi (jika terdeteksi lebih akurat dari APK)
        selected_app.app_name = extract_res.app_name
        app_folder_name = sanitize_filename(extract_res.app_name)
        app_extracted_folder: Optional[Path] = None
        fw_info: Optional[dict] = None

        # 7. Bongkar isi APK jika dipilih
        if selected_action in ("extract_only", "both"):
            app_extracted_folder = extracted_dir / app_folder_name
            with active_console.status(f"[bold cyan][3/4] Mengekstrak isi APK ke {app_folder_name}...[/bold cyan]") as unpack_status:
                def update_unpack_progress(msg: str, current: int, total: int):
                    if hasattr(unpack_status, "update"):
                        unpack_status.update(f"[bold cyan][3/4] {msg}[/bold cyan]")

                packager.unpack(
                    extract_res.output_path,
                    app_extracted_folder,
                    progress_callback=update_unpack_progress,
                )

            if not as_json:
                console.print(f"[bold green][V][/bold green] Berhasil membongkar berkas APK ke [cyan]{app_extracted_folder.name}[/cyan]")

        # 8. Menganalisis teknologi & struktur aplikasi
        if app_extracted_folder and app_extracted_folder.exists():
            with active_console.status("[bold cyan][4/4] Menganalisis arsitektur & teknologi aplikasi...[/bold cyan]"):
                fw_info = packager.generate_analysis_summary(
                    app_extracted_folder, selected_app.app_name, selected_app.package_name
                )
            if not as_json and fw_info:
                fw_name = fw_info.get("framework", "Native Android")
                console.print(f"[bold green][V][/bold green] Arsitektur terdeteksi: [bold magenta]{fw_name}[/bold magenta]")

        # Jika aksi adalah extract_only, hapus file installer APK dari apks_dir agar bersih
        final_apk_path: Optional[Path] = extract_res.output_path
        if selected_action == "extract_only":
            try:
                extract_res.output_path.unlink()
                final_apk_path = None
            except Exception:
                pass

        # 9. Tampilkan hasil ringkasan
        if as_json:
            res_json = {
                "status": "success",
                "package_name": selected_app.package_name,
                "app_name": selected_app.app_name,
                "action": selected_action,
                "is_split": extract_res.is_split,
                "total_parts": extract_res.total_parts,
                "output_apk": str(final_apk_path) if final_apk_path else None,
                "extracted_folder": str(app_extracted_folder) if app_extracted_folder else None,
                "framework_info": fw_info,
            }
            print(json.dumps(res_json, indent=2, ensure_ascii=False))
        else:
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
        if as_json:
            print(json.dumps({"status": "error", "message": f"Terjadi kesalahan saat memproses APK: {str(e)}"}))
            raise typer.Exit(code=1)
        else:
            show_error(f"Terjadi kesalahan saat memproses APK:\n{str(e)}")


def query_matches_handled(action: str) -> bool:
    """Helper untuk memeriksa apakah action sudah terisi dari modal TUI."""
    return action in ("apk_only", "extract_only", "both")


if __name__ == "__main__":
    app()
