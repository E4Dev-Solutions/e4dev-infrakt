from cli.core.crypto import decrypt, decrypt_env_dict, encrypt, encrypt_env_dict


def test_encrypt_decrypt_roundtrip(isolated_config):
    original = "my-secret-value"
    token = encrypt(original)
    assert token != original
    assert decrypt(token) == original


def test_encrypt_env_dict_roundtrip(isolated_config):
    env = {"DB_PASSWORD": "secret123", "API_KEY": "abc-def"}
    encrypted = encrypt_env_dict(env)
    assert encrypted["DB_PASSWORD"] != "secret123"
    decrypted = decrypt_env_dict(encrypted)
    assert decrypted == env
