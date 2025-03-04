"""Priority-based lock system for Mazda Connected Services API requests."""
import asyncio
import logging
import time
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

class RequestPriority(IntEnum):
    """Priority levels for API requests."""
    USER_COMMAND = 0    # Highest priority (door locks, engine start/stop)
    VEHICLE_STATUS = 1  # Medium priority (regular status updates)
    HEALTH_REPORT = 2   # Lowest priority (health report updates)

class PriorityLock:
    """A lock that can be acquired with priority levels.
    
    This lock ensures that higher priority operations can preempt lower
    priority operations that are waiting, while still maintaining order
    within the same priority level.
    """
    
    def __init__(self):
        """Initialize the priority lock."""
        self._lock = asyncio.Lock()
        self._current_operation = None
        self._current_priority = None
        self._start_time = None
    
    async def acquire(self, priority, operation_name):
        """Acquire the lock with a given priority level.
        
        Args:
            priority: Priority level from RequestPriority enum
            operation_name: Name of the operation for logging
            
        Returns:
            True when the lock is acquired
        """
        while True:
            # If nobody has the lock, take it
            if not self._lock.locked():
                await self._lock.acquire()
                self._current_priority = priority
                self._current_operation = operation_name
                self._start_time = time.time()
                _LOGGER.debug(
                    "Lock acquired for %s (priority %s)",
                    operation_name,
                    priority.name
                )
                return True
            
            # If lock is held by a lower priority operation, wait for it
            if self._current_priority is not None and priority < self._current_priority:
                _LOGGER.debug(
                    "Waiting for lower priority operation %s (priority %s) to complete before running %s (priority %s)",
                    self._current_operation,
                    self._current_priority.name if self._current_priority is not None else "None",
                    operation_name,
                    priority.name
                )
                # Just wait a bit and try again
                await asyncio.sleep(1)
                continue
            
            # Otherwise, priority is equal or lower, so wait for lock normally
            _LOGGER.debug(
                "Waiting for operation %s (priority %s) to complete before running %s (priority %s)",
                self._current_operation,
                self._current_priority.name if self._current_priority is not None else "None",
                operation_name,
                priority.name
            )
            await asyncio.sleep(1)
    
    def release(self):
        """Release the lock."""
        if self._lock.locked():
            duration = time.time() - self._start_time if self._start_time else 0
            _LOGGER.debug(
                "Releasing lock for %s (priority %s) after %.2f seconds",
                self._current_operation,
                self._current_priority.name if self._current_priority is not None else "None",
                duration
            )
            self._current_operation = None
            self._current_priority = None
            self._start_time = None
            self._lock.release()
    
    @property
    def locked(self):
        """Return whether the lock is currently held."""
        return self._lock.locked()
    
    @property
    def current_operation(self):
        """Return the name of the current operation holding the lock."""
        return self._current_operation
    
    @property
    def current_priority(self):
        """Return the priority of the current operation holding the lock."""
        return self._current_priority

# Singleton instance
priority_lock = PriorityLock()
