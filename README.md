# Hikvision Overlay Sync Manager

Automatically synchronize text overlays to Hikvision cameras at configurable intervals. Perfect for displaying dynamic content like timestamps, camera names, or custom messages on your camera feeds.

## Features

- **Automated Sync**: Update camera overlays on a scheduled interval
- **Dynamic Templates**: Use placeholders like `{timestamp}`, `{date}`, `{camera_name}` for dynamic content
- **Multi-Camera**: Manage multiple cameras from a single configuration
- **Robust Error Handling**: Continues running even if cameras are temporarily unreachable
- **Simple Configuration**: JSON-based configuration with validation
- **Production Ready**: Includes systemd service example and graceful shutdown

## Quick Start

### Installation

```bash
# Clone or download the repository
cd hikvision_overlay

# Install dependencies (requests only)
pip install -r requirements.txt
```

### Configuration

1. Copy the example configuration:

```bash
cp config.example.json config.json
chmod 600 config.json  # Protect passwords
```

2. Edit `config.json` with your camera details:

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

### Validation

Test your configuration before running:

```bash
python overlay_sync_manager.py --validate config.json
```

Expected output:
```
✓ Configuration is valid
  - 1 camera configured
  - 1 overlay total
  - Sync interval: 30 seconds
```

### Running

**One-Shot Mode** (test with single sync):
```bash
python overlay_sync_manager.py --once config.json
```

**Daemon Mode** (continuous syncing):
```bash
python overlay_sync_manager.py config.json
```

Press **Ctrl+C** to stop gracefully.

## Template Placeholders

Use these placeholders in your overlay content:

- `{timestamp}` - Full date and time (e.g., "2025-10-22 14:30:00")
- `{date}` - Date only (e.g., "2025-10-22")
- `{time}` - Time only (e.g., "14:30:00")
- `{camera_name}` - Camera name from config
- `{overlay_id}` - Overlay ID

Example:
```json
{
  "content": "{camera_name} | {date} {time}"
}
```

## Configuration Reference

### Top-Level Fields

- `sync_interval` (integer) - Seconds between sync cycles (required)
- `timeout` (integer) - HTTP request timeout in seconds (default: 10)
- `log_level` (string) - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `cameras` (array) - List of camera configurations (required)

### Camera Fields

- `name` (string) - Unique identifier for logs (required)
- `ip` (string) - Camera IP address (required)
- `port` (integer) - HTTP port (default: 80)
- `username` (string) - Camera admin username (required)
- `password` (string) - Camera admin password (required)
- `channel` (integer) - Video channel number (default: 1)
- `overlays` (array) - List of overlay configurations (required)

### Overlay Fields

- `id` (string) - Overlay slot (typically "1" through "8") (required)
- `content` (string) - Text or template with placeholders (required)
- `enabled` (boolean) - Enable this overlay (default: true)
- `position_x` (integer|null) - X position in pixels (null to keep current)
- `position_y` (integer|null) - Y position in pixels (null to keep current)

## CLI Reference

```bash
# Show version
python overlay_sync_manager.py --version

# Validate configuration
python overlay_sync_manager.py --validate config.json

# Run once and exit
python overlay_sync_manager.py --once config.json

# Start daemon mode
python overlay_sync_manager.py config.json
```

**Exit Codes:**
- `0` - Success
- `1` - Configuration error or sync failures
- `2` - All cameras unreachable

## Production Deployment

### Docker (Recommended)

The easiest way to run the overlay sync manager is with Docker:

**Build and run with Docker Compose:**
```bash
# Build the image
docker-compose build

# Run in daemon mode (detached)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

**Build and run with Docker:**
```bash
# Build the image
docker build -t hikvision-overlay .

# Run in daemon mode
docker run -d --name hikvision-overlay \
  --network host \
  -v $(pwd)/config.json:/app/config.json:ro \
  hikvision-overlay

# Run validation
docker run --rm -v $(pwd)/config.json:/app/config.json:ro \
  hikvision-overlay --validate config.json

# Run once (test)
docker run --rm -v $(pwd)/config.json:/app/config.json:ro \
  hikvision-overlay --once config.json

# View logs
docker logs -f hikvision-overlay

# Stop and remove
docker stop hikvision-overlay
docker rm hikvision-overlay
```

**Notes:**
- Uses `--network host` to access cameras on local network
- Config file is mounted read-only for security
- Container restarts automatically unless stopped
- Logs are managed by Docker (10MB max, 3 files)

### systemd Service (Linux)

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

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable overlay-sync
sudo systemctl start overlay-sync
sudo systemctl status overlay-sync
```

View logs:
```bash
sudo journalctl -u overlay-sync -f
```

### Cron (Periodic Sync)

For periodic updates without a persistent daemon:

```bash
# Edit crontab
crontab -e

# Sync every 5 minutes
*/5 * * * * cd /opt/overlay-sync && /usr/bin/python3 overlay_sync_manager.py --once config.json >> /var/log/overlay-sync.log 2>&1
```

## Troubleshooting

### Configuration Errors

**Problem**: Configuration validation fails

**Solution**:
1. Use a JSON validator (e.g., https://jsonlint.com)
2. Check for syntax errors (missing commas, quotes, brackets)
3. Ensure all required fields are present

### Connection Issues

**Problem**: "Connection refused" or "Timeout"

**Solution**:
1. Verify camera IP: `ping 192.168.1.100`
2. Check camera HTTP port (default 80)
3. Ensure network connectivity
4. Test with `example_update_overlay.py`

### Authentication Errors

**Problem**: "Authentication failed" (401/403)

**Solution**:
1. Verify credentials via camera web interface
2. Ensure account has admin privileges
3. Check for special characters in password

### Overlays Not Visible

**Problem**: Overlays not appearing in video feed

**Solution**:
1. Set `"enabled": true` in config
2. Check overlay position (use `null` to keep current)
3. Verify overlay text is not empty
4. Check camera's OSD settings in web interface

## Multiple Cameras

Add more cameras to the configuration:

```json
{
  "sync_interval": 30,
  "cameras": [
    {
      "name": "front-door",
      "ip": "192.168.1.100",
      "username": "admin",
      "password": "password1",
      "overlays": [...]
    },
    {
      "name": "backyard",
      "ip": "192.168.1.101",
      "username": "admin",
      "password": "password2",
      "overlays": [...]
    }
  ]
}
```

Each camera syncs independently. If one fails, others continue.

## Requirements

- Python 3.9 or higher
- Network access to Hikvision cameras
- Camera admin credentials
- Dependencies: `requests>=2.31.0`, `urllib3>=2.0.0`

## Architecture

- Single-file Python script (~1000 lines)
- Minimal dependencies (stdlib + requests)
- Configuration-driven (no code changes needed)
- Signal-based graceful shutdown (SIGINT/SIGTERM)
- Per-camera and per-overlay error isolation
- Automatic retry on next cycle for failures

## License

See LICENSE file for details.

## Support

- Configuration schema: `specs/001-overlay-sync-manager/contracts/config-schema.json`
- CLI reference: `specs/001-overlay-sync-manager/contracts/cli-interface.md`
- Example script: `example_update_overlay.py`

## Success Checklist

- [ ] Configuration file created and validated
- [ ] Tested with `--once` mode successfully
- [ ] Overlays visible in camera video feed
- [ ] Daemon running and syncing on schedule
- [ ] (Optional) Deployed as systemd service or cron job

---

**Version**: 1.0.0
