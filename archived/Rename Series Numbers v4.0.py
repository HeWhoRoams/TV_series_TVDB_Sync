import os
import re
import json
import tvdb_v4_official
import pathlib
from fuzzywuzzy import fuzz
from colorama import Fore, Style, init
import logging
import argparse # NEW: For a more professional command-line interface

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(filename='rename.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class SeriesRenamer:
    """
    A class to find and rename TV series files using TheTVDB API.
    """
    def __init__(self, config_path, non_interactive=False, dry_run=False):
        """
        Initializes the SeriesRenamer instance.
        
        Args:
            config_path (str): Path to the configuration JSON file.
            non_interactive (bool): If True, runs without user prompts.
            dry_run (bool): If True, shows proposed changes without renaming files.
        """
        self.non_interactive = non_interactive
        self.dry_run = dry_run
        self.episode_cache = {}

        try:
            with open(config_path, "r") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"{Fore.RED}Config file not found at {config_path}. Please create it.")
            logging.error(f"Config file not found at {config_path}. Exiting.")
            exit(1)

        api_key = self.config.get("api_key")
        if not api_key:
            print(f"{Fore.RED}API key is missing in the config file.")
            logging.error("API key is missing in config.json. Exiting.")
            exit(1)
        
        self.tvdb = tvdb_v4_official.TVDB(api_key)
        self.valid_extensions = set(self.config.get("valid_extensions", []))
        self.quality_tags = self.config.get("quality_tags", [])
        print("Series Renamer initialized.")
        if self.dry_run:
            print(f"{Fore.YELLOW}Dry Run mode is ENABLED. No files will be changed.")
        if self.non_interactive:
            print(f"{Fore.YELLOW}Non-Interactive mode is ENABLED. Using best guess for all prompts.")


    def run(self, start_directory, scan_subdirs=False):
        """
        The main entry point to start the renaming process.
        
        Args:
            start_directory (str): The root directory to start scanning from.
            scan_subdirs (bool): Whether to scan subdirectories of the start_directory.
        """
        logging.info(f"Script started on directory: {start_directory}")

        if scan_subdirs:
            dirs_to_scan = [os.path.join(start_directory, d) for d in os.listdir(start_directory) if os.path.isdir(os.path.join(start_directory, d))]
            if not dirs_to_scan:
                print("No subdirectories found to scan.")
                # Fallback to scanning the start directory itself
                dirs_to_scan = [start_directory]
        else:
            dirs_to_scan = [start_directory]
        
        for dir_path in dirs_to_scan:
            print(f"\n{'='*50}\n{Fore.MAGENTA}Processing Directory: {dir_path}{Style.RESET_ALL}")
            matched_series = self._determine_and_validate_series(dir_path)
            if matched_series:
                all_episodes = self._fetch_all_episodes(matched_series['id'])
                if all_episodes:
                    self._process_directory(dir_path, matched_series, all_episodes)
            else:
                print(f"Could not validate a series for '{dir_path}'. Skipping.")
                logging.error(f"Could not validate series for '{dir_path}', skipping.")
        
        logging.info("Script finished.")
        print("\nProcessing complete.")

    def _process_directory(self, directory, matched_series, all_episodes):
        """Processes all video files in a single directory."""
        print(f"\nScanning files in '{directory}'...")
        
        files_to_process = sorted([
            f for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f)) and pathlib.Path(f).suffix.lower() in self.valid_extensions
        ])

        if not files_to_process:
            print("No video files found to process in this directory.")
            return

        for filename in files_to_process:
            print(f"\n---\nProcessing file: {Fore.YELLOW}{filename}{Style.RESET_ALL}")
            
            extracted_title = self._extract_metadata(filename)
            if not extracted_title:
                extracted_title = os.path.splitext(filename)[0]
                print("Could not extract a specific title, using full filename for matching.")
            
            episode_titles = [t.strip() for t in extracted_title.split("+")]
            matched_episodes = []
            all_parts_matched = True

            for title_part in episode_titles:
                episode = self._find_episode_by_title_in_list(all_episodes, title_part)
                if episode:
                    matched_episodes.append(episode)
                else:
                    print(f"Could not find a match for title part: '{title_part}'")
                    all_parts_matched = False
                    break
            
            if matched_episodes and all_parts_matched:
                self._rename_file(os.path.join(directory, filename), matched_series, matched_episodes)
            else:
                print(f"Skipping rename for '{filename}' due to incomplete match.")
                logging.warning(f"Skipped '{filename}' due to incomplete title match.")

    def _determine_and_validate_series(self, directory):
        """Determines the series for the run, validates it once, and returns it."""
        suggested_name = pathlib.Path(directory).name
        
        if self.non_interactive:
            series_name = suggested_name
        else:
            print(f"Suggested series name from directory: {Fore.CYAN}{suggested_name}{Style.RESET_ALL}")
            series_name_input = input("Press Enter to accept, or enter the correct series name: ").strip()
            series_name = series_name_input or suggested_name
        
        try:
            search_results = self.tvdb.search(series_name)
            if not search_results:
                print(f"{Fore.RED}No series found for '{series_name}'.")
                return None
            
            selected_series_id_str = None
            if self.non_interactive:
                selected_series_id_str = search_results[0]['id']
                print(f"Non-interactive mode: auto-selecting first result: {search_results[0]['name']}")
            else:
                print("\nPlease select the correct series from the list below:")
                for i, result in enumerate(search_results[:3]):
                    year = result.get('year', 'N/A')
                    print(f"  {i+1}) {result['name']} ({year}) - ID: {result['id']}")
                choice = input(f"Enter choice (1-{len(search_results[:3])}), or a specific Series ID: ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(search_results[:3]):
                    selected_series_id_str = search_results[int(choice)-1]['id']
                else:
                    selected_series_id_str = choice

            if not selected_series_id_str:
                print(f"{Fore.RED}No selection made. Skipping directory.")
                return None
            
            numeric_id = selected_series_id_str.split('-')[-1]
            validated_series = self.tvdb.get_series(numeric_id)
            
            print(f"\n{Fore.GREEN}Series confirmed: {validated_series['name']} ({validated_series['year']})")
            logging.info(f"Series confirmed for this run: {validated_series['name']} (ID: {validated_series['id']})")
            return validated_series

        except Exception as e:
            print(f"{Fore.RED}An error occurred during series validation: {e}")
            logging.error(f"Failed to validate series '{series_name}': {e}")
            return None

    def _fetch_all_episodes(self, series_id):
        """Fetches and returns all episodes for a given series ID, using a cache."""
        if series_id in self.episode_cache:
            print("Found episode data in cache.")
            return self.episode_cache[series_id]

        try:
            print("\nFetching and caching all episode data for this series...")
            series_extended = self.tvdb.get_series_extended(series_id)
            all_episodes = []
            for season in series_extended.get("seasons", []):
                if season.get("type", {}).get("name") == "Aired Order":
                    season_episodes = self.tvdb.get_season_extended(season["id"])
                    all_episodes.extend(season_episodes.get("episodes", []))
            
            self.episode_cache[series_id] = all_episodes
            print(f"Successfully cached {len(all_episodes)} episodes.")
            logging.info(f"Cached {len(all_episodes)} episodes for series ID {series_id}.")
            return all_episodes
        except Exception as e:
            print(f"{Fore.RED}Error: Could not fetch episode data: {e}")
            logging.error(f"Failed to fetch episodes for Series ID {series_id}: {e}")
            return []

    def _rename_file(self, file_path, series_data, matched_episodes):
        """Renames a file based on matched episodes."""
        directory, filename = os.path.split(file_path)
        original_extension = pathlib.Path(filename).suffix

        # Use a default template if none is in config.json
        template = self.config.get("naming_template", "{series_name} - S{season_num:02d}E{episode_num:02d} - {episode_title}")
        
        if len(matched_episodes) == 1:
            episode = matched_episodes[0]
            format_map = {
                "series_name": series_data.get('name'), "series_year": series_data.get('year'),
                "episode_title": episode.get('name'), "season_num": episode.get('seasonNumber'),
                "episode_num": episode.get('number'), "absolute_num": episode.get('absoluteNumber'),
                "aired_date": episode.get('aired')
            }
            new_base_name = template.format_map(format_map)
        else: # Handle multi-episode files by joining titles
            first, second = sorted(matched_episodes, key=lambda x: x['number'])
            new_base_name = (f"{series_data['name']} - S{first['seasonNumber']:02d}E{first['number']:02d}-E{second['number']:02d} - "
                             f"{first['name']} + {second['name']}")

        new_name = self._sanitize_filename(f"{new_base_name}{original_extension}")
        new_path = os.path.join(directory, new_name)

        if file_path == new_path:
            print(f"File already meets formatting standards: {filename}")
            return

        print(f"  {Fore.CYAN}{filename}{Style.RESET_ALL}\n  -> {Fore.GREEN}{new_name}{Style.RESET_ALL}")
        
        if self.dry_run:
            logging.info(f"[DRY RUN] Would rename '{filename}' to '{new_name}'.")
            return
        
        user_confirm = True
        if not self.non_interactive:
            confirm_input = input("  Continue? (Y/N): ").strip().lower()
            if confirm_input != 'y':
                user_confirm = False

        if user_confirm:
            try:
                os.rename(file_path, new_path)
                logging.info(f"Renamed '{filename}' to '{new_name}'.")
            except Exception as e:
                print(f"  {Fore.RED}Error renaming file: {e}")
                logging.error(f"Failed to rename '{filename}': {e}")
        else:
            print("  Skipping rename.")
            logging.warning(f"User skipped rename for '{filename}'.")

    # --- Static Helper Methods ---
    def _sanitize_filename(self, filename):
        return re.sub(r'[<>:"/\\|?*]', '', filename)

    def _sanitize_title(self, title):
        quality_pattern = r'\b(?:' + '|'.join(map(re.escape, self.quality_tags)) + r')\b'
        sanitized = re.sub(quality_pattern, '', title, flags=re.IGNORECASE)
        return re.sub(r'[._-]+', ' ', sanitized).strip()

    def _extract_metadata(self, filename):
        clean_filename = os.path.splitext(filename)[0]
        patterns = [
            r"^(?P<series>.*?) - [sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))? - (?P<title>.*)$",
            r"^(?P<series>.*?)[. ]-[. ]?[sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))?[. ](?P<title>.*)$"
        ]
        for pattern in patterns:
            match = re.match(pattern, clean_filename)
            if match and 'title' in match.groupdict():
                return re.sub(r'[._]', ' ', match.group('title')).strip()
        return None

    def _find_episode_by_title_in_list(self, episodes, title):
        sanitized_title = self._sanitize_title(title)
        if not episodes or not sanitized_title: return None
        best_match, highest_score = None, 0
        for ep in episodes:
            ep_name = ep.get("name") or ""
            score = fuzz.ratio(ep_name.lower(), sanitized_title.lower())
            if score > highest_score: highest_score, best_match = score, ep
        if best_match and highest_score >= 70:
            print(f"Matched '{sanitized_title}' -> '{best_match['name']}' [Score: {highest_score}]")
            return best_match
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rename TV Show files using TheTVDB.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('directory', nargs='?', default=os.getcwd(),
                        help="The directory to process (defaults to the current directory).")
    parser.add_argument('-s', '--scan-subdirs', action='store_true',
                        help="Scan all subdirectories within the target directory.")
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help="Perform a dry run without renaming any files.")
    parser.add_argument('-y', '--non-interactive', action='store_true',
                        help="Enable non-interactive mode. Automatically accepts prompts.")
    parser.add_argument('-c', '--config', default="config.json",
                        help="Path to the configuration file (defaults to config.json).")
    args = parser.parse_args()

    # Initialize and run the renamer
    renamer = SeriesRenamer(
        config_path=args.config,
        non_interactive=args.non_interactive,
        dry_run=args.dry_run
    )
    renamer.run(
        start_directory=args.directory,
        scan_subdirs=args.scan_subdirs
    )