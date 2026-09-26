from sqlalchemy.orm import Session

from app.models import User

TEST_USER_EMAIL = "test+leadprophet@example.com"
SECOND_TEST_USER_EMAIL = "test+second@example.com"


def create_test_user_if_not_exists(db: Session) -> User:
    user = db.query(User).filter(User.email == TEST_USER_EMAIL).first()
    if not user:
        user = User(email=TEST_USER_EMAIL, display_name="LeadProphet Test User", role="test")
        db.add(user)
        db.flush()
    return user


def create_second_test_user_if_not_exists(db: Session) -> User:
    user = db.query(User).filter(User.email == SECOND_TEST_USER_EMAIL).first()
    if not user:
        user = User(email=SECOND_TEST_USER_EMAIL, display_name="Second Test User", role="test")
        db.add(user)
        db.flush()
    return user
