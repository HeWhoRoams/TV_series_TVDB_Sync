# Changelog

## 2026-01-05

### Summary of Changes

1. **Fixed Dot-Separated Filename Matching**
   - Added `_normalize_filename` to convert internal dots, underscores, and hyphens to spaces while preserving extensions and decimal points.
   - This prevents dot-separated filenames from failing title extraction and triggering false-positive multi-episode matches.
2. **Improved Title Extraction**
   - Added a new regex pattern to `_extract_metadata` to handle space-separated season/episode patterns (e.g., `Show S01E01 Title`).
3. **Enhanced Matching Robustness**
   - Implemented short-token filtering in `_find_episode_by_title_in_list` to skip common short words (e.g., "du", "le", "sur") that cause spurious matches.
   - Added deduplication of matched episodes in `_match_episodes_from_titles` and `_iterative_episode_match`.

## 2025-10-28

### Summary of Changes Made Today

1. **Fixed Multi-Episode Detection Logic**
   - Completely rewrote the _iterative_episode_match method to use a greedy algorithm for multi-episode matching.
   - Improved fuzzy matching and selection of non-overlapping episode matches.
2. **Enhanced Main Matching Logic**
   - Added special case handling for complex filenames with multiple episodes.
   - Ensured multiple interpretations are considered for long input titles.
3. **Fixed Multi-Episode Naming Format**
   - Updated episode range format to use "E" separator (e.g., S01E01E02) instead of hyphen ranges.
4. **Added Test Mode Functionality**
   - New test mode (-t or --test) for automated renaming and validation in test directories.
   - Provides pass/fail results, statistics, and before/after comparisons.
5. **Improved File Processing Flow**
   - Enhanced fallback logic and robust detection of multi-episode content.
   - Better handling of filename separator formats.
6. **Code Quality Improvements**
   - Comprehensive error handling, user feedback, and color-coded console output.
   - Maintained config compatibility and command-line options.

### Other Major Changes
- Moved all series folders with videos into a `test` folder.
- Renamed main Python script to `TVDB_sync.py`.
- Restored `.gitignore` and `config.template.json` for safe config management.
- Cleaned up references to old script names.
