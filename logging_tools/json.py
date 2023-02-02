import json
import os
from typing import Any, Callable, Optional, Dict
import traceback
import logging

from .common import GLOBAL_LOG_CONTEXT

# skip natural LogRecord attributes
# http://docs.python.org/library/logging.html#logrecord-attributes
LOGGING_RECORD_ATTRS = set(
    [
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "thread",
        "threadName",
    ]
)

def safemerge(target, input, reserved=None, skip=None):
    for key in input:
        if skip is not None and key in skip:
            continue
        src_key = key
        while key in target or (reserved is not None and key in reserved):
            key = "%s_" % (key,)
        target[key] = input[src_key]
    return target


class JsonLogFormatter(logging.Formatter):
    # `base_fields` are included verbatim in every log record.
    # For example, if:
    #
    #   base_fields = {
    #       "app": "myapp",
    #       "env": "prod",
    #   }
    #
    # Then, the resulting JSON log will contain:
    #   > log.info("hello")
    #   {"app": "myapp", "env": "prod", "message": "hello", ...}
    base_fields: Optional[dict] = None

    # `get_environ` is a function that returns a dictionary of the current
    # environment (typically a Flask request or other WSGI environment).
    get_environ: Optional[Callable[[], Dict[str, Any]]] = None

    # `context_from_environ` maps field names the environment returned by
    # `get_environ` to fields in the resulting JSON log. For example, if:
    #
    #    context_from_environ = {
    #        "rid": "LOG_REQUEST_ID",
    #    }
    #
    # Then, assuming the environment returned by `get_environ` contains a
    # key "LOG_REQUEST_ID", then the resulting JSON log will contain a field
    # "rid" with the value of "LOG_REQUEST_ID":
    #
    #     > log.info("hello")
    #     {"rid": "1234", "message": "hello", ...}
    context_from_environ: Optional[dict] = None

    # Prefix appended to all log messages, as required by some logging
    # platforms. For exmaple, if prefix = "foo:", then then formatted log
    # messages will be similar to:
    #
    #   > log.info("hello")
    #   foo:{"message": "hello", ...}
    prefix: str = ""

    # Function to serialize JSON. Defaults to `json.dumps`.
    json_dumps: Optional[Callable[[Any], str]] = None

    def __init__(
        self,
        base_fields: Optional[dict] = None,
        get_environ: Optional[Callable[[], Dict[str, Any]]] = None,
        context_from_environ: Optional[dict] = None,
        prefix: str = "",
        json_dumps: Optional[Callable[[Any], str]] = None,
        **kwargs,
    ):
        # Base fields will be included in every log record
        self.base_fields = base_fields or {}

        # If a Flask request is active, these fields will be included
        # in the "context".
        self.get_environ = get_environ
        self.context_from_environ = context_from_environ
        self.json_dumps = json_dumps or json.dumps

        self.prefix = prefix or ""
        self.fields = [
            "asctime",
            "levelname",
            "levelno",
            "pid",
            "threadName",
            "thread",
            "name",
            "message",
            "*exc",
            "*context",
            "*extra",
        ]
        self._reserved_fields = set(self.fields).union(LOGGING_RECORD_ATTRS)
        logging.Formatter.__init__(self, **kwargs)

    def _add_exc(self, record_obj, record):
        e = record.exc_info
        record_obj["exc_message"] = "".join(traceback.format_exception_only(e[0], e[1]))
        record_obj["exc_traceback"] = traceback.format_exception(*e)

    def format_obj(self, record):
        record_obj = dict(self.base_fields)
        for field in self.fields:
            if field == "*exc":
                if record.exc_info:
                    self._add_exc(record_obj, record)
            elif field == "*extra":
                safemerge(
                    record_obj,
                    record.__dict__,
                    reserved=self._reserved_fields,
                    skip=LOGGING_RECORD_ATTRS,
                )
            elif field == "*context":
                context = {}
                if self.get_environ is not None:
                    environ = self.get_environ()
                    for (field, env_field) in self.context_from_environ.items():
                        if env_field in environ:
                            context[field] = environ[env_field]
                safemerge(context, GLOBAL_LOG_CONTEXT.get_log_context())
                safemerge(record_obj, {"context": context})
            elif field == "asctime":
                record_obj[field] = self.formatTime(record, self.datefmt)
            elif field == "message":
                if isinstance(record.msg, dict):
                    safemerge(record_obj, record.msg, self._reserved_fields)
                    continue
                record_obj[field] = record.getMessage()
            elif field == "pid":
                record_obj[field] = os.getpid()
            else:
                record_obj[field] = record.__dict__.get(field)
        return record_obj

    def format(self, record):
        record_obj = self.format_obj(record)
        try:
            json_str = self.json_dumps(record_obj)
        except Exception as e:
            try:
                json_str = "(error encoding: %r) %r" % (e, record_obj)
            except Exception as e:
                json_str = "(error encoding: %r)" % (e,)
        return "%s%s" % (self.prefix, json_str)