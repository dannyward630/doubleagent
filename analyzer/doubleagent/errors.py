"""Define the analyzer's own exceptions, whose messages are written for the analyst."""

from __future__ import annotations


class DoubleAgentError(RuntimeError):
    """An error the command reports as `error: <message>` with exit code 2."""


class InputError(DoubleAgentError):
    """An input that is neither a file nor a directory, or an archive that cannot be extracted."""


__all__ = ["DoubleAgentError", "InputError"]
