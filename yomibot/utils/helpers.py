import os
import json
import re
import time

# Queue directory for saving/loading queue data
QUEUE_DIR = 'queues'

# Ensure queue directory exists
if not os.path.exists(QUEUE_DIR):
    os.makedirs(QUEUE_DIR)

def save_queue(server_id, queue_data):
    """Save the queue data for a server to a file"""
    queue_file = os.path.join(QUEUE_DIR, f'queue_{server_id}.json')
    with open(queue_file, 'w') as f:
        json.dump(queue_data, f, indent=4)

def load_queue(server_id):
    """Load the queue data for a server from a file"""
    queue_file = os.path.join(QUEUE_DIR, f'queue_{server_id}.json')
    if os.path.exists(queue_file):
        with open(queue_file, 'r') as f:
            return json.load(f)
    return []

def save_currently_playing(guild_id, current_song_data, next_song_data=None):
    """Save the currently playing song data to a file"""
    currently_playing = {
        "title": current_song_data.title,
        "channel": current_song_data.channel,
        "duration": current_song_data.duration,
        "url": current_song_data.original_url,
        "start_time": int(time.time())
    }

    next_song = None
    if next_song_data:
        next_song = {
            "title": next_song_data.title,
            "channel": next_song_data.channel,
            "duration": next_song_data.duration,
            "url": next_song_data.original_url
        }

    data = {
        "currently_playing": currently_playing,
        "next_song": next_song
    }

    file_path = os.path.join(QUEUE_DIR, f'currently_playing_{guild_id}.json')
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def normalize_youtube_music_url(url):
    """Normalize YouTube Music URLs to standard YouTube URLs"""
    if 'watch' in url:
        url = re.sub(r'(\?|&)list=.+', '', url)
    url = re.sub(r'(\?|&)start_radio=1', '', url)
    url = re.sub(r'(\?|&)si=.+', '', url)
    url = url.replace('music.youtube.com', 'www.youtube.com')
    return url

def transform_metric_name(metric):
    """
    Removes 'the_' prefix if present and capitalizes the metric words.
    """
    if metric.startswith("the_"):
        metric = metric[4:]
    return " ".join(word.capitalize() for word in metric.split("_"))