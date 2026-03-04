#!/bin/bash
set -e

echo "=== Health App Backend Starting ==="

# Wait for PostgreSQL to be ready
if [ -n "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL at $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
    for i in $(seq 1 30); do
        if python -c "
import socket, sys, os
host = os.environ.get('POSTGRES_HOST', 'localhost')
port = int(os.environ.get('POSTGRES_PORT', '5432'))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect((host, port))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "PostgreSQL is ready!"
            break
        fi
        echo "Attempt $i/30: PostgreSQL not ready, waiting..."
        sleep 2
    done
fi

# Initialize database tables via SQLAlchemy
echo "Initializing database tables..."
python -c "
from app.database import engine, Base
from app.models import *
Base.metadata.create_all(bind=engine)
print('Database tables initialized successfully')
"

echo "Starting application..."
exec "$@"
