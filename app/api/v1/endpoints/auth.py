from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import create_access_token, Token, get_current_user
from app.core.users import authenticate_user, UserInDB, get_user # Assuming UserInDB has a 'username' attribute

router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Ensure user object (UserInDB) has a 'username' attribute for the token subject
    # And 'roles' attribute if you plan to include roles in the token
    access_token = create_access_token(
        data={"sub": user.username, "roles": user.roles if hasattr(user, 'roles') else []}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model_exclude_none=True) # Using User model from users.py
async def read_users_me(current_user: Annotated[UserInDB, Depends(get_current_user)]):
    """
    Test endpoint to get current user details.
    """
    # Note: get_current_user returns TokenPayload. We might want to fetch the full user from DB.
    # For this example, we'll assume TokenPayload's sub is the username and fetch the user.
    # In a real app, you might store user ID in 'sub' and fetch by ID.
    user_in_db = get_user(current_user.sub) # get_user is from app.core.users
    if user_in_db is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user_in_db
