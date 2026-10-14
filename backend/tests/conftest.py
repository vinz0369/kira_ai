from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, delete, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import Item, User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session]:
    with Session(engine) as session:
        init_db(session)
        # Keep rows that existed before pytest. The template's blanket User
        # deletion also cascaded into real local characters and live sessions
        # when tests accidentally pointed at the development database.
        existing_user_ids = set(session.exec(select(User.id)).all())
        existing_item_ids = set(session.exec(select(Item.id)).all())
        yield session
        new_item_ids = set(session.exec(select(Item.id)).all()) - existing_item_ids
        new_user_ids = set(session.exec(select(User.id)).all()) - existing_user_ids
        if new_item_ids:
            session.exec(delete(Item).where(col(Item.id).in_(new_item_ids)))
        if new_user_ids:
            session.exec(delete(User).where(col(User.id).in_(new_user_ids)))
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
