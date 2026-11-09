import unittest
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Button

from apk_extractor.app_names import AppInfo
from apk_extractor.tui import (
    ActionModal,
    APKSelectorApp,
    DetailPanel,
    run_tui_selector,
    setup_universal_terminal,
)


class TestTUIUnits(unittest.TestCase):
    def test_setup_universal_terminal(self):
        # Should execute safely on any platform
        setup_universal_terminal()

    def test_detail_panel(self):
        panel = DetailPanel()
        app = AppInfo(app_name="Example", package_name="com.example")
        panel.update_detail(None, 0, 5)
        panel.update_detail(app, 1, 5)

    def test_action_modal_actions(self):
        app = AppInfo(app_name="Example", package_name="com.example")
        modal = ActionModal(app)

        with patch.object(modal, "dismiss") as mock_dismiss:
            modal.action_dismiss_modal()
            mock_dismiss.assert_called_with(None)

            modal.action_select_apk_only()
            mock_dismiss.assert_called_with("apk_only")

            modal.action_select_extract_only()
            mock_dismiss.assert_called_with("extract_only")

            modal.action_select_both()
            mock_dismiss.assert_called_with("both")

        with patch.object(modal, "focus_next") as mock_next, patch.object(modal, "focus_previous") as mock_prev:
            modal.action_focus_next()
            mock_next.assert_called_once()
            modal.action_focus_previous()
            mock_prev.assert_called_once()

    def test_action_modal_button_pressed(self):
        app = AppInfo(app_name="Example", package_name="com.example")
        modal = ActionModal(app)

        buttons = {
            "btn-apk": "apk_only",
            "btn-extract": "extract_only",
            "btn-both": "both",
            "btn-cancel": None,
        }

        for btn_id, expected_arg in buttons.items():
            btn = MagicMock(spec=Button)
            btn.id = btn_id
            event = MagicMock(spec=Button.Pressed)
            event.button = btn

            with patch.object(modal, "dismiss") as mock_dismiss:
                modal.on_button_pressed(event)
                mock_dismiss.assert_called_with(expected_arg)

    def test_action_modal_keys(self):
        app = AppInfo(app_name="Example", package_name="com.example")
        modal = ActionModal(app)

        with patch.object(modal, "focus_next") as mock_next, patch.object(modal, "focus_previous") as mock_prev:
            ev_down = MagicMock()
            ev_down.key = "down"
            modal.on_key(ev_down)
            mock_next.assert_called_once()
            ev_down.stop.assert_called_once()

            ev_up = MagicMock()
            ev_up.key = "up"
            modal.on_key(ev_up)
            mock_prev.assert_called_once()
            ev_up.stop.assert_called_once()

            btn = MagicMock(spec=Button)
            with patch.object(type(modal), "focused", new_callable=unittest.mock.PropertyMock) as mock_focused:
                mock_focused.return_value = btn
                ev_enter = MagicMock()
                ev_enter.key = "enter"
                modal.on_key(ev_enter)
                btn.press.assert_called_once()
                ev_enter.stop.assert_called_once()

    @patch("os.system")
    @patch.object(APKSelectorApp, "run")
    def test_run_tui_selector(self, mock_run, mock_system):
        app = AppInfo(app_name="Example", package_name="com.example")
        mock_run.return_value = (app, "apk_only")

        res = run_tui_selector([app], device_id="test-dev", default_action="apk_only")
        self.assertEqual(res, (app, "apk_only"))
        mock_system.assert_called_once()


@pytest.mark.asyncio
async def test_apk_selector_app_empty():
    app = APKSelectorApp(apps=[])
    async with app.run_test() as pilot:
        assert app.selected_app is None
        await pilot.press("escape")
    assert app.return_value is None


@pytest.mark.asyncio
async def test_apk_selector_app_modal_flow():
    apps = [AppInfo(app_name="Alpha", package_name="com.alpha")]
    app = APKSelectorApp(apps=apps)
    async with app.run_test() as pilot:
        # Move down to table then press enter
        await pilot.press("down")
        await pilot.press("enter")
        # ActionModal should be open, press 1 for apk_only
        await pilot.press("1")
    assert app.return_value == (apps[0], "apk_only")
    apps = [
        AppInfo(app_name="Alpha", package_name="com.alpha"),
        AppInfo(app_name="Beta", package_name="com.beta"),
    ]
    app = APKSelectorApp(apps=apps, device_id="emu", default_action="apk_only")
    async with app.run_test() as pilot:
        await pilot.press("enter")
    assert app.return_value == (apps[0], "apk_only")


@pytest.mark.asyncio
async def test_apk_selector_app_search_and_cancel():
    apps = [
        AppInfo(app_name="Alpha", package_name="com.alpha"),
        AppInfo(app_name="Beta", package_name="com.beta"),
    ]
    app = APKSelectorApp(apps=apps)
    async with app.run_test() as pilot:
        # Search query by setting input value
        search_box = app.query_one("#search-box")
        search_box.value = "beta"
        await pilot.pause()
        assert len(app.filtered_apps) == 1
        assert app.filtered_apps[0].package_name == "com.beta"

        # Clear search
        search_box.value = ""
        await pilot.pause()
        assert len(app.filtered_apps) == 2

        # Cancel
        await pilot.press("escape")
    assert app.return_value is None
