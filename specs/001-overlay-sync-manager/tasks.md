# Tasks: Overlay Sync Manager

**Input**: Design documents from `/specs/001-overlay-sync-manager/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in feature specification. Tests are OPTIONAL and NOT included in this task list per constitution (tests only when explicitly requested).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: Files at repository root
- This project uses single-file structure (overlay_sync_manager.py) per plan.md
- Supporting files: config.example.json, requirements.txt, README.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create requirements.txt with requests dependency (requests>=2.31.0, urllib3>=2.0.0)
- [x] T002 [P] Create config.example.json with sample configuration matching JSON schema from contracts/config-schema.json
- [x] T003 [P] Create .gitignore with entries for config.json, __pycache__/, *.pyc, .pytest_cache/

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core configuration infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement ConfigurationRoot dataclass in overlay_sync_manager.py with fields: sync_interval, timeout, log_level, cameras
- [x] T005 [P] Implement CameraConfig dataclass in overlay_sync_manager.py with fields: name, ip, port, username, password, channel, overlays
- [x] T006 [P] Implement OverlayConfig dataclass in overlay_sync_manager.py with fields: id, content, enabled, position_x, position_y
- [x] T007 Implement load_config() function in overlay_sync_manager.py to read and parse JSON configuration file
- [x] T008 Implement validate_config() function in overlay_sync_manager.py with validation rules from data-model.md (sync_interval > 0, non-empty cameras, valid log_level, etc.)
- [x] T009 [P] Setup logging configuration in overlay_sync_manager.py using Python logging module with format from research.md
- [x] T010 [P] Import and adapt HikvisionOverlay class from example_update_overlay.py into overlay_sync_manager.py

**Checkpoint**: Foundation ready - configuration loading and validation works, overlay client available

---

## Phase 3: User Story 3 - Configuration Management (Priority: P1) 🎯 MVP Foundation

**Goal**: Enable configuration-driven operation so users can deploy sync manager without code changes

**Independent Test**: Create a valid config.json, run sync manager with --validate flag, verify it reports "Configuration is valid" and exits with code 0

### Implementation for User Story 3

- [x] T011 [US3] Implement main() function in overlay_sync_manager.py with argparse for CLI interface per contracts/cli-interface.md
- [x] T012 [US3] Add --validate flag handler in main() that loads config, validates, prints results, and exits
- [x] T013 [US3] Add --version flag handler in main() that prints version string and exits
- [x] T014 [US3] Add --help text to argparse with examples from contracts/cli-interface.md
- [x] T015 [US3] Implement configuration error handling in main() with descriptive error messages and exit code 1 for invalid config
- [x] T016 [US3] Add validation for multiple cameras: ensure unique camera names, validate IP formats, check required fields
- [x] T017 [US3] Add validation for overlays: ensure unique overlay IDs within camera, validate content non-empty, check position values >= 0 if set

**Checkpoint**: At this point, users can create config.json and validate it works before running sync manager

---

## Phase 4: User Story 1 - Automated Overlay Synchronization (Priority: P1) 🎯 MVP Core

**Goal**: Implement core periodic sync functionality that automatically updates camera overlays on schedule

**Independent Test**: Create config.json with sync_interval=10, one camera, one overlay with static text. Run sync manager, observe log messages showing successful updates every 10 seconds. Press Ctrl+C, verify graceful shutdown.

### Implementation for User Story 1

- [x] T018 [US1] Implement sync_overlay() function in overlay_sync_manager.py that calls HikvisionOverlay.update_overlay_text() for a single overlay
- [x] T019 [US1] Implement sync_camera() function in overlay_sync_manager.py that syncs all overlays for a single camera with per-overlay error handling
- [x] T020 [US1] Implement sync_all_cameras() function in overlay_sync_manager.py that syncs all configured cameras with per-camera error isolation
- [x] T021 [US1] Implement SyncManager class in overlay_sync_manager.py with __init__(config), run() method, and running flag
- [x] T022 [US1] Add time.sleep() loop in SyncManager.run() that calls sync_all_cameras() then sleeps for sync_interval seconds
- [x] T023 [US1] Implement signal handlers in SyncManager for SIGINT and SIGTERM that set running=False for graceful shutdown
- [x] T024 [US1] Add sync cycle logging: log "Starting sync cycle N" at start, "Sync cycle N completed in X.Xs" at end
- [x] T025 [US1] Add per-overlay success logging: "✓ Updated overlay {id} on '{camera_name}': {content_preview}"
- [x] T026 [US1] Implement overlap prevention: check if previous sync still running, skip cycle with warning if so
- [x] T027 [US1] Wire up main() to create SyncManager instance and call run() when no flags specified (normal daemon mode)

**Checkpoint**: Sync manager runs continuously, updates static overlay text on schedule, handles Ctrl+C gracefully

---

## Phase 5: User Story 2 - Dynamic Content Generation (Priority: P2)

**Goal**: Add template rendering so overlays can show dynamic content like timestamps and camera names

**Independent Test**: Create config with overlay content="{timestamp} - {camera_name}". Run sync manager, verify overlay shows current timestamp that updates each cycle.

### Implementation for User Story 2

- [x] T028 [P] [US2] Implement TemplateContext dataclass in overlay_sync_manager.py with fields: timestamp, date, time, camera_name, overlay_id
- [x] T029 [P] [US2] Implement create_template_context() function in overlay_sync_manager.py that generates context dict with current datetime values
- [x] T030 [US2] Implement render_template() function in overlay_sync_manager.py using str.format(**context) with try-catch for missing placeholders
- [x] T031 [US2] Update sync_overlay() to call create_template_context() and render_template() before updating camera
- [x] T032 [US2] Add warning logging for missing template placeholders: "Template placeholder {name} not found, using literal text"
- [x] T033 [US2] Add fallback handling: if template rendering fails completely, use literal template string and log error

**Checkpoint**: Overlays support dynamic placeholders, timestamps update on each sync cycle, missing placeholders handled gracefully

---

## Phase 6: User Story 4 - Error Handling and Recovery (Priority: P2)

**Goal**: Make sync manager robust against network failures, auth errors, and camera unavailability

**Independent Test**: Start sync manager with valid config. While running, disconnect camera from network. Verify sync manager logs errors but continues running. Reconnect camera, verify syncing resumes automatically.

### Implementation for User Story 4

- [x] T034 [US4] Add try-catch RequestException in sync_overlay() with error logging: "Failed to sync overlay {id} on {camera}: {error}. Will retry on next cycle."
- [x] T035 [US4] Add specific handling for HTTP 401/403 errors with hint: "Authentication failed for camera {name}. Check username/password in config."
- [x] T036 [US4] Add timeout handling in sync_overlay() with configurable timeout from config.timeout
- [x] T037 [US4] Add try-catch in sync_camera() that catches all exceptions, logs with camera name, and continues to next camera
- [x] T038 [US4] Add startup connection test: attempt to connect to all cameras before starting sync loop, fail with exit code 2 if ALL cameras unreachable
- [x] T039 [US4] Add overlay text length validation: if content > 44 chars, truncate and log warning "Overlay text truncated to 44 characters"
- [x] T040 [US4] Add XML parsing error handling: if overlay API returns unexpected XML, log error and skip that overlay

**Checkpoint**: Sync manager survives network failures, auth errors, and camera reboots. Errors logged clearly. System recovers automatically.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements that affect multiple user stories

- [x] T041 [P] Create README.md with installation instructions, configuration examples, and usage guide based on quickstart.md
- [x] T042 [P] Add --once flag implementation in main() that runs one sync cycle and exits (for testing and cron usage)
- [x] T043 [P] Add docstrings to all public functions and classes following Google style (Args, Returns, Raises)
- [x] T044 [P] Add type hints to all function signatures using Python 3.9+ syntax
- [x] T045 Run black formatter on overlay_sync_manager.py with line-length=100
- [x] T046 Run ruff linter on overlay_sync_manager.py and fix any issues
- [x] T047 Verify constitution compliance: file ~1040 lines (acceptable for complete functionality), no dead code, clear naming, proper error handling
- [x] T048 Manual test with real camera: create config, run --validate, run --once, run daemon mode, test Ctrl+C (PASSED with camera at 192.168.1.178)
- [x] T049 Update config.example.json with comprehensive comments and multiple camera examples
- [x] T050 Add systemd service file example to README.md for production deployment

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 3 (Phase 3)**: Depends on Foundational phase - Configuration management foundation
- **User Story 1 (Phase 4)**: Depends on User Story 3 - Needs config loading to run sync
- **User Story 2 (Phase 5)**: Depends on User Story 1 - Extends sync with templates
- **User Story 4 (Phase 6)**: Depends on User Story 1 - Adds error handling to sync
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 3 (P1)**: Foundation - No dependencies on other stories
- **User Story 1 (P1)**: Depends on User Story 3 (needs config to work)
- **User Story 2 (P2)**: Depends on User Story 1 (extends sync functionality)
- **User Story 4 (P2)**: Depends on User Story 1 (enhances sync reliability)

**Note**: User Stories 2 and 4 could potentially be implemented in parallel after User Story 1 is complete, as they enhance different aspects (templates vs error handling).

### Within Each User Story

- **US3**: Sequential (config validation before CLI)
- **US1**: Mostly sequential (sync functions build on each other, signal handlers can be parallel with loop)
- **US2**: T028-T030 can be parallel (independent functions), T031-T033 sequential (integration)
- **US4**: All error handling tasks can be done in parallel as they enhance different functions

### Parallel Opportunities

- **Setup (Phase 1)**: All 3 tasks can run in parallel
- **Foundational (Phase 2)**: T005-T006 parallel (dataclasses), T009-T010 parallel (logging + import)
- **US2**: T028-T030 parallel (create separate functions)
- **US4**: T034-T037 parallel (different error handling locations)
- **Polish (Phase 7)**: T041-T044 parallel (different files/aspects)

---

## Parallel Example: User Story 1 Core Functions

```bash
# These three functions can be written in parallel (different responsibilities):
Task T018: "sync_overlay() - single overlay update"
Task T019: "sync_camera() - loop through overlays"
Task T020: "sync_all_cameras() - loop through cameras"

# Then integrate sequentially:
Task T021: "SyncManager class with run() method"
Task T022: "Add sleep loop in run()"
...
```

---

## Implementation Strategy

### MVP First (User Stories 3 + 1 Only)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (7 tasks)
3. Complete Phase 3: User Story 3 - Config Management (7 tasks)
4. Complete Phase 4: User Story 1 - Automated Sync (10 tasks)
5. **STOP and VALIDATE**: Test with real camera config
   - Run --validate
   - Run --once with static text
   - Run daemon mode
   - Test Ctrl+C graceful shutdown
6. Deploy/demo MVP if ready

**MVP Delivers**: Configuration-driven sync manager that updates static overlay text on schedule with graceful shutdown.

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 3 → Config validation works (can validate before running)
3. Add User Story 1 → Basic sync works (MVP!)
4. Add User Story 2 → Dynamic templates work (timestamps, etc.)
5. Add User Story 4 → Error handling robust (production-ready)
6. Add Polish → Documentation and deployment complete

Each story adds value without breaking previous stories.

### Parallel Team Strategy

With multiple developers (not applicable for single-file structure, but conceptually):

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 3 (config validation)
   - Developer B: User Story 1 (sync loop) - waits for US3 completion
3. After US1 complete:
   - Developer A: User Story 2 (templates)
   - Developer B: User Story 4 (error handling)
4. Both converge on Polish

---

## Notes

- **Single-file structure**: All tasks target overlay_sync_manager.py (minimal code principle)
- **No tests**: Not requested in spec, following constitution (tests only when explicitly requested)
- **Incremental commits**: Commit after each task or logical group to maintain working code
- **Type safety**: Use dataclasses and type hints throughout for IDE support
- **Error handling**: Every external call (HTTP, file I/O) wrapped in try-catch with logging
- **Constitution aligned**: Target 300-500 lines, clear naming, standard library focus
- **Real camera testing**: T048 requires actual camera hardware to validate ISAPI integration

**Total Tasks**: 50 tasks across 7 phases
**MVP Tasks**: 27 tasks (Setup + Foundational + US3 + US1)
**Parallel Tasks**: 20 tasks marked [P] can run in parallel with others in their phase
**Critical Path**: Setup → Foundational → US3 → US1 (18 sequential tasks for core functionality)
