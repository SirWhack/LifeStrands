import os
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

    def __init__(self, jwt_secret: Optional[str] = None, jwt_expiration: int = 86400):
        # Prefer env secret; allow random secret in dev/test only
        env_secret = jwt_secret or os.getenv("AUTH_JWT_SECRET")
        if not env_secret:
            if os.getenv("ENV", "dev").lower() in {"dev", "test"}:
                logger.warning("AUTH_JWT_SECRET not set; generating ephemeral dev secret")
                env_secret = secrets.token_urlsafe(32)
            else:
                raise RuntimeError("AUTH_JWT_SECRET is required in production")
        self.jwt_secret = env_secret
        self.jwt_expiration = jwt_expiration  # seconds
        self.jwt_algorithm = "HS256"

        # In-memory stores
        self.users: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        # API keys are stored by SHA-256 digest, never plaintext
        self.api_keys: Dict[str, Dict[str, Any]] = {}

        # Role-based permissions
        self.role_permissions = {
            UserRole.ADMIN: [
                Permission.NPC_READ,
                Permission.NPC_WRITE,
                Permission.NPC_DELETE,
                Permission.CONVERSATION_START,
                Permission.CONVERSATION_READ,
                Permission.CONVERSATION_END,
                Permission.MODEL_STATUS,
                Permission.MODEL_SWITCH,
                Permission.MODEL_ADMIN,
                Permission.ADMIN_METRICS,
                Permission.ADMIN_HEALTH,
                Permission.ADMIN_ALERTS,
                Permission.ADMIN_USERS,
            ],
            UserRole.USER: [
                Permission.NPC_READ,
                Permission.NPC_WRITE,
                Permission.CONVERSATION_START,
                Permission.CONVERSATION_READ,
                Permission.CONVERSATION_END,
                Permission.MODEL_STATUS,
            ],
            UserRole.READONLY: [
                Permission.NPC_READ,
                Permission.CONVERSATION_READ,
                Permission.MODEL_STATUS,
            ],
            UserRole.SERVICE: [
                Permission.NPC_READ,
                Permission.NPC_WRITE,
                Permission.CONVERSATION_READ,
                Permission.MODEL_STATUS,
                Permission.ADMIN_METRICS,
                Permission.ADMIN_HEALTH,
            ],
        }

        # Dev-only default users
        if os.getenv("ENV", "dev").lower() in {"dev", "test"}:
            self._create_default_users()

    def _create_default_users(self):
        """Create default admin and service users (dev/test only)"""
        try:
            # Admin
            admin_password = self._hash_password("admin123")
            self.users["admin"] = {
                "user_id": "admin",
                "username": "admin",
                "email": "admin@lifestrands.local",
                "password_hash": admin_password,
                "role": UserRole.ADMIN,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_login": None,
            }
            # Service
            service_password = self._hash_password("service_secret_key")
            self.users["service"] = {
                "user_id": "service",
                "username": "service",
                "email": "service@lifestrands.local",
                "password_hash": service_password,
                "role": UserRole.SERVICE,
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_login": None,
            }
            # API key for service (store digest only)
            raw_key, digest = self._generate_api_key()
            self.api_keys[digest] = {
                "user_id": "service",
                "key_name": "default_service_key",
                "permissions": [p.value for p in self.role_permissions[UserRole.SERVICE]],
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": None,  # Never expires
                "is_active": True,
            }
            logger.info("Created default dev users and service API key (hidden)")
            # If you need to display the raw key in dev: print(raw_key)
            _ = raw_key  # avoid linter complaints
        except Exception as e:
            logger.error(f"Error creating default users: {e}")

    async def authenticate_request(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token or API key and extract user info"""
        try:
            if not token:
                return None
            # API key?
            if token.startswith("lsak_"):
                return await self._authenticate_api_key(token)
            # JWT
            return await self._authenticate_jwt_token(token)
        except Exception as e:
            logger.error(f"Error authenticating request: {e}")
            return None

    async def _authenticate_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Authenticate JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            user_id = payload.get("user_id")
            session_id = payload.get("session_id")
            if not user_id or not session_id:
                return None
            if user_id not in self.users:
                return None
            user = self.users[user_id]
            if not user.get("is_active", False):
                return None
            if session_id not in self.sessions:
                return None
            session = self.sessions[session_id]
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.utcnow() > expires_at:
                del self.sessions[session_id]
                return None
            return {
                "user_id": user_id,
                "username": user["username"],
                "role": user["role"],
                "session_id": session_id,
                "permissions": [p.value for p in self.role_permissions[user["role"]]],
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
        """Authenticate API key (hash compare)"""
        try:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            key_info = self.api_keys.get(digest)
            if not key_info:
                return None
            if not key_info.get("is_active", False):
                return None
            expires_at = key_info.get("expires_at")
            if expires_at and datetime.utcnow() > datetime.fromisoformat(expires_at):
                return None
            user_id = key_info["user_id"]
            user = self.users.get(user_id)
            if not user or not user.get("is_active", False):
                return None
            return {
                "user_id": user_id,
                "username": user["username"],
                "role": user["role"],
                "api_key": "REDACTED",
                "permissions": key_info["permissions"],
            }
        except Exception as e:
            logger.error(f"Error authenticating API key: {e}")
            return None

    async def authorize_action(self, user: Dict[str, Any], resource: str, action: str) -> bool:
        """Check if user can perform action"""
        try:
            if not user:
                return False
            required_permission = self._get_required_permission(resource, action)
            if not required_permission:
                return True
            user_permissions = user.get("permissions", [])
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

    async def create_session(self, username_or_email_or_id: str, password: str = None) -> Optional[str]:
        """Create new authenticated session"""
        try:
            # Find user by id OR username OR email
            user = self.users.get(username_or_email_or_id)
            if not user:
                user = next(
                    (
                        u
                        for u in self.users.values()
                        if u["username"] == username_or_email_or_id or u["email"] == username_or_email_or_id
                    ),
                    None,
                )
            if not user:
                return None
            if password and not await self._verify_password(user["user_id"], password):
                return None
            if not user.get("is_active", False):
                return None

            session_id = secrets.token_urlsafe(32)
            session = {
                "session_id": session_id,
                "user_id": user["user_id"],
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(seconds=self.jwt_expiration)).isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
            }
            self.sessions[session_id] = session

            user["last_login"] = datetime.utcnow().isoformat()

            token_payload = {
                "user_id": user["user_id"],
                "session_id": session_id,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + timedelta(seconds=self.jwt_expiration),
            }
            token = jwt.encode(token_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            logger.info(f"Created session for user {user['user_id']}")
            return token
        except Exception as e:
            logger.error(f"Error creating session for user {username_or_email_or_id}: {e}")
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
                "last_login": None,
            }
            logger.info(f"Created user: {username} ({role.value})")
            return user_id
        except Exception as e:
            logger.error(f"Error creating user {username}: {e}")
            return None

    async def create_api_key(
        self, user_id: str, key_name: str, permissions: List[str] = None, expires_days: int = None
    ) -> Optional[str]:
        """Create API key for user; returns the **raw key** once"""
        try:
            if user_id not in self.users:
                return None
            raw_key, digest = self._generate_api_key()
            expires_at = None
            if expires_days:
                expires_at = (datetime.utcnow() + timedelta(days=expires_days)).isoformat()

            if not permissions:
                user_role = self.users[user_id]["role"]
                permissions = [p.value for p in self.role_permissions[user_role]]

            self.api_keys[digest] = {
                "user_id": user_id,
                "key_name": key_name,
                "permissions": permissions,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at,
                "is_active": True,
            }
            logger.info(f"Created API key for user {user_id}: {key_name}")
            return raw_key
        except Exception as e:
            logger.error(f"Error creating API key for user {user_id}: {e}")
            return None

    async def revoke_api_key(self, api_key: str):
        """Revoke API key (accepts raw key)"""
        try:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            if digest in self.api_keys:
                self.api_keys[digest]["is_active"] = False
                user_id = self.api_keys[digest]["user_id"]
                logger.info(f"Revoked API key for user {user_id}")
        except Exception as e:
            logger.error(f"Error revoking API key: {e}")

    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    async def _verify_password(self, user_id: str, password: str) -> bool:
        """Verify password for user (non-blocking)"""
        try:
            if user_id not in self.users:
                return False
            user = self.users[user_id]
            stored_hash = user["password_hash"].encode("utf-8")
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, bcrypt.checkpw, password.encode("utf-8"), stored_hash)
        except Exception as e:
            logger.error(f"Error verifying password for user {user_id}: {e}")
            return False

    def _generate_api_key(self) -> (str, str):
        """Generate API key; return (raw_key, sha256_digest)"""
        kid = secrets.token_urlsafe(8)
        secret = secrets.token_urlsafe(32)
        raw = f"lsak_{kid}_{secret}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return raw, digest

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            if user_id not in self.users:
                return None
            user = self.users[user_id].copy()
            if "password_hash" in user:
                del user["password_hash"]
            active_sessions = [session for session in self.sessions.values() if session["user_id"] == user_id]
            user["active_sessions"] = len(active_sessions)
            return user
        except Exception as e:
            logger.error(f"Error getting user info for {user_id}: {e}")
            return None

    async def list_users(self, requesting_user: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List all users (admin only)"""
        try:
            if not await self.authorize_action(requesting_user, "users", "GET"):
                return []
            users = []
            for user in self.users.values():
                user_info = user.copy()
                user_info.pop("password_hash", None)
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
            role_counts: Dict[str, int] = {}
            for user in self.users.values():
                role = user["role"].value
                role_counts[role] = role_counts.get(role, 0) + 1
            return {
                "total_users": len(self.users),
                "active_sessions": active_sessions,
                "active_api_keys": active_api_keys,
                "role_distribution": role_counts,
                "jwt_expiration_seconds": self.jwt_expiration,
            }
        except Exception as e:
            logger.error(f"Error getting auth stats: {e}")
            return {}

    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        try:
            current_time = datetime.utcnow()
            expired_sessions = []
            for session_id, session in list(self.sessions.items()):
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
            auth_header = headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:]
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
            logger.info("AuthManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AuthManager: {e}")
            raise
