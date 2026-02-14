#!/bin/bash
# Note: NOT using set -e because we need to catch IBC exit code 7 and fallback

echo "============================================="
echo "=== IB Gateway Startup Script             ==="
echo "=== Date: $(date)                         ==="
echo "============================================="

# Read the installed version
if [ ! -f "/opt/ibgateway/VERSION.txt" ]; then
    echo "FATAL: VERSION.txt not found at /opt/ibgateway/VERSION.txt"
    echo "Contents of /opt/ibgateway:"
    ls -laR /opt/ibgateway/ 2>/dev/null || echo "  directory does not exist"
    exit 1
fi

INSTALLED_VERSION=$(cat /opt/ibgateway/VERSION.txt)
echo "IB Gateway Version: $INSTALLED_VERSION"

# Ensure DISPLAY is set for X11 GUI (Xvfb runs on :1 via supervisor)
export DISPLAY=${DISPLAY:-:1}
echo "DISPLAY=$DISPLAY"
echo ""

# ----------------------------------------------------------------
# IBC 3.17.0 path resolution for --gateway mode on Linux:
#   gateway_program_path = $TWS_PATH/ibgateway/$VERSION
#   tws_program_path     = $TWS_PATH/$VERSION (fallback)
#
# IBC first checks gateway_program_path/jars.
#   If found → uses ibgateway.vmoptions from gateway_program_path
#   If NOT found → falls back to tws_program_path with tws.vmoptions
#
# We create BOTH paths at build time, but verify/repair at runtime
# in case Docker layers or Railway cause files to go missing.
# ----------------------------------------------------------------

GATEWAY_PATH="/opt/ibgateway/ibgateway/$INSTALLED_VERSION"
TWS_FALLBACK_PATH="/opt/ibgateway/$INSTALLED_VERSION"

echo "=== Runtime File Verification ==="
echo ""

# Verify/repair GATEWAY path (primary)
echo "--- Primary gateway path: $GATEWAY_PATH ---"
mkdir -p "$GATEWAY_PATH"

if [ ! -d "$GATEWAY_PATH/jars" ]; then
    echo "  WARNING: jars missing, copying from /opt/ibgateway/jars"
    if [ -d "/opt/ibgateway/jars" ]; then
        cp -r /opt/ibgateway/jars "$GATEWAY_PATH/"
    else
        echo "  FATAL: No source jars found at /opt/ibgateway/jars"
        exit 1
    fi
fi

if [ ! -d "$GATEWAY_PATH/.install4j" ]; then
    echo "  WARNING: .install4j missing, copying from /opt/ibgateway/.install4j"
    if [ -d "/opt/ibgateway/.install4j" ]; then
        cp -r /opt/ibgateway/.install4j "$GATEWAY_PATH/"
    fi
fi

if [ ! -f "$GATEWAY_PATH/ibgateway.vmoptions" ]; then
    echo "  WARNING: ibgateway.vmoptions missing, creating"
    if ls /opt/ibgateway/*.vmoptions 1>/dev/null 2>&1; then
        cp /opt/ibgateway/*.vmoptions "$GATEWAY_PATH/"
    else
        echo -e "-Xmx768m\n-XX:+UseG1GC\n-XX:MaxGCPauseMillis=200" > "$GATEWAY_PATH/ibgateway.vmoptions"
    fi
fi

echo "  Contents:"
ls -la "$GATEWAY_PATH/" 2>/dev/null | head -15

# Verify/repair TWS FALLBACK path
echo ""
echo "--- TWS fallback path: $TWS_FALLBACK_PATH ---"
mkdir -p "$TWS_FALLBACK_PATH"

if [ ! -d "$TWS_FALLBACK_PATH/jars" ]; then
    echo "  WARNING: jars missing, copying from /opt/ibgateway/jars"
    if [ -d "/opt/ibgateway/jars" ]; then
        cp -r /opt/ibgateway/jars "$TWS_FALLBACK_PATH/"
    fi
fi

if [ ! -d "$TWS_FALLBACK_PATH/.install4j" ]; then
    echo "  WARNING: .install4j missing, copying from /opt/ibgateway/.install4j"
    if [ -d "/opt/ibgateway/.install4j" ]; then
        cp -r /opt/ibgateway/.install4j "$TWS_FALLBACK_PATH/"
    fi
fi

# IBC looks for tws.vmoptions (not ibgateway.vmoptions) at the fallback path
if [ ! -f "$TWS_FALLBACK_PATH/tws.vmoptions" ]; then
    echo "  WARNING: tws.vmoptions missing, creating"
    if [ -f "$GATEWAY_PATH/ibgateway.vmoptions" ]; then
        cp "$GATEWAY_PATH/ibgateway.vmoptions" "$TWS_FALLBACK_PATH/tws.vmoptions"
    elif ls /opt/ibgateway/*.vmoptions 1>/dev/null 2>&1; then
        cp /opt/ibgateway/ibgateway.vmoptions "$TWS_FALLBACK_PATH/tws.vmoptions" 2>/dev/null || \
        echo -e "-Xmx768m\n-XX:+UseG1GC\n-XX:MaxGCPauseMillis=200" > "$TWS_FALLBACK_PATH/tws.vmoptions"
    else
        echo -e "-Xmx768m\n-XX:+UseG1GC\n-XX:MaxGCPauseMillis=200" > "$TWS_FALLBACK_PATH/tws.vmoptions"
    fi
fi

# Also put ibgateway.vmoptions in fallback (belt and suspenders)
if [ ! -f "$TWS_FALLBACK_PATH/ibgateway.vmoptions" ]; then
    if [ -f "$GATEWAY_PATH/ibgateway.vmoptions" ]; then
        cp "$GATEWAY_PATH/ibgateway.vmoptions" "$TWS_FALLBACK_PATH/"
    fi
fi

echo "  Contents:"
ls -la "$TWS_FALLBACK_PATH/" 2>/dev/null | head -15

echo ""
echo "--- Root /opt/ibgateway/ ---"
ls -la /opt/ibgateway/*.vmoptions 2>/dev/null || echo "  No vmoptions in root"
echo ""

# ----------------------------------------------------------------
# Determine Java path explicitly
# IBC 3.17.0 rejects OpenJDK when detecting system Java
# (only accepts "Java(TM) SE Runtime Environment" i.e. Oracle Java).
# Passing --java-path explicitly bypasses this check entirely.
# ----------------------------------------------------------------
JAVA_BIN=""

# First try: IB Gateway's bundled JRE
if [ -f "$GATEWAY_PATH/.install4j/inst_jre.cfg" ]; then
    BUNDLED_JRE=$(cat "$GATEWAY_PATH/.install4j/inst_jre.cfg" 2>/dev/null)
    if [ -x "$BUNDLED_JRE/bin/java" ]; then
        JAVA_BIN="$BUNDLED_JRE/bin"
        echo "Using bundled JRE: $JAVA_BIN"
    fi
fi

# Second try: System OpenJDK
if [ -z "$JAVA_BIN" ]; then
    if [ -x "/usr/lib/jvm/java-17-openjdk-amd64/bin/java" ]; then
        JAVA_BIN="/usr/lib/jvm/java-17-openjdk-amd64/bin"
        echo "Using system OpenJDK 17: $JAVA_BIN"
    elif [ -n "$JAVA_HOME" ] && [ -x "$JAVA_HOME/bin/java" ]; then
        JAVA_BIN="$JAVA_HOME/bin"
        echo "Using JAVA_HOME: $JAVA_BIN"
    fi
fi

if [ -z "$JAVA_BIN" ]; then
    echo "WARNING: Could not determine Java path, IBC will try to find it"
fi

# Verify Java works
if [ -n "$JAVA_BIN" ]; then
    echo "Java version:"
    "$JAVA_BIN/java" -version 2>&1 | head -3
fi

echo ""
echo "============================================="
echo "=== Pre-launch IBC Path Simulation        ==="
echo "============================================="
# Simulate exactly what IBC's ibcstart.sh will compute
echo "IBC will resolve these paths with --tws-path=/opt/ibgateway --gateway $INSTALLED_VERSION:"
echo "  gateway_program_path = /opt/ibgateway/ibgateway/$INSTALLED_VERSION"
echo "  tws_program_path     = /opt/ibgateway/$INSTALLED_VERSION"
echo ""
echo "Checking gateway_program_path/jars:"
ls -la "/opt/ibgateway/ibgateway/$INSTALLED_VERSION/jars/" 2>/dev/null | head -3 || echo "  NOT FOUND"
echo "Checking ibgateway.vmoptions in gateway_program_path:"
ls -la "/opt/ibgateway/ibgateway/$INSTALLED_VERSION/ibgateway.vmoptions" 2>/dev/null || echo "  NOT FOUND"
echo ""
echo "Checking tws_program_path/jars:"
ls -la "/opt/ibgateway/$INSTALLED_VERSION/jars/" 2>/dev/null | head -3 || echo "  NOT FOUND"
echo "Checking tws.vmoptions in tws_program_path:"
ls -la "/opt/ibgateway/$INSTALLED_VERSION/tws.vmoptions" 2>/dev/null || echo "  NOT FOUND"
echo ""

# Full tree dump for debugging
echo "=== Complete /opt/ibgateway/ tree ==="
find /opt/ibgateway -maxdepth 4 -type f -name "*.vmoptions" -o -type d -name "jars" -o -type d -name ".install4j" 2>/dev/null
echo ""

echo "============================================="
echo "=== Launching IBC                         ==="
echo "============================================="

# Build command arguments
IBC_ARGS="$INSTALLED_VERSION"
IBC_ARGS="$IBC_ARGS --gateway"
IBC_ARGS="$IBC_ARGS --tws-path=/opt/ibgateway"
IBC_ARGS="$IBC_ARGS --tws-settings-path=/opt/ibgateway"
IBC_ARGS="$IBC_ARGS --ibc-path=/opt/ibc"
IBC_ARGS="$IBC_ARGS --ibc-ini=/opt/ibc/config.ini"
IBC_ARGS="$IBC_ARGS --mode=paper"

if [ -n "$JAVA_BIN" ]; then
    IBC_ARGS="$IBC_ARGS --java-path=$JAVA_BIN"
fi

echo "Command: /opt/ibc/scripts/ibcstart.sh $IBC_ARGS"
echo ""

# Run IBC but if it fails with exit code 7 (vmoptions not found), try direct launch
/opt/ibc/scripts/ibcstart.sh $IBC_ARGS
IBC_EXIT=$?

if [ $IBC_EXIT -eq 7 ]; then
    echo ""
    echo "============================================="
    echo "=== IBC FAILED (exit 7) - Direct Launch   ==="
    echo "============================================="
    echo "IBC could not find vmoptions. Launching IB Gateway directly with Java."
    echo ""

    # Build classpath from jars
    JARS_DIR=""
    for candidate in \
        "/opt/ibgateway/ibgateway/$INSTALLED_VERSION/jars" \
        "/opt/ibgateway/$INSTALLED_VERSION/jars" \
        "/opt/ibgateway/jars"; do
        if [ -d "$candidate" ]; then
            JARS_DIR="$candidate"
            break
        fi
    done

    if [ -z "$JARS_DIR" ]; then
        echo "FATAL: Cannot find any jars directory"
        find /opt/ibgateway -type d -name jars 2>/dev/null
        exit 1
    fi

    echo "Using jars from: $JARS_DIR"

    # Build classpath
    IBC_CP=""
    for jar in "$JARS_DIR"/*.jar; do
        if [ -n "$IBC_CP" ]; then IBC_CP="$IBC_CP:"; fi
        IBC_CP="$IBC_CP$jar"
    done

    # Add install4j runtime if available
    for candidate_i4j in \
        "/opt/ibgateway/ibgateway/$INSTALLED_VERSION/.install4j" \
        "/opt/ibgateway/$INSTALLED_VERSION/.install4j" \
        "/opt/ibgateway/.install4j"; do
        if [ -f "$candidate_i4j/i4jruntime.jar" ]; then
            IBC_CP="$IBC_CP:$candidate_i4j/i4jruntime.jar"
            break
        fi
    done

    # Add IBC jar
    IBC_CP="$IBC_CP:/opt/ibc/IBC.jar"

    # Read vmoptions if available
    VM_OPTS=""
    for candidate_vm in \
        "/opt/ibgateway/ibgateway/$INSTALLED_VERSION/ibgateway.vmoptions" \
        "/opt/ibgateway/$INSTALLED_VERSION/ibgateway.vmoptions" \
        "/opt/ibgateway/$INSTALLED_VERSION/tws.vmoptions" \
        "/opt/ibgateway/ibgateway.vmoptions"; do
        if [ -f "$candidate_vm" ]; then
            while IFS= read -r line; do
                case "$line" in
                    "#"*|"-D"*|"") continue ;;
                    *) VM_OPTS="$VM_OPTS $line" ;;
                esac
            done < "$candidate_vm"
            echo "Read VM options from: $candidate_vm"
            break
        fi
    done

    if [ -z "$VM_OPTS" ]; then
        VM_OPTS="-Xmx768m -XX:+UseG1GC"
    fi

    JAVA_EXEC="${JAVA_BIN:-/usr/lib/jvm/java-17-openjdk-amd64/bin}/java"

    echo "Java: $JAVA_EXEC"
    echo "Classpath entries: $(echo "$IBC_CP" | tr ':' '\n' | wc -l)"
    echo "VM Options: $VM_OPTS"
    echo ""

    # Module access flags for Java 17+
    MODULE_ACCESS="--add-opens=java.base/java.util=ALL-UNNAMED \
--add-opens=java.base/java.util.concurrent=ALL-UNNAMED \
--add-opens=java.desktop/java.awt=ALL-UNNAMED \
--add-opens=java.desktop/javax.swing=ALL-UNNAMED \
--add-opens=java.desktop/javax.swing.event=ALL-UNNAMED"

    echo "Launching: $JAVA_EXEC $MODULE_ACCESS $VM_OPTS -DjtsConfigDir=/opt/ibgateway -cp $IBC_CP ibcalpha.ibc.IbcGateway /opt/ibc/config.ini paper"

    exec "$JAVA_EXEC" $MODULE_ACCESS $VM_OPTS \
        -DjtsConfigDir=/opt/ibgateway \
        -Dtwslaunch.autoupdate.serviceImpl=com.ib.tws.twslaunch.install4j.Install4jAutoUpdateService \
        -Dchannel=latest \
        -Dexe4j.isInstall4j=true \
        -DinstallType=standalone \
        -cp "$IBC_CP" \
        ibcalpha.ibc.IbcGateway \
        /opt/ibc/config.ini \
        paper
fi

exit $IBC_EXIT
