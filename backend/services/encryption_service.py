from cryptography.fernet import Fernet
import os

import core.config

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