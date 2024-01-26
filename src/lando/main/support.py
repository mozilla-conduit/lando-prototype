from django.http import HttpResponse
from unittest.mock import MagicMock
from lando.api.legacy.phabricator import PhabricatorClient
from lando import settings


class ProblemException(Exception):
    def __init__(self, status=500, title=None, detail=None, type=None, instance=None, headers=None, ext=None):
        # TODO: this should be reimplemented as either middleware or HttpResponse return values.
        super().__init__(self)


def problem(status, title, detail, type=None, instance=None, headers=None, ext=None):
    return HttpResponse(content=detail, headers=headers, status_code=status)


class request:
    headers = {}

session = {}


class g:
    class auth0_user:
        email = "no-one@example.com"

        @staticmethod
        def is_in_groups(*args):
            return True

    access_token = None
    access_token_payload = None
    _request_start_timestamp = None


class FlaskApi:
    @classmethod
    def get_response(self, _problem):
        return _problem


class ConnexionResponse(HttpResponse):
    pass


celery = MagicMock()

phab = PhabricatorClient(
    settings.PHABRICATOR_URL,
    settings.PHABRICATOR_UNPRIVILEGED_API_KEY,
)

is_user_authenticated = MagicMock()
is_user_authenticated.return_value = True
