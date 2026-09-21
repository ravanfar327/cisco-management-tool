# Building standalone Windows executables

This produces two `.exe` files that don't require Python installed on the target machine: one for the CLI, one for the GUI.

## 1. Set up a clean build environment (recommended)

Do this on a **Windows** machine (PyInstaller builds platform-specific binaries — you cannot build a `.exe` from Linux/macOS).

```powershell
python -m venv build-env
build-env\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

## 2. Build the CLI executable

```powershell
pyinstaller --onefile --name CiscoMgmtCLI --console cisco_mgmt.py
```

## 3. Build the GUI executable

```powershell
pyinstaller --onefile --name CiscoMgmtGUI --windowed gui_app.py
```

`--windowed` suppresses the console window (the GUI has its own log console on the Backup page, and everything else logs to `cisco_mgmt.log`).

## 4. Where the executables end up

Both commands create `dist\CiscoMgmtCLI.exe` and `dist\CiscoMgmtGUI.exe`. Copy **both** into the same folder for distribution — the GUI needs the same data files (`devices.enc`, `backup_settings.json`, etc.) as the CLI, and they're designed to be run side by side from one folder.

## 5. Important: `--onefile` and data files

With `--onefile`, PyInstaller unpacks the app into a temporary folder on every launch. This project already accounts for that (see `app_paths.py`) — all data files (`devices.enc`, `devices.salt`, `backups/`, `*.log`, `backup_settings.json`, `gui_preferences.json`, `master_password.dpapi`) are always written **next to the `.exe`**, not into that temporary folder, so nothing gets lost between runs.

If you ever add a new module that stores data on disk, use `app_paths.get_app_dir(__file__)` for its base directory — do **not** use `os.path.dirname(os.path.abspath(__file__))` directly, or its data will vanish after every run when frozen.

## 6. Common PyInstaller issues with this project's dependencies

- **`ModuleNotFoundError` for netmiko vendor drivers**: if this happens, rebuild with `pyinstaller --onefile --collect-all netmiko ...`.
- **PySide6 missing plugins / blank window**: rebuild the GUI with `pyinstaller --onefile --windowed --collect-all PySide6 gui_app.py`. This makes the executable larger but avoids missing-Qt-plugin issues.
- **`pywin32` (DPAPI) not found**: only needed for "unattended startup." If you don't need that feature, you can skip installing `pywin32` entirely — the app degrades gracefully (see `windows_credential_store.is_available()`).

## 7. Testing the build

Before publishing a release, on the actual target Windows machine (or a clean VM):

1. Run `CiscoMgmtCLI.exe` — set a master password, add a test device, run a backup.
2. Confirm `devices.enc`, `devices.salt`, and a `backups\` folder appear **next to the exe** (not in a temp folder).
3. Run `CiscoMgmtGUI.exe` from the same folder — it should unlock with the same master password and show the same device you just added.
4. Close and reopen both — confirm the device list and backup history persist.

## 8. Antivirus / SmartScreen false positives

PyInstaller-built executables are frequently flagged by Windows Defender/SmartScreen and some antivirus engines as suspicious, purely because of how PyInstaller bundles Python — this is a well-known false-positive pattern, not specific to this project. Consider:

- Code-signing the executables (requires a code-signing certificate) if you plan wide distribution.
- Mentioning this in your README/release notes so users aren't alarmed.
- Uploading the built `.exe` to [VirusTotal](https://www.virustotal.com/) before release and linking the scan result in your release notes, as reassurance.
