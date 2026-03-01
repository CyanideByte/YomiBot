# yt-dlp Deno Setup Summary

**Date:** 2026-02-28

## Overview
Configured yt-dlp to use Deno JavaScript runtime for YouTube challenge solving. This ensures reliable video/audio extraction as YouTube increasingly requires JavaScript challenges for format access.

---

## Files Modified (for git commit)

### 1. `test_music_format.py`
Added JavaScript runtime and remote components support to yt-dlp options in two places:

```python
'js_runtimes': {'deno': {'path': '/home/cyanide/.deno/bin'}},
'remote_components': {'ejs:github'},
```

### 2. `src/music/music_sources.py`
Added the same options to `ytdl_format_options` dictionary:

```python
# JavaScript runtime for YouTube challenge solving
'js_runtimes': {'deno': {'path': '/home/cyanide/.deno/bin'}},
'remote_components': {'ejs:github'},
```

---

## System Changes (not for git, but required for the bot to work)

### 3. `~/.bashrc`
Added deno to PATH:

```bash
export PATH="$HOME/.deno/bin:$PATH"
```

### 4. `~/.config/yt-dlp/config` (new file)
Created yt-dlp config:

```
--js-runtimes deno:/home/cyanide/.deno/bin
```

### 5. Deno Installed
- **Location:** `~/.deno/bin/deno`
- **Version:** 2.7.1 (stable, aarch64-unknown-linux-gnu)
- **Installed via:** `curl -fsSL https://deno.land/install.sh | sh`

---

## Test Results

All format strings tested successfully:

| Format String | Format ID | Extension | Codec |
|--------------|-----------|-----------|-------|
| `bestaudio/best` | 251 | webm | opus |
| `bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best` | 140 | m4a | mp4a.40.2 |
| `bestaudio[acodec=opus]/bestaudio` | 251 | webm | opus |

---

## Why These Changes?

### JavaScript Runtime
YouTube now requires JavaScript challenge solving to access certain video formats. Without a JS runtime:
- Some formats may be missing
- Extraction may fail as YouTube updates protections
- Warnings appear about deprecated extraction methods

### Remote Components (ejs:github)
- Enables automatic download of challenge solver scripts from GitHub
- Recommended by yt-dlp for complete YouTube support
- Future-proofs the bot against YouTube changes

---

## Git Commit Message Suggestion

```
Configure yt-dlp with Deno JS runtime for YouTube

- Add js_runtimes configuration to enable Deno for YouTube challenge solving
- Enable remote_components (ejs:github) for automatic solver script downloads
- Update test_music_format.py and music_sources.py

This ensures reliable YouTube extraction as YouTube increasingly requires
JavaScript challenge solving for format access.
```

---

## Setup Commands (for reference)

```bash
# Install Deno
curl -fsSL https://deno.land/install.sh | sh

# Add to PATH (already added to ~/.bashrc)
export PATH="$HOME/.deno/bin:$PATH"

# Create yt-dlp config
mkdir -p ~/.config/yt-dlp
echo "--js-runtimes deno:/home/cyanide/.deno/bin" > ~/.config/yt-dlp/config

# Verify Deno is working
~/.deno/bin/deno --version

# Test the configuration
source venv/bin/activate
python test_music_format.py "https://www.youtube.com/watch?v=S5cOAb2mSWU"
```
