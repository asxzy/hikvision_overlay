# CLI Interface Contract

**Program**: `overlay_sync_manager.py`
**Purpose**: Command-line interface for the Overlay Sync Manager daemon

---

## Usage

```bash
python overlay_sync_manager.py [OPTIONS] CONFIG_FILE
```

---

## Arguments

### Positional Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `CONFIG_FILE` | Yes | Path to JSON configuration file |

**Examples**:
```bash
python overlay_sync_manager.py config.json
python overlay_sync_manager.py /etc/overlay-sync/config.json
python overlay_sync_manager.py ~/camera-config.json
```

---

## Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--validate` | `-v` | flag | false | Validate configuration and exit (don't start daemon) |
| `--once` | `-1` | flag | false | Run sync once and exit (no daemon mode) |
| `--help` | `-h` | flag | - | Show help message and exit |
| `--version` | `-V` | flag | - | Show version and exit |

---

## Exit Codes

| Code | Meaning | When |
|------|---------|------|
| 0 | Success | Normal shutdown or validation passed |
| 1 | Configuration error | Invalid JSON, missing required fields, validation failure |
| 2 | Connection error | Cannot reach any configured cameras on startup |
| 130 | Interrupted | User pressed Ctrl+C (SIGINT) |
| 143 | Terminated | Process received SIGTERM |

---

## Behavior

### Normal Mode (Daemon)

```bash
python overlay_sync_manager.py config.json
```

1. Load and validate configuration
2. Log "Starting Overlay Sync Manager" message
3. Attempt to connect to all cameras (fail if all unreachable)
4. Enter infinite sync loop:
   - Sync all cameras/overlays
   - Log results
   - Sleep for `sync_interval` seconds
   - Repeat
5. On SIGINT/SIGTERM: log "Shutting down gracefully" and exit(0)

**Output** (to stdout/stderr via logging):
```
2025-10-21 14:30:00 [INFO] Starting Overlay Sync Manager v1.0.0
2025-10-21 14:30:00 [INFO] Loaded configuration: 2 cameras, sync every 30s
2025-10-21 14:30:00 [INFO] ✓ Connected to camera 'front-door' (192.168.1.100)
2025-10-21 14:30:00 [INFO] ✓ Connected to camera 'backyard' (192.168.1.101)
2025-10-21 14:30:01 [INFO] Starting sync cycle 1
2025-10-21 14:30:02 [INFO] ✓ Updated overlay 1 on 'front-door': "Front Door - 2025-10-21 14:30:02"
2025-10-21 14:30:03 [INFO] ✓ Updated overlay 1 on 'backyard': "Backyard - 2025-10-21 14:30:03"
2025-10-21 14:30:03 [INFO] Sync cycle 1 completed in 2.1s. Next cycle in 30s.
^C2025-10-21 14:30:15 [INFO] Received interrupt signal (SIGINT)
2025-10-21 14:30:15 [INFO] Shutting down gracefully...
2025-10-21 14:30:15 [INFO] Goodbye!
```

---

### Validation Mode

```bash
python overlay_sync_manager.py --validate config.json
```

1. Load configuration file
2. Validate all fields and constraints
3. Print validation results
4. Exit with code 0 (valid) or 1 (invalid)
5. **Do not connect to cameras or start sync**

**Output** (success):
```
Validating configuration file: config.json
✓ Configuration is valid
  - 2 cameras configured
  - 3 overlays total
  - Sync interval: 30 seconds
```

**Output** (failure):
```
Validating configuration file: config.json
✗ Configuration is invalid:
  - Missing required field 'cameras'
  - Invalid sync_interval: must be > 0 (got: -5)
```

---

### One-Shot Mode

```bash
python overlay_sync_manager.py --once config.json
```

1. Load and validate configuration
2. Perform ONE sync cycle for all cameras/overlays
3. Log results
4. Exit with code 0 (all succeeded) or 1 (any failed)

**Use Case**: Testing, cron jobs, manual syncs

**Output**:
```
2025-10-21 14:30:00 [INFO] One-shot mode: running single sync cycle
2025-10-21 14:30:02 [INFO] ✓ Updated 2/2 overlays successfully
2025-10-21 14:30:02 [INFO] Done.
```

---

## Signal Handling

| Signal | Behavior |
|--------|----------|
| SIGINT (Ctrl+C) | Graceful shutdown: finish current sync cycle, then exit |
| SIGTERM | Graceful shutdown: finish current sync cycle, then exit |
| SIGHUP | Ignored (no config reload in v1.0) |

**Graceful Shutdown**:
- Finish any in-progress sync operations
- Log shutdown message
- Exit cleanly with code 0

---

## Environment Variables

**None required**. All configuration via JSON file.

Optional for debugging:
- `PYTHONUNBUFFERED=1` - Force unbuffered output (useful for log streaming)

---

## File Requirements

### Configuration File

- **Format**: JSON (UTF-8 encoding)
- **Location**: Any readable file path
- **Permissions**: Must be readable by user running the script
- **Recommended**: Store outside repository with restrictive permissions (600) due to passwords

**Security Note**: Configuration contains plaintext camera passwords. Protect accordingly:
```bash
chmod 600 config.json
chown $USER:$USER config.json
```

---

## Integration Examples

### systemd Service (Linux)

```ini
[Unit]
Description=Hikvision Overlay Sync Manager
After=network.target

[Service]
Type=simple
User=camera-sync
WorkingDirectory=/opt/overlay-sync
ExecStart=/usr/bin/python3 /opt/overlay-sync/overlay_sync_manager.py /etc/overlay-sync/config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### launchd (macOS)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hikvision.overlay-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/usr/local/bin/overlay_sync_manager.py</string>
        <string>/etc/overlay-sync/config.json</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

### Cron (periodic sync)

```cron
# Run sync every 5 minutes
*/5 * * * * /usr/bin/python3 /opt/overlay-sync/overlay_sync_manager.py --once /etc/overlay-sync/config.json >> /var/log/overlay-sync.log 2>&1
```

---

## Help Output

```bash
$ python overlay_sync_manager.py --help

usage: overlay_sync_manager.py [-h] [-v] [-1] [-V] CONFIG_FILE

Hikvision Overlay Sync Manager - Automatically synchronize text overlays
to Hikvision cameras at configurable intervals.

positional arguments:
  CONFIG_FILE       Path to JSON configuration file

options:
  -h, --help        Show this help message and exit
  -v, --validate    Validate configuration and exit (don't start daemon)
  -1, --once        Run sync once and exit (no daemon mode)
  -V, --version     Show version and exit

Examples:
  overlay_sync_manager.py config.json           Start daemon with config
  overlay_sync_manager.py --validate config.json  Validate configuration
  overlay_sync_manager.py --once config.json     Run single sync cycle

Configuration:
  See config.example.json for configuration format and options.
  Configuration includes camera credentials, overlay definitions, and
  sync interval settings.

Signals:
  SIGINT/SIGTERM - Graceful shutdown after completing current sync

For more information, see README.md
```

---

## Version Output

```bash
$ python overlay_sync_manager.py --version
Overlay Sync Manager v1.0.0
Python 3.11.5
```

---

## Summary

The CLI interface provides:
- Simple single-command operation for daemon mode
- Validation mode for testing configuration
- One-shot mode for manual or cron-based syncing
- Graceful shutdown on signals
- Clear, informative output and error messages
- Standard exit codes for scripting

Follows the **Readability First** and **Standard Python Patterns** principles from the constitution.
