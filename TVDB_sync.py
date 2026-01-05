import os
import re
import json
import tvdb_v4_official
import pathlib
from fuzzywuzzy import fuzz
from colorama import Fore, Style, init
import logging
import argparse

# Initialize colorama
init(autoreset=True)

# Configure logging
logging.basicConfig(filename='rename.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Hardcoded path to the configuration file ---
CONFIG_FILE_PATH = r"C:\Tools\Rename Series\config.json"


class SeriesRenamer:
    """
    A class to find and rename TV series files using TheTVDB API.
    """
    def __init__(self, non_interactive=False, dry_run=False):
        """
        Initializes the SeriesRenamer using the hardcoded config path.
        """
        self.non_interactive = non_interactive
        self.dry_run = dry_run
        self.episode_cache = {}

        try:
            with open(CONFIG_FILE_PATH, "r") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"{Fore.RED}Config file not found at {CONFIG_FILE_PATH}. Please create it.")
            logging.error(f"Config file not found at {CONFIG_FILE_PATH}. Exiting.")
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


    def run(self, start_directory):
        """
        Determines a single series, then recursively finds and processes all files.
        """
        logging.info(f"Script started in single-series mode for directory: {start_directory}")

        # Step 1: Determine the single series for the entire run.
        print(f"Determining the series for all files in '{start_directory}' and its subdirectories...")
        matched_series = self._determine_and_validate_series(start_directory)
        if not matched_series:
            print(f"{Fore.RED}Could not validate a series for '{start_directory}'. Aborting.")
            logging.error(f"Could not validate series for '{start_directory}', aborting run.")
            return

        # Step 2: Fetch all episodes for that single series, once.
        all_episodes = self._fetch_all_episodes(matched_series['id'])
        if not all_episodes:
            print("No episodes found for the series. Aborting.")
            return

        # Step 3: Recursively find all video files in the start_directory and all subdirectories.
        print("\nFinding all video files recursively...")
        files_to_process = []
        try:
            for root, dirs, files in os.walk(start_directory):
                for filename in files:
                    if pathlib.Path(filename).suffix.lower() in self.valid_extensions:
                        files_to_process.append(os.path.join(root, filename))
        except FileNotFoundError:
            print(f"{Fore.RED}Error: The directory '{start_directory}' does not exist.")
            logging.error(f"Start directory not found: {start_directory}")
            return
            
        if not files_to_process:
            print("No video files found to process.")
            return

        print(f"Found {len(files_to_process)} files to process. Starting rename process...")

        # Step 4: Loop through the consolidated list of files and process each one.
        for file_path in sorted(files_to_process):
            original_filename = os.path.basename(file_path)
            filename = self._normalize_filename(original_filename)
            print(f"\n---\nProcessing file: {Fore.YELLOW}{original_filename}{Style.RESET_ALL}")
            if filename != original_filename:
                print(f"Normalized filename for matching: '{Fore.CYAN}{filename}{Style.RESET_ALL}'")
            
            extracted_title = self._extract_metadata(filename)
            if not extracted_title:
                # --- THIS IS THE IMPROVED FALLBACK LOGIC ---
                series_name_pattern = re.escape(matched_series['name'])
                base_filename = os.path.splitext(filename)[0]
                
                # 1. Remove the series name (case-insensitively).
                potential_title = re.sub(series_name_pattern, '', base_filename, flags=re.IGNORECASE)
                
                # 2. Normalize all delimiters (spaces, dots, underscores, dashes) to a single space.
                normalized_title = re.sub(r'[\s._-]+', ' ', potential_title).strip()
                
                # 3. Remove any leading digits (like episode numbers) and surrounding spaces.
                cleaned_title = re.sub(r'^\d+\s*', '', normalized_title).strip()
                
                extracted_title = cleaned_title
                print(f"Could not extract specific title, using cleaned filename for matching: '{extracted_title}'")
                # --- END OF IMPROVEMENT ---

            # Try multiple separator patterns to identify potential multi-episode titles
            separators_to_try = [" + ", " - ", " _ ", " ", "_"]
            matched_episodes = []
            all_parts_matched = False
            best_separator = None
            
            # First, try the original + separator
            episode_titles = [t.strip() for t in extracted_title.split("+")]
            matched_episodes, all_parts_matched = self._match_episodes_from_titles(episode_titles, all_episodes)
            
            # If not all parts matched, try other separators
            if not all_parts_matched:
                for sep in separators_to_try:
                    if sep in extracted_title:
                        episode_titles = [t.strip() for t in extracted_title.split(sep)]
                        temp_episodes, temp_all_matched = self._match_episodes_from_titles(episode_titles, all_episodes)
                        if temp_all_matched and len(temp_episodes) > len(matched_episodes):
                            matched_episodes = temp_episodes
                            all_parts_matched = temp_all_matched
                            best_separator = sep
                        elif temp_all_matched and not all_parts_matched:
                            matched_episodes = temp_episodes
                            all_parts_matched = temp_all_matched
                            best_separator = sep

            # Special case: if we have a single match with a very long input title, 
            # it might actually contain multiple episodes that weren't separated by common delimiters
            # So we should also try iterative matching even if we found a single match
            if len(matched_episodes) == 1 and len(extracted_title.split()) > 2:
                # Try finding individual matches iteratively as an alternative
                iterative_episodes = self._iterative_episode_match(extracted_title, all_episodes)
                if len(iterative_episodes) > len(matched_episodes):
                    # Iterative approach found more episodes, use that instead
                    matched_episodes = iterative_episodes
                    matched_texts = [ep.get('name', '') for ep in matched_episodes]
                    all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)
            
            # If we still don't have a good match, try iterative verification approach
            if not all_parts_matched and len(matched_episodes) == 0:
                # Try finding individual matches iteratively
                matched_episodes = self._iterative_episode_match(extracted_title, all_episodes)
                if len(matched_episodes) > 0:
                    # Check if all words in the extracted_title are covered by matched episodes
                    matched_texts = [ep.get('name', '') for ep in matched_episodes]
                    all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)
            
            # If we still don't have a match after the fallback and separator attempts,
            # try to further break down the extracted title by common separators
            if not all_parts_matched and len(matched_episodes) == 0:
                # Split by common separators and try to match individual parts
                potential_parts = re.split(r'[_+\s-]+', extracted_title)
                potential_parts = [part.strip() for part in potential_parts if part.strip() and len(part) > 1]
                
                # For each potential part, try to match with fuzzy logic
                temp_episodes = []
                for part in potential_parts:
                    episode = self._find_episode_by_title_in_list(all_episodes, part)
                    if episode:
                        temp_episodes.append(episode)
                
                # If we got some matches, check if they're better than what we had
                if len(temp_episodes) > len(matched_episodes):
                    matched_episodes = temp_episodes
                    matched_texts = [ep.get('name', '') for ep in matched_episodes]
                    all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)
            
            if matched_episodes and all_parts_matched:
                self._rename_file(file_path, matched_series, matched_episodes)
            elif matched_episodes and len(matched_episodes) > 1:
                # Even if not all parts matched perfectly, if we have multiple episodes matched, try renaming
                print(f"Partial match found but multiple episodes identified, attempting rename with {len(matched_episodes)} episodes.")
                self._rename_file(file_path, matched_series, matched_episodes)
            else:
                print(f"Skipping rename for '{filename}' due to incomplete match.")
                logging.warning(f"Skipped '{filename}' due to incomplete title match.")

        logging.info("Script finished.")
        print("\nProcessing complete.")

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
        else:
            # Sort episodes by episode number to ensure correct order
            sorted_episodes = sorted(matched_episodes, key=lambda x: x['number'])
            # Use the first episode's season number (assuming all episodes are from the same season)
            season_num = sorted_episodes[0]['seasonNumber']
            
            # Get the episode numbers for the range
            episode_nums = [ep['number'] for ep in sorted_episodes]
            min_ep_num = min(episode_nums)
            max_ep_num = max(episode_nums)
            
            # Create the episode range format (e.g., S01E01E02)
            # For multiple episodes (2 or more), use the E separator format
            episode_range = f"S{season_num:02d}E" + "E".join([f"{num:02d}" for num in sorted(episode_nums)])
            
            # Create the title part with all episode names joined by " + "
            episode_titles = [ep['name'] for ep in sorted_episodes]
            titles_combined = " + ".join(episode_titles)
            
            new_base_name = f"{series_data['name']} - {episode_range} - {titles_combined}"

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
                # If file is in use, make a copy and rename the copy
                if hasattr(e, 'winerror') and e.winerror == 32:
                    import shutil
                    try:
                        shutil.copy2(file_path, new_path)
                        print(f"  {Fore.YELLOW}File was in use. Copied and renamed instead.{Style.RESET_ALL}")
                        logging.info(f"Copied and renamed '{filename}' to '{new_name}' due to file lock.")
                    except Exception as copy_err:
                        print(f"  {Fore.RED}Failed to copy and rename: {copy_err}")
                        logging.error(f"Failed to copy and rename '{filename}': {copy_err}")
        else:
            print("  Skipping rename.")
            logging.warning(f"User skipped rename for '{filename}'.")

    def _sanitize_filename(self, filename):
        return re.sub(r'[<>:"/\\|?*]', '', filename)

    def _normalize_filename(self, filename):
        """
        Normalizes a filename by replacing internal dots, underscores, and hyphens with spaces,
        while preserving the file extension and avoiding decimal points in numbers.
        """
        path = pathlib.Path(filename)
        basename = path.stem
        extension = path.suffix
        
        # Replace dots, underscores, and hyphens with spaces
        # Use a regex that avoids replacing dots between digits (e.g., v1.2)
        # First, replace underscores and hyphens
        normalized = re.sub(r'[_]', ' ', basename)
        
        # Replace dots that are NOT between digits
        # This regex matches a dot that is not both preceded and followed by a digit
        normalized = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', normalized)
        
        # Collapse multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return f"{normalized}{extension}"

    def _sanitize_title(self, title):
        quality_pattern = r'\b(?:' + '|'.join(map(re.escape, self.quality_tags)) + r')\b'
        sanitized = re.sub(quality_pattern, '', title, flags=re.IGNORECASE)
        return re.sub(r'[._-]+', ' ', sanitized).strip()

    def _extract_metadata(self, filename):
        clean_filename = os.path.splitext(filename)[0]
        patterns = [
            r"^(?P<series>.*?) - [sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))? - (?P<title>.*)$",
            r"^(?P<series>.*?)[. ]-[. ]?[sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))?[. ](?P<title>.*)$",
            r"^(?P<series>.*?) [sS](?P<season>\d{1,2})[eE](?P<ep_start>\d{2})(?:-[eE](?P<ep_end>\d{2}))? (?P<title>.*)$"
        ]
        for pattern in patterns:
            match = re.match(pattern, clean_filename)
            if match and 'title' in match.groupdict():
                return re.sub(r'[._]', ' ', match.group('title')).strip()
        return None

    def _iterative_episode_match(self, extracted_title, all_episodes):
        """Iteratively tries to match parts of the title to episodes in the series."""
        import re
        # First, try to identify potential multi-episode by splitting on common separators
        potential_parts = re.split(r'[_+\s-]+', extracted_title)
        potential_parts = [part.strip() for part in potential_parts if part.strip()]
        
        if not potential_parts:
            return []
        
        # Create a list of potential matches with their positions and scores
        # Format: [(start_idx, end_idx, episode, score), ...]
        potential_matches = []
        
        # Try all possible consecutive combinations of parts
        for i in range(len(potential_parts)):
            for j in range(i, len(potential_parts)):
                potential_title = " ".join(potential_parts[i:j+1])
                episode = self._find_episode_by_title_in_list(all_episodes, potential_title)
                if episode:
                    # Get the actual score by calculating it again (since _find_episode_by_title_in_list prints it)
                    ep_name = episode.get("name") or ""
                    score = fuzz.ratio(ep_name.lower(), potential_title.lower())
                    potential_matches.append((i, j, episode, score))
        
        if not potential_matches:
            return []
        
        # Sort potential matches by their score in descending order (highest first)
        # Also prefer longer matches to shorter ones when scores are similar
        potential_matches.sort(key=lambda x: (x[3], -(x[1]-x[0])), reverse=True)
        
        # Greedily select non-overlapping matches with highest scores
        selected_matches = []
        used_indices = set()
        
        for start_idx, end_idx, episode, score in potential_matches:
            # Check if this match overlaps with already selected matches
            overlaps = any(i in used_indices for i in range(start_idx, end_idx + 1))
            if not overlaps:
                selected_matches.append((start_idx, end_idx, episode, score))
                # Mark these indices as used
                for i in range(start_idx, end_idx + 1):
                    used_indices.add(i)
        
        # Extract just the episodes from selected matches
        matched_episodes = []
        matched_ids = set()
        for match in selected_matches:
            episode = match[2]
            if episode['id'] not in matched_ids:
                matched_episodes.append(episode)
                matched_ids.add(episode['id'])
        
        return matched_episodes

    def _check_all_parts_matched(self, original_title, matched_texts):
        """Check if all parts of the original title are covered by matched episode titles."""
        import re
        # Split the original title into words/parts
        original_parts = re.split(r'[_+\s-]+', original_title.lower())
        original_parts = [part.strip() for part in original_parts if part.strip()]
        
        # Flatten and normalize matched text parts
        matched_words = []
        for text in matched_texts:
            words = re.split(r'[_+\s-]+', text.lower())
            matched_words.extend([word.strip() for word in words if word.strip()])
        
        # Check if all original parts are covered in matched words
        all_covered = all(any(original_part in matched_word or matched_word in original_part 
                              for matched_word in matched_words) 
                          for original_part in original_parts if len(original_part) > 2)
        
        return all_covered

    def _match_episodes_from_titles(self, episode_titles, all_episodes):
        """Helper method to match multiple episode titles against all episodes and return results."""
        matched_episodes = []
        all_parts_matched = True
        matched_ids = set()

        for title_part in episode_titles:
            # Skip matching if the title part is empty after cleaning
            if not title_part: 
                continue

            episode = self._find_episode_by_title_in_list(all_episodes, title_part)
            if episode:
                if episode['id'] not in matched_ids:
                    matched_episodes.append(episode)
                    matched_ids.add(episode['id'])
            else:
                all_parts_matched = False
                # Don't break here to allow checking all parts
                # We'll return partial matches if any exist
        
        # If no matches were found, return empty list with False
        if not matched_episodes:
            all_parts_matched = False
            
        return matched_episodes, all_parts_matched and len(matched_episodes) == len(episode_titles)
    
    def _find_episode_by_title_in_list(self, episodes, title):
        sanitized_title = self._sanitize_title(title)
        if not episodes or not sanitized_title: return None
        
        # Skip very short titles to avoid spurious matches (e.g., "du", "le", "sur")
        # unless the original title was also very short.
        if len(sanitized_title) < 3 and len(title) < 5:
            logging.info(f"Skipping match for very short title: '{sanitized_title}'")
            return None

        match_threshold = self.config.get("match_threshold", 85)
        best_match, highest_score = None, 0
        for ep in episodes:
            ep_name = ep.get("name") or ""
            score = fuzz.ratio(ep_name.lower(), sanitized_title.lower())
            if score > highest_score:
                highest_score, best_match = score, ep
        if best_match and highest_score >= match_threshold:
            print(f"Matched '{sanitized_title}' -> '{best_match['name']}' [Score: {highest_score}]")
            logging.info(f"Matched '{sanitized_title}' -> '{best_match['name']}' [Score: {highest_score}]")
            return best_match
        # Only log low-score matches and no-match info, do not print to console
        logging.info(f"No match found for '{sanitized_title}'. Best score ({highest_score}) was below threshold ({match_threshold}).")
        return None


    def run_test_mode(self):
        """Run the script in test mode, processing predefined test directories."""
        import json
        print(f"{Fore.CYAN}Starting test mode...{Style.RESET_ALL}")
        
        # Define test cases with expected outcomes
        test_cases = {
            "Rosie's Rules": [
                {
                    "original": "Abuela_s Birthday_Cat Mail.mp4",
                    "expected": "Rosie's Rules - S01E01E02 - Abuela's Birthday + Cat Mail.mp4",
                    "directory": "Rosie's Rules"
                }
            ],
            "Daniel Tiger's Neighborhood": [
                {
                    "original": "Daniel Tiger's Neighborhood - S03E02 - Firefighters at School + Daniel's Doll.mkv",
                    "expected": "Daniel Tiger's Neighborhood - S03E02E03 - Firefighters at School + Daniel's Doll.mkv", 
                    "directory": "Daniel Tiger's Neighborhood"
                },
                {
                    "original": "Daniel Tiger's Neighborhood - S03E05 - daniel and margaret play school + treasure hunt at the castle.mp4",
                    "expected": "Daniel Tiger's Neighborhood - S03E05E06 - Daniel and Margaret Play School + Treasure Hunt at the Castle.mp4",
                    "directory": "Daniel Tiger's Neighborhood"
                }
            ]
            # Additional test cases can be added here
        }
        
        # Track results
        test_results = []
        original_files_map = {}  # To store original names for potential revert
        
        # Process each test directory
        base_dir = os.getcwd()
        for series_name, test_files in test_cases.items():
            series_dir = os.path.join(base_dir, series_name)
            
            if not os.path.exists(series_dir):
                print(f"{Fore.YELLOW}Warning: Test directory does not exist: {series_dir}{Style.RESET_ALL}")
                continue
                
            print(f"\n{Fore.CYAN}Testing series: {series_name}{Style.RESET_ALL}")
            print(f"Processing directory: {series_dir}")
            
            # Determine the series (this will be automatic since directory name matches series)
            matched_series = self._determine_and_validate_series(series_dir)
            if not matched_series:
                print(f"{Fore.RED}Could not validate series for test: {series_name}{Style.RESET_ALL}")
                continue

            # Fetch all episodes for this series
            all_episodes = self._fetch_all_episodes(matched_series['id'])
            if not all_episodes:
                print(f"{Fore.RED}No episodes found for test series: {series_name}{Style.RESET_ALL}")
                continue

            # Process each test file in this directory
            for test_file in test_files:
                original_name = test_file['original']
                expected_name = test_file['expected']
                file_path = os.path.join(series_dir, original_name)
                
                if not os.path.exists(file_path):
                    print(f"{Fore.YELLOW}Warning: Test file does not exist: {file_path}{Style.RESET_ALL}")
                    continue
                
                print(f"\n  Testing file: {Fore.YELLOW}{original_name}{Style.RESET_ALL}")
                
                # Store original name for potential revert
                original_files_map[file_path] = {
                    'original_path': file_path,
                    'original_name': original_name,
                    'expected_name': expected_name
                }
                
                # Process the file using existing logic (non-interactive)
                original_filename = os.path.basename(file_path)
                filename = self._normalize_filename(original_filename)
                print(f"  Processing file: {Fore.YELLOW}{original_filename}{Style.RESET_ALL}")
                if filename != original_filename:
                    print(f"  Normalized filename for matching: '{Fore.CYAN}{filename}{Style.RESET_ALL}'")
                
                extracted_title = self._extract_metadata(filename)
                if not extracted_title:
                    # Use fallback logic as before
                    series_name_pattern = re.escape(matched_series['name'])
                    base_filename = os.path.splitext(filename)[0]
                    
                    # 1. Remove the series name (case-insensitively).
                    potential_title = re.sub(series_name_pattern, '', base_filename, flags=re.IGNORECASE)
                    
                    # 2. Normalize all delimiters (spaces, dots, underscores, dashes) to a single space.
                    normalized_title = re.sub(r'[\s._-]+', ' ', potential_title).strip()
                    
                    # 3. Remove any leading digits (like episode numbers) and surrounding spaces.
                    cleaned_title = re.sub(r'^\d+\s*', '', normalized_title).strip()
                    
                    extracted_title = cleaned_title
                    print(f"  Could not extract specific title, using cleaned filename for matching: '{extracted_title}'")

                # Apply the same matching logic as the main run method
                separators_to_try = [" + ", " - ", " _ ", " ", "_"]
                matched_episodes = []
                all_parts_matched = False
                best_separator = None
                
                # First, try the original + separator
                episode_titles = [t.strip() for t in extracted_title.split("+")]
                matched_episodes, all_parts_matched = self._match_episodes_from_titles(episode_titles, all_episodes)
                
                # If not all parts matched, try other separators
                if not all_parts_matched:
                    for sep in separators_to_try:
                        if sep in extracted_title:
                            episode_titles = [t.strip() for t in extracted_title.split(sep)]
                            temp_episodes, temp_all_matched = self._match_episodes_from_titles(episode_titles, all_episodes)
                            if temp_all_matched and len(temp_episodes) > len(matched_episodes):
                                matched_episodes = temp_episodes
                                all_parts_matched = temp_all_matched
                                best_separator = sep
                            elif temp_all_matched and not all_parts_matched:
                                matched_episodes = temp_episodes
                                all_parts_matched = temp_all_matched
                                best_separator = sep

                # Special case: if we have a single match with a very long input title, 
                # it might actually contain multiple episodes that weren't separated by common delimiters
                # So we should also try iterative matching even if we found a single match
                if len(matched_episodes) == 1 and len(extracted_title.split()) > 2:
                    # Try finding individual matches iteratively as an alternative
                    iterative_episodes = self._iterative_episode_match(extracted_title, all_episodes)
                    if len(iterative_episodes) > len(matched_episodes):
                        # Iterative approach found more episodes, use that instead
                        matched_episodes = iterative_episodes
                        matched_texts = [ep.get('name', '') for ep in matched_episodes]
                        all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)
                
                # If we still don't have a good match, try iterative verification approach
                if not all_parts_matched and len(matched_episodes) == 0:
                    # Try finding individual matches iteratively
                    matched_episodes = self._iterative_episode_match(extracted_title, all_episodes)
                    if len(matched_episodes) > 0:
                        # Check if all words in the extracted_title are covered by matched episodes
                        matched_texts = [ep.get('name', '') for ep in matched_episodes]
                        all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)
                
                # If we still don't have a match after the fallback and separator attempts,
                # try to further break down the extracted title by common separators
                if not all_parts_matched and len(matched_episodes) == 0:
                    # Split by common separators and try to match individual parts
                    potential_parts = re.split(r'[_+\s-]+', extracted_title)
                    potential_parts = [part.strip() for part in potential_parts if part.strip() and len(part) > 1]
                    
                    # For each potential part, try to match with fuzzy logic
                    temp_episodes = []
                    for part in potential_parts:
                        episode = self._find_episode_by_title_in_list(all_episodes, part)
                        if episode:
                            temp_episodes.append(episode)
                    
                    # If we got some matches, check if they're better than what we had
                    if len(temp_episodes) > len(matched_episodes):
                        matched_episodes = temp_episodes
                        matched_texts = [ep.get('name', '') for ep in matched_episodes]
                        all_parts_matched = self._check_all_parts_matched(extracted_title, matched_texts)

                # Generate the expected new name using existing logic
                if matched_episodes:
                    directory, filename = os.path.split(file_path)
                    original_extension = pathlib.Path(filename).suffix
                    template = self.config.get("naming_template", "{series_name} - S{season_num:02d}E{episode_num:02d} - {episode_title}")
                    
                    if len(matched_episodes) == 1:
                        episode = matched_episodes[0]
                        format_map = {
                            "series_name": matched_series.get('name'), "series_year": matched_series.get('year'),
                            "episode_title": episode.get('name'), "season_num": episode.get('seasonNumber'),
                            "episode_num": episode.get('number'), "absolute_num": episode.get('absoluteNumber'),
                            "aired_date": episode.get('aired')
                        }
                        new_base_name = template.format_map(format_map)
                    else:
                        # Sort episodes by episode number to ensure correct order
                        sorted_episodes = sorted(matched_episodes, key=lambda x: x['number'])
                        # Use the first episode's season number (assuming all episodes are from the same season)
                        season_num = sorted_episodes[0]['seasonNumber']
                        
                        # Get the episode numbers for the range
                        episode_nums = [ep['number'] for ep in sorted_episodes]
                        
                        # Create the episode range format (e.g., S01E01E02)
                        episode_range = f"S{season_num:02d}E" + "E".join([f"{num:02d}" for num in sorted(episode_nums)])
                        
                        # Create the title part with all episode names joined by " + "
                        episode_titles = [ep['name'] for ep in sorted_episodes]
                        titles_combined = " + ".join(episode_titles)
                        
                        new_base_name = f"{matched_series['name']} - {episode_range} - {titles_combined}"

                    new_name = self._sanitize_filename(f"{new_base_name}{original_extension}")
                    new_path = os.path.join(directory, new_name)

                    # Track the result
                    actual_name = os.path.basename(new_path)
                    expected_name_clean = self._sanitize_filename(expected_name)
                    
                    is_success = (actual_name.lower() == expected_name_clean.lower())
                    test_results.append({
                        'series': series_name,
                        'original': original_name,
                        'expected': expected_name_clean,
                        'actual': actual_name,
                        'success': is_success
                    })
                    
                    print(f"    Expected: {Fore.CYAN}{expected_name_clean}{Style.RESET_ALL}")
                    print(f"    Actual:   {Fore.GREEN if is_success else Fore.RED}{actual_name}{Style.RESET_ALL}")
                    print(f"    Result:   {'PASS' if is_success else 'FAIL'}")
                    
                    # Actually rename the file in test mode
                    if file_path != new_path:
                        print(f"    Renaming: {filename} -> {os.path.basename(new_path)}")
                        try:
                            os.rename(file_path, new_path)
                            print(f"    {Fore.GREEN}SUCCESS: File renamed{Style.RESET_ALL}")
                        except Exception as e:
                            print(f"    {Fore.RED}ERROR: {e}{Style.RESET_ALL}")
                            test_results[-1]['success'] = False
                    else:
                        print(f"    {Fore.YELLOW}INFO: File already has correct name{Style.RESET_ALL}")
                else:
                    print(f"    {Fore.RED}FAILED: Could not match episodes for {filename}{Style.RESET_ALL}")
                    test_results.append({
                        'series': series_name,
                        'original': original_name,
                        'expected': expected_name,
                        'actual': "NO_MATCH",
                        'success': False
                    })

        # Print summary
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results if result['success'])
        
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}TEST SUMMARY{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        print(f"Total tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        if total_tests > 0:
            print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
        else:
            print("Success rate: 0%")
        
        for result in test_results:
            status = "PASS" if result['success'] else "FAIL"
            color = Fore.GREEN if result['success'] else Fore.RED
            print(f"  {color}{status}{Style.RESET_ALL}: {result['series']} - {result['original']}")
        
        # Ask if user wants to revert
        print(f"\n{Fore.CYAN}Would you like to revert the test files to their original names? (y/n): {Style.RESET_ALL}")
        revert_choice = input().strip().lower()
        
        if revert_choice in ['y', 'yes']:
            self._revert_test_files(original_files_map)
        else:
            print(f"{Fore.YELLOW}Files remain renamed. You can manually revert them if needed.{Style.RESET_ALL}")

    def _revert_test_files(self, original_files_map):
        """Revert test files back to their original names."""
        print(f"\n{Fore.CYAN}Reverting test files to original names...{Style.RESET_ALL}")
        
        revert_results = []
        for new_path, original_info in original_files_map.items():
            original_path = original_info['original_path']
            original_name = original_info['original_name']
            expected_name = original_info['expected_name']
            
            # Construct the actual new path based on where the file should currently be
            directory = os.path.dirname(original_path)
            current_path = os.path.join(directory, expected_name)
            
            if os.path.exists(current_path):
                try:
                    os.rename(current_path, original_path)
                    print(f"  {Fore.GREEN}Reverted{Style.RESET_ALL}: {os.path.basename(current_path)} -> {original_name}")
                    revert_results.append(True)
                except Exception as e:
                    print(f"  {Fore.RED}ERROR reverting{Style.RESET_ALL}: {os.path.basename(current_path)} - {e}")
                    revert_results.append(False)
            else:
                # Try to find the actual renamed file by looking for files that start with the series name
                directory = os.path.dirname(original_path)
                found = False
                for file in os.listdir(directory):
                    if file != original_name and original_name.startswith(file.split(' - ')[0] if ' - ' in file else ''):
                        actual_current_path = os.path.join(directory, file)
                        try:
                            os.rename(actual_current_path, original_path)
                            print(f"  {Fore.GREEN}Reverted{Style.RESET_ALL}: {file} -> {original_name}")
                            revert_results.append(True)
                            found = True
                            break
                        except Exception as e:
                            print(f"  {Fore.RED}ERROR reverting{Style.RESET_ALL}: {file} - {e}")
                            revert_results.append(False)
                            found = True
                            break
                if not found:
                    print(f"  {Fore.YELLOW}Could not find renamed file for{Style.RESET_ALL}: {original_name}")
                    revert_results.append(False)
        
        successful_reverts = sum(revert_results)
        total_reverts = len(revert_results)
        print(f"\n{Fore.CYAN}Reverted {successful_reverts}/{total_reverts} files{Style.RESET_ALL}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rename TV Show files using TheTVDB. Assumes all files in a directory and its subdirectories belong to a single series.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('directory', nargs='?', default=os.getcwd(),
                        help="The top-level directory to process (defaults to the current directory).")
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help="Perform a dry run without renaming any files.")
    parser.add_argument('-y', '--non-interactive', action='store_true',
                        help="Enable non-interactive mode. Automatically accepts prompts.")
    parser.add_argument('-t', '--test', action='store_true',
                        help="Run in test mode with predefined test cases.")
    args = parser.parse_args()

    # Initialize and run the renamer
    renamer = SeriesRenamer(
        non_interactive=args.non_interactive or args.test,  # Test mode is non-interactive
        dry_run=args.dry_run
    )
    
    if args.test:
        renamer.run_test_mode()
    else:
        renamer.run(start_directory=args.directory)