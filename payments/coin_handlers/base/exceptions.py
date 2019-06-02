class CoinHandlerException(Exception):
    """Base exception for all Coin handler exceptions to inherit"""
    pass


class TokenNotFound(CoinHandlerException):
    """The token/coin requested doesn't exist"""
    pass


class AccountNotFound(CoinHandlerException):
    """The sending or receiving account requested doesn't exist"""
    pass


class NotEnoughBalance(CoinHandlerException):
    """The sending account does not have enough balance for this operation"""
    pass


class AuthorityMissing(CoinHandlerException):
    """Missing private key or other authorization for this operation"""
    pass


class IssueNotSupported(CoinHandlerException):
    """This class does not support issuing, the token name cannot be issued, or other issue problems."""
    pass


class IssuerKeyError(AuthorityMissing):
    """Attempted to issue tokens you don't have the issuer key for"""
    pass


class DeadAPIError(CoinHandlerException):
    """A main API, e.g. a coin daemon or public node used by this coin handler is offline."""
    pass


class MissingTokenMetadata(CoinHandlerException):
    """
    Could not process a transaction or run the requested Loader/Manager method as required coin metadata is missing,
    such as :py:attr:`payments.models.Coin.our_account` or a required key in the custom JSON settings.
    """
    pass
