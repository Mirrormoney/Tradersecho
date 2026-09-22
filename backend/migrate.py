"""Apply idempotent schema additions to the configured persistent database."""
import os
os.environ['VERCEL']='1'  # No implicit SQLite fallback or import-time migration.
from .service import init
if __name__=='__main__':
    init()
    print('Persistent schema ready.')
