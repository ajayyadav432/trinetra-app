import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("TRINETRA_SECRET", "trinetra-local-dev-key")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "trinetra.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    TOR_SOCKS = os.environ.get("TRINETRA_TOR", "socks5h://127.0.0.1:9050")
    REQUEST_TIMEOUT = int(os.environ.get("TRINETRA_TIMEOUT", "12"))
    STYLOMETRY_LIB = os.environ.get(
        "TRINETRA_STYLO", os.path.join(os.path.dirname(BASE_DIR), "sih-refs", "stylometry-python")
    )
    DEMO_SOURCE = "demo-seed"
