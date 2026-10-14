from typing import List, Optional, Tuple

from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from apk_extractor.app_names import AppInfo


def setup_universal_terminal() -> None:
    """Mengaktifkan UTF-8 dan Virtual Terminal Processing di Windows agar tampilan bersih di semua terminal."""
    import sys
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
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class ActionModal(ModalScreen[Optional[str]]):
    """Dialog popup untuk memilih aksi bagi aplikasi yang dipilih."""

    DEFAULT_CSS = """
    ActionModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #modal-box {
        width: 66;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }

    #modal-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    .modal-btn {
        width: 100%;
        margin-bottom: 1;
    }

    #btn-cancel {
        width: 100%;
        margin-top: 1;
    }

    Button:focus {
        text-style: bold;
        border: heavy white;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Batal", show=True),
        Binding("up", "focus_previous", "Atas", show=False),
        Binding("down", "focus_next", "Bawah", show=False),
        Binding("1", "select_apk_only", "1", show=False),
        Binding("2", "select_extract_only", "2", show=False),
        Binding("3", "select_both", "3", show=False),
    ]

    def __init__(self, app_info: AppInfo):
        super().__init__()
        self.app_info = app_info

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label(f"Pilih Tindakan untuk {self.app_info.app_name}", id="modal-title")
            yield Label(f"Package: {self.app_info.package_name}", id="modal-subtitle")
            yield Button("[1] Ambil File APK Saja (ke output/apks/)", id="btn-apk", variant="primary", classes="modal-btn")
            yield Button("[2] Ambil & Ekstrak Isi APK (ke output/extracted/)", id="btn-extract", variant="success", classes="modal-btn")
            yield Button("[3] Keduanya (Simpan APK + Ekstrak Isi)", id="btn-both", variant="warning", classes="modal-btn")
            yield Button("Batal / Kembali (Esc)", id="btn-cancel", variant="error")

    def on_mount(self) -> None:
        # Fokus otomatis tombol pertama saat modal terbuka
        self.query_one("#btn-apk", Button).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "down":
            self.focus_next()
            event.stop()
        elif event.key == "up":
            self.focus_previous()
            event.stop()
        elif event.key == "enter":
            focused = self.focused
            if isinstance(focused, Button):
                focused.press()
                event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apk":
            self.dismiss("apk_only")
        elif event.button.id == "btn-extract":
            self.dismiss("extract_only")
        elif event.button.id == "btn-both":
            self.dismiss("both")
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def action_focus_next(self) -> None:
        self.focus_next()

    def action_focus_previous(self) -> None:
        self.focus_previous()

    def action_select_apk_only(self) -> None:
        self.dismiss("apk_only")

    def action_select_extract_only(self) -> None:
        self.dismiss("extract_only")

    def action_select_both(self) -> None:
        self.dismiss("both")


class DetailPanel(Static):
    """Panel preview di sisi kanan yang menampilkan info aplikasi yang dipilih."""

    def update_detail(self, app_info: Optional[AppInfo], total_filtered: int, total_all: int) -> None:
        content = Text()
        if not app_info:
            content.append("Tidak ada aplikasi yang dipilih.\n\n", style="bold yellow")
            content.append("Gunakan kolom pencarian di atas atau tombol panah untuk memilih aplikasi.", style="dim")
        else:
            content.append("Nama Aplikasi:\n", style="bold cyan")
            content.append(f"{app_info.app_name}\n\n", style="bold green")

            content.append("Package ID:\n", style="bold cyan")
            content.append(f"{app_info.package_name}\n\n", style="bold white")

            content.append("Status Filter:\n", style="bold cyan")
            content.append("Menampilkan ")
            content.append(str(total_filtered), style="bold green")
            content.append(" dari ")
            content.append(str(total_all), style="bold white")
            content.append(" aplikasi\n\n")

            content.append("Petunjuk Penggunaan:\n", style="bold yellow")
            content.append(" • [Enter]   : Pilih tindakan aplikasi ini\n", style="bold green")
            content.append(" • [↑ / ↓]   : Pilih baris aplikasi\n", style="bold white")
            content.append(" • [/]       : Fokus ke kotak pencarian\n", style="bold white")
            content.append(" • [Esc]     : Batal & Keluar\n", style="bold red")

        self.update(Panel(content, title="[bold cyan]Detail Aplikasi[/bold cyan]", border_style="cyan"))


class APKSelectorApp(App[Optional[Tuple[AppInfo, str]]]):
    """Aplikasi Textual TUI interaktif untuk memilih aplikasi Android dan tindakan eksekusi."""

    CSS = """
    Screen {
        background: $surface-darken-1;
        overflow: hidden;
    }

    #search-container {
        height: 3;
        margin: 0 1 0 1;
    }

    #search-box {
        border: round $accent;
        background: $surface;
    }

    #search-box:focus {
        border: round $success;
    }

    #main-container {
        height: 1fr;
        margin: 0 1 0 1;
    }

    #table-container {
        width: 68%;
        height: 100%;
    }

    #app-table {
        height: 100%;
        border: round $primary;
        background: $surface;
    }

    #detail-container {
        width: 32%;
        height: 100%;
        margin-left: 1;
    }

    #detail-panel {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Keluar", show=True),
        Binding("slash", "focus_search", "Cari", show=True),
        Binding("enter", "select_app", "Pilih", show=True),
    ]

    def __init__(self, apps: List[AppInfo], device_id: Optional[str] = None, default_action: Optional[str] = None):
        super().__init__()
        self.all_apps = apps
        self.filtered_apps = apps.copy()
        self.device_id = device_id or "Perangkat Terhubung"
        self.selected_app: Optional[AppInfo] = apps[0] if apps else None
        self.default_action = default_action

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, icon="")
        with Container(id="search-container"):
            yield Input(
                placeholder="Cari nama aplikasi atau package ID (tekan / untuk fokus)...",
                id="search-box",
            )
        with Horizontal(id="main-container"):
            with Container(id="table-container"):
                yield DataTable(id="app-table", cursor_type="row")
            with Container(id="detail-container"):
                yield DetailPanel(id="detail-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "apkx - Android APK Extractor"
        self.sub_title = f"Device: {self.device_id} ({len(self.all_apps)} Apps)"

        table = self.query_one("#app-table", DataTable)
        table.add_column("No", width=5)
        table.add_column("Nama Aplikasi", width=24)
        table.add_column("Package ID")

        self._populate_table(self.all_apps)
        self.query_one("#search-box", Input).focus()

    def _populate_table(self, apps: List[AppInfo]) -> None:
        table = self.query_one("#app-table", DataTable)
        table.clear()
        self.filtered_apps = apps

        for idx, app_info in enumerate(apps, start=1):
            table.add_row(str(idx), app_info.app_name, app_info.package_name, key=app_info.package_name)

        detail = self.query_one("#detail-panel", DetailPanel)
        if apps:
            self.selected_app = apps[0]
            table.move_cursor(row=0)
            detail.update_detail(self.selected_app, len(apps), len(self.all_apps))
        else:
            self.selected_app = None
            detail.update_detail(None, 0, len(self.all_apps))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        if not query:
            self._populate_table(self.all_apps)
        else:
            matched = [
                app for app in self.all_apps
                if query in app.app_name.lower() or query in app.package_name.lower()
            ]
            self._populate_table(matched)

    def _open_action_modal(self, app_info: AppInfo) -> None:
        if self.default_action:
            self.exit((app_info, self.default_action))
            return

        def on_action_chosen(action: Optional[str]) -> None:
            if action:
                self.exit((app_info, action))

        self.push_screen(ActionModal(app_info), on_action_chosen)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.selected_app:
            self._open_action_modal(self.selected_app)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            pkg_key = str(event.row_key.value)
            for app_info in self.filtered_apps:
                if app_info.package_name == pkg_key:
                    self.selected_app = app_info
                    break
            detail = self.query_one("#detail-panel", DetailPanel)
            detail.update_detail(self.selected_app, len(self.filtered_apps), len(self.all_apps))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self.selected_app:
            self._open_action_modal(self.selected_app)

    def on_key(self, event: events.Key) -> None:
        if event.key == "down" and self.query_one("#search-box", Input).has_focus:
            self.query_one("#app-table", DataTable).focus()
            event.stop()
        elif event.key == "up" and self.query_one("#app-table", DataTable).has_focus:
            table = self.query_one("#app-table", DataTable)
            if table.cursor_row == 0:
                self.query_one("#search-box", Input).focus()
                event.stop()

    def action_cancel(self) -> None:
        self.exit(None)

    def action_focus_search(self) -> None:
        self.query_one("#search-box", Input).focus()

    def action_select_app(self) -> None:
        if self.selected_app:
            self._open_action_modal(self.selected_app)


def run_tui_selector(
    apps: List[AppInfo],
    device_id: Optional[str] = None,
    default_action: Optional[str] = None,
) -> Optional[Tuple[AppInfo, str]]:
    """Menjalankan antarmuka TUI untuk memilih aplikasi dan aksi."""
    setup_universal_terminal()
    import os
    os.system("cls" if os.name == "nt" else "clear")
    app = APKSelectorApp(apps=apps, device_id=device_id, default_action=default_action)
    return app.run()
