#!/bin/bash
# Run IBC with proper arguments
# No need for envsubst since config has hardcoded values
exec /opt/ibc/scripts/ibcstart.sh \
    10.19 \
    --gateway \
    --tws-path=/opt/ibgateway \
    --ibc-path=/opt/ibc \
    --ibc-ini=/opt/ibc/config.ini \
    --mode=paper
