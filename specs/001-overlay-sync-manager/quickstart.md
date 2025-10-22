# Quickstart Guide: Overlay Sync Manager

**Target Audience**: System administrators deploying the Overlay Sync Manager
**Time to Complete**: 5-10 minutes
**Prerequisites**: Python 3.9+, network access to Hikvision cameras, admin credentials

---

## Installation

### 1. Install Python Dependencies

```bash
# Clone or download the repository
cd /path/to/hikvision_overlay

# Install required library (requests only)
pip install -r requirements.txt
```

**Contents of `requirements.txt`**:
```
requests>=2.31.0
urllib3>=2.0.0
```

---

## Configuration

### 2. Create Configuration File

Copy the example configuration and edit for your cameras:

```bash
cp config.example.json config.json
chmod 600 config.json  # Protect passwords
```

### 3. Edit Configuration

Edit `config.json` with your camera details:

```json
{
  "sync_interval": 30,
  "timeout": 10,
  "log_level": "INFO",
  "cameras": [
    {
      "name": "front-door",
      "ip": "192.168.1.100",
      "port": 80,
      "username": "admin",
      "password": "your-camera-password",
      "channel": 1,
      "overlays": [
        {
          "id": "1",
          "content": "Front Door - {timestamp}",
          "enabled": true
        }
      ]
    }
  ]
}
```

**Configuration Fields**:
- `sync_interval`: How often to update overlays (seconds)
- `timeout`: HTTP request timeout (seconds)
- `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `cameras`: List of camera configurations
  - `name`: Unique identifier for logs
  - `ip`: Camera IP address (can include port like "192.168.1.100:8080")
  - `username`/`password`: Camera admin credentials
  - `channel`: Video channel number (usually 1)
  - `overlays`: List of text overlays to sync
    - `id`: Overlay slot (1-8 on most Hikvision cameras)
    - `content`: Text or template with `{placeholders}`

**Available Placeholders**:
- `{timestamp}`: Full date and time (e.g., "2025-10-21 14:30:00")
- `{date}`: Date only (e.g., "2025-10-21")
- `{time}`: Time only (e.g., "14:30:00")
- `{camera_name}`: Camera name from config
- `{overlay_id}`: Overlay ID

---

## Validation

### 4. Test Configuration

Validate your configuration before starting the daemon:

```bash
python overlay_sync_manager.py --validate config.json
```

**Expected Output** (if valid):
```
Validating configuration file: config.json
✓ Configuration is valid
  - 1 camera configured
  - 1 overlay total
  - Sync interval: 30 seconds
```

**If validation fails**, you'll see clear error messages:
```
✗ Configuration is invalid:
  - Camera 'front-door': Invalid IP format
  - Missing required field 'username' in camera 'front-door'
```

Fix any errors and re-validate.

---

## First Run

### 5. Test with One-Shot Mode

Before running as a daemon, test with a single sync:

```bash
python overlay_sync_manager.py --once config.json
```

**Expected Output**:
```
2025-10-21 14:30:00 [INFO] One-shot mode: running single sync cycle
2025-10-21 14:30:01 [INFO] ✓ Connected to camera 'front-door' (192.168.1.100)
2025-10-21 14:30:02 [INFO] ✓ Updated overlay 1 on 'front-door': "Front Door - 2025-10-21 14:30:02"
2025-10-21 14:30:02 [INFO] Sync completed: 1/1 overlays updated successfully
2025-10-21 14:30:02 [INFO] Done.
```

**Check your camera** - you should see the overlay text updated on the video feed!

---

## Running as Daemon

### 6. Start Sync Manager

Start the sync manager in daemon mode:

```bash
python overlay_sync_manager.py config.json
```

**Expected Output**:
```
2025-10-21 14:30:00 [INFO] Starting Overlay Sync Manager v1.0.0
2025-10-21 14:30:00 [INFO] Loaded configuration: 1 camera, sync every 30s
2025-10-21 14:30:00 [INFO] ✓ Connected to camera 'front-door' (192.168.1.100)
2025-10-21 14:30:01 [INFO] Starting sync cycle 1
2025-10-21 14:30:02 [INFO] ✓ Updated overlay 1 on 'front-door'
2025-10-21 14:30:02 [INFO] Sync cycle 1 completed in 1.2s. Next cycle in 30s.
```

The manager will continue syncing overlays every 30 seconds (or your configured interval).

### 7. Stop Sync Manager

Press **Ctrl+C** to gracefully stop the daemon:

```
^C2025-10-21 14:31:00 [INFO] Received interrupt signal (SIGINT)
2025-10-21 14:31:00 [INFO] Shutting down gracefully...
2025-10-21 14:31:00 [INFO] Goodbye!
```

---

## Production Deployment

### Option A: systemd Service (Linux)

Create `/etc/systemd/system/overlay-sync.service`:

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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable overlay-sync
sudo systemctl start overlay-sync
sudo systemctl status overlay-sync
```

**View logs**:
```bash
sudo journalctl -u overlay-sync -f
```

---

### Option B: Screen/tmux Session

For quick deployment without systemd:

```bash
# Start in screen session
screen -S overlay-sync
python overlay_sync_manager.py config.json

# Detach: Ctrl+A, then D
# Reattach later: screen -r overlay-sync
```

---

### Option C: Cron (Periodic Sync)

For periodic updates without a persistent daemon:

```bash
# Edit crontab
crontab -e

# Add line to sync every 5 minutes
*/5 * * * * cd /opt/overlay-sync && /usr/bin/python3 overlay_sync_manager.py --once config.json >> /var/log/overlay-sync.log 2>&1
```

---

## Troubleshooting

### Issue: "Configuration is invalid"

**Cause**: Syntax error in JSON or missing required fields

**Solution**:
1. Use a JSON validator (e.g., https://jsonlint.com)
2. Check for missing commas, quotes, brackets
3. Ensure all required fields present (name, ip, username, password, overlays)

---

### Issue: "Connection refused" or "Timeout"

**Cause**: Cannot reach camera

**Solution**:
1. Verify camera IP address: `ping 192.168.1.100`
2. Check camera HTTP port (default 80)
3. Ensure camera is on same network or routable
4. Test with example script: `python example_update_overlay.py 192.168.1.100 admin password --list`

---

### Issue: "Authentication failed" (401/403)

**Cause**: Incorrect credentials

**Solution**:
1. Verify username/password by logging into camera web interface
2. Ensure account has admin privileges
3. Check for special characters in password (may need escaping in JSON)

---

### Issue: "Overlay not found"

**Cause**: Invalid overlay ID

**Solution**:
1. List available overlays: `python example_update_overlay.py 192.168.1.100 admin password --list`
2. Use overlay IDs from that list (typically "1", "2", etc.)
3. Update config.json with valid overlay IDs

---

### Issue: Overlays not updating in video feed

**Cause**: Overlay disabled or position off-screen

**Solution**:
1. Set `"enabled": true` in config
2. Check overlay position (null = keep current position)
3. Verify overlay text not empty
4. Check camera's on-screen display settings in web interface

---

## Next Steps

### Multiple Cameras

Add more cameras to the `cameras` array:

```json
{
  "sync_interval": 30,
  "cameras": [
    {
      "name": "front-door",
      "ip": "192.168.1.100",
      ...
    },
    {
      "name": "backyard",
      "ip": "192.168.1.101",
      ...
    }
  ]
}
```

Each camera syncs independently - if one fails, others continue.

---

### Dynamic Content

Use templates for dynamic overlays:

```json
{
  "id": "1",
  "content": "{date} {time} | Camera: {camera_name}",
  "enabled": true
}
```

This will update to show current date/time on each sync cycle.

---

### Debugging

Enable debug logging for detailed information:

```json
{
  "log_level": "DEBUG",
  ...
}
```

This shows full HTTP requests, XML payloads, and detailed timing.

---

## Support

- **Example script**: Test camera connectivity with `example_update_overlay.py`
- **Configuration schema**: See `contracts/config-schema.json` for full spec
- **CLI reference**: See `contracts/cli-interface.md` for all options

---

## Success Checklist

- [ ] Configuration file created and validated
- [ ] Tested with `--once` mode successfully
- [ ] Overlays visible in camera video feed
- [ ] Daemon running and syncing on schedule
- [ ] (Optional) Deployed as systemd service or cron job

**Congratulations!** Your Overlay Sync Manager is running. Overlays will automatically update at your configured interval.
