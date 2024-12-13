This python script was my answer to constantly acquiring media that was labeled with Season # and Episode # that didn't match TVDB, and thus imported into Sonarr incorrectly. 

It parses through a directory and looks for media files (file extensions are in the config file). From there it extracts what data is can from the file name, looking for show name, Season, episode and episode title.
It attempts to identify the series ID through the TVDB API, but allows for the user to override.
From there it uses some fuzzy matching logic to match the episode title with the one on TVDB and then attempts to rename the file appropriately, prompting for confirmation.

Usage: I keep the config file in a tools directory on my C drive, and copy and paste the python script to whatever directory I am looking to parse and rename. The config file stays in that location.

Note: you will need an account at TheTVDB.com and to request a free API key.

File Renaming Script - Installation Guide

This guide will walk you through installing the necessary tools and dependencies to use the File Renaming Script on both Linux and Windows.

Prerequisites

1. Python Installation

This script requires Python 3.6 or higher.

Check if Python is installed:

Open a terminal or command prompt.

Run the command:

    python --version

or

    python3 --version

If Python is installed, it will display the version number.

Install Python (if not installed):

Windows:

Download the latest Python installer from the official Python website.

Run the installer and check the box "Add Python to PATH" during installation.

Complete the installation process.

Linux:

Use your package manager to install Python:

For Debian/Ubuntu:

    sudo apt update
    sudo apt install python3 python3-pip

For Fedora:

    sudo dnf install python3 python3-pip

For Arch:

    sudo pacman -S python python-pip

2. Install Git (optional, for downloading the script from GitHub)

Windows:

Download Git from the official website.

Run the installer and follow the setup instructions. Select the recommended options for beginners.

Linux:

Use your package manager to install Git:

    sudo apt install git      # Debian/Ubuntu
    sudo dnf install git      # Fedora
    sudo pacman -S git        # Arch

3. Install Additional Tools

This script uses the following Python libraries:

tvdb_v4_official

fuzzywuzzy

colorama

You will also need a configuration file to store API keys and other settings.

Installation Steps

Step 1: Clone or Download the Script

Using Git (recommended):

    git clone https://github.com/your-repo-name/rename-series.git
    cd rename-series

Without Git:

Go to the GitHub repository.

Click Code > Download ZIP.

Extract the ZIP file to your desired directory.

Step 2: Install Dependencies

Run the following command to install the required Python libraries:

    pip install tvdb_v4_official fuzzywuzzy colorama

If you encounter issues, ensure pip is installed by running:

    python -m ensurepip --upgrade

Step 3: Configure the Script

Locate the config.json file in the script directory (or create one if it doesn't exist).

Edit the file to include your settings:

{
    "api_key": "your_tvdb_api_key",
    "quality_tags": ["1080p", "720p", "WEBRip"],
    "valid_extensions": [".mp4", ".mkv", ".avi"]
}

Save the file.

Running the Script

Navigate to the script directory:

    cd /path/to/script

Run the script:

    python rename_series.py

Follow the prompts to rename files in the current directory or its subdirectories.

Troubleshooting

Common Issues:

"Command not found" or "ModuleNotFoundError":

Ensure Python and required libraries are installed.

Check that pip install completed successfully.

Permission Errors:

On Linux, you may need to run the script with sudo if accessing protected directories.

Logging:

The script provides detailed logs in the terminal. If you encounter issues, copy the error message and search for solutions or create an issue on the GitHub repository.

Contributing

If you'd like to contribute to this project, feel free to fork the repository and submit a pull request. Contributions are welcome!
