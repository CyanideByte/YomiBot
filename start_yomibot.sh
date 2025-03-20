#!/bin/bash

# Name of the screen session
SESSION_NAME="yomibot"

# Path to your virtual environment and yomibot script
VENV_PATH="$HOME/yomibot/venv"
SCRIPT_PATH="$HOME/yomibot/yomibot.py"

# Start a new screen session and run the commands inside it
screen -dmS $SESSION_NAME bash -c "
  # Activate the virtual environment
  source $VENV_PATH/bin/activate
  # Navigate to the project directory
  cd $(dirname $SCRIPT_PATH)
  # Start the yomibot script
  python $(basename $SCRIPT_PATH)
  # Keep the session alive
  exec bash
"
