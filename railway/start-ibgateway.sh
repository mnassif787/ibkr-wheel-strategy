#!/bin/bash
set -e

# Read the installed version
if [ -f "/opt/ibgateway/VERSION.txt" ]; then
    INSTALLED_VERSION=$(cat /opt/ibgateway/VERSION.txt)
    echo "=== Starting IB Gateway Version $INSTALLED_VERSION ==="
    echo "Expected path: /opt/ibgateway/$INSTALLED_VERSION"
    
    # Verify directory structure
    if [ ! -d "/opt/ibgateway/$INSTALLED_VERSION" ]; then
        echo "ERROR: Version directory not found at /opt/ibgateway/$INSTALLED_VERSION"
        echo "Contents of /opt/ibgateway:"
        ls -la /opt/ibgateway/
        exit 1
    fi
    
    # Verify jars folder exists
    if [ ! -d "/opt/ibgateway/$INSTALLED_VERSION/jars" ]; then
        echo "ERROR: jars folder not found at /opt/ibgateway/$INSTALLED_VERSION/jars"
        echo "Contents of version directory:"
        ls -laR "/opt/ibgateway/$INSTALLED_VERSION/"
        exit 1
    fi
    
    echo "✓ IB Gateway installation verified"
    echo "Contents of jars folder:"
    ls -1 "/opt/ibgateway/$INSTALLED_VERSION/jars/" | head -10
    echo ""
    
    # Verify vmoptions file exists (IBC needs this in root)
    echo "Checking for vmoptions files:"
    ls -la /opt/ibgateway/*.vmoptions 2>/dev/null || echo "WARNING: No vmoptions files found in /opt/ibgateway/"
    ls -la "/opt/ibgateway/$INSTALLED_VERSION/"*.vmoptions 2>/dev/null || echo "WARNING: No vmoptions files found in version directory"
    echo ""
    
    # Run IBC with detected version
    exec /opt/ibc/scripts/ibcstart.sh \
        "$INSTALLED_VERSION" \
        --gateway \
        --tws-path=/opt/ibgateway \
        --ibc-path=/opt/ibc \
        --ibc-ini=/opt/ibc/config.ini \
        --mode=paper
else
    echo "ERROR: VERSION.txt not found"
    echo "Contents of /opt/ibgateway:"
    ls -la /opt/ibgateway/
    exit 1
fi
