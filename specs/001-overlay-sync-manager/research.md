# Research: Overlay Sync Manager

**Phase**: 0 (Outline & Research)
**Date**: 2025-10-21
**Purpose**: Resolve technical unknowns and establish implementation patterns

## Overview

This document consolidates research findings for implementing the Overlay Sync Manager. Since the feature builds directly on `example_update_overlay.py`, most patterns are already proven. Research focuses on scheduling, template rendering, and configuration management approaches.

---

## 1. Scheduling Pattern for Python Daemon

**Question**: What's the simplest way to run periodic sync operations in Python?

### Decision: Simple time.sleep() Loop with Threading

**Rationale**:
- Aligns with **Minimal Code** principle (no external scheduler libraries)
- Python standard library `threading` + `time.sleep()` sufficient for 10-60 second intervals
- Proven pattern for daemon-style applications
- Easy to implement graceful shutdown via `signal` handlers

**Implementation Pattern**:
```python
import time
import signal
import threading

class SyncManager:
    def __init__(self, config):
        self.running = False
        self.config = config

    def run(self):
        """Main sync loop"""
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        while self.running:
            try:
                self._sync_all_cameras()
                time.sleep(self.config.sync_interval)
            except Exception as e:
                logging.error(f"Sync cycle failed: {e}")
                # Continue to next cycle

    def _shutdown(self, signum, frame):
        """Graceful shutdown handler"""
        logging.info("Shutdown signal received")
        self.running = False
```

**Alternatives Considered**:
- **APScheduler library**: Rejected - adds external dependency for simple use case
- **cron + single-shot script**: Rejected - less control, harder to manage state
- **asyncio**: Rejected - unnecessary complexity for synchronous HTTP operations

---

## 2. Dynamic Template Rendering

**Question**: How to implement placeholder substitution for dynamic content (e.g., `{timestamp}`)?

### Decision: Python str.format() with Custom Context Dict

**Rationale**:
- **Standard library**: `str.format()` built into Python, no dependencies
- **Simple API**: `template.format(**context)` is clear and readable
- **Extensible**: Easy to add new placeholders without changing template engine
- **Type-safe**: Can validate placeholder names at runtime

**Implementation Pattern**:
```python
from datetime import datetime

def render_template(template: str, context: dict) -> str:
    """
    Render a template string by replacing {placeholders}.

    Args:
        template: String with {placeholder} syntax
        context: Dictionary of placeholder values

    Returns:
        Rendered string with placeholders replaced

    Example:
        render_template("Time: {timestamp}", {"timestamp": "2025-01-01 12:00"})
        # Returns: "Time: 2025-01-01 12:00"
    """
    try:
        return template.format(**context)
    except KeyError as e:
        # Missing placeholder - log warning and use fallback
        logging.warning(f"Template placeholder not found: {e}")
        return template  # Return unrendered template
```

**Built-in Placeholders**:
- `{timestamp}`: Current date/time (ISO format or custom format)
- `{date}`: Current date (YYYY-MM-DD)
- `{time}`: Current time (HH:MM:SS)
- `{camera_name}`: Name from config (for debugging)
- `{overlay_id}`: Current overlay ID being updated

**Alternatives Considered**:
- **Jinja2 template engine**: Rejected - overkill for simple placeholder substitution, adds dependency
- **f-strings**: Rejected - requires eval(), security risk
- **Custom parser**: Rejected - reinventing the wheel

---

## 3. JSON Configuration Schema

**Question**: What should the JSON configuration structure look like?

### Decision: Nested Structure with Camera List and Overlay Definitions

**Schema Design**:
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
      "password": "password123",
      "channel": 1,
      "overlays": [
        {
          "id": "1",
          "content": "Front Door - {timestamp}",
          "enabled": true,
          "position_x": null,
          "position_y": null
        },
        {
          "id": "2",
          "content": "Status: OK",
          "enabled": true
        }
      ]
    }
  ]
}
```

**Rationale**:
- **Hierarchical**: Cameras contain overlays (natural relationship)
- **Explicit**: All options visible (no hidden defaults in code)
- **Extensible**: Easy to add per-camera or per-overlay settings
- **Validation-friendly**: Can check required fields with clear error messages

**Validation Rules** (FR-004):
- `sync_interval`: Required, integer > 0
- `cameras`: Required, non-empty array
- Each camera: `name`, `ip`, `username`, `password` required
- Each overlay: `id`, `content` required
- Port defaults to 80, channel defaults to 1

**Alternatives Considered**:
- **Flat structure** (all cameras at top level): Rejected - harder to group related settings
- **YAML format**: Rejected - requires external library (PyYAML), JSON chosen per spec clarification
- **Separate file per camera**: Rejected - harder to manage, overkill for typical use

---

## 4. Error Handling Strategy

**Question**: How to handle transient failures without stopping the sync manager?

### Decision: Try-Catch Per Camera with Logging and Continue

**Pattern**:
```python
def _sync_all_cameras(self):
    """Sync all cameras, handling errors independently"""
    for camera_config in self.config.cameras:
        try:
            self._sync_camera(camera_config)
        except requests.RequestException as e:
            logging.error(
                f"Failed to sync camera {camera_config.name}: {e}. "
                f"Will retry on next cycle."
            )
        except Exception as e:
            logging.error(
                f"Unexpected error syncing camera {camera_config.name}: {e}",
                exc_info=True  # Include stack trace
            )
```

**Rationale**:
- **Isolation**: One camera failure doesn't affect others
- **Resilience**: Automatic retry on next cycle (FR-012)
- **Observability**: All failures logged with context (FR-008)
- **Simplicity**: No complex retry logic or circuit breakers needed

**Error Categories**:
1. **Network errors** (RequestException): Log and retry next cycle
2. **Auth errors** (401/403): Log with hint to check credentials
3. **Config errors**: Fail fast on startup (don't start sync loop)
4. **XML parsing errors**: Log and skip that overlay

**Alternatives Considered**:
- **Exponential backoff**: Rejected - overkill for fixed-interval syncing
- **Dead letter queue**: Rejected - no need to persist failed syncs
- **Circuit breaker pattern**: Rejected - unnecessary complexity

---

## 5. Logging Strategy

**Question**: How to implement comprehensive logging per FR-008 and constitution requirements?

### Decision: Python logging Module with Structured Messages

**Configuration**:
```python
import logging

# Setup in main()
logging.basicConfig(
    level=config.log_level,  # From JSON config
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

**Log Levels**:
- **INFO**: Sync cycle start/completion, successful updates
- **WARNING**: Missing template placeholders, timeouts with retry
- **ERROR**: Network failures, authentication failures, unexpected errors
- **DEBUG**: Full request/response details, XML payloads

**Example Messages**:
```python
logging.info(f"Starting sync cycle for {len(cameras)} cameras")
logging.info(f"✓ Updated overlay {overlay_id} on camera {camera_name}")
logging.error(f"✗ Camera {camera_name} unreachable: {error}. Retry next cycle.")
logging.warning(f"Template placeholder {missing} not found, using literal text")
```

**Rationale**:
- **Standard library**: No dependencies
- **Flexible**: Can redirect to file, syslog, or stderr
- **Structured**: Timestamps and levels help with debugging
- **Constitution aligned**: Errors to stderr with context

---

## 6. Code Reuse from example_update_overlay.py

**Question**: How to reuse the existing HikvisionOverlay class?

### Decision: Extract Core Class to Shared Module (if needed) or Duplicate Minimal Methods

**Option A: Import from example_update_overlay.py**
```python
from example_update_overlay import HikvisionOverlay

# Use directly in sync manager
client = HikvisionOverlay(ip, username, password, channel)
client.update_overlay_text(overlay_id, rendered_content)
```

**Option B: Copy Minimal Methods**
```python
# Copy only the methods we need:
# - update_overlay_text()
# - get_overlay_text()
# Simplify by removing CLI-specific code
```

**Recommendation**: **Option A** (import) initially, refactor to shared module if needed

**Rationale**:
- **DRY principle**: Don't duplicate working code
- **Proven**: Example code is already tested and working
- **Minimal changes**: Just add scheduling/config on top
- **Refactor later**: If example file changes, can extract shared lib

---

## 7. Preventing Overlapping Syncs

**Question**: How to ensure sync cycles don't overlap (FR-013)?

### Decision: Simple Flag Check Before Starting New Cycle

**Pattern**:
```python
class SyncManager:
    def __init__(self, config):
        self.running = False
        self.syncing = False  # Track if sync in progress

    def run(self):
        while self.running:
            if not self.syncing:  # Only start if not already syncing
                self.syncing = True
                try:
                    self._sync_all_cameras()
                finally:
                    self.syncing = False
                time.sleep(self.config.sync_interval)
            else:
                logging.warning(
                    f"Previous sync still in progress, skipping cycle. "
                    f"Consider increasing sync_interval."
                )
                time.sleep(5)  # Short sleep before checking again
```

**Rationale**:
- **Simple**: Boolean flag, no locks needed (single-threaded)
- **Defensive**: Warns if interval too short for sync duration
- **Prevents queue buildup**: Skips rather than queues overlapping work

**Alternatives Considered**:
- **Threading locks**: Rejected - unnecessary for single-threaded daemon
- **Queue system**: Rejected - overcomplicates simple periodic task

---

## Summary of Decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Scheduling | `time.sleep()` loop with `signal` handlers | Minimal code, standard library, sufficient for use case |
| Templates | `str.format()` with context dict | Standard library, simple API, extensible |
| Config Format | Nested JSON with camera/overlay hierarchy | Explicit, validation-friendly, extensible |
| Error Handling | Per-camera try-catch with logging | Isolation, resilience, observability |
| Logging | Python `logging` module with structured messages | Standard library, flexible, constitution-aligned |
| Code Reuse | Import `HikvisionOverlay` from example | DRY, proven code, minimal duplication |
| Overlap Prevention | Boolean flag with warning | Simple, effective for single-threaded case |

**No unknowns remaining**. All NEEDS CLARIFICATION items from Technical Context resolved. Ready for Phase 1 (Design).
