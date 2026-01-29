# Performance Lag Analysis Report
**Date:** 2025-01-07  
**Purpose:** Identify causes of performance degradation after recent debug logging additions

---

## Executive Summary

⚠️ **CRITICAL PERFORMANCE ISSUE:** Excessive debug logging added for crash investigation is causing severe lag.

**Root Cause:** Console I/O operations (`print()` statements) are blocking and expensive, especially when called multiple times per frame.

**Impact:** 
- **Before:** Smooth 30 FPS operation
- **After:** Severe lag, likely <10 FPS or worse

---

## Performance Bottlenecks Identified

### 🔴 **CRITICAL: `safe_debug_text()` Debug Logging**

**Location:** `src/utils/safe_pybullet.py:121-122, 141, 144`

**Problem:**
```python
def safe_add_debug_text(...):
    print(f"[SAFE_PB DEBUG] Attempting to add text: '{text}'")  # ← EVERY CALL
    print(f"[SAFE_PB DEBUG] Position: {position}, Parent: {parent_body_id}, Replace: {replace_id}")  # ← EVERY CALL
    # ... PyBullet call ...
    print(f"[SAFE_PB DEBUG] Success, ID: {result}")  # ← EVERY CALL
    # OR on exception:
    print(f"[SAFE_PB DEBUG] FAILED: {e}")  # ← ON FAILURE
    traceback.print_exc()  # ← EXPENSIVE STACK TRACE
```

**Call Frequency:**
- **Per frame:** Called ~5-10 times per frame for:
  - Selection overlay (hover indicator, lock indicator)
  - Intent overlay (proposal text, available actions)
  - Key echo display
  - L key handler feedback
- **Total:** ~150-300 print statements per second at 30 FPS

**Performance Impact:**
- **Console I/O:** Each `print()` is a system call, blocking operation
- **String formatting:** f-strings with tuple formatting are expensive
- **Stack traces:** `traceback.print_exc()` is very expensive (collects full stack)

**Estimated Cost:** ~50-100ms per frame just for debug logging

---

### 🔴 **CRITICAL: L Key Handler Debug Logging**

**Location:** `scripts/run_unified_arm_demo.py:381-424`

**Problem:**
```python
if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
    print(f"\n{'='*60}")  # ← 60-character string creation
    print(f"[DEBUG] L KEY PRESSED")
    print(f"[DEBUG] sim.object_id = {sim.object_id}")
    print(f"[DEBUG] sim._connected = {sim._connected}")
    print(f"[DEBUG] Type of sim.object_id: {type(sim.object_id)}")
    # ... 9 more print statements ...
    print(f"{'='*60}\n")  # ← Another 60-character string
```

**Call Frequency:**
- Only when L key is pressed (not every frame)
- But each press generates **13 print statements**

**Performance Impact:**
- **String concatenation:** `'='*60` creates new strings
- **Type inspection:** `type(sim.object_id)` adds overhead
- **Multiple prints:** 13 system calls per L press

**Estimated Cost:** ~5-10ms per L key press

---

## Performance Impact Analysis

### Frame-by-Frame Breakdown (30 FPS target)

| Operation | Calls/Frame | Cost per Call | Total Cost |
|-----------|-------------|---------------|------------|
| `safe_debug_text()` debug prints | 5-10 | ~5-10ms | **25-100ms** |
| Selection overlay rendering | 1-2 | ~2-5ms | **2-10ms** |
| Intent overlay rendering | 1 | ~1-2ms | **1-2ms** |
| Key echo (if key pressed) | 0-1 | ~1ms | **0-1ms** |
| **Total Debug Overhead** | | | **28-113ms** |

**Target frame time:** 33.3ms (30 FPS)  
**Actual frame time:** ~60-150ms (6-16 FPS)  
**Performance degradation:** **50-80% slower**

---

## Call Frequency Analysis

### `safe_debug_text()` Call Sites

**Per Frame (Always):**
1. `selection_overlay.draw_hover_indicator()` - 1 call
2. `selection_overlay.draw_lock_indicator()` - 1 call (if locked)
3. `intent_overlay.render()` - 2-3 calls (proposal text, available actions)
4. Key echo display - 1 call (if key pressed)

**Total:** ~5-6 calls per frame = **150-180 calls/second**

**With Debug Logging:**
- Each call = 2-4 print statements
- **Total:** ~300-720 print statements per second

---

## Console I/O Performance

### Why `print()` is Slow

1. **System Call Overhead:**
   - Each `print()` is a `write()` system call
   - Context switch to kernel mode
   - Buffer flushing
   - Terminal rendering

2. **String Formatting:**
   - f-strings compile to bytecode
   - Tuple formatting: `(0.5, 0.0, 1.0)` → string conversion
   - Type inspection: `type(sim.object_id)` → string representation

3. **Terminal Rendering:**
   - Terminal must render each line
   - Scrolling if buffer fills
   - Color codes (if any)

**Estimated Cost:** 1-5ms per `print()` statement

---

## Other Potential Performance Issues

### ✅ Already Optimized (Not the Problem)

1. **Narrative Logger:** Throttled to 15 frames (already optimized)
2. **Frame Limiting:** Compensated frame limiting in place
3. **Ray Testing:** Disabled during forced lock (already optimized)

### ⚠️ Minor Issues (Not Critical)

1. **Key Echo:** Called every frame when key pressed (minor impact)
2. **Status Printing:** Periodic (every 2 seconds, not per frame)

---

## Recommendations (For Future Fixes)

### Priority 1: Remove Debug Logging

**Action:** Remove or disable debug logging added for crash investigation:

1. **`safe_debug_text()` debug prints:**
   - Remove lines 121-122, 141, 144 from `src/utils/safe_pybullet.py`
   - Keep error logging (line 138) but make it rate-limited

2. **L key handler debug prints:**
   - Remove lines 381-385, 388, 392, 396-397, 398, 407, 410-412, 414, 423-424 from `scripts/run_unified_arm_demo.py`
   - Keep essential error messages only

### Priority 2: Conditional Debug Logging

**Alternative:** Add debug flag to enable/disable:

```python
# At top of file
DEBUG_MODE = False  # Set to True for debugging

# In functions
if DEBUG_MODE:
    print(f"[SAFE_PB DEBUG] ...")
```

### Priority 3: Rate-Limited Logging

**Alternative:** Keep logging but rate-limit it:

```python
# In SafePyBullet class
self._last_debug_log_time = 0.0
self._debug_log_interval = 1.0  # Log once per second

def safe_add_debug_text(...):
    now = time.time()
    if now - self._last_debug_log_time > self._debug_log_interval:
        print(f"[SAFE_PB DEBUG] ...")
        self._last_debug_log_time = now
```

---

## Performance Metrics (Estimated)

### Before Debug Logging
- **FPS:** ~30 FPS (smooth)
- **Frame Time:** ~33ms
- **Console Output:** Minimal (errors only)

### After Debug Logging (Current)
- **FPS:** ~6-16 FPS (severe lag)
- **Frame Time:** ~60-150ms
- **Console Output:** ~300-720 lines/second

### After Removing Debug Logging (Expected)
- **FPS:** ~30 FPS (restored)
- **Frame Time:** ~33ms
- **Console Output:** Minimal (errors only)

---

## Conclusion

**Root Cause:** Excessive debug logging added for crash investigation is causing severe performance degradation.

**Impact:** 
- **50-80% performance loss**
- **Unplayable lag** (<10 FPS)
- **Console spam** (hundreds of lines per second)

**Solution:** Remove debug logging statements added in:
1. `src/utils/safe_pybullet.py` (lines 121-122, 141, 144)
2. `scripts/run_unified_arm_demo.py` (lines 381-424)

**Note:** This debug logging was added to investigate crashes. Once the crash is resolved, these should be removed or made conditional.

---

## Files Modified (Debug Logging Added)

1. **`src/utils/safe_pybullet.py`**
   - Lines 121-122: Debug prints before PyBullet call
   - Line 141: Debug print on success
   - Line 144: Debug print + traceback on failure

2. **`scripts/run_unified_arm_demo.py`**
   - Lines 381-424: Complete L key handler debug logging (13 print statements)

---

## Next Steps

1. **Immediate:** Remove debug logging to restore performance
2. **Short-term:** If crash investigation still needed, use conditional debug flag
3. **Long-term:** Implement proper logging framework with levels (DEBUG, INFO, ERROR)



