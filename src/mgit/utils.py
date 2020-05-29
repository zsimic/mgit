import json
import logging
import os
import time

try:
    from urllib.parse import unquote, urlparse, urlencode, urljoin
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:
    from urlparse import urljoin, urlparse
    from urllib import unquote, urlencode
    from urllib2 import urlopen, Request, HTTPError, URLError

import runez


LOG = logging.getLogger(__name__)
USER_HOME = os.path.expanduser("~")


class Cache:
    """Helps iterate faster while developing, by avoiding hitting REST servers too often"""

    def __init__(self, cache_dir, ttl, debug_ttl=48):
        """
        :param str cache_dir: Local folder to use for caching
        :param int ttl: Time to live for caching, in seconds (0: forever)
        :param int debug_ttl: Time to live for caching when running in PyCharm, in hours
        """
        self.given_path = cache_dir
        self.cache_dir = os.path.expanduser(cache_dir)
        self.ttl = ttl
        if ttl and "PYCHARM_HOSTED" in os.environ:
            self.ttl = max(ttl, debug_ttl * runez.date.SECONDS_IN_ONE_HOUR)
        if not os.path.isdir(self.cache_dir):
            os.makedirs(self.cache_dir)

    def __repr__(self):
        return "%s %s" % (runez.represented_duration(self.ttl), self.given_path)

    def get(self, path, ttl=None):
        """
        :param str path: Relative path
        :param int|None ttl: Override ttl
        :return object: Deserialized object from cache, if present and not expired
        """
        full_path = os.path.join(self.cache_dir, path)

        try:
            if ttl is None:
                ttl = self.ttl

            if ttl:
                age = time.time() - os.path.getmtime(full_path)
                if age > ttl:
                    return None

            with open(full_path) as fh:
                return json.load(fh)

        except Exception:
            return None

    def put(self, data, path):
        """
        :param object data: Object to store in cache
        :param str path: Relative path
        """
        full_path = os.path.join(self.cache_dir, path)
        parent = os.path.dirname(full_path)
        if not os.path.isdir(parent):
            os.makedirs(parent)

        try:
            with open(full_path, "w") as fh:
                json.dump(data, fh, sort_keys=True, indent=2)

        except Exception as e:
            LOG.debug("Couldn't store object %s in cache: %s", full_path, e)


class RestWrapper:
    """
    Simple wrapper helping access REST end points, with optionally cached results
    """

    def __init__(self, base_url, cache=None, default=None, retry=1):
        """
        :param str base_url: Base URL of REST service
        :param Cache|None cache: Optional cache object
        :param object default: Default to return when REST call fails
        :param int retry: How many times to retry failed calls
        """
        self.base_url = base_url
        self.cache = cache
        self.default = default
        self.retry = retry if retry > 0 else 1

    def __repr__(self):
        return self.base_url

    def headers(self):
        """
        :return dict: Header file to use (from cache), if any
        """
        if self.cache:
            return self.cache.get(self.cache_path("_headers"), ttl=0) or {}
        return {}

    def save_headers(self, data):
        """
        :param dict data: Data to store in cache
        """
        self.cache.put(data, self.cache_path("_headers"))

    def cache_path(self, relative_url):
        """
        :param str relative_url: Relative URL
        :return str|None: Relative path
        """
        if not self.cache:
            return None

        p = urlparse(relative_url)
        result = p.path.replace("/", "-")

        if p.query:
            qpath = unquote(p.query)
            if result:
                result += "-"
            for char in qpath:
                if char.isalnum():
                    result += char

        p = urlparse(self.base_url)
        result = os.path.join(self.cache.cache_dir, p.hostname, "%s.json" % result)

        return result

    def relative_url(self, *args, **kwargs):
        """
        :param tuple|list args: URL components (relative to self.base_url)
        :param dict kwargs: GET parameters to encode
        :return str: Encoded relative URL to use (with encoded parameters, if any)
        """
        if args:
            result = os.path.join(*args)
        else:
            result = ""

        if kwargs:
            params = urlencode(kwargs)
            result = "%s?%s" % (result, params)

        return result

    def url(self, *args, **kwargs):
        """
        :param list args: URL to GET
        :param dict kwargs: Optional args
        :return str: Full URL to use
        """
        relative_url = self.relative_url(*args, **kwargs)
        return urljoin(self.base_url, relative_url)

    def get(self, *args, **kwargs):
        """
        :param list *args: URL to GET
        :param dict **kwargs: Optional args
        :return obj: Deserialized json object
        """
        ttl = kwargs.pop("ttl", None)
        relative_url = self.relative_url(*args, **kwargs)
        cache_path = self.cache_path(relative_url)
        if self.cache:
            data = self.cache.get(cache_path, ttl=ttl)
            if data is not None:
                LOG.debug("Using cached '%s'" % relative_url)
                return data

        url = urljoin(self.base_url, relative_url)
        headers = self.headers()

        remaining_tries = self.retry
        while remaining_tries > 0:
            try:
                remaining_tries -= 1
                request = Request(url, headers=headers)     # nosec
                response = urlopen(request).read()          # nosec
                data = json.loads(response)
                LOG.debug("GET %s" % relative_url)
                if self.cache:
                    self.cache.put(data, cache_path)
                return data

            except HTTPError as e:
                if e.code == 404:
                    LOG.debug("404 on %s" % relative_url)
                    return None

                if remaining_tries <= 0:
                    if self.default is not None:
                        LOG.debug("GET %s: using default" % relative_url)
                        return self.default
                    raise Exception("GET %s failed after %s retries: %s" % (url, self.retry, e))

                time.sleep(3)

            except URLError as e:
                if hasattr(e.reason, "errno") and e.reason.errno == 8:
                    raise Exception("GET %s failed: server is not running" % url)
                raise Exception("GET %s failed: %s" % (url, e))

            except Exception as e:
                raise Exception("GET %s failed: %s" % (url, e))
