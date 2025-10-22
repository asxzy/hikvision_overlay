# Exact Interval Scheduling

## Overview

The sync manager now uses **fixed-interval scheduling** that fires syncs at **exact 1-second boundaries** regardless of sync duration.

## Scheduling Strategy

### Old Approach (Wait for Completion)
```
Time: 0s        1.2s              2.2s              3.2s
      |---------|-----------------|-----------------|
      Sync 1    Wait 1s           Sync 2            Wait 1s
      (200ms)   ↓                 (200ms)           ↓
                Next at 1.2s+1s=2.2s               Next at 2.2s+1s=3.2s

Problem: Intervals drift based on sync duration
Actual intervals: 1.2s, 1.0s, 1.0s, 1.0s (inconsistent)
```

### New Approach (Fixed Intervals)
```
Time: 0s     1s        2s        3s        4s
      |------|---------|---------|---------|
      Sync 1  Sync 2    Sync 3    Sync 4
      ↓       ↓         ↓         ↓
      Scheduled at exact 1-second boundaries

Benefit: Perfect timing regardless of sync duration
Actual intervals: 1.0s, 1.0s, 1.0s, 1.0s (consistent)
```

## Key Changes

### 1. Schedule Next Sync Immediately

```python
# Old: Schedule after sync completes
sync()  # Takes 200ms
next_sync_time = time.time() + interval  # 0.2s + 1s = 1.2s

# New: Schedule before sync starts
cycle_start = time.time()  # 0s
next_sync_time = cycle_start + interval  # 0s + 1s = 1.0s
sync()  # Takes 200ms (doesn't affect schedule)
```

### 2. Handle Slow Syncs Gracefully

**If sync takes longer than interval:**

```
Interval: 1.0s
Sync duration: 1.2s

Old behavior:
  → Next cycle in -0.2s (negative!)
  → Start immediately (confusing)

New behavior:
  → Warning: "Sync exceeded interval by 0.2s"
  → Next cycle still fires at exact 2.0s boundary
  → Predictable timing
```

### 3. Overlap Detection (Non-Blocking)

**If previous sync still running:**

```
Time: 0s              1s              2s
      |---------------|---------------|
      Sync 1          Sync 2          Sync 3
      (still running) ← Skip         ← Will start
                      ↓
                      Warning logged
                      Continue to next boundary
```

## Example Scenarios

### Scenario 1: Fast Syncs (100ms)

```
Config: sync_interval = 1

Timeline:
0.000s: Sync 1 starts
0.100s: Sync 1 completes
1.000s: Sync 2 starts  ← Exactly 1s after Sync 1
1.100s: Sync 2 completes
2.000s: Sync 3 starts  ← Exactly 1s after Sync 2

Result: Perfect 1-second intervals ✅
```

### Scenario 2: Slow Sync (1.2s)

```
Config: sync_interval = 1

Timeline:
0.000s: Sync 1 starts
1.000s: Sync 2 scheduled (but Sync 1 still running)
1.000s: Warning: "Previous sync still in progress"
1.200s: Sync 1 completes
2.000s: Sync 2 starts  ← Exactly 2s after Sync 1 started
3.000s: Sync 3 starts  ← Exactly 1s after Sync 2 started

Result: Skipped one cycle, but timing remains exact ✅
```

### Scenario 3: Variable Sync Times

```
Config: sync_interval = 1

Timeline:
0.000s: Sync 1 starts (takes 0.5s)
0.500s: Sync 1 completes
1.000s: Sync 2 starts (takes 0.2s)  ← Exactly 1s
1.200s: Sync 2 completes
2.000s: Sync 3 starts (takes 0.8s)  ← Exactly 1s
2.800s: Sync 3 completes
3.000s: Sync 4 starts               ← Exactly 1s

Result: Intervals always 1.0s regardless of sync duration ✅
```

## Log Output Examples

### Normal Operation
```
2025-10-22 10:00:00.000 [INFO] Starting sync cycle 1
2025-10-22 10:00:00.095 [INFO] ✓ Updated overlay 1 on 'Back': "..." (95ms)
2025-10-22 10:00:00.095 [INFO] Sync cycle 1 completed in 0.095s. Success: 1, Failed: 0. Next cycle in 0.905s.

2025-10-22 10:00:01.000 [INFO] Starting sync cycle 2
2025-10-22 10:00:01.087 [INFO] ✓ Updated overlay 1 on 'Back': "..." (87ms)
2025-10-22 10:00:01.087 [INFO] Sync cycle 2 completed in 0.087s. Success: 1, Failed: 0. Next cycle in 0.913s.
```

Notice: Cycles start at exactly 0.000s and 1.000s

### Slow Sync Warning
```
2025-10-22 10:00:00.000 [INFO] Starting sync cycle 1
2025-10-22 10:00:01.200 [INFO] ✓ Updated overlay 1 on 'Back': "..." (1200ms)
2025-10-22 10:00:01.200 [WARNING] Sync cycle 1 completed in 1.200s (exceeded interval of 1.0s by 0.200s). Success: 1, Failed: 0.

2025-10-22 10:00:02.000 [INFO] Starting sync cycle 2
```

Notice: Despite 1.2s sync, cycle 2 still starts at exactly 2.000s

### Overlap Detection
```
2025-10-22 10:00:00.000 [INFO] Starting sync cycle 1
2025-10-22 10:00:01.000 [WARNING] Sync cycle 2: Previous sync still in progress (running in background). Consider increasing sync_interval or timeout.
2025-10-22 10:00:01.200 [INFO] Sync cycle 1 completed in 1.200s (exceeded interval of 1.0s by 0.200s). Success: 1, Failed: 0.
2025-10-22 10:00:02.000 [INFO] Starting sync cycle 2
```

Notice: Cycle 2 was skipped, but cycle 3 starts on schedule

## Benefits

### 1. Predictable Timing ⏰
- Syncs fire at **exact second boundaries**
- No drift or accumulation errors
- Easy to correlate with wall clock

### 2. Timestamp Consistency 🕒
```
Overlay content: "{timestamp}"

With exact intervals:
10:00:00 → "2025-10-22 10:00:00"
10:00:01 → "2025-10-22 10:00:01"
10:00:02 → "2025-10-22 10:00:02"

Perfect alignment with actual time!
```

### 3. Graceful Degradation 📉
```
If sync takes 1.2s with 1s interval:
- Old: Panics with negative times
- New: Skips one cycle, continues normally
```

### 4. Overlapping Sync Detection 🔍
```
If camera is slow:
- Detects overlap
- Logs warning
- Skips cycle (doesn't pile up)
- Maintains schedule
```

## Configuration Guidelines

### For 1-Second Intervals
```json
{
  "sync_interval": 1,
  "timeout": 3  // Allow 3s for completion (3x interval)
}
```

**Expectation**: Sync completes in <1s, next starts at exactly 1s

### For Sub-Second Intervals
```json
{
  "sync_interval": 0.5,
  "timeout": 2  // 4x interval for safety
}
```

**Warning**: Requires very fast cameras and network

### For Variable Network Conditions
```json
{
  "sync_interval": 2,
  "timeout": 5  // 2.5x interval
}
```

**Benefit**: More tolerance for slow syncs

## Monitoring

### Watch for These Warnings

#### 1. Exceeded Interval
```
Sync cycle 3 completed in 1.200s (exceeded interval of 1.0s by 0.200s)
```

**Action**:
- Increase `sync_interval` to 2s, or
- Reduce `timeout` to fail faster, or
- Check network/camera performance

#### 2. Previous Sync in Progress
```
Sync cycle 5: Previous sync still in progress (running in background)
```

**Action**:
- Increase `sync_interval` significantly
- Camera cannot keep up with current rate

## Performance Implications

### CPU Usage
- **Same**: Fixed intervals don't change CPU load
- Still async/concurrent for multiple cameras

### Network Load
- **Same**: Same number of HTTP requests
- Just better timing control

### Memory
- **Same**: No additional memory overhead
- Single sync in flight at a time

## Edge Cases

### Case 1: Very Slow Camera
```
Interval: 1s
Camera A: 100ms
Camera B: 5s (very slow)

Behavior:
- Camera A completes quickly
- Camera B takes 5s
- Next 4 cycles skipped (warnings logged)
- Cycle 6 starts normally

Solution: Increase interval or check Camera B
```

### Case 2: Intermittent Failures
```
Interval: 1s
Sync 1: 100ms ✅
Sync 2: Timeout (5s) ❌
Sync 3: Skipped (overlap)
Sync 4: 100ms ✅

Behavior:
- System recovers automatically
- Schedule maintained
```

### Case 3: All Cameras Slow
```
If ALL cameras exceed interval:
- Every cycle shows warning
- System still functions
- Just slower than configured

This is EXPECTED behavior - not a bug!
```

## Comparison with Other Approaches

### Approach 1: Fire and Forget (Ours) ✅
```
Pro: Exact intervals, predictable
Con: May skip cycles if too slow
Best for: Time-critical overlays (clocks, timestamps)
```

### Approach 2: Wait for Completion
```
Pro: Never skips cycles
Con: Intervals drift with sync time
Best for: Non-time-critical updates
```

### Approach 3: Parallel Overlapping
```
Pro: Maximum throughput
Con: Can overwhelm camera/network
Best for: Very fast hardware only
```

## Summary

✅ **Exact 1-second intervals** (no drift)
✅ **Handles slow syncs gracefully** (skip + warn)
✅ **Detects overlaps** (prevents pile-up)
✅ **Predictable timestamps** (aligned to wall clock)
✅ **Clear logging** (shows actual vs expected)

**Perfect for overlay updates that need consistent timing!** ⏱️
