#!/bin/bash
# IB Gateway startup script
# Follows the proven ghcr.io/unusualalpha/ib-gateway approach

echo "============================================="
echo "=== IB Gateway Startup                    ==="
echo "=== $(date)                               ==="
echo "============================================="

export DISPLAY=:1

# Wait for Xvfb to be ready (check for X11 socket)
echo "Waiting for Xvfb..."
for i in $(seq 1 15); do
    [ -e /tmp/.X11-unix/X1 ] && break
    sleep 1
done
echo "Xvfb ready (waited ${i}s)"

# Detect IB Gateway version
VERSION=$(cat /root/Jts/ibgateway-version.txt 2>/dev/null)
if [ -z "$VERSION" ]; then
    VERSION=$(ls /root/Jts/ibgateway/ 2>/dev/null | head -1)
fi

if [ -z "$VERSION" ]; then
    echo "FATAL: Cannot detect IB Gateway version"
    ls -la /root/Jts/ 2>/dev/null
    exit 1
fi

echo "IB Gateway version: $VERSION"
GATEWAY_PATH="/root/Jts/ibgateway/$VERSION"

# Verify installation
echo "Gateway path: $GATEWAY_PATH"
ls -la "$GATEWAY_PATH/jars/" 2>/dev/null | head -3 || echo "WARNING: No jars found"
ls "$GATEWAY_PATH/"*.vmoptions 2>/dev/null || echo "WARNING: No vmoptions found"

# Template IBC config from environment variables
# Only substitutes TRADING_MODE and READ_ONLY_API, leaves everything else intact
if [ -f /root/ibc/config.ini.tmpl ]; then
    envsubst '${TRADING_MODE} ${READ_ONLY_API}' < /root/ibc/config.ini.tmpl > /root/ibc/config.ini
    echo "IBC config templated from environment"
fi

# Build IBC arguments (matches community image's run.sh)
IBC_ARGS="$VERSION"
IBC_ARGS="$IBC_ARGS -g"
IBC_ARGS="$IBC_ARGS --tws-path=/root/Jts"
IBC_ARGS="$IBC_ARGS --ibc-path=/root/ibc"
IBC_ARGS="$IBC_ARGS --ibc-ini=/root/ibc/config.ini"

# Add credentials for automated login (if provided via Railway env vars)
if [ -n "$TWS_USERID" ]; then
    echo "Automated login enabled for user: $TWS_USERID"
    IBC_ARGS="$IBC_ARGS --user=$TWS_USERID --pw=$TWS_PASSWORD"
else
    echo "Manual login mode — use VNC to enter credentials"
fi

IBC_ARGS="$IBC_ARGS --mode=${TRADING_MODE:-paper}"
# Do NOT restart on 2FA timeout — let user complete manually via VNC
IBC_ARGS="$IBC_ARGS --on2fatimeout=${TWOFA_TIMEOUT_ACTION:-exit}"

# Detect bundled JRE (installed by IB Gateway's install4j installer)
# This is the PROVEN approach — no system OpenJDK needed
if [ -f "$GATEWAY_PATH/.install4j/inst_jre.cfg" ]; then
    BUNDLED_JRE=$(cat "$GATEWAY_PATH/.install4j/inst_jre.cfg" 2>/dev/null)
    if [ -x "$BUNDLED_JRE/bin/java" ]; then
        echo "Using bundled JRE: $BUNDLED_JRE"
        "$BUNDLED_JRE/bin/java" -version 2>&1 | head -1
        IBC_ARGS="$IBC_ARGS --java-path=$BUNDLED_JRE/bin"
    else
        echo "WARNING: Bundled JRE not executable at $BUNDLED_JRE"
    fi
else
    echo "WARNING: No inst_jre.cfg found, IBC will search for Java"
fi

echo ""
echo "Launching: /root/ibc/scripts/ibcstart.sh $IBC_ARGS"
echo ""

exec /root/ibc/scripts/ibcstart.sh $IBC_ARGS
