import os
import re
import json
import logging
import pathlib
import tvdb_v4_official
from typing import List, Optional, Tuple, Dict, Union

# Rich library imports
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.syntax import Syntax

# Other existing imports
from fuzzywuzzy import fuzz
from colorama import Fore, Style, init

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    filename='tv_renamer.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Initialize console and colorama
console = Console()
init(autoreset=True)

# Configuration validation function remains the same as in previous script
def validate_config(config: Dict[str, Union[str, List[str]]]) -> None:
    required_keys = ['api_key', 'valid_extensions', 'quality_tags']
    for key in required_keys:
        if key not in config:
            logger.error(f"Missing required configuration key: {key}")
            raise ValueError(f"Configuration is missing {key}")
        
        # Additional type checks
        if key == 'api_key' and not isinstance(config[key], str):
            raise ValueError("API key must be a string")
        
        if key in ['valid_extensions', 'quality_tags'] and not isinstance(config[key], list):
            raise ValueError(f"{key} must be a list")

# Enhanced user interaction methods
def display_file_processing_start(filename: str):
    """Display a nicely formatted start of file processing."""
    console.print(
        Panel.fit(
            f"Processing: [bold green]{filename}[/bold green]", 
            border_style="blue"
        )
    )

def display_rename_preview(old_name: str, new_name: str):
    """Show a preview of the rename with rich formatting."""
    console.print(Panel(
        f"[bold]Original:[/bold] {old_name}\n"
        f"[bold]New Name:[/bold] [green]{new_name}[/green]",
        title="Rename Preview",
        border_style="yellow"
    ))

def get_user_confirmation(message: str) -> bool:
    """
    Get user confirmation with rich formatting and error handling.
    
    Args:
        message (str): Confirmation prompt
    
    Returns:
        bool: User's confirmation choice
    """
    try:
        with console.style("bold yellow"):
            choice = console.input(f"{message} [y/N] ").lower().strip()
        return choice in ['y', 'yes']
    except KeyboardInterrupt:
        console.print("[bold red]Operation cancelled by user.[/bold red]")
        return False

def display_error(message: str, details: Optional[str] = None):
    """Display errors in a visually distinct manner."""
    console.print(
        Panel(
            f"[bold red]Error:[/bold red] {message}\n"
            f"[dim]{details or 'No additional details available'}[/dim]",
            title="Error Details",
            border_style="red"
        )
    )

def report_processing_summary(
    total_files: int, 
    renamed_files: int, 
    skipped_files: int
):
    """Generate a comprehensive processing summary."""
    console.rule("[bold blue]Processing Summary[/bold blue]")
    summary_panel = Panel(
        f"[bold]Total Files Processed:[/bold] {total_files}\n"
        f"[green]Successfully Renamed:[/green] {renamed_files}\n"
        f"[yellow]Skipped Files:[/yellow] {skipped_files}",
        title="TV Show Renamer",
        border_style="green"
    )
    console.print(summary_panel)

# Load configuration
CONFIG_PATH = r"C:\Tools\Rename Series\config.json"
try:
    with open(CONFIG_PATH, "r") as config_file:
        config = json.load(config_file)
    
    validate_config(config)
    API_KEY = config.get("api_key")
    QUALITY_TAGS = config.get("quality_tags", [])
    VALID_VIDEO_EXTENSIONS = set(config.get("valid_extensions", []))
except Exception as e:
    display_error("Configuration Loading Failed", str(e))
    logger.critical(f"Failed to load configuration: {e}")
    exit(1)

# Initialize TVDB client
try:
    tvdb = tvdb_v4_official.TVDB(API_KEY)
except Exception as e:
    display_error("TVDB Client Initialization Failed", str(e))
    logger.critical(f"Failed to initialize TVDB client: {e}")
    exit(1)

# Existing helper functions remain the same (sanitize_filename, sanitize_title, etc.)
def sanitize_filename(filename: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def sanitize_title(title: str) -> str:
    quality_pattern = r'\b(?:' + '|'.join(map(re.escape, QUALITY_TAGS)) + r')\b'
    sanitized_title = re.sub(quality_pattern, '', title, flags=re.IGNORECASE)
    sanitized_title = re.sub(r'[._-]+', ' ', sanitized_title).strip()
    return sanitized_title

def extract_metadata(filename: str) -> Tuple[Optional[str], Optional[int], Optional[Tuple[int, int]], Optional[str]]:
    patterns = [
        r"^(.*?) - [sS](\d{2})[eE](\d{2})(?:-[eE](\d{2}))? - (.*?)\.[a-zA-Z0-9]+$",
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

    logger.warning(f"Filename does not match any expected patterns: {filename}")
    return None, None, None, None

# Keep the existing TVDB lookup and episode matching functions 
# (lookup_series_id, validate_series_id, lookup_episode_by_title)

def process_directory(directory: str, scan_subdirs: bool = False) -> Tuple[int, int, int]:
    """
    Process the given directory with enhanced reporting.
    
    Returns:
        Tuple of (total_files, renamed_files, skipped_files)
    """
    total_files = 0
    renamed_files = 0
    skipped_files = 0
    last_series_name = None
    last_series_id = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        processing_task = progress.add_task("[cyan]Processing Files...", total=None)

        for root, _, files in os.walk(directory):
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # Skip non-video files
                if not os.path.isfile(file_path) or pathlib.Path(filename).suffix.lower() not in VALID_VIDEO_EXTENSIONS:
                    continue

                total_files += 1
                display_file_processing_start(filename)

                # Extract metadata
                series_name, _, episode_range, extracted_title = extract_metadata(filename)
                if not series_name:
                    display_error(f"Invalid metadata for file", filename)
                    skipped_files += 1
                    continue

                # Look up the series ID
                if series_name != last_series_name:
                    series_id = lookup_series_id(series_name)
                    if not series_id:
                        display_error(f"Invalid series ID for", filename)
                        skipped_files += 1
                        continue
                    
                    matched_series = validate_series_id(series_id)
                    if not matched_series:
                        skipped_files += 1
                        continue
                    
                    last_series_name = series_name
                    last_series_id = series_id

                # Handle combined episode titles
                episode_titles = [title.strip() for title in extracted_title.split("+")]
                matched_episodes = []
                
                for title in episode_titles:
                    episode = lookup_episode_by_title(matched_series, title)
                    if episode:
                        matched_episodes.append(episode)

                # Verify and rename if all parts matched
                if len(matched_episodes) == len(episode_titles):
                    try:
                        display_rename_preview(filename, f"{matched_series['name']} - Episode details")
                        if get_user_confirmation("Do you want to rename this file?"):
                            rename_file(file_path, matched_series["name"], matched_episodes)
                            renamed_files += 1
                        else:
                            skipped_files += 1
                    except Exception as e:
                        display_error(f"Rename failed for {filename}", str(e))
                        skipped_files += 1
                else:
                    display_error(f"Could not match all parts of the title", extracted_title)
                    skipped_files += 1

            if not scan_subdirs:
                break

    return total_files, renamed_files, skipped_files

def main() -> None:
    """Main function with enhanced user interaction."""
    console.print(
        Panel.fit(
            "[bold blue]TV Show File Renamer[/bold blue]\n"
            "Automatically renames TV show files using TVDB metadata",
            border_style="green"
        )
    )

    current_directory = os.getcwd()
    logger.info(f"Starting file renaming process in directory: {current_directory}")

    subdirs = [d for d in os.listdir(current_directory) if os.path.isdir(os.path.join(current_directory, d))]

    scan_subdirs = False
    if subdirs:
        scan_subdirs = get_user_confirmation("Subdirectories detected. Scan them?")
        logger.info(f"Scanning subdirectories: {scan_subdirs}")

    try:
        total_files, renamed_files, skipped_files = process_directory(current_directory, scan_subdirs)
        report_processing_summary(total_files, renamed_files, skipped_files)
        logger.info("File renaming process completed successfully")
    except Exception as e:
        display_error("An error occurred during file renaming", str(e))
        logger.error(f"An error occurred during file renaming: {e}")

# Existing rename_file, lookup_series_id, validate_series_id, 
# and lookup_episode_by_title functions from the previous script remain the same

if __name__ == "__main__":
    main()