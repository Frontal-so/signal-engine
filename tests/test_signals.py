from engine import signals


def test_canonical_resolves_aliases():
    assert signals.canonical("job_repost_2nd") == "job_repost"
    assert signals.canonical("Series B raised") == "funding_round"
    assert signals.canonical("appointed new CRO") == "new_leader"
    assert signals.canonical("") is None


def test_announced_vs_watched():
    assert signals.is_announced("funding_round")
    assert not signals.is_announced("pricing_page_visit")
    assert "layoffs" in signals.HOLD
    assert all(s in signals.TYPES for v in signals.FROM_SOURCE.values() for s in v)
