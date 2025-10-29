# TVDB_sync.py - TV Series Renamer & Sync Tool

This Python script helps you rename and organize TV series files to match TVDB standards, ensuring correct import into Sonarr and other media managers.

## Key Features
- Parses media files for show name, season, episode, and title
- Uses TVDB API for series and episode matching
- Fuzzy matching logic for episode titles
- Automated and manual renaming options
- **Test mode** for validating renaming logic in a controlled environment

## Recent Major Changes (2025-10-28)
- Script renamed to `TVDB_sync.py`
- All references to the old name have been cleaned up
- Series folders moved to `test/` directory
- Added `CHANGELOG.md` for tracking updates
- Restored `.gitignore` and `config.template.json` for safe config management
- Multi-episode detection and naming logic improved
- Enhanced file processing and error handling
- Test mode added for automated validation

See `CHANGELOG.md` for a detailed summary of today's changes and improvements.

---

## Quick Start

1. **Install Python 3.6+**
   - [Download Python](https://www.python.org/downloads/) and install (check "Add Python to PATH").
2. **Install Git (optional)**
   - [Download Git](https://git-scm.com/downloads) and install.
3. **Clone the Repository**
   ```sh
   git clone https://github.com/HeWhoRoams/TV_series_TVDB_Sync.git
   cd TV_series_TVDB_Sync
   ```
4. **Install Dependencies**
   ```sh
   pip install tvdb_v4_official fuzzywuzzy colorama
   ```
5. **Configure the Script**
   - Copy `config.template.json` to `config.json` and add your TVDB API key.
6. **Run the Script**
   ```sh
   python TVDB_sync.py
   ```
   - Use test mode for automated validation: `python TVDB_sync.py --test`

---

## Troubleshooting
- If you see `ModuleNotFoundError`, run `pip install tvdb_v4_official fuzzywuzzy colorama`.
- For permission errors, run as administrator or use `sudo` on Linux.
- For help, open an issue on GitHub.

## Contributing
Contributions are welcome! Fork the repo and submit a pull request.

---

## Test Mode

To run the script in test mode:

    python TVDB_sync.py -t

### What test mode does:
1. Processes predefined test directories—looks for subdirectories named after TV shows
2. Automatically renames files without asking for confirmation
3. Validates against expected output—checks if renamed files match expected format
4. Shows pass/fail results with success rate statistics
5. Prompts to revert—asks if you want to restore original filenames after testing

### Required setup:
Create test directories in your root folder named after shows (e.g., Rosie's Rules, Daniel Tiger's Neighborhood) with improperly named files inside.

#### Example:
- Input: Abuela_s Birthday_Cat Mail.mp4
- Expected: Rosie's Rules - S01E01E02 - Abuela's Birthday + Cat Mail.mp4
- Test mode validates the rename matches this format

After running, you'll see a summary showing how many tests passed vs failed, and you can choose to revert all changes back to original filenames.

For full details, see the [CHANGELOG.md](CHANGELOG.md).
