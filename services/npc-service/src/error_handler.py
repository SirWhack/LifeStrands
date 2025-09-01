import logging
from typing import Any, Dict, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class ServiceError(Exception):
    """Base service error with error code"""
    def __init__(self, message: str, error_code: str = "UNKNOWN_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)

class ValidationError(ServiceError):
    """Data validation error"""
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR")

class NotFoundError(ServiceError):
    """Resource not found error"""
    def __init__(self, resource: str, resource_id: str):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}", "RESOURCE_NOT_FOUND")

class DatabaseError(ServiceError):
    """Database operation error"""
    def __init__(self, message: str, operation: str):
        self.operation = operation
        super().__init__(f"Database {operation} failed: {message}", "DATABASE_ERROR")

def handle_service_error(error: Exception, operation: str, resource_id: Optional[str] = None) -> HTTPException:
    """Convert service errors to HTTP exceptions with consistent logging"""
    
    # Log error with context
    log_context = f"Operation: {operation}"
    if resource_id:
        log_context += f", Resource: {resource_id}"
    
    if isinstance(error, ValidationError):
        logger.warning(f"{log_context}, Validation error: {error.message}")
        return HTTPException(
            status_code=400,
            detail={
                "error": error.error_code,
                "message": error.message,
                "field": getattr(error, "field", None)
            }
        )
        
    elif isinstance(error, NotFoundError):
        logger.info(f"{log_context}, Resource not found: {error.message}")
        return HTTPException(
            status_code=404,
            detail={
                "error": error.error_code,
                "message": error.message,
                "resource": error.resource,
                "resource_id": error.resource_id
            }
        )
        
    elif isinstance(error, DatabaseError):
        logger.error(f"{log_context}, Database error: {error.message}")
        return HTTPException(
            status_code=500,
            detail={
                "error": error.error_code,
                "message": "Database operation failed",
                "operation": error.operation
            }
        )
        
    elif isinstance(error, ServiceError):
        logger.error(f"{log_context}, Service error: {error.message}")
        return HTTPException(
            status_code=500,
            detail={
                "error": error.error_code,
                "message": error.message
            }
        )
        
    else:
        # Generic error handling
        logger.error(f"{log_context}, Unexpected error: {str(error)}")
        return HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred"
            }
        )

def log_request_error(operation: str, resource_id: Optional[str], error: Exception):
    """Standardized error logging for requests"""
    context = f"Operation: {operation}"
    if resource_id:
        context += f", Resource: {resource_id}"
    logger.error(f"{context}, Error: {str(error)}")