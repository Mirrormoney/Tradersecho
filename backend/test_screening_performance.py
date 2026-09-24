import random
from difflib import SequenceMatcher
from .screening import _same_template, _characters


def test_template_optimization_preserves_previous_decisions():
    rng=random.Random(742)
    pairs=[('', ''),('short','short'),('short','shorter'),('a'*100,'a'*90+'b'*10),
           ('a'*100,'a'*89+'b'*11),('a'*400,'b'*400)]
    for length in (20,31,80,200,500):
        for _ in range(30):
            text=''.join(rng.choices('abcdefghij ',k=length))
            edited=list(text)
            for i in rng.sample(range(length),max(1,length//12)):
                edited[i]=rng.choice('abcdefghij ')
            pairs.extend([(text,''.join(edited)),(text,text[:length//2])])
    for text,other in pairs:
        expected=text==other or (len(text)>30 and SequenceMatcher(None,text,other).ratio()>.9)
        assert _same_template(text,other)==expected
        reverse=other==text or (len(other)>30 and SequenceMatcher(None,other,text).ratio()>.9)
        assert _same_template(other,text)==reverse


def test_clearly_unrelated_long_posts_skip_expensive_comparison(monkeypatch):
    from . import screening
    _same_template.cache_clear();_characters.cache_clear()
    def unexpected(*args,**kwargs):
        raise AssertionError('Unrelated posts must not run quadratic matching')
    monkeypatch.setattr(screening,'SequenceMatcher',unexpected)
    assert not _same_template('a'*1000,'b'*1000)
    assert not _same_template('same words '*100,'same words ')
