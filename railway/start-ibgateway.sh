#!/bin/bash
# Read the installed version
if [ -f "/opt/ibgateway/VERSION.txt" ]; then
    INSTALLED_VERSION=$(cat /opt/ibgateway/VERSION.txt)
    VERSION_SHORT=$(echo $INSTALLED_VERSION | tr -d '.')
    echo "=== Starting IB Gateway Version $INSTALLED_VERSION ==="
    echo "Using path: /opt/ibgateway/$VERSION_SHORT"
    
    # Verify jars folder exists
    if [ ! -d "/opt/ibgateway/$VERSION_SHORT/jars" ]; then
        echo "ERROR: jars folder not found at /opt/ibgateway/$VERSION_SHORT/jars"
        echo "Contents of /opt/ibgateway:"
        ls -laR /opt/ibgateway/
        exit 1
    fi
    
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
