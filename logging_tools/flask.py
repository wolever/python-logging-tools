import time
import logging

try:
    import flask_login
except ImportError:
    flask_login = None

import flask
from flask import request

from .common import safe_to_str, ReadTimingStreamWrapper

class FlaskRequestLogger(object):
    log = logging.getLogger("request_log")

    def init_app(self, app):
        app.before_request(self._before_request)
        app.after_request(self._after_request)

    def _before_request(self):
        request._start_time = time.time()

    def _after_request(self, response):
        try:
            self.log_response(request, response)
        except Exception:
            self.log.exception("Error generating response log:")
        return response

    def _get_current_user_id(self):
        if flask_login is None:
            return None
        if flask_login.current_user.is_authenticated:
            return flask_login.current_user.id
        return None

    def log_response(self, request, response):
        env = request.environ

        body_bytes = response and self.get_body_bytes(response)

        path = env.get("RAW_URI") or env.get("REQUEST_URI")
        if not path:
            _query = env.get("QUERY_STRING") and "?%s" % (env["QUERY_STRING"],) or ""
            _path_info = request.path_info.replace("?", "%3F")
            path = "%s%s" % (_path_info, _query)

        duration = getattr(request, "_start_time", None)
        if duration is not None:
            duration = time.time() - duration

        res = {
            "addr": env.get("REMOTE_ADDR"),
            "user_id": self._get_current_user_id(),
            "method": env.get("REQUEST_METHOD"),
            "host": env.get("HTTP_HOST"),
            "path": path,
            "status_code": response.status_code,
            "size": body_bytes,
            "duration": duration,
            "sql_num_queries": env.get("SQL_NUM_QUERIES", 0),
            "sql_total_time": env.get("SQL_TOTAL_TIME", 0),
            "referer": env.get("HTTP_REFERER"),
        }

        if response and "location" in response.headers:
            res["location"] = response.headers["location"]

        if response and "content-type" in response.headers:
            res["content_type"] = response.headers["content-type"]

        if "user-agent" in request.headers:
            res["user_agent"] = request.headers["user-agent"]

        if "x-rx-app-version" in request.headers:
            res["app_version"] = request.headers["x-rx-app-version"]

        if response and response.status_code >= 400:
            try:
                res["body"] = safe_to_str(response.data[:512])
            except Exception:
                pass

        if isinstance(env["wsgi.input"], ReadTimingStreamWrapper):
            body: ReadTimingStreamWrapper = env["wsgi.input"]
            if body.first_read_time is not None:
                res["req_body_size"] = body.read_byte_count
                res["req_body_duration"] = body.last_read_time - body.first_read_time

        if "search_by_photo_ffe_queue" in path:
            res["debug_photo_ffe_form"] = safe_to_str(dict(request.form))

        self.log.info("%(addr)s %(method)s %(path)s %(status_code)s", res, extra=res)

    def get_body_bytes(self, resp):
        try:
            return int(resp.headers.get("Content-Length"))
        except (TypeError, ValueError):
            pass

        try:
            return len(resp.data)
        except Exception:
            return -1

