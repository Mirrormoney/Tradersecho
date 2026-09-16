"""Small DB-API bridge: persistent PostgreSQL in Vercel, SQLite for offline tests.

Only the SQL forms used by this application are translated. All values remain
driver parameters. PostgreSQL transactions replace SQLite's immediate writer lock.
"""
import os, re, sqlite3
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

IntegrityError = (sqlite3.IntegrityError, psycopg.IntegrityError)

class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Result:
    def __init__(self, cursor=None, rows=None, lastrowid=None):
        self.cursor=cursor; self.rows=rows; self.lastrowid=lastrowid
        self.rowcount=cursor.rowcount if cursor else 0
    def fetchone(self):
        row=self.rows.pop(0) if self.rows else (self.cursor.fetchone() if self.cursor else None)
        return Row(row) if row is not None else None
    def fetchall(self):
        rows=self.rows if self.rows is not None else self.cursor.fetchall()
        self.rows=[]
        return [Row(r) for r in rows]
    def __iter__(self): return iter(self.fetchall())

def translate(sql):
    sql=sql.strip()
    sql=re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY', sql, flags=re.I)
    sql=re.sub(r'\bREAL\b','DOUBLE PRECISION',sql,flags=re.I)
    sql=re.sub(r'SUM\(([^()]+(?:=|>|<)[^()]+)\)',r'SUM(CAST(\1 AS INTEGER))',sql)
    sql=sql.replace('MIN(13,CAST(', 'LEAST(13,CAST(')
    sql=sql.replace('GROUP_CONCAT(DISTINCT m.ticker)', "STRING_AGG(DISTINCT m.ticker, ',')")
    sql=sql.replace('count=count+1','count=attempts.count+1')
    if re.match(r'INSERT OR IGNORE',sql,re.I):
        sql=re.sub(r'INSERT OR IGNORE','INSERT',sql,flags=re.I)+' ON CONFLICT DO NOTHING'
    if re.match(r'INSERT OR REPLACE INTO meta',sql,re.I):
        sql=re.sub(r'INSERT OR REPLACE','INSERT',sql,flags=re.I)+' ON CONFLICT(key) DO UPDATE SET value=excluded.value'
    # Do not substitute question marks or percent signs inside quoted literals.
    parts=re.split("('(?:''|[^'])*')",sql)
    return ''.join(re.sub(r'\bend\b', '"end"', p).replace('?', '%s') if i%2==0 else p.replace('%','%%') for i,p in enumerate(parts))

class Postgres:
    def __init__(self, connection): self.connection=connection
    def executemany(self, sql, rows):
        # psycopg batches these commands in pipeline mode: one network exchange,
        # rather than one exchange for every historical hour.
        cursor = self.connection.cursor()
        cursor.executemany(translate(sql), rows)
        return Result(cursor, rows=[])
    def execute(self,sql,args=()):
        if sql.strip().upper()=='BEGIN IMMEDIATE':
            return Result(self.connection.execute('SELECT pg_advisory_xact_lock(742091826)'))
        if sql.startswith('PRAGMA table_info('):
            table=sql.split('(')[1].split(')')[0]
            return Result(self.connection.execute('SELECT column_name AS name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s',(table,)))
        if sql.strip().upper().startswith('PRAGMA'): return Result(rows=[])
        sql=translate(sql)
        serial=bool(re.match(r'INSERT INTO (chat_messages|audit_log|x_spend|collection_jobs)\b',sql,re.I))
        if serial and 'RETURNING' not in sql.upper(): sql+=' RETURNING id'
        cursor=self.connection.execute(sql,args)
        if serial:
            result=cursor.fetchone()
            return Result(cursor,rows=[],lastrowid=result['id'] if result else None)
        return Result(cursor)
    def executescript(self,script):
        for statement in script.split(';'):
            if statement.strip(): self.execute(statement)

@contextmanager
def connect(sqlite_path):
    url=os.getenv('APP_DATABASE_URL') or os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
    if os.getenv('VERCEL') and not url:
        raise RuntimeError('Persistent DATABASE_URL is required on Vercel; SQLite fallback is disabled.')
    if url:
        with psycopg.connect(url,connect_timeout=10,row_factory=dict_row) as connection:
            schema=os.getenv('TRADERSECHO_SCHEMA','public')
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',schema): raise ValueError('Invalid database schema')
            connection.execute(psycopg.sql.SQL('SET LOCAL search_path TO {}').format(psycopg.sql.Identifier(schema)))
            yield Postgres(connection)
    else:
        Path(sqlite_path).parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(sqlite_path,timeout=30)
        connection.row_factory=sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback();raise
        finally: connection.close()
