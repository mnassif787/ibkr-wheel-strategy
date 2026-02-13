#!/bin/bash
# Debug: Check IB Gateway installation
echo "=== Debugging IB Gateway Installation ==="
echo "Contents of /opt/ibgateway:"
ls -la /opt/ibgateway/
echo ""
echo "Looking for version folders:"
ls -d /opt/ibgateway/*/ 2>/dev/null || echo "No subdirectories found"
echo ""

# Find the actual installed version
if [ -d "/opt/ibgateway" ]; then
    # Look for Jts directory or version-specific folders
    VERSION_DIR=$(find /opt/ibgateway -type d -name "jars" | head -1)
    if [ -n "$VERSION_DIR" ]; then
        GATEWAY_PATH=$(dirname "$VERSION_DIR")
        echo "Found Gateway at: $GATEWAY_PATH"
        
        # Try to detect version from directory name
        VERSION=$(basename "$GATEWAY_PATH" | grep -oP '\d+\.\d+' | head -1)
        if [ -z "$VERSION" ]; then
            # Try looking in current directory
            VERSION=$(find "$GATEWAY_PATH" -name "*.jar" -exec basename {} \; | grep -oP '\d+\.\d+' | head -1)
        fi
        
        if [ -z "$VERSION" ]; then
            VERSION="10.19"  # fallback
        fi
        
        echo "Using version: $VERSION"
        echo "Using path: $GATEWAY_PATH"
        
        # Run IBC
        exec /opt/ibc/scripts/ibcstart.sh \
            "$VERSION" \
            --gateway \
            --tws-path="$GATEWAY_PATH" \
            --ibc-path=/opt/ibc \
            --ibc-ini=/opt/ibc/config.ini \
            --mode=paper
    else
        echo "ERROR: Could not find jars folder in /opt/ibgateway"
        ls -laR /opt/ibgateway/ | head -100
        exit 1
    fi
else
    echo "ERROR: /opt/ibgateway does not exist"
    exit 1
fi
