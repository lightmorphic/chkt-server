import os

# Load .env if present (docker-compose does this itself; this covers running
# directly with python or gunicorn). SECRET_KEY is the only expected entry.
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from app import create_app  # noqa: E402  (env must load first)

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8321, debug=False)
