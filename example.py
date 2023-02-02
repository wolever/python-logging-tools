import os
import json
import socket
import logging
import logging.config

import flask
import rich.console
from flask import Flask
from logging_tools.common import RequestIdLogContextWsgiApp

from logging_tools.json import JsonLogFormatter
from logging_tools.flask import FlaskRequestLogger


def _get_host_name():
    if "HOSTNAME" in os.environ:
        return os.environ["HOSTNAME"]
    try:
        return socket.gethostname()
    except Exception:
        return "unknown_host"

rich_console = rich.console.Console()

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": JsonLogFormatter,
            "base_fields": {
                "environment": "dev",
                "hostname": _get_host_name(),
            },
            "get_environ": lambda: flask.request.environ if flask.has_request_context() else {},
            "context_from_environ": {
                "rid": "LOG_REQUEST_ID",
                "ip": "REMOTE_ADDR",
                "uid": "LOG_USER_ID",
                "tok": "LOG_AUTH_TOKEN_PREFIX",
                "endpoint": "LOG_API_ENDPOINT",
            },
            "json_dumps": lambda x: json.dumps(x, indent=2),
        },
        "default": {
            "format": "%(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "rich.logging.RichHandler",
            "level": "DEBUG",
            "formatter": "default",
        },
        "json_to_console": {
            "class": "rich.logging.RichHandler",
            "level": "DEBUG",
            "formatter": "json",
        },
    },
    "loggers": {
        "": {
            "level": "INFO",
            "handlers": ["console", "json_to_console"],
            "propogate": True,
        },
        "werkzeug": {
            # Suppress Werkzeug's logging to make demo output more readable
            "level": "INFO",
            "propagate": False,
            "handlers": [],
        },
    },
})

# Setup the Flask app
app = Flask(__name__)

@app.before_request
def logging_add_environment_context():
    # Include the Flask endpoint in each request
    env = flask.request.environ
    env["LOG_API_ENDPOINT"] = flask.request.endpoint

# Include the request ID in each request, and add instrumentation to the input
# stream to log the number of bytes read
app.wsgi_app = RequestIdLogContextWsgiApp(app.wsgi_app)

# Initialize the request logger, which logs each request to the `request_log`
# logger.
FlaskRequestLogger().init_app(app)

log = logging.getLogger(__name__)

@app.route('/')
def index():
    log.info("Hello, World!")
    return "Hello, World!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8181, debug=True)