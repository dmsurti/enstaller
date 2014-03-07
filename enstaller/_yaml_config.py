"""
This is temporary.

DO NOT USE IF YOU DON'T UNDERSTAND WHY STUFF IS HERE !
"""
import ast
import os.path
import sys
import warnings

from enstaller.config import Configuration, _get_password
from enstaller.errors import InvalidConfiguration
from enstaller.plat import custom_plat
from enstaller.vendor import yaml


def _translate_store(value):
    return "webservice_entry_point", "{0}/eggs/{1}/".format(value, custom_plat)


def _translate_username(value):
    return "EPD_username", value


def _translate_repository_cache(value):
    return "repository_cache", value


def _translate_http_proxy(value):
    http_key = "http"
    https_key = "https"
    proxy = None
    if http_key in value:
        proxy = value[http_key]
    if https_key in value:
        if proxy is not None:
            raise InvalidConfiguration(
                "Setting up both '{0}' and '{1}' in http_proxies is not " \
                "supported yet".format(http_key, https_key))
        proxy = value[https_key]

    return "proxy", proxy


def from_yaml(filename_or_fp):
    assert isinstance(filename_or_fp, basestring), \
            "Parsing frome file object not supported yet"

    accepted_keys = {"store_url": _translate_store,
                     "username": _translate_username,
                     "eggs_cache": _translate_repository_cache,
                     "http_proxies": _translate_http_proxy}

    with open(filename_or_fp, "r") as fp:
        data = yaml.load(fp)

    config = Configuration()
    enstaller_data = data.get("enstaller", {})
    for yaml_name, yaml_value in enstaller_data.items():
        if yaml_name in accepted_keys:
            name, value = accepted_keys[yaml_name](yaml_value)
            setattr(config, name, value)
        else:
            warnings.warn("Unknown setting '{0}', ignoring".format(yaml_name))

    if config._username is not None:
        config._password = _get_password(config._username)
    config._filename = filename_or_fp
    return config


def canopy_hack_path():
    return os.path.join(sys.prefix, ".CANOPYR_HACK")


def use_canopy_hack():
    return os.path.isfile(canopy_hack_path())


def canopy_hack_content():
    with open(canopy_hack_path()) as fp:
        path = ast.literal_eval(fp.read())
        if not isinstance(path, str):
            raise ValueError("Unexpected content in '{0}'".format(canopy_hack_path()))
        else:
            return path
