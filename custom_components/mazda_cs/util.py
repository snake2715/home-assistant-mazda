"""Utility functions for Mazda Connected Services integration."""
import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union, cast

_LOGGER = logging.getLogger(__name__)

# Type variable for return type
T = TypeVar('T')

class RetryConfig:
    """Configuration class for retry mechanism."""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_retry_backoff: float = 30.0,
        retry_codes: Optional[list[str]] = None,
        factor: float = 2.0,
        jitter: float = 0.2
    ):
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts (minimum 1)
            retry_delay: Initial delay between retries in seconds
            max_retry_backoff: Maximum delay between retries in seconds
            retry_codes: List of error codes or types to retry, None means retry all
            factor: Exponential backoff factor (must be >= 1.0)
            jitter: Random jitter factor (0-1.0) to add to delay
        """
        self.max_attempts = max(1, max_retries)
        self.min_delay = max(0.0, retry_delay)
        self.max_delay = max(self.min_delay, max_retry_backoff)
        self.retry_codes = retry_codes
        self.factor = max(1.0, factor)
        self.jitter = max(0.0, min(1.0, jitter))


async def with_retry(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    retry_config: Optional[RetryConfig] = None,
    **kwargs: Any
) -> T:
    """Execute a coroutine with retry logic and exponential backoff.

    Args:
        func: The async function to call
        *args: Positional arguments to pass to the function
        retry_config: Configuration for retry behavior
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The return value from the function

    Raises:
        Exception: The last exception encountered if all retries fail
    """
    if retry_config is None:
        retry_config = RetryConfig()

    attempt = 0
    last_exception = None
    start_time = time.time()

    while attempt < retry_config.max_attempts:
        try:
            if attempt > 0:
                # Calculate delay with exponential backoff and jitter
                delay = min(
                    retry_config.max_delay,
                    retry_config.min_delay * (retry_config.factor ** (attempt - 1))
                )
                
                # Add random jitter to prevent synchronized retries
                if retry_config.jitter > 0:
                    delay += delay * random.uniform(0, retry_config.jitter)
                
                _LOGGER.debug(
                    "Retry attempt %d/%d for %s, waiting %.2f seconds",
                    attempt, 
                    retry_config.max_attempts - 1,
                    func.__name__,
                    delay
                )
                
                await asyncio.sleep(delay)
            
            result = await func(*args, **kwargs)
            
            if attempt > 0:
                total_time = time.time() - start_time
                _LOGGER.info(
                    "Operation %s succeeded on attempt %d/%d after %.2f seconds",
                    func.__name__,
                    attempt + 1,
                    retry_config.max_attempts,
                    total_time
                )
            
            return result
            
        except Exception as ex:
            attempt += 1
            last_exception = ex
            
            # Check if this exception should be retried
            should_retry = True
            if retry_config.retry_codes:
                error_code = getattr(ex, 'code', None)
                error_type = type(ex).__name__
                should_retry = (
                    error_code in retry_config.retry_codes or 
                    error_type in retry_config.retry_codes
                )
            
            if not should_retry or attempt >= retry_config.max_attempts:
                _LOGGER.warning(
                    "Operation %s failed after %d attempts: %s",
                    func.__name__,
                    attempt,
                    str(ex)
                )
                raise
            
            _LOGGER.debug(
                "Attempt %d/%d for %s failed: %s",
                attempt,
                retry_config.max_attempts,
                func.__name__,
                str(ex)
            )

    # This line should not be reached due to the raise in the loop,
    # but is here for type safety
    assert last_exception is not None
    raise last_exception


def retry_decorator(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    max_retry_backoff: float = 30.0,
    retry_codes: Optional[list[str]] = None,
    factor: float = 2.0,
    jitter: float = 0.2
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """Create a decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Minimum delay between retries in seconds
        max_retry_backoff: Maximum delay between retries in seconds
        retry_codes: List of error codes or types to retry, None means retry all
        factor: Exponential backoff factor
        jitter: Random jitter factor (0-1.0) to add to delay

    Returns:
        Decorator function
    """
    retry_config = RetryConfig(
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_backoff=max_retry_backoff,
        retry_codes=retry_codes,
        factor=factor,
        jitter=jitter
    )
    
    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await with_retry(func, *args, retry_config=retry_config, **kwargs)
        return wrapper
    
    return decorator


async def with_advanced_timeout(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    timeout_seconds: float = 30.0,
    retry_config: Optional[RetryConfig] = None,
    **kwargs: Any
) -> T:
    """Run an async function with timeout and retry capability.
    
    Args:
        func: The async function to execute
        *args: Arguments to pass to the function
        timeout_seconds: Maximum time to wait for task completion
        retry_config: Configuration for retry behavior, including:
                     - max_retries: Maximum number of retries after timeout
                     - retry_delay: Initial delay between retries
                     - max_retry_backoff: Maximum delay with backoff
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The return value from the function
        
    Raises:
        asyncio.TimeoutError: If the operation times out and retries are exhausted
        Any other exception raised by the function
    """
    if retry_config is None:
        retry_config = RetryConfig()
        
    attempt = 0
    
    while attempt < retry_config.max_attempts:
        try:
            attempt += 1
            is_retry = attempt > 1
            
            if is_retry:
                # Calculate delay with exponential backoff and jitter
                delay = min(
                    retry_config.max_delay,
                    retry_config.min_delay * (retry_config.factor ** (attempt - 2))
                )
                
                # Add random jitter to prevent synchronized retries
                if retry_config.jitter > 0:
                    delay += delay * random.uniform(0, retry_config.jitter)
                
                _LOGGER.debug(
                    "Timeout retry attempt %d/%d for %s, waiting %.2f seconds",
                    attempt - 1,
                    retry_config.max_attempts - 1,
                    func.__name__,
                    delay
                )
                await asyncio.sleep(delay)
            
            # Use asyncio.timeout context
            async with asyncio.timeout(timeout_seconds):
                return await func(*args, **kwargs)
                
        except asyncio.TimeoutError:
            if attempt >= retry_config.max_attempts:
                _LOGGER.error(
                    "Operation %s timed out after %.2f seconds with %d retry attempts",
                    func.__name__,
                    timeout_seconds,
                    attempt - 1
                )
                raise
            
            _LOGGER.warning(
                "Operation %s timed out after %.2f seconds, will retry (%d/%d)",
                func.__name__,
                timeout_seconds,
                attempt,
                retry_config.max_attempts - 1
            )

    # This should never be reached
    raise asyncio.TimeoutError(f"Operation {func.__name__} timed out")
