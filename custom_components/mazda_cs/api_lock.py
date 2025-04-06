"""API lock manager for Mazda Connected Services."""
import asyncio
import logging
from enum import Enum, auto
from typing import Dict, Optional

_LOGGER = logging.getLogger(__name__)

class RequestPriority(Enum):
    """Priority levels for API requests."""
    
    # Command requests (door lock/unlock, etc.) have highest priority
    COMMAND = auto()
    
    # Regular status updates have medium priority
    STATUS = auto()
    
    # Health reports have lowest priority (can wait)
    HEALTH_REPORT = auto()

class AccountLock:
    """Lock for a specific Mazda account to coordinate API access."""
    
    def __init__(self):
        """Initialize the account lock."""
        self._lock = asyncio.Lock()
        self._current_operation = None
        self._current_priority = None
    
    class LockContext:
        """Context manager for the account lock."""
        
        def __init__(self, account_lock, priority, operation_name):
            """Initialize the lock context."""
            self.account_lock = account_lock
            self.priority = priority
            self.operation_name = operation_name
            
        async def __aenter__(self):
            """Acquire the lock."""
            # Wait for the lock
            await self.account_lock._lock.acquire()
            
            # Set the current operation and priority
            self.account_lock._current_operation = self.operation_name
            self.account_lock._current_priority = self.priority
            
            _LOGGER.debug(
                "Acquired lock for operation %s with priority %s", 
                self.operation_name, 
                self.priority
            )
            
            return self
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            """Release the lock."""
            # Clear the current operation and priority
            self.account_lock._current_operation = None
            self.account_lock._current_priority = None
            
            # Release the lock
            self.account_lock._lock.release()
            
            _LOGGER.debug(
                "Released lock for operation %s with priority %s", 
                self.operation_name, 
                self.priority
            )
    
    def acquire_context(self, priority, operation_name):
        """Get a context manager for the lock with the specified priority."""
        return self.LockContext(self, priority, operation_name)
    
    @property
    def is_locked(self):
        """Return True if the lock is currently held."""
        return self._lock.locked()
    
    @property
    def current_operation(self):
        """Return the name of the current operation holding the lock."""
        return self._current_operation
    
    @property
    def current_priority(self):
        """Return the priority of the current operation holding the lock."""
        return self._current_priority

# Global dictionary to store locks for each account
_ACCOUNT_LOCKS: Dict[str, AccountLock] = {}

def get_account_lock(account_email: str) -> AccountLock:
    """Get the lock for the specified account."""
    if account_email not in _ACCOUNT_LOCKS:
        _ACCOUNT_LOCKS[account_email] = AccountLock()
    return _ACCOUNT_LOCKS[account_email]