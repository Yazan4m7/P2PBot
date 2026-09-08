from p2pbot.config import Settings


def test_preferred_payment_methods_accepts_empty_string(monkeypatch):
    monkeypatch.setenv('PREFERRED_PAYMENT_METHODS', '')
    settings = Settings(_env_file=None)
    assert settings.preferred_payment_methods == []


def test_preferred_payment_methods_accepts_csv(monkeypatch):
    monkeypatch.setenv('PREFERRED_PAYMENT_METHODS', 'cliq, bank_transfer')
    settings = Settings(_env_file=None)
    assert settings.preferred_payment_methods == ['CLIQ', 'BANK_TRANSFER']


def test_preferred_payment_methods_accepts_json_list(monkeypatch):
    monkeypatch.setenv('PREFERRED_PAYMENT_METHODS', '["cliq", "bank_transfer"]')
    settings = Settings(_env_file=None)
    assert settings.preferred_payment_methods == ['CLIQ', 'BANK_TRANSFER']
