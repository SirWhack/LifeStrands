"""
Configuration loader for native service execution
Handles environment variables and provides defaults for local execution
"""
import os
from typing import Dict, Any

class NativeConfig:
    """Configuration class for native service execution"""
    
    def __init__(self, service_name: str = None):
        self.service_name = service_name
        self._load_env_file()
        
    def _load_env_file(self):
        """Load environment variables from .env.native if it exists"""
        env_file = os.path.join(os.getcwd(), '.env.native')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        if key not in os.environ:
                            os.environ[key] = value
    
    @property
    def database_url(self) -> str:
        """Database connection URL"""
        return os.getenv(
            "DATABASE_URL", 
            "postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands"
        )
    
    @property 
    def redis_url(self) -> str:
        """Redis connection URL"""
        return os.getenv(
            "REDIS_URL",
            "redis://:redis_password@localhost:6379"
        )
    
    @property
    def model_service_url(self) -> str:
        """Model service URL - native Windows service"""
        return os.getenv(
            "MODEL_SERVICE_URL",
            "http://localhost:8001"
        )
    
    @property
    def service_urls(self) -> Dict[str, str]:
        """URLs for all services"""
        return {
            "gateway": os.getenv("GATEWAY_URL", "http://localhost:8000"),
            "chat_service": os.getenv("CHAT_SERVICE_URL", "http://localhost:8002"),
            "npc_service": os.getenv("NPC_SERVICE_URL", "http://localhost:8003"),
            "summary_service": os.getenv("SUMMARY_SERVICE_URL", "http://localhost:8004"),
            "monitor_service": os.getenv("MONITOR_SERVICE_URL", "http://localhost:8005")
        }
    
    @property
    def cors_origins(self) -> list:
        """CORS allowed origins"""
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:3002")
        return origins.split(',')
    
    @property
    def jwt_secret(self) -> str:
        """JWT signing secret"""
        return os.getenv("JWT_SECRET", "your-jwt-secret-here-change-in-production")
    
    @property
    def log_level(self) -> str:
        """Logging level"""
        return os.getenv("LOG_LEVEL", "INFO")
    
    @property
    def max_concurrent_conversations(self) -> int:
        """Maximum concurrent conversations"""
        return int(os.getenv("MAX_CONCURRENT_CONVERSATIONS", "50"))
    
    @property
    def conversation_timeout_minutes(self) -> int:
        """Conversation timeout in minutes"""
        return int(os.getenv("CONVERSATION_TIMEOUT_MINUTES", "30"))
    
    @property
    def rate_limit_requests_per_minute(self) -> int:
        """Rate limit for requests"""
        return int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100"))
    
    @property
    def enable_embeddings(self) -> bool:
        """Whether to enable embeddings"""
        return os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true"
    
    @property
    def summary_auto_approval_threshold(self) -> float:
        """Auto-approval threshold for summary changes"""
        return float(os.getenv("SUMMARY_AUTO_APPROVAL_THRESHOLD", "0.8"))
    
    @property
    def summary_worker_concurrency(self) -> int:
        """Number of summary worker threads"""
        return int(os.getenv("SUMMARY_WORKER_CONCURRENCY", "3"))
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """Get configuration specific to a service"""
        base_config = {
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "model_service_url": self.model_service_url,
            "log_level": self.log_level,
            "service_urls": self.service_urls
        }
        
        service_configs = {
            "gateway": {
                **base_config,
                "cors_origins": self.cors_origins,
                "jwt_secret": self.jwt_secret,
                "rate_limit_requests_per_minute": self.rate_limit_requests_per_minute
            },
            "chat": {
                **base_config,
                "max_concurrent_conversations": self.max_concurrent_conversations,
                "conversation_timeout_minutes": self.conversation_timeout_minutes
            },
            "npc": {
                **base_config,
                "enable_embeddings": self.enable_embeddings
            },
            "summary": {
                **base_config,
                "summary_auto_approval_threshold": self.summary_auto_approval_threshold,
                "summary_worker_concurrency": self.summary_worker_concurrency
            },
            "monitor": {
                **base_config,
                "metrics_retention_days": int(os.getenv("METRICS_RETENTION_DAYS", "30")),
                "alert_webhook": os.getenv("ALERT_WEBHOOK", "")
            }
        }
        
        return service_configs.get(service_name, base_config)

# Global config instance
config = NativeConfig()