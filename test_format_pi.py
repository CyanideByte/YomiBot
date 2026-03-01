#!/usr/bin/env python3
"""
Test script to check available formats for a YouTube video on the Pi server
Usage: python test_format_pi.py <url>
"""

import sys
import yt_dlp

def list_formats(url):
    """List all available formats for a video"""
    print(f"\n{'='*60}")
    print(f"Checking formats for: {url}")
    print(f"{'='*60}\n")

    ytdl_opts = {
        'quiet': False,
        'no_warnings': False,
        'listformats': True,
    }

    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as ytdl:
            ytdl.extract_info(url, download=False)
    except SystemExit:
        pass  # --listformats causes sys.exit()

def test_format_extraction(url, format_string):
    """Test if a specific format works"""
    print(f"\n{'='*60}")
    print(f"Testing format: '{format_string}'")
    print(f"{'='*60}\n")

    ytdl_opts = {
        'format': format_string,
        'quiet': False,
        'no_warnings': False,
    }

    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as ytdl:
            info = ytdl.extract_info(url, download=False)
            print(f"\n>> SUCCESS!")
            print(f"  Title: {info.get('title')}")
            print(f"  Duration: {info.get('duration')}s")
            print(f"  Selected format: {info.get('format', 'N/A')}")
            print(f"  Format ID: {info.get('format_id', 'N/A')}")
            print(f"  Ext: {info.get('ext', 'N/A')}")
            return True
    except Exception as e:
        print(f"\n>> FAILED: {str(e)}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_format_pi.py <youtube_url>")
        print("Example: python test_format_pi.py https://www.youtube.com/watch?v=S5cOAb2mSWU")
        sys.exit(1)

    url = sys.argv[1]

    # List all formats
    list_formats(url)

    # Test different format strings
    test_formats = [
        'bestaudio/best',
        'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        'bestaudio[acodec=opus]/bestaudio',
    ]

    print(f"\n\n{'='*60}")
    print("Testing different format strings:")
    print(f"{'='*60}")

    for fmt in test_formats:
        test_format_extraction(url, fmt)
