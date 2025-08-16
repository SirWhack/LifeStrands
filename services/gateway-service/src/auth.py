import jwt
import bcrypt
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import secrets
import hashlib
from enum import Enum

logger = logging.getLogger(__name__)

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"
    SERVICE = "service"

class Permission(Enum):
    # NPC permissions
    NPC_READ = "npc:read"
    NPC_WRITE = "npc:write"
    NPC_DELETE = "npc:delete"
    
    # Conversation permissions
    CONVERSATION_START = "conversation:start"
    CONVERSATION_READ = "conversation:read"
    CONVERSATION_END = "conversation:end"
    
    # Model permissions
    MODEL_STATUS = "model:status"
    MODEL_SWITCH = "model:switch"
    MODEL_ADMIN = "model:admin"
    
    # Admin permissions
    ADMIN_METRICS = "admin:metrics"
    ADMIN_HEALTH = "admin:health"
    ADMIN_ALERTS = "admin:alerts"
    ADMIN_USERS = "admin:users"

class AuthManager:
    """Handle authentication and authorization"""
    
    def __init__(self, jwt_secret: str = None, jwt_expiration: int = 86400):
        self.jwt_secret = jwt_secret or secrets.token_urlsafe(32)
        self.jwt_expiration = jwt_expiration  # seconds
        self.jwt_algorithm = "HS256"
        
        # In-memory user store (in production, use database)
        self.users: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.api_keys: Dict[str, Dict[str, Any]] = {}
        
        # Role-based permissions
        self.role_permissions = {
            UserRole.ADMIN: [
                Permission.NPC_READ, Permission.NPC_WRITE, Permission.NPC_DELETE,
                Permission.CONVERSATION_START, Permission.CONVERSATION_READ, Permission.CONVERSATION_END,
                Permission.MODEL_STATUS, Permission.MODEL_SWITCH, Permission.MODEL_ADMIN,
                Permission.ADMIN_METRICS, Permission.ADMIN_HEALTH, Permission.ADMIN_ALERTS, Permission.ADMIN_USERS
            ],
            UserRole.USER: [
                Permission.NPC_READ, Permission.NPC_WRITE,
                Permission.CONVERSATION_START, Permission.CONVERSATION_READ, Permission.CONVERSATION_END,
                Permission.MODEL_STATUS
            ],
            UserRole.READONLY: [
                Permission.NPC_READ,
                Permission.CONVERSATION_READ,
                Permission.MODEL_STATUS
            ],
            UserRole.SERVICE: [
                Permission.NPC_READ, Permission.NPC_WRITE,
                Permission.CONVERSATION_READ,
                Permission.MODEL_STATUS, Permission.ADMIN_METRICS, Permission.ADMIN_HEALTH
            ]
        }
        
        # Create default admin user
        self._create_default_users()
        
    def _create_default_users(self):
        """Create default admin and service users"""
        try:
            # Create admin user
            admin_password = self._hash_password("admin123")
            self.users["admin"] = {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@lifestrands.local",
                "password_hash": admin_password,
                "role": UserRole.ADMIN,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_login": None
            }
            
            # Create service user for inter-service communication
            service_password = self._hash_password("service_secret_key")
            self.users["service"] = {
                "user_id": "service",
                "username": "service",
                "email": "service@lifestrands.local",
                "password_hash": service_password,
                "role": UserRole.SERVICE,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_login": None
            }
            
            # Create API key for services
            api_key = self._generate_api_key()
            self.api_keys[api_key] = {
                "user_id": "service",
                "key_name": "default_service_key",
                "permissions": [p.value for p in self.role_permissions[UserRole.SERVICE]],
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": None,  # Never expires
                "is_active": True
            }
            
            logger.info(f"Created default users and API key: {api_key}")
            
        except Exception as e:
            logger.error(f"Error creating default users: {e}")
            
    async def authenticate_request(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and extract user info"""
        try:
            if not token:
                return None
                
            # Check if it's an API key
            if token.startswith("lsak_"):  # Life Strands API Key
                return await self._authenticate_api_key(token)
                
            # Try JWT token
            return await self._authenticate_jwt_token(token)
            
        except Exception as e:
            logger.error(f"Error authenticating request: {e}")
            return None
            
    async def _authenticate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Authenticate JWT token"""
        try:
            # Decode token
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            
            user_id = payload.get("user_id")
            session_id = payload.get("session_id")
            
            if not user_id or not session_id:
                return None
                
            # Check if user exists
            if user_id not in self.users:
                return None
                
            user = self.users[user_id]
            
            # Check if user is active
            if not user.get("is_active", False):
                return None
                
            # Check session
            if session_id not in self.sessions:
                return None
                
            session = self.sessions[session_id]
            
            # Check session expiration
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.utcnow() > expires_at:
                # Clean up expired session
                del self.sessions[session_id]
                return None
                
            return {
                "user_id": user_id,
                "username": user["username"],
                "role": user["role"],
                "session_id": session_id,
                "permissions": [p.value for p in self.role_permissions[user["role"]]]
            }
            
        except jwt.ExpiredSignatureError:
            logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid JWT token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error authenticating JWT token: {e}")
            return None
            
    async def _authenticate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Authenticate API key"""
        try:
            if api_key not in self.api_keys:
                return None
                
            key_info = self.api_keys[api_key]
            
            # Check if key is active
            if not key_info.get("is_active", False):
                return None
                
            # Check expiration
            expires_at = key_info.get("expires_at")
            if expires_at:
                if datetime.utcnow() > datetime.fromisoformat(expires_at):
                    return None
                    
            user_id = key_info["user_id"]
            user = self.users.get(user_id)
            
            if not user or not user.get("is_active", False):
                return None
                
            return {
                "user_id": user_id,
                "username": user["username"],
                "role": user["role"],
                "api_key": api_key,
                "permissions": key_info["permissions"]
            }
            
        except Exception as e:
            logger.error(f"Error authenticating API key: {e}")
            return None
            
    async def authorize_action(self, user: Dict[str, Any], resource: str, action: str) -> bool:
        """Check if user can perform action"""
        try:
            if not user:
                return False
                
            # Get required permission
            required_permission = self._get_required_permission(resource, action)
            if not required_permission:
                # No specific permission required
                return True
                
            # Check if user has permission
            user_permissions = user.get("permissions", [])
            
            # Admin users can do everything
            if user.get("role") == UserRole.ADMIN:
                return True
                
            return required_permission.value in user_permissions
            
        except Exception as e:
            logger.error(f"Error authorizing action {action} on {resource}: {e}")
            return False
            
    def _get_required_permission(self, resource: str, action: str) -> Optional[Permission]:
        """Map resource/action to required permission"""
        try:
            permission_map = {
                ("npcs", "GET"): Permission.NPC_READ,
                ("npcs", "POST"): Permission.NPC_WRITE,
                ("npcs", "PUT"): Permission.NPC_WRITE,
                ("npcs", "DELETE"): Permission.NPC_DELETE,
                
                ("conversations", "GET"): Permission.CONVERSATION_READ,
                ("conversations", "POST"): Permission.CONVERSATION_START,
                ("conversations", "DELETE"): Permission.CONVERSATION_END,
                
                ("model", "GET"): Permission.MODEL_STATUS,
                ("model", "POST"): Permission.MODEL_SWITCH,
                
                ("metrics", "GET"): Permission.ADMIN_METRICS,
                ("health", "GET"): Permission.ADMIN_HEALTH,
                ("alerts", "GET"): Permission.ADMIN_ALERTS,
                ("alerts", "POST"): Permission.ADMIN_ALERTS,
                
                ("users", "GET"): Permission.ADMIN_USERS,
                ("users", "POST"): Permission.ADMIN_USERS,
                ("users", "PUT"): Permission.ADMIN_USERS,
                ("users", "DELETE"): Permission.ADMIN_USERS,
            }
            
            return permission_map.get((resource, action))
            
        except Exception as e:
            logger.error(f"Error mapping permission for {resource}/{action}: {e}")
            return None
            
    async def create_session(self, user_id: str, password: str = None) -> Optional[str]:
        """Create new authenticated session"""
        try:
            # Authenticate user
            if password:
                if not await self._verify_password(user_id, password):
                    return None
                    
            if user_id not in self.users:
                return None
                
            user = self.users[user_id]
            if not user.get("is_active", False):
                return None
                
            # Create session
            session_id = secrets.token_urlsafe(32)
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(seconds=self.jwt_expiration)).isoformat(),
                "last_activity": datetime.utcnow().isoformat()
            }
            
            self.sessions[session_id] = session
            
            # Update user last login
            user["last_login"] = datetime.utcnow().isoformat()
            
            # Create JWT token
            token_payload = {
                "user_id": user_id,
                "session_id": session_id,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + timedelta(seconds=self.jwt_expiration)
            }
            
            token = jwt.encode(token_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            
            logger.info(f"Created session for user {user_id}")
            return token
            
        except Exception as e:
            logger.error(f"Error creating session for user {user_id}: {e}")
            return None
            
    async def revoke_session(self, session_id: str):
        """Invalidate session"""
        try:
            if session_id in self.sessions:
                user_id = self.sessions[session_id]["user_id"]
                del self.sessions[session_id]
                logger.info(f"Revoked session {session_id} for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error revoking session {session_id}: {e}")
            
    async def create_user(self, username: str, email: str, password: str, role: UserRole) -> Optional[str]:
        """Create new user"""
        try:
            # Check if user already exists
            for existing_user in self.users.values():
                if existing_user["username"] == username or existing_user["email"] == email:
                    return None
                    
            # Create user
            user_id = secrets.token_urlsafe(16)
            password_hash = self._hash_password(password)
            
            self.users[user_id] = {
                "user_id": user_id,
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "role": role,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_login": None
            }
            
            logger.info(f"Created user: {username} ({role.value})")
            return user_id
            
        except Exception as e:
            logger.error(f"Error creating user {username}: {e}")
            return None
            
    async def create_api_key(self, user_id: str, key_name: str, permissions: List[str] = None, expires_days: int = None) -> Optional[str]:
        """Create API key for user"""
        try:
            if user_id not in self.users:
                return None
                
            # Generate API key
            api_key = self._generate_api_key()
            
            # Set expiration
            expires_at = None
            if expires_days:
                expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()
                
            # Default permissions based on user role
            if not permissions:
                user_role = self.users[user_id]["role"]
                permissions = [p.value for p in self.role_permissions[user_role]]
                
            self.api_keys[api_key] = {
                "user_id": user_id,
                "key_name": key_name,
                "permissions": permissions,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at,
                "is_active": True
            }
            
            logger.info(f"Created API key for user {user_id}: {key_name}")
            return api_key
            
        except Exception as e:
            logger.error(f"Error creating API key for user {user_id}: {e}")
            return None
            
    async def revoke_api_key(self, api_key: str):
        """Revoke API key"""
        try:
            if api_key in self.api_keys:
                self.api_keys[api_key]["is_active"] = False
                user_id = self.api_keys[api_key]["user_id"]
                logger.info(f"Revoked API key for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")
            
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
    async def _verify_password(self, user_id: str, password: str) -> bool:
        """Verify password for user"""
        try:
            if user_id not in self.users:
                return False
                
            user = self.users[user_id]
            stored_hash = user["password_hash"].encode('utf-8')
            
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash)
            
        except Exception as e:
            logger.error(f"Error verifying password for user {user_id}: {e}")
            return False
            
    def _generate_api_key(self) -> str:
        """Generate API key with prefix"""
        return f"lsak_{secrets.token_urlsafe(32)}"
        
    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            if user_id not in self.users:
                return None
                
            user = self.users[user_id].copy()
            
            # Remove sensitive data
            del user["password_hash"]
            
            # Add session info
            active_sessions = [
                session for session in self.sessions.values()
                if session["user_id"] == user_id
            ]
            
            user["active_sessions"] = len(active_sessions)
            
            return user
            
        except Exception as e:
            logger.error(f"Error getting user info for {user_id}: {e}")
            return None
            
    async def list_users(self, requesting_user: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List all users (admin only)"""
        try:
            # Check admin permission
            if not await self.authorize_action(requesting_user, "users", "GET"):
                return []
                
            users = []
            for user in self.users.values():
                user_info = user.copy()
                del user_info["password_hash"]  # Remove sensitive data
                users.append(user_info)
                
            return users
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []
            
    def get_auth_stats(self) -> Dict[str, Any]:
        """Get authentication statistics"""
        try:
            active_sessions = len(self.sessions)
            active_api_keys = len([k for k in self.api_keys.values() if k["is_active"]])
            
            role_counts = {}
            for user in self.users.values():
                role = user["role"].value
                role_counts[role] = role_counts.get(role, 0) + 1
                
            return {
                "total_users": len(self.users),
                "active_sessions": active_sessions,
                "active_api_keys": active_api_keys,
                "role_distribution": role_counts,
                "jwt_expiration_seconds": self.jwt_expiration
            }
            
        except Exception as e:
            logger.error(f"Error getting auth stats: {e}")
            return {}
            
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        try:
            current_time = datetime.utcnow()
            expired_sessions = []
            
            for session_id, session in self.sessions.items():
                expires_at = datetime.fromisoformat(session["expires_at"])
                if current_time > expires_at:
                    expired_sessions.append(session_id)
                    
            for session_id in expired_sessions:
                del self.sessions[session_id]
                
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            
    async def extract_auth_from_headers(self, headers: Dict[str, str]) -> Optional[str]:
        """Extract authentication token from headers"""
        try:
            # Check Authorization header
            auth_header = headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:]  # Remove "Bearer " prefix
                
            # Check X-API-Key header
            api_key = headers.get("X-API-Key")
            if api_key:
                return api_key
                
            return None
            
        except Exception as e:
            logger.error(f"Error extracting auth from headers: {e}")
            return None
            
    async def initialize(self):
        """Initialize the AuthManager"""
        try:
            logger.info("Initializing AuthManager...")
            # Auth manager is already initialized in __init__
            logger.info("AuthManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AuthManager: {e}")
            raise