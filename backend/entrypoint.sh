#!/bin/bash
set -e

# Run migrations only if the first arg is uvicorn (API server)
if [[ "$1" == "uvicorn" ]]; then
    echo "Running database migrations..."
    cd /app
    alembic upgrade head 2>&1 || {
        echo "Alembic migration failed, falling back to create_all..."
        python -c "
from app.db.base import Base
from app.models import *
from sqlalchemy import create_engine
import os
url = os.getenv('DATABASE_URL_SYNC', 'postgresql://plagiarism:plagiarism@postgres:5432/plagiarism')
engine = create_engine(url)
Base.metadata.create_all(engine)
print('Tables created via create_all')
engine.dispose()
" 2>&1 || echo "Warning: Could not create tables"
    }
fi

echo "Starting: $@"
exec "$@"
