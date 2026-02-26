#!/bin/sh
# Match the container's docker group GID to the host's Docker socket GID
# so the infrakt user can run docker commands via the mounted socket.

SOCKET=/var/run/docker.sock

if [ -S "$SOCKET" ]; then
    HOST_GID=$(stat -c '%g' "$SOCKET" 2>/dev/null)
    CURRENT_GID=$(getent group docker | cut -d: -f3)
    if [ -n "$HOST_GID" ] && [ "$HOST_GID" != "0" ] && [ "$HOST_GID" != "$CURRENT_GID" ]; then
        groupmod -g "$HOST_GID" docker 2>/dev/null || true
    fi
fi

# Drop to non-root user and exec the main command
exec gosu infrakt "$@"
