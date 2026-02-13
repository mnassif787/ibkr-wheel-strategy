#!/bin/bash
# Substitute environment variables in IBC config at runtime
envsubst < /opt/ibc/config.ini.template > /opt/ibc/config.ini

# Run IBC with proper arguments
exec /opt/ibc/scripts/ibcstart.sh \
    10.19 \
    --gateway \
    --tws-path=/opt/ibgateway \
    --ibc-path=/opt/ibc \
    --ibc-ini=/opt/ibc/config.ini \
    --mode=${IBKR_TRADING_MODE:-paper}
