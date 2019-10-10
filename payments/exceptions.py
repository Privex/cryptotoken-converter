
class CTCException(Exception):
    """Base exception for CryptoToken Converter custom exceptions."""
    pass


class EncryptKeyMissing(CTCException):
    """Raised when settings.ENCRYPT_KEY is not set, or invalid"""
    pass


class EncryptionError(CTCException):
    """Raised when something went wrong attempting to encrypt or decrypt a piece of data"""
    pass


class ConvertError(CTCException):
    """
    Raised when something strange, but predicted has happened. Generally caused either by a bug, or admin mistakes.
    Deposit should set to err, and save exception msg.
    """
    pass


class ConvertInvalid(CTCException):
    """
    Raised when deposit has missing/invalid information needed to route it to a destination coin/address.
    Generally user's fault. Deposit should set to inv, and save exception msg
    """
    pass


class NotRefunding(CTCException):
    """
    Raised when a refund was skipped due to various reasons e.g. it was already refunded.
    """
    pass
