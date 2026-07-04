from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto"
)

print(
    pwd_context.hash("Password@123")
)