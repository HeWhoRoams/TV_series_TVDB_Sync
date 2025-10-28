import os
import re
import json
import tvdb_v4_official
import pathlib
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
    Extract series name and title from the filename.
    Assumes the pattern: <Series> - SXXEYY(-EYY)* - <Title>.ext
    """
    pattern = r"^(.*?) - S(\d{2})E(\d{2})(?:-E(\d{2}))? - (.*?)\.[a-zA-Z0-9]+$"
    match = re.match(pattern, filename)
    if not match:
        print(f"Filename does not match expected pattern: {filename}")
        return None, None, None, None
    series_name = match.group(1).strip()
    season = int(match.group(2))
    episode_start = int(match.group(3))
    episode_end = int(match.group(4)) if match.group(4) else episode_start
    title = match.group(5).strip()

    # Check if the episode range is valid
    if episode_start > episode_end:
        print(f"Invalid episode range in filename: {filename}")
        return None, None, None, None

    return series_name, season, (episode_start, episode_end), title

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
        print(f"Found series: {best_match['name']} (ID: {best_match['id']})")
        
        # If the ID is in the form of 'series-<ID>', extract the numeric ID
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
        # Ensure we are using the correct ID format
        if series_id.startswith("series-"):
            series_id = series_id.split("-")[-1]  # Extract numeric part of the ID if needed
        
        series = tvdb.get_series(series_id)
        print(f"Validated Series ID {series_id}: {series['name']}")
        return series
    except Exception as e:
        print(f"Invalid Series ID {series_id}: {e}")
        return None

def lookup_episode_by_title(series, title):
    """
    Match an episode using the title with fuzzy matching.
    """
    sanitized_title = sanitize_title(title)
    print(f"Looking up episode for sanitized title: {sanitized_title}")
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
            print(f"Matched Episode: {best_match['name']} "
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
    Rename the file based on the matched episodes.
    """
    directory, filename = os.path.split(file_path)
    if len(matched_episodes) == 1:
        episode = matched_episodes[0]
        new_name = f"{series_name} - S{episode['seasonNumber']:02d}E{episode['number']:02d} - {episode['name']}.mkv"
    else:
        first, second = matched_episodes
        new_name = (f"{series_name} - S{first['seasonNumber']:02d}"
                    f"E{first['number']:02d}-E{second['number']:02d} - "
                    f"{first['name']} + {second['name']}.mkv")
    
    # Check if the new name matches the current filename
    if filename == new_name:
        print(f"File currently meets formatting standards: {filename}")
        return
    
    new_path = os.path.join(directory, new_name)
    print(f"\nUsing this information, the file will be renamed from:")
    print(f"{filename}\nTO\n{new_name}")
    confirm = input("Continue? (Y/N): ").strip().lower()
    if confirm == 'y':
        os.rename(file_path, new_path)
        print(f"Renamed to: {new_name}")
    else:
        print("Skipping rename.")

def process_directory(directory, scan_subdirs=False):
    """
    Process the given directory and optionally scan subdirectories.
    """
    last_series_name = None
    last_series_id = None

    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            # Skip non-video files
            if not os.path.isfile(file_path) or pathlib.Path(filename).suffix.lower() not in VALID_VIDEO_EXTENSIONS:
                continue

            print(f"\nFile: {filename}")
            series_name, _, episode_range, extracted_title = extract_metadata(filename)
            if not series_name:
                print(f"Skipping file: {filename}")
                continue

            # Look up the series ID
            if series_name != last_series_name:
                series_id = lookup_series_id(series_name)
                if not series_id:
                    print(f"Skipping file: {filename}")
                    continue
                matched_series = validate_series_id(series_id)
                if not matched_series:
                    continue
                last_series_name = series_name
                last_series_id = series_id
            else:
                print(f"Reusing Series ID {last_series_id} for '{series_name}'")
                matched_series = validate_series_id(last_series_id)

            # Handle combined episode titles
            episode_titles = [title.strip() for title in extracted_title.split("+")]
            matched_episodes = []
            for title in episode_titles:
                episode = lookup_episode_by_title(matched_series, title)
                if episode:
                    matched_episodes.append(episode)

            # Verify and rename if all parts matched
            if len(matched_episodes) == len(episode_titles):
                rename_file(file_path, matched_series["name"], matched_episodes)
            else:
                print(f"Could not match all parts of the combined title: {extracted_title}")
                print(f"Skipping file: {filename}")

        if not scan_subdirs:
            break

def main():
    current_directory = os.getcwd()
    subdirs = [d for d in os.listdir(current_directory) if os.path.isdir(os.path.join(current_directory, d))]

    scan_subdirs = False
    if subdirs:
        scan_subdirs = input("Subdirectories detected. Do you want to scan them? (Y/N): ").strip().lower() == 'y'

    process_directory(current_directory, scan_subdirs)

if __name__ == "__main__":
    main()
