import os


def _database_uri():
    """Build the SQLAlchemy URI from the environment.

    Defaults target the database on the same host as the app, so a fresh
    deployment works without a fixed IP. Override any part via the
    environment (or a .env file) when the database lives elsewhere.
    """
    uri = os.getenv('SQLALCHEMY_DATABASE_URI')
    if uri:
        return uri

    host = os.getenv('DB_HOST', '127.0.0.1')
    port = os.getenv('DB_PORT', '3307')
    user = os.getenv('DB_USER', 'root')
    password = os.getenv('DB_PASSWORD')
    if not password:
        raise RuntimeError('DB_PASSWORD is not set (copy .env.example to .env)')
    name = os.getenv('DB_NAME', 'fqdn_tool')
    return f'mysql+pymysql://{user}:{password}@{host}:{port}/{name}'


class Config:
    SECRET_KEY = os.urandom(16)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class ProdConfig(Config):
    DEBUG = False


class DevConfig(Config):
    DEBUG = True
