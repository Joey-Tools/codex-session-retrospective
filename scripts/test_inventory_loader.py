#!/usr/bin/env -S python3 -I -B -S
"""Closed unittest module and method discovery for the shared test inventory."""

from __future__ import annotations

from collections.abc import Callable
import inspect
from types import MethodType, ModuleType
import unittest


class ClosedTestDiscoveryError(ValueError):
    """Raised when a test module can influence or hide discovery."""


def _wrapped_function_chain(candidate: object) -> tuple[object, ...]:
    chain: list[object] = []
    while True:
        if not inspect.isfunction(candidate) or candidate in chain:
            raise ClosedTestDiscoveryError("test method wrapper chain is not supported")
        chain.append(candidate)
        if not hasattr(candidate, "__wrapped__"):
            return tuple(chain)
        candidate = candidate.__wrapped__


def _closed_test_method_names(
    loader: unittest.TestLoader, test_case: type[unittest.TestCase]
) -> tuple[str, ...]:
    if any("runTest" in vars(base) for base in test_case.__mro__):
        raise ClosedTestDiscoveryError("runTest fallback is not supported")
    names: set[str] = set()
    for base in reversed(test_case.__mro__):
        for name, member in vars(base).items():
            if not name.startswith(loader.testMethodPrefix):
                continue
            candidate = (
                member.__func__
                if isinstance(member, (classmethod, staticmethod))
                else member
            )
            chain = _wrapped_function_chain(candidate)
            if any(
                inspect.isgeneratorfunction(function)
                or inspect.isasyncgenfunction(function)
                for function in chain
            ):
                raise ClosedTestDiscoveryError(
                    "generator test methods are not supported"
                )
            if any(map(inspect.iscoroutinefunction, chain)) and not (
                inspect.iscoroutinefunction(chain[0])
                and issubclass(test_case, unittest.IsolatedAsyncioTestCase)
            ):
                raise ClosedTestDiscoveryError(
                    "async test methods require IsolatedAsyncioTestCase"
                )
            names.add(name)
    return tuple(sorted(names))


def _closed_test_cases(
    loader: unittest.TestLoader, module: ModuleType
) -> tuple[type[unittest.TestCase], ...]:
    cases: list[type[unittest.TestCase]] = []
    for _name, value in sorted(vars(module).items()):
        if not isinstance(value, type) or not issubclass(value, unittest.TestCase):
            continue
        if type(value) is not type:
            raise ClosedTestDiscoveryError("custom test metaclass is not supported")
        if value.__module__ != module.__name__:
            if _closed_test_method_names(loader, value):
                raise ClosedTestDiscoveryError(
                    "test modules must not import external TestCase classes"
                )
            continue
        cases.append(value)
    return tuple(cases)


def _call_test_method_requiring_none(
    test: unittest.TestCase, method: Callable[[], object]
) -> None:
    if isinstance(test, unittest.IsolatedAsyncioTestCase):
        result = test._callMaybeAsync(method)
    else:
        result = method()
    if result is None:
        return
    close = getattr(result, "close", None)
    if callable(close):
        close()
    raise ClosedTestDiscoveryError("test methods must return None")


def _instrument_test_case(test: unittest.TestCase) -> unittest.TestCase:
    test._callTestMethod = MethodType(_call_test_method_requiring_none, test)
    return test


class ClosedTestLoader(unittest.TestLoader):
    """Build suites without module or metaclass enumeration hooks."""

    _FORBIDDEN_MODULE_HOOKS = frozenset({"__dir__", "__getattr__", "load_tests"})

    def loadTestsFromModule(
        self, module: ModuleType, *, pattern: str | None = None
    ) -> unittest.TestSuite:
        del pattern
        if type(module) is not ModuleType:
            raise ClosedTestDiscoveryError("test module type is not supported")
        namespace = vars(module)
        if self._FORBIDDEN_MODULE_HOOKS.intersection(namespace):
            raise ClosedTestDiscoveryError(
                "test modules must not define dynamic discovery hooks"
            )
        suites = map(self._load_closed_test_case, _closed_test_cases(self, module))
        return self.suiteClass(suites)

    def _load_closed_test_case(
        self, test_case: type[unittest.TestCase]
    ) -> unittest.TestSuite:
        names = _closed_test_method_names(self, test_case)
        return self.suiteClass(map(_instrument_test_case, map(test_case, names)))
