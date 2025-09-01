import os
import jwt
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

class AuthManager:
    """JWT authentication and authorization for NPC service"""
    
    def __init__(self):
        self.jwt_secret = os.getenv("JWT_SECRET", "default-secret-change-in-production")
        self.jwt_algorithm = "HS256"
        self.jwt_issuer = os.getenv("JWT_ISSUER", "life-strands-system")
        self.security = HTTPBearer(auto_error=False)
        
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                issuer=self.jwt_issuer
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None
            
    def get_current_user(self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
        """Extract user from JWT token"""
        if not credentials:
            return None
            
        payload = self.decode_token(credentials.credentials)
        if not payload:
            return None
            
        return {
            "user_id": payload.get("sub"),
            "username": payload.get("username"),
            "role": payload.get("role", "user"),
            "permissions": payload.get("permissions", [])
        }
        
    def require_auth(self, credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer())) -> Dict[str, Any]:
        """Require valid authentication"""
        if not credentials:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        user = self.get_current_user(credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
            
        return user
        
    def require_role(self, required_role: str):
        """Decorator to require specific role"""
        def role_checker(user: Dict[str, Any] = Depends(self.require_auth)) -> Dict[str, Any]:
            if user.get("role") != required_role and user.get("role") != "admin":
                raise HTTPException(
                    status_code=403, 
                    detail=f"Role '{required_role}' or 'admin' required"
                )
            return user
        return role_checker
        
    def require_permission(self, required_permission: str):
        """Decorator to require specific permission"""
        def permission_checker(user: Dict[str, Any] = Depends(self.require_auth)) -> Dict[str, Any]:
            permissions = user.get("permissions", [])
            if required_permission not in permissions and "admin" not in permissions:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Permission '{required_permission}' required"
                )
            return user
        return permission_checker

# Global auth manager instance
auth_manager = AuthManager()