#!/bin/bash
################################################################################
# Deno Setup Script for yt-dlp YouTube Challenge Solving
#
# This script installs Deno and configures yt-dlp to use it for JavaScript
# challenge solving, which is required for reliable YouTube video extraction.
#
# Usage:
#   bash setup_deno_yt-dlp.sh
#
# Requirements:
#   - curl
#   - bash
#   - Write access to home directory
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DENO_INSTALL_DIR="$HOME/.deno"
DENO_BIN="$DENO_INSTALL_DIR/bin/deno"
YT_DLP_CONFIG_DIR="$HOME/.config/yt-dlp"
BASHRC="$HOME/.bashrc"

echo "======================================================================"
echo "  Deno Setup for yt-dlp YouTube Challenge Solving"
echo "======================================================================"
echo

# Check if Deno is already installed
if [ -f "$DENO_BIN" ]; then
    echo -e "${GREEN}✓${NC} Deno is already installed at: $DENO_BIN"
    $DENO_BIN --version
    echo
else
    echo -e "${YELLOW}Installing Deno...${NC}"
    curl -fsSL https://deno.land/install.sh | sh
    echo -e "${GREEN}✓${NC} Deno installed successfully"
    $DENO_BIN --version
    echo
fi

# Add Deno to PATH in .bashrc if not already there
if grep -q "$DENO_INSTALL_DIR/bin" "$BASHRC"; then
    echo -e "${GREEN}✓${NC} Deno already in PATH in $BASHRC"
else
    echo -e "${YELLOW}Adding Deno to PATH in $BASHRC...${NC}"
    echo "" >> "$BASHRC"
    echo "# Deno JavaScript runtime for yt-dlp" >> "$BASHRC"
    echo "export PATH=\"$DENO_INSTALL_DIR/bin:\$PATH\"" >> "$BASHRC"
    echo -e "${GREEN}✓${NC} Added Deno to PATH"
    echo
fi

# Create yt-dlp config directory
if [ -d "$YT_DLP_CONFIG_DIR" ]; then
    echo -e "${GREEN}✓${NC} yt-dlp config directory already exists: $YT_DLP_CONFIG_DIR"
else
    echo -e "${YELLOW}Creating yt-dlp config directory...${NC}"
    mkdir -p "$YT_DLP_CONFIG_DIR"
    echo -e "${GREEN}✓${NC} Created $YT_DLP_CONFIG_DIR"
fi

# Create/update yt-dlp config
YT_DLP_CONFIG="$YT_DLP_CONFIG_DIR/config"
if [ -f "$YT_DLP_CONFIG" ]; then
    if grep -q "js-runtimes" "$YT_DLP_CONFIG"; then
        echo -e "${GREEN}✓${NC} yt-dlp config already has js-runtimes configured"
    else
        echo -e "${YELLOW}Adding js-runtimes to existing yt-dlp config...${NC}"
        echo "--js-runtimes deno:$DENO_INSTALL_DIR/bin" >> "$YT_DLP_CONFIG"
        echo -e "${GREEN}✓${NC} Added js-runtimes to $YT_DLP_CONFIG"
    fi
else
    echo -e "${YELLOW}Creating yt-dlp config...${NC}"
    echo "--js-runtimes deno:$DENO_INSTALL_DIR/bin" > "$YT_DLP_CONFIG"
    echo -e "${GREEN}✓${NC} Created $YT_DLP_CONFIG"
fi
echo

# Verify setup
echo "======================================================================"
echo "  Verification"
echo "======================================================================"
echo

# Check Deno is in current PATH
if command -v deno &> /dev/null; then
    echo -e "${GREEN}✓${NC} Deno is available in current PATH"
else
    echo -e "${YELLOW}⚠${NC} Deno is not in current PATH. You may need to run:"
    echo "    source $BASHRC"
    echo "    or log out and log back in"
fi
echo

# Check Deno binary works
if [ -f "$DENO_BIN" ]; then
    echo "Deno version:"
    $DENO_BIN --version
    echo
fi

# Show yt-dlp config
if [ -f "$YT_DLP_CONFIG" ]; then
    echo "yt-dlp config ($YT_DLP_CONFIG):"
    cat "$YT_DLP_CONFIG"
    echo
fi

echo "======================================================================"
echo "  Setup Complete!"
echo "======================================================================"
echo
echo "Next steps:"
echo "  1. Source your .bashrc or restart your shell:"
echo "     source $BASHRC"
echo
echo "  2. Verify Deno works:"
echo "     deno --version"
echo
echo "  3. Test yt-dlp with a YouTube video:"
echo "     python test_music_format.py 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'"
echo
echo "Python configuration (add this to your yt-dlp options):"
echo "  'js_runtimes': {'deno': {'path': '$DENO_INSTALL_DIR/bin'}},"
echo "  'remote_components': {'ejs:github'},"
echo
