# Async/Concurrent Implementation

## Overview

The overlay sync manager now uses **async/await** with `httpx` for truly concurrent camera updates. Multiple cameras no longer block each other.

## Key Changes

### 1. Async HTTP Client (`httpx`)

**Why httpx instead of aiohttp?**
- ✅ Built-in HTTP Digest Auth support (Hikvision requirement)
- ✅ Similar API to requests (easy migration)
- ✅ Excellent connection pooling
- ✅ Automatic retry handling

```python
import httpx

async with httpx.AsyncClient(
    auth=httpx.DigestAuth(username, password),
    verify=False,
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
) as client:
    response = await client.put(url, content=data)
```

### 2. Concurrent Camera Syncing

**Before (Sequential)**:
```python
for camera in cameras:
    sync_camera(camera)  # Blocks until complete
    # Camera 1: 100ms
    # Camera 2: 100ms (waits for Camera 1)
    # Camera 3: 100ms (waits for Camera 2)
    # Total: 300ms
```

**After (Concurrent)**:
```python
tasks = [sync_camera_async(cam) for cam in cameras]
results = await asyncio.gather(*tasks)
    # Camera 1: 100ms ┐
    # Camera 2: 100ms ├─ All run simultaneously
    # Camera 3: 100ms ┘
    # Total: 100ms (fastest = slowest camera)
```

### 3. Per-Camera Overlay Concurrency

Within each camera, all overlays update concurrently:

```python
tasks = [sync_overlay_async(client, camera, overlay, timeout)
         for overlay in camera.overlays]
results = await asyncio.gather(*tasks)
```

**Benefit**: Camera with 4 overlays = 100ms (not 400ms)

---

## Performance Comparison

### Single Camera (1 overlay)
- **Sequential**: ~100-150ms
- **Async**: ~100-150ms
- **Improvement**: No change (only 1 operation)

### Multiple Cameras (3 cameras, 1 overlay each)
- **Sequential**: ~300-450ms (sum of all)
- **Async**: ~100-150ms (max of all)
- **Improvement**: **3x faster** ⚡

### Multiple Cameras with Multiple Overlays (3 cameras, 4 overlays each)
- **Sequential**: ~1200ms (3 × 4 × 100ms)
- **Async**: ~100-150ms (all concurrent)
- **Improvement**: **12x faster** 🚀

---

## HTTP Digest Auth Flow

### Understanding 401 Responses

When you see logs like:
```
[INFO] HTTP Request: PUT .../text/1 "HTTP/1.1 401 Unauthorized"
[INFO] HTTP Request: PUT .../text/1 "HTTP/1.1 200 OK"
```

This is **NORMAL**. It's the HTTP Digest Auth handshake:

1. **Request 1**: Client → Server (no auth)
2. **Response 1**: Server → Client (`401` + challenge nonce)
3. **Request 2**: Client → Server (with digest hash)
4. **Response 2**: Server → Client (`200 OK`)

The `httpx` library automatically handles this, so you see both requests in logs.

### Reducing Log Noise

```python
# In setup_logging()
logging.getLogger("httpx").setLevel(logging.WARNING)
```

Now you'll only see actual errors, not auth challenges.

---

## Runtime Metrics

Each camera update now shows timing:

```
✓ Updated overlay 1 on 'Back': "177 - 2025-10-22 10:58:10" (95ms)
✗ Failed to update overlay 1 on 'Back East' (1023ms)
```

This helps identify:
- Slow cameras (network issues)
- Timeout problems
- Performance bottlenecks

---

## Handling Slow Syncs

### Negative "Next Cycle" Warning

When sync takes longer than interval:

```
Sync cycle 3 completed in 1.023s.
Sync took 0.023s longer than interval (1.0s).
Starting next cycle immediately.
```

**Solution**: Increase `sync_interval` or reduce `timeout`:

```json
{
  "sync_interval": 2,  // Increase if syncs take >1s
  "timeout": 3         // Reduce to fail fast
}
```

---

## Dependencies

### Updated requirements.txt

```
requests>=2.31.0      # Sync fallback & connection test
urllib3>=2.0.0        # SSL warnings suppression
httpx>=0.27.0         # Async HTTP with digest auth
```

---

## Code Structure

### Async Functions

```python
async def sync_overlay_async(client, camera_name, overlay, timeout)
    → Single overlay update (with timing)

async def sync_camera_async(camera, timeout)
    → All overlays for one camera (concurrent)
    → Creates async client context

async def sync_all_cameras_async(config)
    → All cameras (concurrent)
    → Returns aggregated results
```

### Integration with SyncManager

```python
class SyncManager:
    def run(self):
        while self.running:
            # Run async sync in sync context
            results = asyncio.run(sync_all_cameras_async(self.config))
```

---

## Best Practices

### 1. Use Async for Multiple Cameras
```json
{
  "cameras": [
    {"name": "front", ...},
    {"name": "back", ...},    // All sync concurrently
    {"name": "side", ...}
  ]
}
```

### 2. Set Appropriate Timeouts
```json
{
  "sync_interval": 2,
  "timeout": 3    // Should be < sync_interval
}
```

### 3. Monitor Per-Camera Timing
Look for slow cameras in logs:
```
✓ Updated ... (95ms)   ← Fast
✓ Updated ... (850ms)  ← Slow (investigate)
✗ Failed ... (1023ms)  ← Timeout
```

### 4. Adjust for Network Conditions
- **LAN**: `sync_interval: 1, timeout: 3`
- **WiFi**: `sync_interval: 2, timeout: 5`
- **Remote**: `sync_interval: 5, timeout: 10`

---

## Troubleshooting

### All Updates Fail with 401

**Problem**: Wrong credentials
**Solution**: Check `username` and `password` in config

### Frequent Timeouts

**Problem**: Network latency or busy camera
**Solution**:
1. Increase `timeout`
2. Increase `sync_interval`
3. Check camera CPU usage

### Sync Takes Longer Than Interval

**Symptom**:
```
Sync took 0.5s longer than interval (1.0s)
```

**Solution**:
1. Increase `sync_interval` to 2s
2. Reduce number of overlays
3. Check for network issues

---

## Performance Tuning

### Connection Limits

```python
httpx.Limits(
    max_connections=10,           # Total concurrent connections
    max_keepalive_connections=5   # Pooled idle connections
)
```

**Tuning**:
- **Few cameras (<5)**: Default is fine
- **Many cameras (10+)**: Increase limits

```python
httpx.Limits(max_connections=20, max_keepalive_connections=10)
```

### Timeout Strategy

```json
{
  "timeout": 5,  // Per-request timeout
}
```

**Balance**:
- **Too low**: Frequent failures
- **Too high**: Blocks other cameras
- **Optimal**: 2-5 seconds for LAN

---

## Migration Notes

### From Sync to Async

The sync manager automatically uses async for better performance. No config changes needed!

**Sync functions still exist** for:
- `--validate` mode (connection test)
- `--once` mode fallback
- Backwards compatibility

### Hybrid Approach

```python
# Connection test: Sync (simple)
if test_camera_connection(camera):
    ...

# Main loop: Async (concurrent)
results = asyncio.run(sync_all_cameras_async(config))
```

---

## Future Optimizations

### 1. Persistent Event Loop
Instead of `asyncio.run()` per cycle, use persistent loop:

```python
async def run_async(self):
    while self.running:
        await sync_all_cameras_async(self.config)
        await asyncio.sleep(self.config.sync_interval)
```

### 2. Connection Pooling Across Cycles
Reuse httpx clients instead of recreating:

```python
self.clients = {
    cam.name: httpx.AsyncClient(...)
    for cam in cameras
}
```

### 3. Batch API Support
If Hikvision adds batch endpoints:

```python
await client.put("/overlays/batch", data=all_overlays)
```

---

## Summary

✅ **Concurrent camera updates** (no blocking)
✅ **Per-camera timing metrics** (identify slow cameras)
✅ **Proper digest auth handling** (httpx)
✅ **Graceful overrun handling** (negative time warnings)
✅ **Connection pooling** (keep-alive)
✅ **Clean error handling** (per-camera isolation)

**Result**: 3-12x faster for multiple cameras! 🚀
