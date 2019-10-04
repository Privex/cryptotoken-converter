from privex.coin_handlers.KeyStore import DjangoKeyStore, KeyPair
from steemengine.helpers import decrypt_str


class EncryptedKeyStore(DjangoKeyStore):
    """
    Wrap :class:`.DjangoKeyStore` and decrypt private keys after they're loaded from the DB.
    """
    def get(self, **kwargs) -> KeyPair:
        key = super(EncryptedKeyStore, self).get(**kwargs)
        key.private_key = decrypt_str(key.private_key)
        return key
