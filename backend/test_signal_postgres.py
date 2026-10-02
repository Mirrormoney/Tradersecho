"""Optional real PostgreSQL regression: TEST_POSTGRES_URL points to a test DB."""
import json
import os
import pytest

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='PostgreSQL test connection not supplied')
def test_fallback_survives_null_in_unrelated_research():
    import psycopg
    from psycopg.rows import dict_row
    from .database import Postgres
    from .signal_lab import retain_valid_axes, VERSION
    with psycopg.connect(os.environ['TEST_POSTGRES_URL'], row_factory=dict_row) as raw:
        try:
            raw.execute('CREATE TEMP TABLE signal_lab_snapshots(ticker TEXT, observed DOUBLE PRECISION, version TEXT, payload TEXT) ON COMMIT DROP')
            axes=[{'score':50,'details':{}} for _ in range(5)]
            axes[4]['reason']='Source text with an invisible\x00character.'
            payload=json.dumps({'axes':axes})
            raw.execute('INSERT INTO pg_temp.signal_lab_snapshots VALUES(%s,%s,%s,%s)',('TEST',100,VERSION,payload))
            panel={'ticker':'TEST','axes':[{'score':None}]+axes[1:]}
            retain_valid_axes(Postgres(raw),[panel],200)
            assert panel['axes'][0]['score']==50
            assert panel['axes'][0]['carried_forward'] is True
            assert raw.execute('SELECT payload FROM pg_temp.signal_lab_snapshots').fetchone()['payload']==payload
        finally:
            raw.rollback()

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='PostgreSQL test connection not supplied')
def test_detail_history_survives_null_in_research():
    import psycopg,time
    from psycopg.rows import dict_row
    from .database import Postgres
    from .signal_history import detail
    from .signal_lab import VERSION,TITLES
    with psycopg.connect(os.environ['TEST_POSTGRES_URL'], row_factory=dict_row) as raw:
        try:
            raw.execute('CREATE TEMP TABLE signal_lab_snapshots(ticker TEXT, slot BIGINT, observed DOUBLE PRECISION, version TEXT, payload TEXT) ON COMMIT DROP')
            raw.execute('CREATE TEMP TABLE signal_x_history(ticker TEXT,version TEXT,source_end DOUBLE PRECISION,observed DOUBLE PRECISION,score DOUBLE PRECISION,payload TEXT) ON COMMIT DROP')
            now=time.time()
            axes=[dict(name=n,score=50,strength=50,state='ready',reason='research\x00text') for n in TITLES]
            payload=json.dumps({'axes':axes})
            raw.execute('INSERT INTO pg_temp.signal_lab_snapshots VALUES(%s,%s,%s,%s,%s)',('TEST',int(now//600),now,VERSION,payload))
            result=detail(Postgres(raw),'TEST',now+1)
            assert all(a['score']==50 and a['points'][0]['value']==50 for a in result['axes'])
            assert raw.execute('SELECT payload FROM pg_temp.signal_lab_snapshots').fetchone()['payload']==payload
        finally:
            raw.rollback()
