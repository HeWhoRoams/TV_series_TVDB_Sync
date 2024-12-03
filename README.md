This python script was my answer to constantly acquiring media that was labeled with Season # and Episode # that didn't match TVDB, and thus imported into Sonarr incorrectly. 

It parses through a directory and looks for media files (file extensions are in the config file). From there it extracts what data is can from the file name, looking for show name, Season, episode and episode title.
It attempts to identify the series ID through the TVDB API, but allows for the user to override.
From there it uses some fuzzy matching logic to match the episode title with the one on TVDB and then attempts to rename the file appropriately, prompting for confirmation.

Usage: I keep the config file in a tools directory on my C drive, and copy and paste the python script to whatever directory I am looking to parse and rename. 
