import pytest
import subprocess


def test_version():
    # explicitly generate the version.py file since we can't
    # guarantee it already exists in the testing environment
    subprocess.call(["lando", "generate_version_file"])

    try:
        from lando.version import version

        assert version is not None, "Version should not be None"
        assert isinstance(version, str), "Version should be a string"
    except ImportError as e:
        pytest.fail(f"ImportError occurred: {e}")
