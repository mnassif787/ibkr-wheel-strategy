#!/bin/bash
# Substitute environment variables in IBC config at runtime
envsubst < /opt/ibc/config.ini.template > /opt/ibc/config.ini

# Set default trading mode if not provided
TRADING_MODE="${IBKR_TRADING_MODE:-paper}"

# Run IBC with proper arguments
exec /opt/ibc/scripts/ibcstart.sh \
    10.19 \
    --gateway \
    --tws-path=/opt/ibgateway \
    --ibc-path=/opt/ibc \
    --ibc-ini=/opt/ibc/config.ini \
    --mode="$TRADING_MODE"
