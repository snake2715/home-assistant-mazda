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
    """A simplified lock that ensures serial API access with minimal prioritization.
    
    This lock ensures that:
    1. API calls happen one at a time (serialized)
    2. User commands (high priority) can 'skip ahead' of waiting background tasks
    3. Maintains simple FIFO ordering otherwise
    """
    
    def __init__(self, account_id=None):
        """Initialize the priority lock.
        
        Args:
            account_id: Optional identifier for the account this lock belongs to
        """
        self._lock = asyncio.Lock()
        self._user_command_event = asyncio.Event()
        self._user_command_event.set()  # Initially no user commands are waiting
        self._current_operation = None
        self._current_priority = None
        self._start_time = None
        self._account_id = account_id
        
    async def acquire(self, priority, operation_name):
        """Acquire the lock with a given priority level.
        
        Args:
            priority: Priority level from RequestPriority enum
            operation_name: Name of the operation for logging
            
        Returns:
            True when the lock is acquired
        """
        # If this is a high-priority USER_COMMAND, signal that one is waiting
        if priority == RequestPriority.USER_COMMAND:
            _LOGGER.debug(
                "User command %s is waiting for lock%s",
                operation_name,
                f" (account: {self._account_id})" if self._account_id else ""
            )
            self._user_command_event.clear()
        
        # For background tasks, wait for any pending user commands
        elif self._user_command_event.is_set() == False:
            _LOGGER.debug(
                "Background task %s waiting for pending user command to complete%s",
                operation_name,
                f" (account: {self._account_id})" if self._account_id else ""
            )
            await self._user_command_event.wait()
        
        # Wait to acquire the actual lock (serializes all access)
        _LOGGER.debug(
            "Waiting to acquire lock for %s (priority %s)%s",
            operation_name,
            priority.name,
            f" (account: {self._account_id})" if self._account_id else ""
        )
        
        try:
            await self._lock.acquire()
            self._current_operation = operation_name
            self._current_priority = priority
            self._start_time = time.time()
            
            _LOGGER.debug(
                "Lock acquired for %s (priority %s)%s",
                operation_name,
                priority.name,
                f" (account: {self._account_id})" if self._account_id else ""
            )
            
            return True
        except asyncio.CancelledError:
            _LOGGER.warning(
                f"Lock acquisition for {operation_name} was cancelled%s",
                f" (account: {self._account_id})" if self._account_id else ""
            )
            raise
    
    def release(self):
        """Release the lock."""
        if self._lock.locked():
            duration = time.time() - self._start_time if self._start_time else 0
            _LOGGER.debug(
                "Releasing lock for %s (priority %s) after %.2f seconds%s",
                self._current_operation,
                self._current_priority.name if self._current_priority is not None else "None",
                duration,
                f" (account: {self._account_id})" if self._account_id else ""
            )
            
            # Store variables before clearing
            old_operation = self._current_operation
            old_priority = self._current_priority
            
            # Reset state
            self._current_operation = None
            self._current_priority = None
            self._start_time = None
            
            # Release lock
            try:
                self._lock.release()
                _LOGGER.debug(
                    f"Lock successfully released for {old_operation}%s",
                    f" (account: {self._account_id})" if self._account_id else ""
                )
                
                # If this was a user command, signal that it's complete
                if old_priority == RequestPriority.USER_COMMAND:
                    self._user_command_event.set()
                    
            except RuntimeError as e:
                _LOGGER.error(
                    f"Error releasing lock for {old_operation}: {str(e)}%s",
                    f" (account: {self._account_id})" if self._account_id else ""
                )
        else:
            _LOGGER.warning(
                "Attempted to release an unlocked lock%s",
                f" (account: {self._account_id})" if self._account_id else ""
            )
    
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

# Dictionary to store lock instances by account ID
_account_locks = {}

# Default singleton instance for backward compatibility
priority_lock = PriorityLock()

def get_account_lock(account_id):
    """Get or create a PriorityLock for a specific account.
    
    Args:
        account_id: Identifier for the account (typically email address)
        
    Returns:
        A PriorityLock instance specific to this account
    """
    if account_id not in _account_locks:
        _account_locks[account_id] = PriorityLock(account_id)
    return _account_locks[account_id]
