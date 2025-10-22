# Implementation Plan: Overlay Sync Manager

**Branch**: `001-overlay-sync-manager` | **Date**: 2025-10-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-overlay-sync-manager/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an automated overlay synchronization manager that periodically updates Hikvision camera text overlays based on JSON configuration. The system will follow the proven logic from `example_update_overlay.py`, adding scheduled execution, configuration management, dynamic content templates, and robust error handling for continuous operation.

## Technical Context

**Language/Version**: Python 3.9+ (for compatibility with standard library features: json, dataclasses, pathlib)
**Primary Dependencies**: `requests` library (already used in example_update_overlay.py for HTTP Digest auth and ISAPI communication)
**Storage**: JSON configuration file (read-only), no persistent state storage required
**Testing**: pytest (when tests explicitly requested per constitution)
**Target Platform**: Linux/macOS/Windows server with Python runtime and network access to cameras
**Project Type**: Single project (command-line daemon/service)
**Performance Goals**: Support 10-50 cameras with sync intervals of 10-60 seconds without CPU/memory issues
**Constraints**:
- Must operate continuously for 7+ days without memory leaks
- Sync operations must complete within configured interval to prevent queue buildup
- Must handle network latency gracefully (timeouts configurable)
**Scale/Scope**:
- Single-file or small module structure (following minimal code principle)
- 300-500 lines of core logic (excluding tests and example code)
- Support for 1-50 cameras in single configuration file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Minimal Code ✅
- **Dependencies**: Only `requests` library (justified: HTTP Digest auth + XML handling not trivial in stdlib)
- **Standard Library First**: Using `json`, `time`, `signal`, `pathlib`, `dataclasses`, `logging` from stdlib
- **No Premature Abstraction**: Building on proven `example_update_overlay.py` code, adding only required sync features
- **Status**: PASS - Minimal external dependencies, reusing existing battle-tested code

### II. Readability First ✅
- **Clear Names**: `SyncManager`, `CameraConfig`, `OverlayConfig`, `sync_overlay()`, etc.
- **Single Responsibility**: Separate functions for config loading, template rendering, sync execution, scheduling
- **Function Length**: Target <50 lines per function (constitution guideline)
- **Docstrings Required**: All public functions/classes with Args/Returns
- **Type Hints Required**: All function signatures
- **Status**: PASS - Following readability standards

### III. Standard Python Patterns ✅
- **PEP 8**: Required via constitution (black formatter)
- **Standard Patterns**: Using dataclasses for config, context managers for file I/O, signal handlers for graceful shutdown
- **No Custom Frameworks**: Pure Python with standard scheduling approach
- **Status**: PASS - Following Pythonic idioms

### IV. Simple Error Handling ✅
- **Fail Fast**: Configuration validation on startup (FR-004)
- **Descriptive Errors**: Context in all error messages (what/why/how to fix)
- **Specific Exceptions**: Catching `requests.RequestException`, `json.JSONDecodeError`, etc.
- **Logging to stderr**: All errors logged with context
- **No Silent Failures**: All exceptions logged and handled explicitly
- **Status**: PASS - Error handling follows constitution

### V. Incremental Development ✅
- **Working Code**: Each commit must run successfully
- **Small Commits**: Frequent commits of working increments
- **Meaningful Messages**: Explain "why" in commit messages
- **No Dead Code**: No commented-out code or undocumented TODOs
- **Status**: PASS - Development workflow aligned

### Overall Gate Status: ✅ PASS

**No constitution violations**. All principles followed. No complexity tracking required.

---

### Post-Design Re-Evaluation (Phase 1 Complete)

**Date**: 2025-10-21

All design artifacts have been generated (research.md, data-model.md, contracts/, quickstart.md). Re-evaluating constitution compliance:

**I. Minimal Code** ✅
- Research confirmed: Only `requests` dependency, all other stdlib
- Single-file structure chosen (overlay_sync_manager.py ~400 lines)
- No additional complexity introduced
- **Status**: STILL PASS

**II. Readability First** ✅
- Data model uses dataclasses (clear, typed)
- CLI interface follows argparse patterns (standard, readable)
- Clear naming throughout design docs
- **Status**: STILL PASS

**III. Standard Python Patterns** ✅
- JSON config (stdlib json module)
- Dataclasses for config objects (stdlib)
- Signal handling for graceful shutdown (stdlib)
- **Status**: STILL PASS

**IV. Simple Error Handling** ✅
- Per-camera error isolation confirmed
- Validation on startup (fail-fast)
- All error messages include context
- **Status**: STILL PASS

**V. Incremental Development** ✅
- Design supports small commits
- Clear phases: config → validation → single sync → daemon loop
- Each phase testable independently
- **Status**: STILL PASS

**Final Gate Status**: ✅ **ALL CHECKS PASS** - Ready for implementation (Phase 2: Tasks)

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
# Single project structure (following minimal code principle)
.
├── example_update_overlay.py          # Existing reference implementation
├── overlay_sync_manager.py            # New: Main sync manager (CLI + daemon)
├── config.example.json                # New: Example configuration file
├── requirements.txt                   # New: Python dependencies (requests only)
├── README.md                          # New: Installation and usage docs
│
└── tests/                             # Optional: Only if tests explicitly requested
    ├── test_config_loading.py         # Config validation tests
    ├── test_template_rendering.py     # Dynamic content tests
    └── test_sync_operations.py        # Integration tests with mock camera
```

**Structure Decision**:

Following the **Minimal Code** principle from the constitution, this feature uses a **single-file structure** for the sync manager. Rationale:

1. **Simplicity**: All sync logic in one file (`overlay_sync_manager.py`) keeps it easy to understand and maintain
2. **Reuse**: Leverages existing `example_update_overlay.py` code and patterns (HikvisionOverlay class can be imported or adapted)
3. **Minimal Hierarchy**: No deep directory nesting - flat structure at repository root
4. **Clear Separation**: Original example code preserved, new sync manager is standalone
5. **Constitution Aligned**: Target 300-500 lines keeps file under 500-line limit

The sync manager will be executable as both:
- **CLI**: `python overlay_sync_manager.py config.json` (starts daemon)
- **Service**: Can be wrapped in systemd/launchd/Windows Service

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations** - No complexity tracking required. All constitution principles followed.

