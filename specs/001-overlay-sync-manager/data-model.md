# Data Model: Overlay Sync Manager

**Phase**: 1 (Design & Contracts)
**Date**: 2025-10-21
**Purpose**: Define data structures and validation rules

## Overview

The Overlay Sync Manager uses Python dataclasses for configuration entities. All data is loaded from JSON configuration file and validated on startup. No persistent storage or database required.

---

## Entity: ConfigurationRoot

**Purpose**: Top-level configuration object containing global settings and camera list

**Attributes**:
| Name | Type | Required | Default | Description | Validation |
|------|------|----------|---------|-------------|------------|
| `sync_interval` | int | Yes | - | Seconds between sync cycles | Must be > 0, typically 10-300 |
| `timeout` | int | No | 10 | HTTP request timeout in seconds | Must be > 0, typically 5-60 |
| `log_level` | str | No | "INFO" | Logging level | Must be one of: DEBUG, INFO, WARNING, ERROR |
| `cameras` | list[CameraConfig] | Yes | - | List of camera configurations | Must be non-empty array |

**Relationships**:
- Contains multiple `CameraConfig` entities (1:N)

**Example**:
```json
{
  "sync_interval": 30,
  "timeout": 10,
  "log_level": "INFO",
  "cameras": [...]
}
```

**Validation Rules**:
- `sync_interval` must be positive integer
- `cameras` array must have at least one camera
- `log_level` must be valid Python logging level
- If `timeout` > `sync_interval`, warn user about potential overlap

---

## Entity: CameraConfig

**Purpose**: Connection details and overlay definitions for a single Hikvision camera

**Attributes**:
| Name | Type | Required | Default | Description | Validation |
|------|------|----------|---------|-------------|------------|
| `name` | str | Yes | - | Human-readable camera identifier | Non-empty string, used in logs |
| `ip` | str | Yes | - | Camera IP address or hostname | Valid IP or hostname format |
| `port` | int | No | 80 | Camera HTTP port | Must be 1-65535 |
| `username` | str | Yes | - | Camera admin username | Non-empty string |
| `password` | str | Yes | - | Camera admin password | Non-empty string (not validated for strength) |
| `channel` | int | No | 1 | Video channel number | Must be > 0, typically 1 |
| `overlays` | list[OverlayConfig] | Yes | - | List of overlay definitions | Must be non-empty array |

**Relationships**:
- Belongs to one `ConfigurationRoot` (N:1)
- Contains multiple `OverlayConfig` entities (1:N)

**Example**:
```json
{
  "name": "front-door",
  "ip": "192.168.1.100",
  "port": 80,
  "username": "admin",
  "password": "password123",
  "channel": 1,
  "overlays": [...]
}
```

**Validation Rules**:
- `name` must be unique within configuration (for logging clarity)
- `ip` can include port suffix (e.g., "192.168.1.100:8080") - parsed automatically
- `overlays` array must have at least one overlay
- Credentials validated on first connection attempt (fail-fast)

---

## Entity: OverlayConfig

**Purpose**: Definition of a single text overlay to be synchronized to camera

**Attributes**:
| Name | Type | Required | Default | Description | Validation |
|------|------|----------|---------|-------------|------------|
| `id` | str | Yes | - | Overlay ID (e.g., "1", "2", "3") | Non-empty string, typically "1"-"8" |
| `content` | str | Yes | - | Text content or template | Non-empty string, supports {placeholders} |
| `enabled` | bool | No | true | Whether to enable overlay on camera | Boolean value |
| `position_x` | int \| null | No | null | X position in pixels | If set, must be >= 0 |
| `position_y` | int \| null | No | null | Y position in pixels | If set, must be >= 0 |

**Relationships**:
- Belongs to one `CameraConfig` (N:1)

**Example**:
```json
{
  "id": "1",
  "content": "Front Door - {timestamp}",
  "enabled": true,
  "position_x": null,
  "position_y": null
}
```

**Validation Rules**:
- `id` must be unique within camera's overlay list
- `content` length should not exceed camera limits (typically 44 characters) - warn if exceeded
- If `position_x` or `position_y` set, both should be set (consistency check, not enforced)
- Template placeholders validated at runtime (missing placeholders logged as warnings)

**Supported Placeholders** (from research.md):
- `{timestamp}`: Full ISO timestamp (e.g., "2025-01-01 12:00:00")
- `{date}`: Date only (YYYY-MM-DD)
- `{time}`: Time only (HH:MM:SS)
- `{camera_name}`: Name from CameraConfig
- `{overlay_id}`: Overlay ID

---

## Entity: TemplateContext

**Purpose**: Runtime data context for rendering dynamic overlay content

**Attributes**:
| Name | Type | Description |
|------|------|-------------|
| `timestamp` | str | Current timestamp in format "YYYY-MM-DD HH:MM:SS" |
| `date` | str | Current date "YYYY-MM-DD" |
| `time` | str | Current time "HH:MM:SS" |
| `camera_name` | str | Camera name from config |
| `overlay_id` | str | Overlay ID being rendered |

**Lifecycle**: Created fresh for each sync cycle, passed to template renderer

**Example**:
```python
context = {
    "timestamp": "2025-10-21 14:30:00",
    "date": "2025-10-21",
    "time": "14:30:00",
    "camera_name": "front-door",
    "overlay_id": "1"
}
```

**Extensibility**: Additional placeholders can be added by extending this dictionary (e.g., external sensor data, system stats)

---

## Entity: SyncResult

**Purpose**: Outcome of a single overlay sync operation (runtime data, not persisted)

**Attributes**:
| Name | Type | Description |
|------|------|-------------|
| `camera_name` | str | Camera identifier |
| `overlay_id` | str | Overlay ID that was synced |
| `success` | bool | Whether sync succeeded |
| `timestamp` | datetime | When sync was attempted |
| `error` | str \| None | Error message if failed, None if successful |
| `duration_ms` | int | How long the sync took in milliseconds |

**Lifecycle**: Created during sync operation, logged immediately, not stored

**Example**:
```python
result = SyncResult(
    camera_name="front-door",
    overlay_id="1",
    success=True,
    timestamp=datetime.now(),
    error=None,
    duration_ms=245
)
```

**Usage**: Logged at INFO level if success, ERROR level if failed

---

## Data Flow

```
JSON Config File
     ↓
ConfigurationRoot (loaded & validated on startup)
     ↓
List of CameraConfig (validated)
     ↓
For each camera, for each overlay:
     ↓
TemplateContext (generated per cycle) → render_template() → rendered content
     ↓
HikvisionOverlay.update_overlay_text() (from example_update_overlay.py)
     ↓
SyncResult (logged, not stored)
```

---

## Validation Strategy

**Startup Validation** (FR-004 - fail fast):
1. Load JSON file with `json.load()`
2. Catch `json.JSONDecodeError` → clear error message about syntax
3. Validate all required fields present
4. Validate data types match expectations
5. Validate ranges (sync_interval > 0, port in valid range, etc.)
6. Validate uniqueness (camera names, overlay IDs within camera)
7. If any validation fails: print error message and exit with code 1
8. If all pass: log "Configuration validated successfully" and start sync loop

**Runtime Validation**:
- Template placeholders checked during render (missing → warning, use literal)
- HTTP errors handled per-camera (logged, continue to next camera)
- Overlay text length checked (if > 44 chars, truncate and warn)

---

## Python Dataclass Implementation

**Approach**: Use `@dataclass` decorator from Python standard library for clean, typed configuration objects

**Example**:
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class OverlayConfig:
    id: str
    content: str
    enabled: bool = True
    position_x: Optional[int] = None
    position_y: Optional[int] = None

@dataclass
class CameraConfig:
    name: str
    ip: str
    username: str
    password: str
    overlays: List[OverlayConfig]
    port: int = 80
    channel: int = 1

@dataclass
class ConfigurationRoot:
    sync_interval: int
    cameras: List[CameraConfig]
    timeout: int = 10
    log_level: str = "INFO"
```

**Benefits**:
- Type hints for IDE support
- Automatic `__init__()`, `__repr__()` generation
- Minimal boilerplate (constitution principle: Minimal Code)
- Easy to serialize/deserialize with `dataclasses.asdict()` / custom loader

---

## State Management

**No persistent state required**. The sync manager is stateless between cycles:
- Configuration loaded once at startup
- Each sync cycle is independent
- No need to track "last successful sync time" or overlay history
- If sync manager restarts, it resumes normal operation immediately

**Rationale**: Aligns with **Simplicity** principle from constitution. No database, no state files, no complexity.

---

## Summary

| Entity | Purpose | Persistence | Validation |
|--------|---------|-------------|------------|
| ConfigurationRoot | Global settings + camera list | JSON file (read-only) | Startup |
| CameraConfig | Camera connection details | Part of ConfigurationRoot | Startup |
| OverlayConfig | Overlay definition + template | Part of CameraConfig | Startup |
| TemplateContext | Dynamic data for rendering | Runtime only | Runtime |
| SyncResult | Sync operation outcome | Logged only, not stored | N/A |

**All entities defined. No database schema required. Ready for contract/API definitions.**
