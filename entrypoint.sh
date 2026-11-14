#!/bin/sh
set -eu
# Schema changes run once in the dedicated migrate service.
exec "$@"
