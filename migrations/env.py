"""Alembic reads DATABASE_URL from the same settings as FastAPI."""

from alembic import context

from app.database import Base, engine
from app import models  # Register the SQLAlchemy tables.


def include_object(obj, name, type_, reflected, compare_to):
    # Manage only EventGate tables, leaving unrelated tables alone.
    return type_ != "table" or name.startswith("eg_")


if context.is_offline_mode():
    context.configure(url=engine.url, target_metadata=Base.metadata, literal_binds=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, include_object=include_object,
                          render_as_batch=engine.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
