from app.core.security import normalize_email


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  User.Name+Tag@Example.COM  ") == "user.name+tag@example.com"
