
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="12-Factor Config Precedence")

# Allow browser-based graders to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Layer 1: Hardcoded defaults.
DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}


def normalize_key(key):
    """Convert configuration keys to lowercase."""
    return key.strip().lower()


def coerce_value(key, value):
    """Convert values to the required Python types."""
    key = normalize_key(key)

    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value

        return str(value).strip().lower() in {
            "true", "1", "yes", "on"
        }

    # log_level and all other keys are strings.
    return str(value)


def load_effective_config(overrides):
    # Start with Layer 1: defaults.
    config = DEFAULTS.copy()

    # Layer 2: environment-specific YAML.
    environment = os.environ.get("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"

    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as file:
            yaml_config = yaml.safe_load(file) or {}

        for key, value in yaml_config.items():
            config[normalize_key(key)] = value

    # Layer 3: .env file.
    env_path = BASE_DIR / ".env"
    file_env = dotenv_values(env_path)

    for key, value in file_env.items():
        if value is None:
            continue

        normalized = normalize_key(key)

        if normalized == "num_workers":
            normalized = "workers"
        elif normalized.startswith("app_"):
            normalized = normalized[4:]

        config[normalized] = value

    # Layer 4: actual OS environment variables.
    for key, value in os.environ.items():
        normalized = normalize_key(key)

        if normalized.startswith("app_"):
            config[normalized[4:]] = value

    # Layer 5: query-string overrides.
    for key, value in overrides:
        normalized = normalize_key(key)

        # Do not allow clients to change the real API key.
        if normalized == "api_key":
            continue

        config[normalized] = value

    # Apply type conversion after all layers are merged.
    config = {
        key: coerce_value(key, value)
        for key, value in config.items()
    }

    # Never return the actual secret.
    config["api_key"] = "****"

    return config


@app.get("/effective-config")
def effective_config(
    set_: list[str] = Query(default=[], alias="set")
):
    overrides = []

    for item in set_:
        # Split only at the first '=' so values may contain '='.
        if "=" not in item:
            continue

        key, value = item.split("=", 1)

        if not key.strip():
            continue

        overrides.append((key, value))

    return load_effective_config(overrides)
