"""
Mock Model Service Implementation

Provides canned responses for testing other services without requiring GPU resources.
Simulates the behavior of the real model service including streaming, embeddings, 
and model state management.
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from typing import Dict, List, AsyncGenerator, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class MockModelState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    LOADED = "loaded"
    GENERATING = "generating"
    UNLOADING = "unloading"
    ERROR = "error"

class MockModelService:
    """Mock implementation of the model service for testing"""
    
    def __init__(self):
        self.current_model_type = None
        self.state = MockModelState.IDLE
        self.request_count = 0
        self.last_request_time = None
        self.mock_vram_usage = 0
        self.generation_speed = 25  # tokens per second
        self.start_time = datetime.utcnow()
        
        # Mock model configurations
        self.model_configs = {
            "chat": {
                "name": "Mock Chat Model",
                "size": "24B",
                "context_size": 8192,
                "vram_usage": 18000,  # MB
                "load_time": 15  # seconds
            },
            "summary": {
                "name": "Mock Summary Model", 
                "size": "7B",
                "context_size": 4096,
                "vram_usage": 8000,  # MB
                "load_time": 8  # seconds
            },
            "embedding": {
                "name": "Mock Embedding Model",
                "size": "384MB", 
                "context_size": 512,
                "vram_usage": 500,  # MB
                "load_time": 3  # seconds
            }
        }
        
        # Canned responses for different scenarios
        self.chat_responses = [
            "Hello! I'm a helpful AI assistant. How can I help you today?",
            "That's an interesting question. Let me think about that for a moment.",
            "I understand what you're asking. Here's my perspective on this topic.",
            "Based on the information you've provided, I would suggest the following approach.",
            "I appreciate you sharing that with me. It sounds like you're dealing with something important.",
            "Let me help you work through this step by step.",
            "That reminds me of something I learned previously. Would you like me to share that insight?",
            "I can see why you might feel that way. It's a complex situation.",
            "From my understanding, there are a few different ways to look at this.",
            "Thank you for being so patient with me as we explore this together."
        ]
        
        self.summary_responses = [
            "This conversation covered several key topics including personal interests and future goals.",
            "The discussion revealed important character development and relationship dynamics.",
            "Main themes included problem-solving approaches and emotional responses to challenges.",
            "The conversation showed growth in understanding and mutual respect between participants.",
            "Key insights emerged about personality traits and decision-making patterns.",
            "The dialogue explored complex feelings about change and adaptation.",
            "Important relationship milestones and shared experiences were discussed.",
            "The conversation revealed underlying motivations and core values.",
            "Significant emotional developments and trust-building occurred during this interaction.",
            "The discussion highlighted personal strengths and areas for growth."
        ]
        
        self.npc_responses = [
            "The townsfolk seem restless tonight. Something's stirring in the shadows beyond the walls.",
            "My family has lived in these lands for generations. We know the old ways, the forgotten paths.",
            "The merchant's tale sounds suspicious. Gold doesn't just disappear from locked vaults.",
            "I've seen strange lights in the forest lately. The animals are acting peculiar too.",
            "Years of training have prepared me for this moment. My blade is ready, my resolve firm.",
            "The prophecy speaks of dark times ahead. We must gather allies and prepare our defenses.",
            "Trust comes slowly in these parts. Strangers often bring more trouble than they're worth.",
            "The king's taxes grow heavier each season. Soon we'll have nothing left to give.",
            "Magic flows differently here than in the cities. The old spirits still watch over us.",
            "My grandmother told stories of times like these. History has a way of repeating itself."
        ]

    async def initialize(self):
        """Initialize the mock service"""
        logger.info("Initializing mock model service...")
        self.state = MockModelState.IDLE
        await asyncio.sleep(0.1)  # Simulate brief initialization
        logger.info("Mock model service initialized successfully")
        
    async def load_model(self, model_type: str) -> bool:
        """Simulate model loading with realistic timing"""
        if model_type not in self.model_configs:
            logger.error(f"Unknown model type: {model_type}")
            return False
            
        logger.info(f"Loading mock {model_type} model...")
        self.state = MockModelState.LOADING
        
        # Simulate model loading time
        config = self.model_configs[model_type]
        load_time = config["load_time"]
        
        # Add some random variation
        actual_load_time = load_time + random.uniform(-2, 3)
        await asyncio.sleep(max(0.5, actual_load_time))
        
        self.current_model_type = model_type
        self.mock_vram_usage = config["vram_usage"]
        self.state = MockModelState.LOADED
        
        logger.info(f"Mock {model_type} model loaded successfully")
        return True
        
    async def unload_current_model(self):
        """Simulate model unloading"""
        if self.current_model_type:
            logger.info(f"Unloading mock {self.current_model_type} model...")
            self.state = MockModelState.UNLOADING
            await asyncio.sleep(0.5)  # Brief unload time
            
        self.current_model_type = None
        self.mock_vram_usage = 0
        self.state = MockModelState.IDLE
        logger.info("Mock model unloaded successfully")
        
    async def generate_stream(self, prompt: str, params: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """Generate streaming text response"""
        self.state = MockModelState.GENERATING
        self.request_count += 1
        self.last_request_time = datetime.utcnow()
        
        try:
            # Select appropriate response set
            if self.current_model_type == "summary":
                response = random.choice(self.summary_responses)
            elif self.current_model_type == "chat":
                # For chat, sometimes use NPC-style responses based on prompt
                if any(word in prompt.lower() for word in ["npc", "character", "medieval", "fantasy", "kingdom"]):
                    response = random.choice(self.npc_responses)
                else:
                    response = random.choice(self.chat_responses)
            else:
                response = random.choice(self.chat_responses)
            
            # Add some contextual variation based on prompt
            if "how are you" in prompt.lower():
                response = "I'm doing well, thank you for asking! " + response
            elif "help" in prompt.lower():
                response = "Of course, I'd be happy to help! " + response
            elif "?" in prompt:
                response = "That's a great question. " + response
                
            # Simulate realistic token streaming
            words = response.split()
            token_delay = 1.0 / self.generation_speed  # Delay between tokens
            
            for i, word in enumerate(words):
                # Add space before word (except first word)
                token = f" {word}" if i > 0 else word
                yield token
                
                # Add some random variation to timing
                actual_delay = token_delay + random.uniform(-0.01, 0.02)
                await asyncio.sleep(max(0.001, actual_delay))
                
            # Occasionally add punctuation as separate token
            if random.random() < 0.3 and not response.endswith((".", "!", "?")):
                await asyncio.sleep(token_delay)
                yield "."
                
        finally:
            self.state = MockModelState.LOADED
            
    async def generate_completion(self, prompt: str, params: Dict[str, Any]) -> str:
        """Generate complete text response (non-streaming)"""
        tokens = []
        async for token in self.generate_stream(prompt, params):
            tokens.append(token)
            
        return "".join(tokens)
        
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings with consistent dimensionality"""
        logger.info(f"Generating mock embeddings for {len(texts)} texts")
        
        # Simulate brief processing time
        await asyncio.sleep(0.1 * len(texts))
        
        embeddings = []
        for text in texts:
            # Generate deterministic but varied embeddings based on text content
            # Use hash of text to ensure consistency across calls
            text_hash = hash(text) % (2**32)  # Ensure positive
            random.seed(text_hash)
            
            # Generate 384-dimensional embedding (common size)
            embedding = [random.uniform(-1.0, 1.0) for _ in range(384)]
            
            # Normalize to unit vector for realism
            magnitude = sum(x*x for x in embedding) ** 0.5
            if magnitude > 0:
                embedding = [x / magnitude for x in embedding]
                
            embeddings.append(embedding)
            
        # Reset random seed
        random.seed()
        
        return embeddings
        
    async def get_model_status(self) -> Dict[str, Any]:
        """Get current model status"""
        uptime = datetime.utcnow() - self.start_time
        
        status = {
            "service": "mock-model-service",
            "state": self.state.value,
            "current_model_type": self.current_model_type,
            "uptime_seconds": int(uptime.total_seconds()),
            "request_count": self.request_count,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
            "mock_mode": True,
            "generation_speed_tps": self.generation_speed,
            "available_models": list(self.model_configs.keys())
        }
        
        if self.current_model_type:
            config = self.model_configs[self.current_model_type]
            status.update({
                "model_name": config["name"],
                "model_size": config["size"],
                "context_size": config["context_size"],
                "vram_usage_mb": self.mock_vram_usage
            })
            
        return status
        
    async def monitor_vram(self) -> Dict[str, Any]:
        """Mock VRAM monitoring"""
        total_vram = 24000  # Mock 24GB GPU
        used_vram = self.mock_vram_usage
        free_vram = total_vram - used_vram
        utilization = (used_vram / total_vram) * 100
        
        return {
            "gpu_name": "Mock AMD 7900 XTX",
            "total_vram_mb": total_vram,
            "used_vram_mb": used_vram,
            "free_vram_mb": free_vram,
            "utilization_percent": round(utilization, 1),
            "mock_mode": True,
            "vulkan_enabled": True
        }
        
    async def emergency_shutdown(self):
        """Simulate emergency shutdown"""
        logger.info("Mock emergency shutdown initiated")
        
        if self.current_model_type:
            await self.unload_current_model()
            
        self.state = MockModelState.IDLE
        self.request_count = 0
        self.last_request_time = None
        
        logger.info("Mock emergency shutdown completed")
        
    def get_request_stats(self) -> Dict[str, Any]:
        """Get request statistics for monitoring"""
        uptime = datetime.utcnow() - self.start_time
        uptime_hours = uptime.total_seconds() / 3600
        
        requests_per_hour = self.request_count / max(uptime_hours, 0.01)
        
        return {
            "total_requests": self.request_count,
            "requests_per_hour": round(requests_per_hour, 2),
            "uptime_hours": round(uptime_hours, 2),
            "current_model": self.current_model_type,
            "state": self.state.value,
            "mock_mode": True
        }

# Create global instance
mock_model_service = MockModelService()


class MockModelManager:
    """Mock version of ModelManager for drop-in replacement"""
    
    def __init__(self):
        self.mock_service = mock_model_service
        self.model_configs = mock_model_service.model_configs
        
    async def initialize(self):
        await self.mock_service.initialize()
        
    async def load_model(self, model_type: str) -> bool:
        return await self.mock_service.load_model(model_type)
        
    async def unload_current_model(self):
        await self.mock_service.unload_current_model()
        
    async def generate_stream(self, prompt: str, params: Dict[str, Any]) -> AsyncGenerator[str, None]:
        async for token in self.mock_service.generate_stream(prompt, params):
            yield token
            
    async def generate_completion(self, prompt: str, params: Dict[str, Any]) -> str:
        return await self.mock_service.generate_completion(prompt, params)
        
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        return await self.mock_service.generate_embeddings(texts)
        
    async def get_model_status(self) -> Dict[str, Any]:
        return await self.mock_service.get_model_status()
        
    async def monitor_vram(self) -> Dict[str, Any]:
        return await self.mock_service.monitor_vram()
        
    async def emergency_shutdown(self):
        await self.mock_service.emergency_shutdown()
        
    @property
    def current_model_type(self):
        return self.mock_service.current_model_type
        
    @property
    def state_machine(self):
        """Mock state machine for compatibility"""
        class MockStateMachine:
            async def get_state_history(self):
                return [
                    {
                        "state": self.mock_service.state.value,
                        "timestamp": datetime.utcnow().isoformat(),
                        "model_type": self.mock_service.current_model_type
                    }
                ]
        
        return MockStateMachine()