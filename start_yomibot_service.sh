#!/bin/bash

# 1. Define Absolute Paths (Safer than $HOME in service context)
VENV_PATH="/home/cyanide/yomibot/venv"
PROJECT_DIR="/home/cyanide/yomibot/src"

# 2. Go to the project folder
cd "$PROJECT_DIR"

# 3. Activate the Virtual Environment
source "$VENV_PATH/bin/activate"

# 4. Update dependencies (Optional: doing this on every boot slows startup, but I'll leave it)
echo "Updating yt-dlp..."
pip install --upgrade pip
pip install --upgrade yt-dlp

# 5. Run the Bot
# CRITICAL: We run python DIRECTLY. 
# No 'screen', no '&', no 'nohup'.
# This command "blocks", meaning the script stays alive as long as the bot is running.
exec python yomibot.py

