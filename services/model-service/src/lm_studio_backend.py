import asyncio
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class LMStudioBackend:
    """LM Studio backend implementation for model service"""
    
    def __init__(self, base_url: str = None):
        import os
        # Default to environment variable or localhost
        if base_url is None:
            base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize HTTP session and verify LM Studio connection"""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300, connect=10)
            )
            
            # Test connection
            async with self.session.get(f"{self.base_url}/v1/models") as response:
                if response.status == 200:
                    models = await response.json()
                    logger.info(f"✅ LM Studio connected - {len(models['data'])} models available")
                    self._initialized = True
                    return True
                else:
                    logger.error(f"LM Studio connection failed: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to initialize LM Studio backend: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
            self.session = None
        self._initialized = False
    
    async def get_models(self) -> Dict[str, Any]:
        """Get available models from LM Studio"""
        if not self._initialized or not self.session:
            raise RuntimeError("LM Studio backend not initialized")
            
        try:
            async with self.session.get(f"{self.base_url}/v1/models") as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            raise
    
    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate chat completion with streaming support"""
        if not self._initialized or not self.session:
            raise RuntimeError("LM Studio backend not initialized")
        
        # Auto-select model if not specified
        if not model:
            models = await self.get_models()
            chat_models = [m for m in models['data'] if 'embed' not in m['id'].lower()]
            if chat_models:
                model = chat_models[0]['id']
            else:
                raise RuntimeError("No chat models available")
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
            **kwargs
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                
                if stream:
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data: '):
                            data_str = line[6:]  # Remove 'data: ' prefix
                            if data_str == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and data['choices']:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        yield delta['content']
                            except json.JSONDecodeError:
                                continue
                else:
                    result = await response.json()
                    if 'choices' in result and result['choices']:
                        content = result['choices'][0]['message']['content']
                        yield content
                        
        except Exception as e:
            logger.error(f"Error generating chat completion: {e}")
            raise
    
    async def generate_completion_from_prompt(
        self,
        prompt: str,
        model: str = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate completion from a single prompt (convert to chat format)"""
        messages = [{"role": "user", "content": prompt}]
        async for token in self.generate_chat_completion(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=stream,
            **kwargs
        ):
            yield token
    
    async def generate_embeddings(self, texts: List[str], model: str = None) -> List[List[float]]:
        """Generate embeddings using LM Studio"""
        if not self._initialized or not self.session:
            raise RuntimeError("LM Studio backend not initialized")
        
        # Auto-select embedding model if not specified
        if not model:
            models = await self.get_models()
            embedding_models = [m for m in models['data'] if 'embed' in m['id'].lower()]
            if embedding_models:
                model = embedding_models[0]['id']
            else:
                raise RuntimeError("No embedding models available")
        
        embeddings = []
        for text in texts:
            payload = {
                "model": model,
                "input": text
            }
            
            try:
                async with self.session.post(
                    f"{self.base_url}/v1/embeddings",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
                    if 'data' in result and result['data']:
                        embeddings.append(result['data'][0]['embedding'])
                    else:
                        raise RuntimeError(f"Invalid embedding response for text: {text[:50]}...")
                        
            except Exception as e:
                logger.error(f"Error generating embedding for text: {e}")
                raise
        
        return embeddings
    
    async def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get information about a specific model"""
        models = await self.get_models()
        for model in models['data']:
            if model['id'] == model_id:
                return model
        raise ValueError(f"Model {model_id} not found")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check LM Studio health and model availability"""
        try:
            if not self._initialized:
                return {"status": "error", "error": "Backend not initialized"}
            
            models = await self.get_models()
            chat_models = [m for m in models['data'] if 'embed' not in m['id'].lower()]
            embedding_models = [m for m in models['data'] if 'embed' in m['id'].lower()]
            
            return {
                "status": "healthy",
                "backend": "lm_studio",
                "base_url": self.base_url,
                "total_models": len(models['data']),
                "chat_models": len(chat_models),
                "embedding_models": len(embedding_models),
                "available_models": [m['id'] for m in models['data']]
            }
            
        except Exception as e:
            logger.error(f"LM Studio health check failed: {e}")
            return {
                "status": "error", 
                "backend": "lm_studio",
                "error": str(e)
            }