import os
import re
import json
import tvdb_v4_official
import pathlib
import sys
from fuzzywuzzy import fuzz

# Load configuration
CONFIG_PATH = r"C:\Tools\Rename Series\config.json"
try:
    with open(CONFIG_PATH, "r") as config_file:
        config = json.load(config_file)
except FileNotFoundError:
    print(f"Config file not found at {CONFIG_PATH}. Please create it.")
    exit(1)

API_KEY = config.get("api_key")
if not API_KEY:
    print("API key is missing in the config file.")
    exit(1)

QUALITY_TAGS = config.get("quality_tags", [])
VALID_VIDEO_EXTENSIONS = set(config.get("valid_extensions", []))

# Initialize TVDB client
tvdb = tvdb_v4_official.TVDB(API_KEY)

# Enable verbose mode if -verbose switch is passed
verbose = "-verbose" in sys.argv

def log(message):
    """
    Prints a log message if verbose mode is enabled.
    """
    if verbose:
        print(message)

def sanitize_title(title):
    """
    Removes quality tags, codecs, and common patterns from a title.
    """
    quality_pattern = r'\b(?:' + '|'.join(map(re.escape, QUALITY_TAGS)) + r')\b'
    sanitized_title = re.sub(quality_pattern, '', title, flags=re.IGNORECASE)
    sanitized_title = re.sub(r'[._-]+', ' ', sanitized_title).strip()
    return sanitized_title

def extract_metadata(filename):
    """
    Extracts series name, season, episode range, and title from the filename.
    Handles multiple formats, including:
    - SXXEYY (standard)
    - sxxeyy (lowercase)
    - Season X Episode Y
    - SXXEYY-EZZ (episode range)
    """
    patterns = [
        # Standard SXXEYY or SXXEYY-EZZ formats
        r"^(.*?) - [sS](\d{2})[eE](\d{2})(?:-[eE](\d{2}))? - (.*?)\.[a-zA-Z0-9]+$",
        # "Season X Episode Y" format
        r"^(.*?) - Season (\d{1,2}) Episode (\d{1,2})(?:-(\d{1,2}))? - (.*?)\.[a-zA-Z0-9]+$"
    ]

    for pattern in patterns:
        match = re.match(pattern, filename)
        if match:
            series_name = match.group(1).strip()
            season = int(match.group(2))
            episode_start = int(match.group(3))
            episode_end = int(match.group(4)) if match.group(4) else episode_start
            title = match.group(5).strip()
            return series_name, season, (episode_start, episode_end), title

    log(f"Filename does not match any expected patterns: {filename}")
    return None, None, None, None

def lookup_series_id(series_name):
    """
    Look up series ID using the extracted series name.
    """
    try:
        search_results = tvdb.search(series_name)
        if not search_results:
            print(f"No series found for '{series_name}'.")
            return None
        # Use the first result as the default
        best_match = search_results[0]
        log(f"Found series: {best_match['name']} (ID: {best_match['id']})")
        
        series_id = best_match["id"].split("-")[-1]  # Take numeric part after 'series-'
        
        series_id_input = input(f"Press Enter to accept Series ID {series_id} "
                                f"or enter a different Series ID: ").strip() or series_id
        return series_id_input
    except Exception as e:
        print(f"Error searching for series '{series_name}': {e}")
        return None

def validate_series_id(series_id):
    """
    Validate the entered series ID by performing a lookup and returning the series data.
    """
    try:
        series_id = series_id.split("-")[-1] if series_id.startswith("series-") else series_id
        series = tvdb.get_series(series_id)
        log(f"Validated Series ID {series_id}: {series['name']}")
        return series
    except Exception as e:
        print(f"Invalid Series ID {series_id}: {e}")
        return None

def lookup_episode_by_title(series, title):
    """
    Match an episode using the title with fuzzy matching.
    """
    sanitized_title = sanitize_title(title)
    log(f"Looking up episode for sanitized title: {sanitized_title}")
    try:
        series_extended = tvdb.get_series_extended(series["id"])
        episodes = []
        for season in series_extended["seasons"]:
            if season["type"]["name"] == "Aired Order":
                season_episodes = tvdb.get_season_extended(season["id"])
                episodes.extend(season_episodes["episodes"])

        best_match = None
        highest_score = 0
        for ep in episodes:
            score = fuzz.ratio(ep["name"].lower(), sanitized_title.lower())
            if score > highest_score:
                highest_score = score
                best_match = ep

        if best_match and highest_score >= 70:  # Only accept matches with a score of 70 or higher
            log(f"Matched Episode: {best_match['name']} "
                f"(Season {best_match['seasonNumber']}, Episode {best_match['number']}) [Score: {highest_score}]")
            return best_match
        else:
            print(f"No good matches found for title: {sanitized_title}")
            return None
    except Exception as e:
        print(f"An error occurred while fetching episodes: {e}")
        return None

def rename_file(file_path, series_name, matched_episodes):
    """
    Rename the file based on the matched episodes, preserving the original extension.
    Handles single episodes, two episodes, and more than two episodes.
    """
    directory, filename = os.path.split(file_path)
    original_extension = pathlib.Path(filename).suffix  # Extract the original file extension

    if len(matched_episodes) == 1:
        # Single episode
        episode = matched_episodes[0]
        new_name = f"{series_name} - S{episode['seasonNumber']:02d}E{episode['number']:02d} - {episode['name']}{original_extension}"
    elif len(matched_episodes) == 2:
        # Exactly two episodes
        first, second = matched_episodes
        new_name = (f"{series_name} - S{first['seasonNumber']:02d}E{first['number']:02d}-E{second['number']:02d} - "
                    f"{first['name']} + {second['name']}{original_extension}")
    else:
        # Three or more episodes
        first = matched_episodes[0]
        last = matched_episodes[-1]
        combined_titles = " + ".join(ep["name"] for ep in matched_episodes)
        new_name = (f"{series_name} - S{first['seasonNumber']:02d}E{first['number']:02d}-E{last['number']:02d} - "
                    f"{combined_titles}{original_extension}")

    # Remove invalid characters from the new name
    invalid_chars = r'[<>:"/\\|?*]'
    new_name = re.sub(invalid_chars, '', new_name)

    new_path = os.path.join(directory, new_name)
    if file_path == new_path:
        log(f"File currently meets formatting standards: {filename}")
        return  # Skip renaming if the file already matches the desired format

    log(f"Renaming file from:\n{filename}\nTO\n{new_name}")
    confirm = input("Continue? (Y/N): ").strip().lower()
    if confirm == 'y':
        os.rename(file_path, new_path)
        print(f"Renamed to: {new_name}")
    else:
        print("Skipping rename.")


def process_directory(directory):
    """
    Process the given directory and its subdirectories.
    """
    last_series_name = None
    last_series_id = None

    log(f"Scanning directory: {directory}")

    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            if not os.path.isfile(file_path) or pathlib.Path(filename).suffix.lower() not in VALID_VIDEO_EXTENSIONS:
                continue

            log(f"Processing file: {file_path}")
            series_name, _, episode_range, extracted_title = extract_metadata(filename)
            if not series_name:
                log(f"Skipping file: {filename}")
                continue

            if series_name != last_series_name:
                series_id = lookup_series_id(series_name)
                if not series_id:
                    log(f"Skipping file: {filename}")
                    continue
                matched_series = validate_series_id(series_id)
                if not matched_series:
                    continue
                last_series_name = series_name
                last_series_id = series_id
            else:
                log(f"Reusing Series ID {last_series_id} for '{series_name}'")
                matched_series = validate_series_id(last_series_id)

            episode_titles = [title.strip() for title in extracted_title.split("+")]
            matched_episodes = []
            for title in episode_titles:
                episode = lookup_episode_by_title(matched_series, title)
                if episode:
                    matched_episodes.append(episode)

            if len(matched_episodes) == len(episode_titles):
                rename_file(file_path, matched_series["name"], matched_episodes)
            else:
                print(f"Could not match all parts of the combined title: {extracted_title}")
                log(f"Skipping file: {filename}")

def main():
    current_directory = os.getcwd()

    log(f"Verbose mode enabled.")
    log(f"Current directory: {current_directory}")
    log(f"Valid extensions: {VALID_VIDEO_EXTENSIONS}")

    process_directory(current_directory)

if __name__ == "__main__":
    main()
