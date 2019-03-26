class TokenNotFound(BaseException):
    """The token/coin requested doesn't exist"""
    pass


class AccountNotFound(BaseException):
    """The sending or receiving account requested doesn't exist"""
    pass


class NotEnoughBalance(BaseException):
    """The sending account does not have enough balance for this operation"""
    pass


class AuthorityMissing(BaseException):
    """Missing private key or other authorization for this operation"""
    pass


class IssueNotSupported(BaseException):
    """This class does not support issuing, the token name cannot be issued, or other issue problems."""
    pass


class IssuerKeyError(AuthorityMissing):
    """Attempted to issue tokens you don't have the issuer key for"""
    pass


class DeadAPIError(BaseException):
    """A main API, e.g. a coin daemon or public node used by this coin handler is offline."""
    pass
