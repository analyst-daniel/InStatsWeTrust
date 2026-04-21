from __future__ import annotations


class ExecutionDisabledError(RuntimeError):
    pass


class RealExecutionClient:
    """Scaffold for future authenticated CLOB execution.

    The self-hosted scanner is read-only and paper-trading only. Real order
    methods intentionally raise until auth, geoblock checks, and explicit
    enablement are added.
    """

    enabled = False

    def place_order(self, *args, **kwargs) -> None:
        raise ExecutionDisabledError("Real execution is disabled by design.")
