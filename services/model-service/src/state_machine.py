import asyncio
import logging
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class ModelState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    LOADED = "loaded"
    GENERATING = "generating"
    UNLOADING = "unloading"
    ERROR = "error"

class StateTransition:
    def __init__(self, from_state: ModelState, to_state: ModelState, timestamp: datetime, success: bool = True, error: Optional[str] = None):
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = timestamp
        self.success = success
        self.error = error

class ModelStateMachine:
    """Manages model state transitions and validates operations"""
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        ModelState.IDLE: [ModelState.LOADING, ModelState.ERROR],
        ModelState.LOADING: [ModelState.LOADED, ModelState.ERROR, ModelState.IDLE],
        ModelState.LOADED: [ModelState.GENERATING, ModelState.UNLOADING, ModelState.ERROR],
        ModelState.GENERATING: [ModelState.LOADED, ModelState.ERROR],
        ModelState.UNLOADING: [ModelState.IDLE, ModelState.ERROR],
        ModelState.ERROR: [ModelState.IDLE, ModelState.LOADING, ModelState.UNLOADING]
    }
    
    def __init__(self):
        self.current_state = ModelState.IDLE
        self.state_history: List[StateTransition] = []
        self.max_history = 100
        
    def can_transition(self, from_state: ModelState, to_state: ModelState) -> bool:
        """Check if state transition is valid"""
        try:
            valid_next_states = self.VALID_TRANSITIONS.get(from_state, [])
            return to_state in valid_next_states
        except Exception as e:
            logger.error(f"Error checking transition validity: {e}")
            return False
            
    async def transition(self, new_state: ModelState):
        """Execute state transition with safety checks"""
        try:
            if not self.can_transition(self.current_state, new_state):
                error_msg = f"Invalid transition from {self.current_state.value} to {new_state.value}"
                logger.error(error_msg)
                await self._record_transition(self.current_state, new_state, False, error_msg)
                raise ValueError(error_msg)
                
            old_state = self.current_state
            self.current_state = new_state
            
            await self._record_transition(old_state, new_state, True)
            logger.info(f"State transition: {old_state.value} -> {new_state.value}")
            
        except Exception as e:
            logger.error(f"Error during state transition: {e}")
            await self._record_transition(self.current_state, new_state, False, str(e))
            raise
            
    async def handle_error(self, error: Exception):
        """Error recovery and state restoration"""
        try:
            logger.error(f"Handling error in state {self.current_state.value}: {error}")
            
            # Record error
            await self._record_transition(self.current_state, ModelState.ERROR, False, str(error))
            
            # Determine recovery strategy based on current state
            if self.current_state == ModelState.LOADING:
                # Failed to load, go back to idle
                recovery_state = ModelState.IDLE
            elif self.current_state == ModelState.GENERATING:
                # Failed during generation, try to restore loaded state
                recovery_state = ModelState.LOADED
            elif self.current_state == ModelState.UNLOADING:
                # Failed to unload, force to idle
                recovery_state = ModelState.IDLE
            else:
                # Default recovery
                recovery_state = ModelState.IDLE
                
            # Transition to error state first
            old_state = self.current_state
            self.current_state = ModelState.ERROR
            await self._record_transition(old_state, ModelState.ERROR, True, str(error))
            
            # Then attempt recovery
            await asyncio.sleep(1)  # Brief delay before recovery
            await self.transition(recovery_state)
            
            logger.info(f"Error recovery completed: {old_state.value} -> ERROR -> {recovery_state.value}")
            
        except Exception as recovery_error:
            logger.critical(f"Error during error recovery: {recovery_error}")
            self.current_state = ModelState.ERROR
            
    async def get_state_history(self) -> List[Dict[str, Any]]:
        """Return recent state transitions for debugging"""
        try:
            return [
                {
                    "from_state": transition.from_state.value,
                    "to_state": transition.to_state.value,
                    "timestamp": transition.timestamp.isoformat(),
                    "success": transition.success,
                    "error": transition.error
                }
                for transition in self.state_history[-20:]  # Last 20 transitions
            ]
        except Exception as e:
            logger.error(f"Error getting state history: {e}")
            return []
            
    def get_current_state(self) -> ModelState:
        """Get current state"""
        return self.current_state
        
    def is_operational(self) -> bool:
        """Check if state machine is in operational state"""
        return self.current_state in [ModelState.IDLE, ModelState.LOADED, ModelState.GENERATING]
        
    def is_busy(self) -> bool:
        """Check if state machine is in busy state"""
        return self.current_state in [ModelState.LOADING, ModelState.GENERATING, ModelState.UNLOADING]
        
    def can_accept_requests(self) -> bool:
        """Check if can accept new requests"""
        return self.current_state in [ModelState.LOADED]
        
    async def _record_transition(self, from_state: ModelState, to_state: ModelState, success: bool, error: Optional[str] = None):
        """Record state transition in history"""
        try:
            transition = StateTransition(
                from_state=from_state,
                to_state=to_state,
                timestamp=datetime.utcnow(),
                success=success,
                error=error
            )
            
            self.state_history.append(transition)
            
            # Trim history if too long
            if len(self.state_history) > self.max_history:
                self.state_history = self.state_history[-self.max_history:]
                
        except Exception as e:
            logger.error(f"Error recording transition: {e}")
            
    def get_stats(self) -> Dict[str, Any]:
        """Get state machine statistics"""
        try:
            if not self.state_history:
                return {"current_state": self.current_state.value, "total_transitions": 0}
                
            total_transitions = len(self.state_history)
            successful_transitions = sum(1 for t in self.state_history if t.success)
            failed_transitions = total_transitions - successful_transitions
            
            # Count transitions by type
            transition_counts = {}
            for transition in self.state_history:
                key = f"{transition.from_state.value}->{transition.to_state.value}"
                transition_counts[key] = transition_counts.get(key, 0) + 1
                
            return {
                "current_state": self.current_state.value,
                "total_transitions": total_transitions,
                "successful_transitions": successful_transitions,
                "failed_transitions": failed_transitions,
                "success_rate": successful_transitions / total_transitions if total_transitions > 0 else 1.0,
                "transition_counts": transition_counts,
                "is_operational": self.is_operational(),
                "is_busy": self.is_busy(),
                "can_accept_requests": self.can_accept_requests()
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"current_state": self.current_state.value, "error": str(e)}