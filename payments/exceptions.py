
class EncryptKeyMissing(BaseException):
    """Raised when settings.ENCRYPT_KEY is not set, or invalid"""
    pass


class EncryptionError(BaseException):
    """Raised when something went wrong attempting to encrypt or decrypt a piece of data"""
    pass
