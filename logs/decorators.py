from __future__ import annotations

import inspect
from functools import wraps

from logs.constants import ExecutionStatus, LogLevel
from logs.service import LoggerService
from logs.utils import (
    duration_ms,
    error_path_from_exception,
    exception_type_name,
    function_name_from_exception,
    now_ms,
    stacktrace_from_exception,
)


def trace_operation(
    operation_type: str,
    workflow_name: str | None = None,
    service_name: str | None = None,
):
    def decorator(func):
        def _success(start):
            LoggerService.log_execution(
                LoggerService.execution_from_context(
                    operation_type=operation_type,
                    workflow_name=workflow_name,
                    service_name=service_name,
                    status=ExecutionStatus.SUCCESS,
                    level=LogLevel.INFO,
                    duration_ms=duration_ms(start),
                    message=f"{func.__name__} completed",
                )
            )

        def _failure(start, exc):
            error_path = error_path_from_exception(exc, f"{func.__module__}.{func.__name__}()")
            LoggerService.log_execution(
                LoggerService.execution_from_context(
                    operation_type=operation_type,
                    workflow_name=workflow_name,
                    service_name=service_name,
                    status=ExecutionStatus.FAILED,
                    level=LogLevel.ERROR,
                    duration_ms=duration_ms(start),
                    error_message=str(exc),
                    error_path=error_path,
                )
            )
            LoggerService.log_error(
                LoggerService.error_from_context(
                    operation_type=operation_type,
                    workflow_name=workflow_name,
                    service_name=service_name,
                    level=LogLevel.ERROR,
                    error_type=exception_type_name(exc),
                    exception_type=exception_type_name(exc),
                    function_name=function_name_from_exception(exc, func.__name__),
                    error_message=str(exc),
                    error_path=error_path,
                    stacktrace=stacktrace_from_exception(exc),
                )
            )

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = now_ms()
                try:
                    result = await func(*args, **kwargs)
                    _success(start)
                    return result
                except Exception as exc:
                    _failure(start, exc)
                    raise

            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            start = now_ms()
            try:
                result = func(*args, **kwargs)
                _success(start)
                return result
            except Exception as exc:
                _failure(start, exc)
                raise

        return wrapper

    return decorator
