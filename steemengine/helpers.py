"""
Various helper functions for use in CryptoToken Converter.

Copyright::

    +===================================================+
    |                 © 2019 Privex Inc.                |
    |               https://www.privex.io               |
    +===================================================+
    |                                                   |
    |        CryptoToken Converter                      |
    |                                                   |
    |        Core Developer(s):                         |
    |                                                   |
    |          (+)  Chris (@someguy123) [Privex]        |
    |                                                   |
    +===================================================+

"""
import binascii
import logging
import random
import string

# characters that shouldn't be mistaken
from base64 import urlsafe_b64decode
from typing import Union

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from payments.exceptions import EncryptKeyMissing, EncryptionError

log = logging.getLogger(__name__)

SAFE_CHARS = 'abcdefhkmnprstwxyz2345679ACDEFGHJKLMNPRSTWXYZ'


def random_str(size=50, chars=SAFE_CHARS):
    return ''.join(random.SystemRandom().choice(chars) for _ in range(size))


def empty(v, zero=False, itr=False) -> bool:
    """
    Quickly check if a variable is empty or not. By default only '' and None are checked, use `itr` and `zero` to
    test for empty iterable's and zeroed variables.

    Returns True if a variable is None or '', returns False if variable passes the tests

    :param v:    The variable to check if it's empty
    :param zero: if zero=True, then return True if the variable is 0
    :param itr:  if itr=True, then return True if the variable is ``[]``, ``{}``, or is an iterable and has 0 length
    :return bool is_blank: True if a variable is blank (``None``, ``''``, ``0``, ``[]`` etc.)
    :return bool is_blank: False if a variable has content (or couldn't be checked properly)
    """

    _check = [None, '']
    if zero: _check.append(0)
    if v in _check: return True
    if itr:
        if v == [] or v == {}: return True
        if hasattr(v, '__len__') and len(v) == 0: return True

    return False


"""
----- Encryption/Decryption functions -----

Various wrapper functions for simplifying the use of the Python library cryptography's Fernet module.

encrypt/decrypt_str facilitate painless encryption and decryption of data using AES-128 CBC, they can either be passed
a 32-byte Fernet key (base64 encoded) as an argument, or leave the key as None and they'll try to use the key defined
in settings.ENCRYPT_KEY (generally set via .env file) 

get_fernet - internal use - obtain an instance of Fernet initialised with a key
is_encrypted - check if a string is encrypted or not
_crypt_str - internal use - handles the encryption/decryption for encrypt/decrypt_str
encrypt_str - encrypt a string or bytes using a given Fernet key
decrypt_str - decrypt a string or bytes that were encrypted using encrypt_str using a given Fernet key

Basic usage:

    # Generates a 32-byte symmetric key, encoded with base64. Use .decode() to convert the key to a string for storage.
    >>> k = Fernet.generate_key()
    
    # Encrypts the string 'hello world' with AES-128 CBC using key ``k`` , returned as a base64 string
    >>> enc = encrypt_str('hello world', k)
    >>> print(enc)
      gAAAAABc7ERTpu2D_uven3l-KtU_ewUC8YWKqXEbLEKrPKrKWT138MNq-I9RRtCD8UZLdQrcdM_IhUU6r8T16lQkoJZ-I7N39g==
    
    # Check if a string/bytes is encrypted
    >>> is_encrypted(enc, k)
      True
    
    # Decrypt the encrypted data using the same key, outputs as a string
    >>> data = decrypt_str(enc, k)
    >>> print(data)
      hello world

"""


def get_fernet(key: Union[str, bytes] = None) -> Fernet:
    """
    Used internally for getting Fernet instance with auto-fallback to settings.ENCRYPT_KEY and exception handling.

    :param str key: Base64 Fernet symmetric key for en/decrypting data. If empty, will fallback to settings.ENCRYPT_KEY
    :raises EncryptKeyMissing: Either no key was passed, or something is wrong with the key.
    :return Fernet f: Instance of Fernet using passed ``key`` or settings.ENCRYPT_KEY for encryption.
    """
    if empty(key) and empty(settings.ENCRYPT_KEY):
        raise EncryptKeyMissing('No key argument passed, and ENCRYPT_KEY is empty. Cannot encrypt/decrypt.')

    key = settings.ENCRYPT_KEY if empty(key) else key
    try:
        f = Fernet(key)
        return f
    except (binascii.Error, ValueError):
        raise EncryptKeyMissing('The passed ``key`` or settings.ENCRYPT_KEY is not a valid Fernet key')


def is_encrypted(data: Union[str, bytes], key: Union[str, bytes] = None) -> bool:
    """
    Returns True if the passed ``data`` appears to be encrypted. Can only verify encryption if the same ``key``
    that was used to encrypt the data is passed.

    :param str data: The data to check for encryption, either as a string or bytes
    :param str key:  Base64 encoded Fernet symmetric key for decrypting data. If empty, fallback to settings.ENCRYPT_KEY
    :raises EncryptKeyMissing: Either no key was passed, or something is wrong with the key.
    :return bool is_encrypted: True if the data is encrypted, False if it's not encrypted or wrong key used.
    """
    f = get_fernet(key)

    # Convert the passed data into bytes before trying to decode it
    data = str(data).encode('utf-8') if type(data) != bytes else data

    # Attempt to extract the Fernet timestamp from the passed data. If exceptions are raised, then it's not encrypted.
    try:
        ts = f.extract_timestamp(data)
        log.debug(f'data was encrypted, token timestamp is {ts}')
        return True
    except (InvalidSignature, InvalidToken, binascii.Error) as e:
        log.debug('data is not encrypted? exception was: %s %s', type(e), str(e))
        return False


def _crypt_str(direction: str, data: Union[str, bytes], key: Union[str, bytes] = None) -> str:
    """
    Used internally by :py:func:`encrypt_str` and :py:func:`decrypt_str`

    :param str direction: Either 'encrypt' or 'decrypt'
    :param str data:      The data to encrypt or decrypt as either a string or bytes
    :param str key:       Base64 encoded Fernet symmetric key for encrypting/decrypting data.
    :return str data_out: Either the encrypted data as a base64 encoded string, or decrypted data as a plain string.
    """
    if direction not in ['encrypt', 'decrypt']:
        raise ValueError('_crypt_str direction must be "encrypt" or "decrypt"')

    f = get_fernet(key)

    # Handle encryption/decryption of ``data``
    try:
        # If ``data`` isn't already bytes, cast to a string and convert it to bytes before encrypting/decrypting
        data = str(data).encode('utf-8') if type(data) != bytes else data
        out = f.encrypt(data) if direction == 'encrypt' else f.decrypt(data)
        return out.decode()    # Return encrypted/decrypted data as a string, not bytes.
    except Exception:
        strdat = str(data) if type(data) != bytes else str(data.decode())
        log.exception(f'An exception occurred while trying to {direction} the data starting with "{strdat:.4}"...')
        raise EncryptionError(f'Failed to {direction} data... An admin must check the logs.')


def encrypt_str(data: Union[str, bytes], key: Union[str, bytes] = None) -> str:
    """
    Encrypts a piece of data ``data`` passed as a string or bytes using Fernet with the passed 32-bit symmetric
    encryption key ``key``. Outputs the encrypted data as a Base64 string for easy storage.

    The ``key`` cannot just be a random "password", it must be a 32-byte key encoded with URL Safe base64. Use the
    management command ``./manage.py generate_key`` to create a Fernet compatible encryption key.

    Under the hood, Fernet uses AES-128 CBC to encrypt the data, with PKCS7 padding and HMAC_SHA256 authentication.

    If the ``key`` parameter isn't passed, or is empty (None / ""), then it will attempt to fall back to
    ``settings.ENCRYPT_KEY`` - if that's also empty, EncryptKeyMissing will be raised.

    :param str data:  The data to be encrypted, in the form of either a str or bytes.
    :param str key:   A Fernet encryption key (base64) to be used, if left blank will fall back to settings.ENCRYPT_KEY
    :raises EncryptKeyMissing: Either no key was passed, or something is wrong with the key.
    :raises EncryptionError:   Something went wrong while attempting to encrypt the data
    :return str encrypted_data:   The encrypted version of the passed ``data`` as a base64 encoded string.
    """

    return _crypt_str('encrypt', data, key)


def decrypt_str(data: Union[str, bytes], key: Union[str, bytes] = None) -> str:
    """
    Decrypts ``data`` previously encrypted using :py:func:`encrypt_str` with the same Fernet compatible ``key``, and
    returns the decrypted version as a string.

    The ``key`` cannot just be a random "password", it must be a 32-byte key encoded with URL Safe base64. Use the
    management command ``./manage.py generate_key`` to create a Fernet compatible encryption key.

    Under the hood, Fernet uses AES-128 CBC to encrypt the data, with PKCS7 padding and HMAC_SHA256 authentication.

    If the ``key`` parameter isn't passed, or is empty (None / ""), then it will attempt to fall back to
    ``settings.ENCRYPT_KEY`` - if that's also empty, EncryptKeyMissing will be raised.

    :param str data:  The base64 encoded data to be decrypted, in the form of either a str or bytes.
    :param str key:   A Fernet encryption key (base64) for decryption, if blank, will fall back to settings.ENCRYPT_KEY
    :raises EncryptKeyMissing: Either no key was passed, or something is wrong with the key.
    :raises EncryptionError:   Something went wrong while attempting to decrypt the data
    :return str decrypted_data:   The decrypted data as a string
    """
    return _crypt_str('decrypt', data, key)
