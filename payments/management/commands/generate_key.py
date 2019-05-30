import sys

from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate a secure key for CTConverter internal encryption/decryption'

    def __init__(self):
        super(Command, self).__init__()

    def handle(self, *args, **options):
        print('Generating key...', file=sys.stderr)
        print(file=sys.stderr)
        print(Fernet.generate_key().decode('utf-8'))
        print(file=sys.stderr)
