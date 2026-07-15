import os
from services.encryption_service import EncryptionService

encrypted = EncryptionService.encrypt(
    "ENCRYPTION_KEY"
)

print(encrypted)