from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_NAME = "启动以撒助手.bat"
WINDOWS_POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


class LauncherTests(unittest.TestCase):
    def test_windows_powershell_can_parse_start_script(self):
        command = (
            "$tokens=$null; $errors=$null; "
            "[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{PROJECT_ROOT / 'start.ps1'}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count) { $errors | ForEach-Object { Write-Output $_.Message }; exit 1 }"
        )

        result = subprocess.run(
            [str(WINDOWS_POWERSHELL), "-NoLogo", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_double_click_launcher_keeps_failures_visible_and_returns_error(self):
        source = PROJECT_ROOT / LAUNCHER_NAME
        self.assertTrue(source.is_file(), f"missing launcher: {LAUNCHER_NAME}")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            launcher = root / LAUNCHER_NAME
            shutil.copy2(source, launcher)
            (root / "start.ps1").write_text(
                'Write-Error "synthetic startup failure"\nexit 7\n',
                encoding="utf-8-sig",
            )
            process = subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(launcher)],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            time.sleep(0.4)
            self.assertIsNone(process.poll(), "launcher closed before the error was readable")
            output, _ = process.communicate("\n", timeout=3)

        self.assertEqual(process.returncode, 7)
        self.assertIn("Startup failed", output)


if __name__ == "__main__":
    unittest.main()
