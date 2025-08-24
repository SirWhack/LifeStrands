import asyncio
import logging
import os
from typing import List, Optional
import aiohttp

logger = logging.getLogger(__name__)

class LocalEmbeddingManager:
    """Manages embedding generation using the model service"""
    
    def __init__(self):
        self.embedding_enabled = os.getenv('ENABLE_EMBEDDINGS', 'false').lower() == 'true'
        self.model_service_url = os.getenv('MODEL_SERVICE_URL', 'http://host.docker.internal:8001')
        self.embedding_dimensions = int(os.getenv('EMBEDDING_DIMENSIONS', '384'))
        self.session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        
    def is_enabled(self) -> bool:
        """Check if embeddings are enabled"""
        return self.embedding_enabled
        
    async def _post_with_retries(self, url: str, json_data: dict, headers: dict, attempts: int = 3, base_delay: float = 0.5) -> dict:
        """HTTP POST with retry logic and exponential backoff"""
        last_error = None
        for attempt in range(attempts):
            try:
                async with self.session.post(url, json=json_data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    error_text = await response.text()
                    last_error = f"HTTP {response.status}: {error_text}"
                    logger.warning(f"Attempt {attempt + 1}/{attempts} failed: {last_error}")
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1}/{attempts} failed with exception: {last_error}")
                
            # Wait before retry (exponential backoff)
            if attempt < attempts - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                
        raise RuntimeError(f"POST {url} failed after {attempts} attempts. Last error: {last_error}")
        
    async def initialize(self):
        """Initialize the HTTP session for model service communication"""
        if not self.embedding_enabled:
            logger.info("Embeddings are disabled, skipping initialization")
            return
            
        async with self._lock:
            if self.session is None:
                logger.info(f"Initializing embedding manager with model service: {self.model_service_url}")
                try:
                    # Create HTTP session with timeout
                    timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_read=25)
                    self.session = aiohttp.ClientSession(timeout=timeout)
                    logger.info("Embedding manager initialized successfully")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize embedding manager: {e}")
                    if self.session:
                        await self.session.close()
                        self.session = None
                    raise
                    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text"""
        if not self.embedding_enabled:
            logger.debug("Embeddings disabled, returning dummy embedding")
            # Return a dummy embedding vector
            return [0.0] * self.embedding_dimensions
            
        if self.session is None:
            await self.initialize()
            
        try:
            # Clean and prepare text
            text = text.strip()
            if not text:
                raise ValueError("Text cannot be empty")
                
            # Call model service embedding endpoint with retry logic
            result = await self._post_with_retries(
                f"{self.model_service_url}/embeddings",
                {"texts": [text]},
                {"Content-Type": "application/json"}
            )
            
            embeddings = result.get("embeddings", [])
            if not embeddings:
                raise Exception("No embeddings returned from model service")
                
            return embeddings[0]
            
        except Exception as e:
            logger.error(f"Failed to generate embedding for text: {e}")
            raise
            
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (more efficient)"""
        if not self.embedding_enabled:
            logger.debug("Embeddings disabled, returning dummy embeddings")
            # Return dummy embeddings for all texts
            return [[0.0] * self.embedding_dimensions for _ in texts]
            
        if self.session is None:
            await self.initialize()
            
        try:
            # Build map of indices to cleaned texts
            cleaned = [(i, t.strip()) for i, t in enumerate(texts)]
            payload = [t for _, t in cleaned]
            
            # If you want strict behavior, raise for any empty item
            if any(not t for t in payload):
                raise ValueError("All texts must be non-empty strings")
                
            # Call model service embedding endpoint with retry logic
            result = await self._post_with_retries(
                f"{self.model_service_url}/embeddings",
                {"texts": payload},
                {"Content-Type": "application/json"}
            )
            
            embeddings = result.get("embeddings", [])
            if len(embeddings) != len(payload):
                raise Exception(f"Expected {len(payload)} embeddings, got {len(embeddings)}")
                
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise
            
    async def generate_npc_embedding(self, npc_data: dict) -> List[float]:
        """Generate comprehensive embedding for NPC personality and background"""
        try:
            # Extract relevant text fields for embedding
            text_components = []
            
            # Background information
            background = npc_data.get('background', {})
            if background.get('occupation'):
                text_components.append(f"Occupation: {background['occupation']}")
            if background.get('personality_summary'):
                text_components.append(f"Personality: {background['personality_summary']}")
            if background.get('history'):
                text_components.append(f"History: {background['history']}")
            if background.get('education'):
                text_components.append(f"Education: {background['education']}")
                
            # Personality traits
            personality = npc_data.get('personality', {})
            if personality.get('traits'):
                traits_text = ', '.join(personality['traits'])
                text_components.append(f"Traits: {traits_text}")
            if personality.get('motivations'):
                motivations_text = ', '.join(personality['motivations'])
                text_components.append(f"Motivations: {motivations_text}")
            if personality.get('values'):
                values_text = ', '.join(personality['values'])
                text_components.append(f"Values: {values_text}")
                
            # Current status
            status = npc_data.get('current_status', {})
            if status.get('location'):
                text_components.append(f"Location: {status['location']}")
            if status.get('current_activity'):
                text_components.append(f"Activity: {status['current_activity']}")
                
            # Combine all components
            combined_text = ' | '.join(text_components)
            
            if not combined_text:
                raise ValueError("No valid text found for NPC embedding generation")
                
            return await self.generate_embedding(combined_text)
            
        except Exception as e:
            logger.error(f"Failed to generate NPC embedding: {e}")
            raise
            
    def get_embedding_dimensions(self) -> int:
        """Get the embedding dimensions for this model"""
        return self.embedding_dimensions
        
    def get_model_info(self) -> dict:
        """Get information about the current model"""
        return {
            'model_service_url': self.model_service_url,
            'dimensions': self.embedding_dimensions,
            'is_initialized': self.session is not None
        }
        
    async def shutdown(self):
        """Clean shutdown of embedding manager"""
        async with self._lock:
            if self.session is not None:
                await self.session.close()
                self.session = None
                logger.info("Embedding manager shutdown completed")

# Global instance
embedding_manager = LocalEmbeddingManager()