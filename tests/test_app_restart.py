import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui_island.app import window as window_module
from ui_island.app.window import IslandWindow


class _HotkeyController:
    def __init__(self) -> None:
        self.stop_count = 0

    def stop_listener(self) -> None:
        self.stop_count += 1


class _Thread:
    def __init__(self) -> None:
        self.join_timeouts: list[float] = []

    def join(self, timeout=None) -> None:
        self.join_timeouts.append(timeout)


class _OtherWidget:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _App:
    def __init__(self, widgets) -> None:
        self._widgets = widgets
        self.quit_count = 0

    def topLevelWidgets(self):
        return self._widgets

    def quit(self) -> None:
        self.quit_count += 1


class _RestartWindow:
    _restart_command = staticmethod(IslandWindow._restart_command)
    _shutdown_background_services = IslandWindow._shutdown_background_services
    _close_other_top_level_widgets = IslandWindow._close_other_top_level_widgets
    restart_app_from_settings = IslandWindow.restart_app_from_settings

    def __init__(self) -> None:
        self._running = True
        self.hotkey_controller = _HotkeyController()
        self._thread = _Thread()
        self.route_panel_controller = SimpleNamespace(save_route_section_expanded=lambda: None)
        self.route_mgr = SimpleNamespace(save_visibility=lambda: None, save_progress=lambda: None)
        self.window_mode_controller = SimpleNamespace(save_window_geometry=lambda: None)


class AppRestartTests(unittest.TestCase):
    def test_restart_command_for_frozen_app_skips_argv0(self) -> None:
        with (
            patch.object(window_module.sys, "frozen", True, create=True),
            patch.object(window_module.sys, "executable", r"C:\App\GMT-N.exe"),
            patch.object(window_module.sys, "argv", [r"C:\App\GMT-N.exe", "--no-selector"]),
        ):
            self.assertEqual(
                IslandWindow._restart_command(),
                [r"C:\App\GMT-N.exe", "--no-selector"],
            )

    def test_restart_command_for_source_run_keeps_script_argv(self) -> None:
        with (
            patch.object(window_module.sys, "frozen", False, create=True),
            patch.object(window_module.sys, "executable", r"C:\Python\python.exe"),
            patch.object(window_module.sys, "argv", ["main_island.py", "--force-selector"]),
        ):
            self.assertEqual(
                IslandWindow._restart_command(),
                [r"C:\Python\python.exe", "main_island.py", "--force-selector"],
            )

    def test_restart_from_settings_stops_services_starts_process_and_quits(self) -> None:
        window = _RestartWindow()
        other = _OtherWidget()
        app = _App([window, other])

        with (
            patch.object(window, "_restart_command", return_value=["GMT-N.exe", "--no-selector"]),
            patch("ui_island.app.window.config.BASE_DIR", r"C:\App"),
            patch("ui_island.app.window.subprocess.Popen") as popen,
            patch("ui_island.app.window.QApplication.instance", return_value=app),
        ):
            window.restart_app_from_settings()

        self.assertFalse(window._running)
        self.assertEqual(window.hotkey_controller.stop_count, 1)
        self.assertEqual(window._thread.join_timeouts, [1.0])
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["GMT-N.exe", "--no-selector"])
        self.assertEqual(popen.call_args.kwargs["cwd"], r"C:\App")
        self.assertTrue(other.closed)
        self.assertEqual(app.quit_count, 1)

    def test_restart_from_settings_reports_popen_failure_without_quitting(self) -> None:
        window = _RestartWindow()
        app = _App([window])

        with (
            patch.object(window, "_restart_command", return_value=["GMT-N.exe"]),
            patch("ui_island.app.window.subprocess.Popen", side_effect=OSError("blocked")),
            patch("ui_island.app.window.QApplication.instance", return_value=app),
            patch("ui_island.app.window.styled_info") as info,
        ):
            window.restart_app_from_settings()

        self.assertFalse(window._running)
        self.assertEqual(window.hotkey_controller.stop_count, 1)
        info.assert_called_once()
        self.assertEqual(app.quit_count, 0)


if __name__ == "__main__":
    unittest.main()
