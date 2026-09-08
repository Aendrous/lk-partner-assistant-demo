# Debug Artifacts Migration (2026-09-08)

## Summary
Moved all debug/probe JSON and TXT files from project root to `debug/` folder for cleaner repository structure.

## Changes Made

### New Module: `src/debug_artifacts.py`
Centralized path management for all debug artifacts:
- `ensure_debug_dir()` - creates debug/ folder
- `analysis_path(task_id)` - new path: `debug/_analysis_{id}.json`
- `analysis_summary_path(task_id)` - new path: `debug/_analysis_{id}_summary.json`
- `legacy_analysis_path(task_id)` - old root path (for reference)
- `find_analysis(task_id)` - searches debug/ first, then root (legacy), then pipeline/runs/
- `debug_file_path(filename)` - general debug file path helper

### Updated Modules

#### `src/analysis_artifact.py`
- Now imports `debug_artifacts`
- `load_analysis()` uses `find_analysis()` for backward-compatible reading
- Searches: debug/ → root (legacy) → pipeline/runs/{run_id}/

#### `scripts/analyze_and_comment.py`
- Imports `debug_artifacts`
- All write operations (5 locations) now use `debug_artifacts.analysis_path()`
- Lines updated: ~887, ~906, ~945, ~975, ~1733, ~1798

#### `src/kb_learning.py`
- Removed duplicate `ANALYSIS_GLOB` constant and `analysis_path()` function
- Now imports and delegates to `debug_artifacts`
- `load_analysis()` uses `find_analysis()` for backward compatibility

#### `app.py`
- Fixed to use `analysis_mod.load_analysis()` which returns the parsed dict
- Removed broken file-path logic (was referencing undefined `analysis_path`)

#### `.gitignore`
- Added `debug/` folder to ignore list

## Files Moved
- **61** `_analysis_*.json` files (разборы заявок)
- **22** other `_*.json` probe/debug files
- **13** `_*.txt` debug/log files
- **Total: 96 files** moved from root to `debug/`

## Backward Compatibility
All reading functions maintain backward compatibility:
1. First check `debug/_analysis_{id}.json` (new location)
2. Then check `_analysis_{id}.json` in root (legacy)
3. Then check `pipeline/runs/{run_id}/_analysis_{id}.json` (pipeline artifacts)

This ensures:
- Old artifacts in root still readable
- Pipeline artifacts still accessible
- New artifacts written to clean debug/ folder

## Testing
✅ Python syntax check: all files compile successfully
✅ Path resolution: `find_analysis()` correctly finds moved files
✅ Load function: `load_analysis()` successfully reads from debug/
✅ Streamlit app: uses correct module functions

## Next Steps (Optional)
Consider:
1. Extend `debug_file_path()` usage to other probe files if needed
2. Add cleanup script to archive old debug artifacts
3. Update any external documentation referencing old paths
