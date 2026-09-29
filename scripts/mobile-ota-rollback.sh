#!/bin/sh
# A rollback is another publication and must not bypass the isolated publisher.
printf '%s\n' 'Local OTA rollback is disabled. Use the reviewed GitHub trusted-ota.yml workflow; select a reviewed corrective source revision.' >&2
exit 78
