from p2pbot.db import Repository


def test_idempotency_kill_switch_and_events(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path / 'db.sqlite3'}")
    repo.create_schema()
    assert repo.claim_idempotency('x') is True
    assert repo.claim_idempotency('x') is False
    assert repo.kill_switch_enabled() is False
    repo.set_state('kill_switch', 'true')
    assert repo.kill_switch_enabled() is True
    repo.append_event('TEST', payload={'ok': True})
    assert repo.recent_events(1)[0]['event_type'] == 'TEST'
