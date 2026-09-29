#!/bin/sh
# Deliberately no environment setup, repository helpers, credentials or network.
printf '%s\n' 'Local OTA publication is disabled. Use the reviewed GitHub trusted-ota.yml workflow for the exact green main SHA.' >&2
exit 78
