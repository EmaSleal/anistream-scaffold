"""Standalone entrypoint for the simulcast scheduler process.

Not a Flask app — run directly as the ``simulcast-scheduler`` service in
docker-compose, separate from the gunicorn/Flask process.
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from scheduler import run_scheduler_forever

if __name__ == "__main__":
    run_scheduler_forever()
