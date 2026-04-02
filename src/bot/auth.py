"""
Single-user authorization for the Dhaara bot.
All messages from unauthorized users are silently ignored.
"""
import logging
from functools import wraps
from telegram import Update

logger = logging.getLogger(__name__)


def authorized_only(authorized_user_id: int):
    """
    Decorator factory. Wraps a handler so it only runs for the authorized user.
    """
    def decorator(handler):
        @wraps(handler)
        async def wrapper(update: Update, context, *args, **kwargs):
            user = update.effective_user
            if user is None or user.id != authorized_user_id:
                if user:
                    logger.warning(f"Unauthorized access attempt from user_id={user.id}")
                return  # Silently ignore
            return await handler(update, context, *args, **kwargs)
        return wrapper
    return decorator
