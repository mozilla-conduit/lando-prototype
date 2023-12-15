# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import Mock

from sqlalchemy.exc import SQLAlchemyError

from landoapi.auth import auth0_subsystem
from landoapi.phabricator import PhabricatorAPIException, phabricator_subsystem
from landoapi.storage import db_subsystem


def test_database_healthy(db):
    assert db_subsystem.healthy() is True


def test_database_unhealthy(db, monkeypatch):
    mock_db = Mock(db)
    monkeypatch.setattr("landoapi.storage.db", mock_db)

    mock_db.engine.connect.side_effect = SQLAlchemyError
    assert db_subsystem.healthy() is not True


def test_phabricator_healthy(app, phabdouble):
    assert phabricator_subsystem.healthy() is True


def test_phabricator_unhealthy(app, monkeypatch):
    def raises(*args, **kwargs):
        raise PhabricatorAPIException

    monkeypatch.setattr("landoapi.phabricator.PhabricatorClient.call_conduit", raises)
    assert phabricator_subsystem.healthy() is not True


def test_auth0_healthy(app, jwks):
    assert auth0_subsystem.healthy() is True


def test_auth0_unhealthy(app):
    assert auth0_subsystem.healthy() is not True
