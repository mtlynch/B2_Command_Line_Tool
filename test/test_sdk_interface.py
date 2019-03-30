######################################################################
#
# File: test/test_sdk_interface.py
#
# Copyright 2019 Backblaze Inc. All Rights Reserved.
#
# License https://www.backblaze.com/using_b2_code.html
#
######################################################################

import imp
import importlib
import pkgutil
import six
import sys
import types
import unittest
import warnings

import b2sdk

from b2._sdk_deprecation import deprecation_message

warnings.simplefilter('always', DeprecationWarning)


def match_warning(cli_module_name, catched_warnings):
    module_deprecation_message = deprecation_message(cli_module_name)
    for warning in catched_warnings:
        try:
            warn_msg = warning.message.args[0]
        except IndexError:
            warn_msg = ''
        if issubclass(warning.category, DeprecationWarning):
            if warn_msg == module_deprecation_message:
                yield warning


def list_modules(package, exclude=None):
    """
    Get a list of modules in a package

    :param package: object, a module object
    :param exclude: set, a set of modules to
    exclude from the resulting list
    :return: list, a list of modules of a package
    """
    if exclude is None:
        exclude = set()
    res = []
    if not hasattr(package, '__path__'):
        return res
    base_name = package.__name__
    for _, m, _ in pkgutil.iter_modules(package.__path__):
        if m.startswith('__'):
            continue
        fullname = '{}.{}'.format(base_name, m)
        mod = importlib.import_module(fullname)
        del sys.modules[fullname]
        res.append(fullname)
        res += list_modules(mod)
    return [m for m in res if m not in exclude]


def _dir(m, skip=()):
    """
    Get a list of attributes of an object, excluding
    the ones starting with underscore

    :param m: object, an object to get attributes from
    :return: list, a list of attributes as strings
    """
    return [a for a in dir(m) if not a.startswith('_') and a not in skip]


if six.PY2:
    """
    Shim for Python 2.x
    """
    import operator

    def accumulate(iterable, func=operator.__add__):
        it = iter(iterable)
        res = next(it)
        yield res
        for val in it:
            res = func(res, val)
            yield res

else:
    from itertools import accumulate


class TestSdkImports(unittest.TestCase):
    def _del_mod(self, name):
        """
        Remove a module with the given name from module cache
        """
        mods = accumulate(name.split('.'), func=lambda a, v: '{}.{}'.format(a, v))
        next(mods)
        for mod_name in mods:
            try:
                del sys.modules[mod_name]
            except KeyError:
                pass

    @classmethod
    def setUpClass(cls):
        cls.sdk_modules = list_modules(b2sdk, exclude=set(['b2sdk.version']))
        cls.cli_modules = [m.replace('b2sdk.', 'b2.') for m in cls.sdk_modules]
        # create a list of all attributes of all sdk modules
        cls.attributes = {}
        for mod_name in cls.sdk_modules:
            cls.attributes[mod_name] = []
            mod = importlib.import_module(mod_name)
            for attr_name in _dir(mod):
                if not isinstance(getattr(mod, attr_name), types.ModuleType):
                    cls.attributes[mod_name].append(attr_name)

    def tearDown(self):
        for mod in self.sdk_modules + self.cli_modules:
            try:
                del sys.modules[mod]
            except KeyError:
                pass

    def test_import_existing_modules(self):
        for mod_name in ['b2.console_tool', 'b2.parse_args', 'b2.version']:
            with warnings.catch_warnings(record=True) as w:
                importlib.import_module(mod_name)
                self.assertEqual(len(w), 0)

    def test_import_modules_from_sdk(self):
        for cli_mod_name, sdk_mod_name in zip(self.cli_modules, self.sdk_modules):
            with warnings.catch_warnings(record=True) as w:
                cli_mod = importlib.import_module(cli_mod_name)
                # import second time to make sure there were no more warnings displayed
                importlib.import_module(cli_mod_name)
                sdk_mod = importlib.import_module(sdk_mod_name)
                matched_warnings = list(match_warning(cli_mod_name, w))
                self.assertEqual(len(matched_warnings), 1)
                if cli_mod_name == 'b2.utils':
                    skip = ('b2', 'current_time_millis', 'repr_dict_deterministically')
                else:
                    skip = ('b2',)
                self.assertEqual(_dir(cli_mod, skip=skip), _dir(sdk_mod))

    def test_import_all_from_modules(self):
        for cli_mod_name, sdk_mod_name in zip(self.cli_modules, self.sdk_modules):
            with warnings.catch_warnings(record=True) as w:
                code = 'from {0} import *'.format(cli_mod_name)
                cli_mod = imp.new_module('tets1')
                exec(code, cli_mod.__dict__)
                sdk_mod = importlib.import_module(sdk_mod_name)
                matched_warnings = list(match_warning(cli_mod_name, w))
                self.assertEqual(len(matched_warnings), 1)
                if cli_mod_name == 'b2.utils':
                    skip = ('b2', 'current_time_millis', 'repr_dict_deterministically')
                else:
                    skip = ('b2',)
                self.assertEqual(_dir(cli_mod, skip=skip), _dir(sdk_mod))

    def test_import_attributes_one_by_one(self):
        for sdk_mod_name, attrs in self.attributes.items():
            cli_mod_name = sdk_mod_name.replace('b2sdk.', 'b2.')
            for attr in attrs:
                with warnings.catch_warnings(record=True) as w:
                    code = 'from {0} import {1}'.format(cli_mod_name, attr)
                    cli_mod = imp.new_module('tets1')
                    exec(code, cli_mod.__dict__)
                    sdk_mod = importlib.import_module(sdk_mod_name)
                    matched_warnings = list(match_warning(cli_mod_name, w))
                    self.assertEqual(len(matched_warnings), 1)
                    self.assertEqual(getattr(cli_mod, attr), getattr(sdk_mod, attr))
                self._del_mod(cli_mod_name)
                self._del_mod(sdk_mod_name)


if __name__ == '__main__':
    unittest.main()
