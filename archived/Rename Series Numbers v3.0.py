import os
import re
import json
import tvdb_v4_official
import pathlib
from fuzzywuzzy import fuzz
from colorama import Fore, Style, init
import logging

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(filename='rename.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION AND INITIALIZATION ---
try:
    with open(r"C:\Tools\Rename Series\config.json", "r") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    print(f"Config file not found. Please create it.")
    logging.error(f"Config file not found. Exiting.")
    exit(1)

API_KEY = config.get("api_key")
if not API_KEY:
    print("API key is missing in the config file.")
    logging.error("API key is missing in config.json. Exiting.")
    exit(1)

QUALITY_TAGS = config.get("quality_tags", [])
VALID_VIDEO_EXTENSIONS = set(config.get("valid_extensions", []))
tvdb = tvdb_v4_official.TVDB(API_KEY)

# --- UTILITY FUNCTIONS ---
def sanitize_filename(filename):
    """Sanitize the filename by removing invalid characters for Windows."""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def sanitize_title(title):
    """Removes quality tags and common patterns from a title."""
    quality_pattern = r'\b(?:' + '|'.join(map(re.escape, QUALITY_TAGS)) + r')\b'
    sanitized_title = re.sub(quality_pattern, '', title, flags=re.IGNORECASE)
    sanitized_title = re.sub(r'[._-]+', ' ', sanitized_title).strip()
    return sanitized_title

def extract_metadata(filename):
    """Extracts metadata from various filename formats, focusing on the title."""
    clean_filename = os.path.splitext(filename)[0]
    patterns = [
        r"^(?P<series>.*?) - [sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))? - (?P<title>.*)$",
        r"^(?P<series>.*?)[. ]-[. ]?[sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))?[. ](?P<title>.*)$",
        r"^(?P<series>.*?) - (?P<season>\d{1,2})x(?P<ep_start>\d{2})(?:-?x?(?P<ep_end>\d{2}))? - (?P<title>.*)$"
    ]
    for pattern in patterns:
        match = re.match(pattern, clean_filename)
        if match and 'title' in match.groupdict():
            return re.sub(r'[._]', ' ', match.group('title')).strip()
    return None

# --- TVDB INTERACTION ---
def find_episode_by_title_in_list(episodes, title):
    """Match an episode using the title with fuzzy matching from a provided list."""
    sanitized_title = sanitize_title(title)
    if not episodes or not sanitized_title:
        return None

    best_match = None
    highest_score = 0
    for ep in episodes:
        ep_name = ep.get("name") or ""
        score = fuzz.ratio(ep_name.lower(), sanitized_title.lower())
        if score > highest_score:
            highest_score = score
            best_match = ep

    if best_match and highest_score >= 70:
        print(f"Matched '{sanitized_title}' -> '{best_match['name']}' [Score: {highest_score}]")
        logging.info(f"Fuzzy matched title '{sanitized_title}' to '{best_match['name']}' with score {highest_score}.")
        return best_match
    
    logging.warning(f"No episode match found for title '{sanitized_title}'. Best score was {highest_score}.")
    return None

def fetch_all_episodes(series_id):
    """NEW: Fetches and returns all episodes for a given series ID."""
    try:
        print("\nFetching and caching all episode data for this series...")
        series_extended = tvdb.get_series_extended(series_id)
        all_episodes = []
        for season in series_extended.get("seasons", []):
            if season.get("type", {}).get("name") == "Aired Order":
                season_episodes = tvdb.get_season_extended(season["id"])
                all_episodes.extend(season_episodes.get("episodes", []))
        
        if not all_episodes:
            print(f"{Fore.YELLOW}Warning: No 'Aired Order' episodes found for this series.")
            logging.warning(f"No 'Aired Order' episodes found for series ID {series_id}.")
        else:
            print(f"Successfully cached {len(all_episodes)} episodes.")
            logging.info(f"Cached {len(all_episodes)} episodes for series ID {series_id}.")
        return all_episodes
    except Exception as e:
        print(f"{Fore.RED}Error: Could not fetch episode data: {e}")
        logging.error(f"Failed to fetch episodes for Series ID {series_id}: {e}")
        return []

def determine_and_validate_series(directory):
    """MODIFIED: Determines the series for the run, validates it once, and returns it."""
    suggested_name = pathlib.Path(directory).name
    
    print(f"The suggested series name based on the directory is: {Fore.CYAN}{suggested_name}{Style.RESET_ALL}")
    series_name_input = input("Press Enter to accept, or enter the correct series name: ").strip()
    series_name = series_name_input or suggested_name

    try:
        search_results = tvdb.search(series_name)
        if not search_results:
            print(f"{Fore.RED}No series found for '{series_name}'.")
            return None

        # Display top 3 results for user to choose from
        print("\nPlease select the correct series from the list below:")
        for i, result in enumerate(search_results[:3]):
            year = result.get('year', 'N/A')
            print(f"  {i+1}) {result['name']} ({year}) - ID: {result['id']}")
        
        choice = input(f"Enter choice (1-{len(search_results[:3])}), or a specific Series ID: ").strip()
        
        selected_series_id_str = None
        if choice.isdigit() and 1 <= int(choice) <= len(search_results[:3]):
             selected_series_id_str = search_results[int(choice)-1]['id']
        else:
             selected_series_id_str = choice # Assume user entered a raw ID

        # --- THIS IS THE FIX ---
        # The get_series() function requires only the numeric part of the ID.
        # We must strip any "series-" prefix before passing it to the function.
        if not selected_series_id_str:
            print(f"{Fore.RED}No selection made. Skipping directory.")
            return None
        
        numeric_id = selected_series_id_str.split('-')[-1]
        
        validated_series = tvdb.get_series(numeric_id)
        # --- END OF FIX ---

        print(f"\n{Fore.GREEN}Series confirmed: {validated_series['name']} ({validated_series['year']})")
        logging.info(f"Series confirmed for this run: {validated_series['name']} (ID: {validated_series['id']})")
        return validated_series

    except Exception as e:
        print(f"{Fore.RED}An error occurred during series validation: {e}")
        logging.error(f"Failed to validate series '{series_name}': {e}")
        return None

# --- FILE PROCESSING ---
def rename_file(file_path, series_name, matched_episodes, dry_run=False):
    """Renames a file based on matched episodes. Now supports dry_run."""
    directory, filename = os.path.split(file_path)
    original_extension = pathlib.Path(filename).suffix

    if len(matched_episodes) == 1:
        episode = matched_episodes[0]
        new_name = f"{series_name} - S{episode['seasonNumber']:02d}E{episode['number']:02d} - {episode['name']}{original_extension}"
    else:
        first, second = sorted(matched_episodes, key=lambda x: x['number'])
        new_name = (f"{series_name} - S{first['seasonNumber']:02d}E{first['number']:02d}-E{second['number']:02d} - "
                    f"{first['name']} + {second['name']}{original_extension}")
    
    new_name = sanitize_filename(new_name)
    new_path = os.path.join(directory, new_name)

    if file_path == new_path:
        print(f"File already meets formatting standards: {filename}")
        return

    print(f"  {Fore.CYAN}{filename}{Style.RESET_ALL}\n  -> {Fore.GREEN}{new_name}{Style.RESET_ALL}")
    
    if dry_run:
        logging.info(f"[DRY RUN] Would rename '{filename}' to '{new_name}'.")
        return

    try:
        os.rename(file_path, new_path)
        logging.info(f"Renamed '{filename}' to '{new_name}'.")
    except Exception as e:
        print(f"  {Fore.RED}Error renaming file: {e}")
        logging.error(f"Failed to rename '{filename}': {e}")

def process_directory(directory, matched_series, all_episodes, dry_run=False):
    """MODIFIED: Processes files in a directory using pre-fetched series and episode data."""
    print(f"\nScanning files in '{directory}'...")
    
    files_to_process = sorted([
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and pathlib.Path(f).suffix.lower() in VALID_VIDEO_EXTENSIONS
    ])

    if not files_to_process:
        print("No video files found to process in this directory.")
        return

    for filename in files_to_process:
        print(f"\n---\nProcessing file: {Fore.YELLOW}{filename}{Style.RESET_ALL}")
        
        # Step 1: Extract a potential title from the filename
        extracted_title = extract_metadata(filename)
        if not extracted_title:
            # Fallback: Use the whole filename (without extension)
            extracted_title = os.path.splitext(filename)[0]
            print("Could not extract specific title, using full filename for matching.")
        
        # Step 2: Split for multi-episode files and match each part
        episode_titles = [t.strip() for t in extracted_title.split("+")]
        matched_episodes = []
        all_parts_matched = True

        for title_part in episode_titles:
            episode = find_episode_by_title_in_list(all_episodes, title_part)
            if episode:
                matched_episodes.append(episode)
            else:
                print(f"Could not find a match for title part: '{title_part}'")
                all_parts_matched = False
                break
        
        # Step 3: Rename if all parts were successfully matched
        if matched_episodes and all_parts_matched:
            rename_file(os.path.join(directory, filename), matched_series["name"], matched_episodes, dry_run)
        else:
            print(f"Skipping rename for '{filename}' due to incomplete match.")
            logging.warning(f"Skipped '{filename}' due to incomplete title match.")

# --- MAIN EXECUTION ---
def main():
    """Main script execution flow."""
    current_directory = os.getcwd()
    
    print("--- TV Show Renamer Script ---")
    logging.info("Script started.")
    
    dry_run = input("Enable Dry Run mode (no files will be changed)? (Y/N): ").strip().lower() == 'y'
    if dry_run:
        print(f"{Fore.YELLOW}Dry Run mode is ENABLED. No actual renaming will occur.")
        logging.info("Dry run mode enabled by user.")

    scan_subdirs = input("Subdirectories detected. Do you want to scan them? (Y/N): ").strip().lower() == 'y'
    
    if scan_subdirs:
        dirs_to_scan = [os.path.join(current_directory, d) for d in os.listdir(current_directory) if os.path.isdir(os.path.join(current_directory, d))]
        if not dirs_to_scan:
            print("No subdirectories found to scan.")
    else:
        dirs_to_scan = [current_directory]
    
    for dir_path in dirs_to_scan:
        print(f"\n{'='*40}\nProcessing Directory: {Fore.MAGENTA}{dir_path}{Style.RESET_ALL}")
        matched_series = determine_and_validate_series(dir_path)
        if matched_series:
            all_episodes = fetch_all_episodes(matched_series['id'])
            if all_episodes:
                process_directory(dir_path, matched_series, all_episodes, dry_run)
        else:
            print(f"Could not validate a series for '{dir_path}'. Skipping this directory.")
            logging.error(f"Could not validate series for '{dir_path}', skipping.")

    logging.info("Script finished.")
    print("\nProcessing complete.")

if __name__ == "__main__":
    main()