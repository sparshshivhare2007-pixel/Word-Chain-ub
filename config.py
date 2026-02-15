import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # =========================
    # TELETHON CREDENTIALS
    # =========================
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    SESSION_NAME = os.getenv("SESSION_NAME", "wordle_user")

    # =========================
    # PATHS
    # =========================
    SESSIONS_DIR = "sessions"
    DATA_DIR = "data"

    # =========================
    # ANTI-BAN SETTINGS
    # =========================
    MIN_DELAY = float(os.getenv("MIN_DELAY", "1.5"))
    MAX_DELAY = float(os.getenv("MAX_DELAY", "3.5"))
    COOLDOWN_BETWEEN_GAMES = int(
        os.getenv("COOLDOWN_BETWEEN_GAMES", "120")
    )

    # =========================
    # GAME SETTINGS
    # =========================
    MAX_GUESSES = 6
    WORD_LENGTH = 5

    # =========================
    # SESSION MANAGEMENT
    # =========================
    MAX_SESSIONS_PER_USER = 3
    SESSION_TIMEOUT = 3600  # seconds

    @classmethod
    def validate(cls):
        if not cls.API_ID:
            raise ValueError("API_ID is required in .env")
        if not cls.API_HASH:
            raise ValueError("API_HASH is required in .env")

        os.makedirs(cls.SESSIONS_DIR, exist_ok=True)
        os.makedirs(cls.DATA_DIR, exist_ok=True)
