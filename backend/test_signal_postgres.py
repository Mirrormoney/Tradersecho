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
