"""
This is a mock coin handler, used for unit testing.

The loader and manager by default will act erratically and return random data, some of which should be valid
and some which should raise errors, to attempt to test error handling.

The mock manager and loader can be customized for more precise testing, by manually adding individual transactions,
addresses, balances etc. to them.

They both provide two fake coin symbols: 'MOCKTESTCOIN', 'FAKEDESTCOIN'

"""
from payments.coin_handlers.MockHandler.handlers import MockLoader, MockManager

exports = {
    "loader": MockLoader,
    "manager": MockManager
}
