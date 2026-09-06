from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.controllers.controller_factory import ControllerFactory
from app.repositories.repository_factory import RepositoryFactory
from app.services.service_factory import ServiceFactory
from core.db import get_db_session


def get_repository_factory(
    session: Annotated[Session, Depends(get_db_session)],
) -> RepositoryFactory:
    return RepositoryFactory(session)


def get_service_factory() -> ServiceFactory:
    return ServiceFactory()


def get_controller_factory(
    repository_factory: Annotated[RepositoryFactory, Depends(get_repository_factory)],
    service_factory: Annotated[ServiceFactory, Depends(get_service_factory)],
) -> ControllerFactory:
    return ControllerFactory(repository_factory, service_factory)


Controllers = Annotated[ControllerFactory, Depends(get_controller_factory)]
