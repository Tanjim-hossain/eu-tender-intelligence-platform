from tendergraph.auth.security import (
    create_session_token,
    hash_password,
    session_token_hash,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("scrypt$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)
    assert "correct horse battery staple" not in encoded


def test_session_tokens_are_opaque_and_hashed() -> None:
    token = create_session_token()
    digest = session_token_hash(token)

    assert len(token) >= 32
    assert len(digest) == 64
    assert token not in digest
