from typing import Any, Optional, Dict
from pydantic import BaseModel

# In a real application, use a secure password hashing library like passlib
# For example: from passlib.context import CryptContext
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    roles: list[str] = []


class UserInDB(User):
    hashed_password: str


# Dummy user database - replace with a real database in production
# Passwords should be hashed in a real application
fake_users_db: Dict[str, Dict[str, Any]] = {
    "testuser": {
        "username": "testuser",
        "full_name": "Test User",
        "email": "testuser@example.com",
        "hashed_password": "fakehashedpassword",  # In a real app, this would be a bcrypt hash
        "disabled": False,
        "roles": ["user"],
    },
    "adminuser": {
        "username": "adminuser",
        "full_name": "Admin User",
        "email": "admin@example.com",
        "hashed_password": "fakehashedadminpassword",
        "disabled": False,
        "roles": ["admin", "user"],
    },
}


def get_user(username: str) -> Optional[UserInDB]:
    if username in fake_users_db:
        user_dict = fake_users_db[username]
        return UserInDB(**user_dict)
    return None


# This is a dummy password verification. In a real app, use pwd_context.verify()
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # For demonstration, we're just comparing the plain password to the fake hashed one.
    # This is NOT secure. A real implementation would be:
    # return pwd_context.verify(plain_password, hashed_password)
    return (
        plain_password == hashed_password
    )  # Replace with actual hash comparison if you were hashing


# This is a dummy authentication function. Replace with actual logic.
def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    user = get_user(username)
    if not user:
        return None
    # In a real app, you'd hash the input password and compare hashes, or use a library function.
    # For this dummy example, we'll pretend 'fakehashedpassword' is the actual password for simplicity.
    # A more realistic dummy check if passwords were not 'hashed' in the db:
    # if user.hashed_password != password_to_check:
    #    return None
    # Using verify_password for consistency, even though it's also dummied up
    if not verify_password(password, user.hashed_password):
        return None
    return user
