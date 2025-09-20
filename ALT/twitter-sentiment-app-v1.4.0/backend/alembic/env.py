from __future__ import with_statement
from alembic import context
from sqlalchemy import engine_from_config,pool
from logging.config import fileConfig
import os,sys
from dotenv import load_dotenv
load_dotenv()
config=context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option('sqlalchemy.url', os.getenv('DB_URL','postgresql+psycopg://postgres:Postgres123@127.0.0.1:5432/sentiment'))
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from db import Base
meta=Base.metadata

def run_migrations_offline():
    url=config.get_main_option('sqlalchemy.url')
    context.configure(url=url,target_metadata=meta,literal_binds=True,dialect_opts={'paramstyle':'named'})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    conn=engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',poolclass=pool.NullPool).connect()
    with conn:
        context.configure(connection=conn,target_metadata=meta)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
