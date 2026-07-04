from cryptography.fernet import Fernet
from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

class EncryptionService:

    @staticmethod
    def get_cipher():

        key = os.getenv(
            "ENCRYPTION_KEY"
        )

        if not key:

            raise ValueError(
                "ENCRYPTION_KEY is not configured"
            )

        return Fernet(
            key.encode()
        )

    @staticmethod
    def encrypt(
        value: str
    ):

        cipher = (
            EncryptionService
            .get_cipher()
        )

        return (
            cipher.encrypt(
                value.encode()
            ).decode()
        )

    @staticmethod
    def decrypt(
        value: str
    ):

        cipher = (
            EncryptionService
            .get_cipher()
        )

        return (
            cipher.decrypt(
                value.encode()
            ).decode()
        )