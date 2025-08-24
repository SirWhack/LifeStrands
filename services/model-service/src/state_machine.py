import asyncio
import logging
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class ModelState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    LOADED = "loaded"
    GENERATING = "generating"
    UNLOADING = "unloading"
    ERROR = "error"

@dataclass(slots=True)
class StateTransition:
    from_state: ModelState
    to_state: ModelState
    timestamp: datetime
    success: bool = True
    error: Optional[str] = None

class ModelStateMachine:
    """Manages model state transitions and validates operations"""
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        ModelState.IDLE: [ModelState.LOADING, ModelState.ERROR],
        ModelState.LOADING: [ModelState.LOADED, ModelState.ERROR, ModelState.IDLE],
        ModelState.LOADED: [ModelState.GENERATING, ModelState.UNLOADING, ModelState.IDLE, ModelState.ERROR],
        ModelState.GENERATING: [ModelState.LOADED, ModelState.ERROR],
        ModelState.UNLOADING: [ModelState.IDLE, ModelState.ERROR],
        ModelState.ERROR: [ModelState.IDLE, ModelState.LOADING, ModelState.UNLOADING]
    }
    
    def __init__(self):
        self.current_state = ModelState.IDLE
        self.state_history: List[StateTransition] = []
        self.max_history = 100
        self._state_lock = asyncio.Lock()
        
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
        async with self._state_lock:
            try:
                if not self.can_transition(self.current_state, new_state):
                    error_msg = f"Invalid transition from {self.current_state.value} to {new_state.value}"
                    logger.error(error_msg)
                    # Record once and raise
                    await self._record_transition(self.current_state, new_state, False, error_msg)
                    raise ValueError(error_msg)
                old_state = self.current_state
                self.current_state = new_state
                await self._record_transition(old_state, new_state, True)
                logger.info(f"State transition: {old_state.value} -> {new_state.value}")
            except Exception as e:
                # Already recorded in invalid case; just log and re-raise
                logger.error(f"Error during state transition: {e}")
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
                # Failed during generation; first go to LOADED, then IDLE if needed
                # GENERATING -> LOADED is valid, then LOADED -> IDLE
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
            try:
                await self.transition(recovery_state)
                
                # If we recovered to LOADED but want to get to IDLE (e.g., from GENERATING error)
                if recovery_state == ModelState.LOADED and old_state == ModelState.GENERATING:
                    # Optionally transition to IDLE after a brief delay
                    await asyncio.sleep(0.5)
                    if self.can_transition(ModelState.LOADED, ModelState.IDLE):
                        await self.transition(ModelState.IDLE)
                        
            except Exception as recovery_error:
                logger.error(f"Recovery transition failed: {recovery_error}")
                # Force to IDLE as last resort
                self.current_state = ModelState.IDLE
                await self._record_transition(ModelState.ERROR, ModelState.IDLE, False, f"Forced recovery: {recovery_error}")
            
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
                "success_rate": (successful_transitions / total_transitions) if total_transitions > 0 else None,
                "transition_counts": transition_counts,
                "is_operational": self.is_operational(),
                "is_busy": self.is_busy(),
                "can_accept_requests": self.can_accept_requests()
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"current_state": self.current_state.value, "error": str(e)}