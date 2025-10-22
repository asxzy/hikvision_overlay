# Feature Specification: Overlay Sync Manager

**Feature Branch**: `001-overlay-sync-manager`
**Created**: 2025-10-21
**Status**: Draft
**Input**: User description: "Follow the core logic in the example_update_overlay.py. Build a sync manager that sync the overlay information to camera on interval, defined by a configuration file."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Overlay Synchronization (Priority: P1)

As a camera system administrator, I want overlay text on my Hikvision cameras to automatically update at regular intervals, so that I can display dynamic information (like timestamps, status messages, or sensor readings) without manual intervention.

**Why this priority**: This is the core functionality of the sync manager. Without automated synchronization, there's no value in the system. This enables "set it and forget it" operation.

**Independent Test**: Can be fully tested by configuring a sync interval, defining overlay text content, and verifying that the camera overlays update automatically at the specified intervals without any manual interaction.

**Acceptance Scenarios**:

1. **Given** a configuration file with sync interval of 30 seconds, **When** the sync manager starts, **Then** the overlay text is updated on the camera every 30 seconds
2. **Given** the sync manager is running with a 1-minute interval, **When** the configured overlay content changes, **Then** the new content appears on the camera within the next sync cycle
3. **Given** a sync manager configured for multiple overlays, **When** the sync cycle runs, **Then** all configured overlays are updated in the same cycle
4. **Given** the sync manager is running, **When** a sync cycle completes successfully, **Then** a success confirmation is logged with timestamp and overlay details

---

### User Story 2 - Dynamic Content Generation (Priority: P2)

As a user, I want overlay content to be dynamically generated based on templates or data sources (like current time, external sensor data, or system status), so that I can show real-time information on camera feeds.

**Why this priority**: While automated syncing is essential, the ability to show dynamic content (not just static text) makes the system practical for real-world use cases like showing timestamps, temperature readings, or system status.

**Independent Test**: Can be tested independently by configuring a template with dynamic placeholders (e.g., "{timestamp}"), running the sync manager, and verifying that the overlay shows current values that update with each sync cycle.

**Acceptance Scenarios**:

1. **Given** an overlay configured with timestamp template "{timestamp}", **When** each sync cycle runs, **Then** the camera displays the current timestamp
2. **Given** an overlay configured with multiple dynamic fields, **When** the sync executes, **Then** all placeholders are replaced with current values
3. **Given** a template with unavailable data source, **When** the sync runs, **Then** the system uses a fallback value or reports the error without stopping the sync

---

### User Story 3 - Configuration Management (Priority: P1)

As a system administrator, I want to define all sync settings in a configuration file (camera credentials, overlay IDs, sync intervals, content), so that I can manage multiple camera setups without modifying code.

**Why this priority**: Configuration-driven operation is essential for usability. This allows non-developers to deploy and manage the sync manager across different environments.

**Independent Test**: Can be fully tested by creating a configuration file with all required settings, starting the sync manager, and verifying that it operates according to the configuration without any code changes.

**Acceptance Scenarios**:

1. **Given** a configuration file with camera IP, credentials, and overlay settings, **When** the sync manager starts, **Then** it connects to the specified camera and begins syncing
2. **Given** a configuration file with multiple camera definitions, **When** the sync manager runs, **Then** it manages overlays for all configured cameras independently
3. **Given** an invalid configuration file, **When** the sync manager starts, **Then** it reports clear error messages indicating what's wrong and refuses to start
4. **Given** a configuration change is made, **When** the user restarts the sync manager, **Then** the new configuration takes effect and syncing continues with updated settings

---

### User Story 4 - Error Handling and Recovery (Priority: P2)

As a system administrator, I want the sync manager to handle network failures, authentication errors, and camera unavailability gracefully, so that temporary issues don't require manual intervention and the system recovers automatically.

**Why this priority**: Robustness is critical for an automated system that runs continuously. The ability to survive and recover from transient failures makes the difference between a production-ready tool and a prototype.

**Independent Test**: Can be tested by simulating various failure conditions (network disconnect, wrong credentials, camera reboot) and verifying that the system logs errors, retries appropriately, and resumes normal operation when conditions improve.

**Acceptance Scenarios**:

1. **Given** the sync manager is running and the camera becomes unreachable, **When** sync cycles fail, **Then** the system logs the error and retries on the next scheduled sync
2. **Given** authentication fails during a sync cycle, **When** the error occurs, **Then** the system logs the authentication failure with clear details and continues trying on subsequent cycles
3. **Given** a sync operation times out, **When** the timeout expires, **Then** the system marks the sync as failed, logs details, and proceeds to the next scheduled sync
4. **Given** the camera returns to normal operation after failures, **When** the next sync cycle runs, **Then** synchronization resumes without requiring a restart

---

### Edge Cases

- What happens when the sync interval is shorter than the time required to complete a sync cycle? (Should prevent overlapping syncs)
- How does the system handle very long overlay text that exceeds camera limits? (Should truncate and warn)
- What happens if the configuration file is deleted or becomes unreadable while the system is running?
- How does the system behave when network latency causes delays in overlay updates?
- What happens if the camera's overlay API changes or returns unexpected XML structures?
- How does the system handle timezone differences between the server running the sync manager and the camera?
- What happens when multiple sync managers are configured to update the same camera overlay?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read camera connection details (IP, port, username, password, channel) from a configuration file
- **FR-002**: System MUST read overlay synchronization settings (overlay IDs, content, sync interval) from a configuration file
- **FR-003**: System MUST support JSON configuration file format
- **FR-004**: System MUST validate the configuration file on startup and report any errors before beginning sync operations
- **FR-005**: System MUST synchronize overlay text to the specified camera at the configured interval
- **FR-006**: System MUST support multiple overlay IDs per camera (e.g., overlay 1, 2, 3, etc.)
- **FR-007**: System MUST support dynamic content templates with placeholders (e.g., timestamps, computed values)
- **FR-008**: System MUST log all sync operations with timestamp, success/failure status, and details
- **FR-009**: System MUST handle HTTP Digest authentication for camera API access (matching example_update_overlay.py behavior)
- **FR-010**: System MUST handle ISAPI XML protocol for reading and updating overlays (matching example_update_overlay.py behavior)
- **FR-011**: System MUST catch and log all errors during sync cycles without crashing the sync manager
- **FR-012**: System MUST continue attempting syncs on subsequent cycles after a failure
- **FR-013**: System MUST prevent overlapping sync cycles (new cycle should not start until previous completes)
- **FR-014**: System MUST provide a graceful shutdown mechanism (e.g., signal handling for SIGTERM/SIGINT)
- **FR-015**: System MUST support configurable timeout values for camera API requests
- **FR-016**: System SHOULD support multiple cameras in a single configuration file (each with independent sync schedules)

### Key Entities

- **Camera Configuration**: Represents connection details for a Hikvision camera including IP address, port, authentication credentials, and channel number
- **Overlay Configuration**: Represents an overlay definition including overlay ID, text content or template, position settings (if applicable), and enabled state
- **Sync Schedule**: Represents the timing configuration for synchronization including sync interval (in seconds) and last sync timestamp
- **Sync Result**: Represents the outcome of a sync operation including success/failure status, timestamp, error details (if failed), and affected overlay IDs
- **Template Context**: Represents data sources available for dynamic content generation including current timestamp, system status, and any external data sources

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sync manager successfully updates camera overlays at the configured interval with 99% reliability over a 24-hour period
- **SC-002**: Configuration validation detects and reports all common errors (missing fields, invalid credentials format, unreachable camera) before starting sync operations
- **SC-003**: System recovers automatically from transient network failures within 2 sync cycles without requiring restart or manual intervention
- **SC-004**: Dynamic timestamp content updates within the configured sync interval (e.g., 30-second interval results in overlays showing timestamps within 30 seconds of current time)
- **SC-005**: All sync operations, successes, and failures are logged with sufficient detail to diagnose issues without access to source code
- **SC-006**: System operates continuously for at least 7 days without memory leaks or degraded performance
- **SC-007**: Users can deploy and configure the sync manager for a new camera in under 5 minutes using only the configuration file

## Assumptions

- The camera hardware and firmware support the ISAPI protocol with text overlay endpoints (consistent with example_update_overlay.py)
- The sync manager will run on a server or computer with persistent network connectivity to the cameras
- Users have administrative credentials for the cameras they wish to manage
- The system clock on the server running the sync manager is accurate (for timestamp generation)
- Sync intervals will typically range from 10 seconds to several minutes (not sub-second precision)
- Configuration files will be edited manually by administrators (no GUI configuration tool in this version)

## Out of Scope

- GUI or web-based configuration interface
- Historical tracking or database storage of overlay states
- Camera discovery or auto-configuration
- Support for non-Hikvision cameras or non-ISAPI protocols
- Advanced templating with conditional logic or loops
- Multi-user access control or authentication for the sync manager itself
- Performance optimization for managing hundreds of cameras simultaneously
- Camera settings beyond overlay text (no motion detection, recording settings, etc.)

