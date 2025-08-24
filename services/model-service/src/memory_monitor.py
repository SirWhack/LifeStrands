import asyncio
import psutil
import logging
import platform
from typing import Dict, Any, Optional
import gc

try:
    import GPUtil
    GPU_UTIL_AVAILABLE = True
except ImportError:
    GPU_UTIL_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import pynvml as nvml
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)

class MemoryMonitor:
    """Monitor GPU/CPU memory usage and predict requirements"""
    
    def __init__(self):
        self.model_memory_estimates = {
            "chat": 8000,    # MB estimate for chat model
            "summary": 4000  # MB estimate for summary model  
        }
        self.safety_margin = 1000  # MB safety margin
        self.is_windows = platform.system() == "Windows"
        
        # Configure backend and minimum VRAM threshold
        import os
        self.backend = os.getenv("BACKEND", "vulkan" if self.is_windows else "cuda").lower()
        self.min_vram_mb = int(os.getenv("MIN_VRAM_MB", "12000"))  # 12GB minimum
        
        logger.info(f"MemoryMonitor initialized: backend={self.backend}, min_vram={self.min_vram_mb}MB")
        
    async def get_gpu_stats(self) -> Dict[str, Any]:
        """Current GPU usage, temperature, and availability"""
        try:
            stats = {
                "available": False,
                "count": 0,
                "devices": []
            }
            
            # Try AMD ROCm SMI first (for AMD GPUs)
            if self.is_windows:
                amd_stats = await self._get_amd_gpu_stats()
                if amd_stats.get("available", False):
                    return amd_stats
            
            # Try NVML second (for NVIDIA GPUs)
            if NVML_AVAILABLE:
                nvml_initialized = False
                try:
                    # Initialize NVML
                    try:
                        nvml.nvmlInit()
                        nvml_initialized = True
                    except Exception as init_error:
                        logger.debug(f"NVML initialization failed: {init_error}")
                        
                    if nvml_initialized:
                        device_count = nvml.nvmlDeviceGetCount()
                        stats["available"] = device_count > 0
                        stats["count"] = device_count
                        
                        for i in range(device_count):
                            try:
                                handle = nvml.nvmlDeviceGetHandleByIndex(i)
                                name = nvml.nvmlDeviceGetName(handle).decode('utf-8')
                                
                                # Memory info
                                mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
                                memory_total = mem_info.total // 1024 // 1024  # Convert to MB
                                memory_used = mem_info.used // 1024 // 1024
                                memory_free = mem_info.free // 1024 // 1024
                                
                                # Temperature
                                try:
                                    temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
                                except Exception:
                                    temp = None
                                    
                                # Utilization
                                try:
                                    util = nvml.nvmlDeviceGetUtilizationRates(handle)
                                    gpu_util = util.gpu
                                    mem_util = util.memory
                                except Exception:
                                    gpu_util = None
                                    mem_util = None
                                    
                                device_stats = {
                                    "index": i,
                                    "name": name,
                                    "memory_total_mb": memory_total,
                                    "memory_used_mb": memory_used,
                                    "memory_free_mb": memory_free,
                                    "memory_utilization_percent": (memory_used / memory_total * 100) if memory_total > 0 else 0,
                                    "temperature_c": temp,
                                    "gpu_utilization_percent": gpu_util,
                                    "memory_bandwidth_utilization_percent": mem_util
                                }
                                
                                stats["devices"].append(device_stats)
                            except Exception as device_error:
                                logger.debug(f"Error reading GPU {i}: {device_error}")
                                continue
                        
                except Exception as e:
                    logger.debug(f"NVML error: {e}")
                finally:
                    # Always try to shutdown NVML if it was initialized
                    if nvml_initialized:
                        try:
                            nvml.nvmlShutdown()
                        except Exception as shutdown_error:
                            logger.debug(f"NVML shutdown error: {shutdown_error}")
                    
            # Fallback to GPUtil
            elif GPU_UTIL_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    stats["available"] = len(gpus) > 0
                    stats["count"] = len(gpus)
                    
                    for i, gpu in enumerate(gpus):
                        device_stats = {
                            "index": i,
                            "name": gpu.name,
                            "memory_total_mb": gpu.memoryTotal,
                            "memory_used_mb": gpu.memoryUsed,
                            "memory_free_mb": gpu.memoryFree,
                            "memory_utilization_percent": gpu.memoryUtil * 100,
                            "temperature_c": gpu.temperature,
                            "gpu_utilization_percent": gpu.load * 100,
                            "memory_bandwidth_utilization_percent": None
                        }
                        
                        stats["devices"].append(device_stats)
                        
                except Exception as e:
                    logger.debug(f"GPUtil error: {e}")
                    
            # PyTorch CUDA info
            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    if not stats["devices"]:  # No detailed info from other methods
                        device_count = torch.cuda.device_count()
                        stats["available"] = device_count > 0
                        stats["count"] = device_count
                        
                        for i in range(device_count):
                            props = torch.cuda.get_device_properties(i)
                            memory_total = props.total_memory // 1024 // 1024  # Convert to MB
                            memory_allocated = torch.cuda.memory_allocated(i) // 1024 // 1024
                            memory_cached = torch.cuda.memory_reserved(i) // 1024 // 1024
                            memory_free = memory_total - memory_cached
                            
                            device_stats = {
                                "index": i,
                                "name": props.name,
                                "memory_total_mb": memory_total,
                                "memory_used_mb": memory_allocated,
                                "memory_cached_mb": memory_cached,
                                "memory_free_mb": memory_free,
                                "memory_utilization_percent": (memory_cached / memory_total * 100) if memory_total > 0 else 0,
                                "temperature_c": None,
                                "gpu_utilization_percent": None,
                                "memory_bandwidth_utilization_percent": None
                            }
                            
                            stats["devices"].append(device_stats)
                            
                except Exception as e:
                    logger.debug(f"PyTorch CUDA error: {e}")
                    
            return stats
            
        except Exception as e:
            logger.error(f"Error getting GPU stats: {e}")
            return {"available": False, "error": str(e)}
            
    async def get_cpu_stats(self) -> Dict[str, Any]:
        """Get CPU and system memory statistics"""
        try:
            # CPU info
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            
            # Memory info
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "frequency_mhz": cpu_freq.current if cpu_freq else None,
                    "load_average": load_avg
                },
                "memory": {
                    "total_mb": memory.total // 1024 // 1024,
                    "available_mb": memory.available // 1024 // 1024,
                    "used_mb": memory.used // 1024 // 1024,
                    "percent": memory.percent
                },
                "swap": {
                    "total_mb": swap.total // 1024 // 1024,
                    "used_mb": swap.used // 1024 // 1024,
                    "percent": swap.percent
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting CPU stats: {e}")
            return {"error": str(e)}
            
    async def predict_memory_requirement(self, model_type: str) -> int:
        """Estimate VRAM needed for model"""
        try:
            base_requirement = self.model_memory_estimates.get(model_type, 4000)
            
            # Add overhead for context, KV cache, etc.
            context_overhead = 1000  # Rough estimate
            
            total_requirement = base_requirement + context_overhead + self.safety_margin
            
            logger.debug(f"Predicted memory requirement for {model_type}: {total_requirement}MB")
            return total_requirement
            
        except Exception as e:
            logger.error(f"Error predicting memory requirement: {e}")
            return self.model_memory_estimates.get(model_type, 4000)
            
    async def can_load_model(self, model_type: str) -> bool:
        """Check if sufficient memory available"""
        try:
            required_memory = await self.predict_memory_requirement(model_type)
            
            # For Vulkan backend on Windows, use conservative threshold approach
            if self.backend == "vulkan":
                if self.min_vram_mb >= required_memory:
                    logger.info(f"Vulkan backend: Assuming sufficient VRAM ({self.min_vram_mb}MB >= {required_memory}MB)")
                    return True
                else:
                    logger.error(f"Vulkan backend: Configured VRAM ({self.min_vram_mb}MB) below requirement ({required_memory}MB)")
                    return False
            
            # For CUDA/ROCm backends, try to get actual GPU stats
            gpu_stats = await self.get_gpu_stats()
            
            if not gpu_stats.get("available", False):
                logger.warning("No GPU available for CUDA/ROCm backend")
                # Fallback to threshold check
                if self.min_vram_mb >= required_memory:
                    logger.warning(f"Fallback: Using minimum VRAM threshold ({self.min_vram_mb}MB >= {required_memory}MB)")
                    return True
                return False
                
            # Check if any GPU has enough free memory
            for device in gpu_stats.get("devices", []):
                free_memory = device.get("memory_free_mb", 0)
                if free_memory >= required_memory:
                    logger.info(f"GPU {device['index']} has sufficient memory: {free_memory}MB >= {required_memory}MB")
                    return True
                    
            logger.warning(f"Insufficient GPU memory. Required: {required_memory}MB")
            return False
            
        except Exception as e:
            logger.error(f"Error checking if can load model: {e}")
            # Fallback to threshold in case of error
            if self.min_vram_mb >= await self.predict_memory_requirement(model_type):
                logger.warning(f"Error fallback: Using minimum VRAM threshold")
                return True
            return False
            
    async def trigger_cleanup(self):
        """Force garbage collection and clear caches"""
        try:
            logger.info("Triggering memory cleanup")
            
            # Python garbage collection
            collected = gc.collect()
            logger.debug(f"Garbage collected {collected} objects")
            
            # PyTorch CUDA cache cleanup
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                logger.debug("Cleared PyTorch CUDA cache")
                
            # Get memory stats after cleanup
            gpu_stats = await self.get_gpu_stats()
            cpu_stats = await self.get_cpu_stats()
            
            logger.info("Memory cleanup completed")
            
            return {
                "cleanup_completed": True,
                "objects_collected": collected,
                "gpu_stats": gpu_stats,
                "cpu_stats": cpu_stats
            }
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return {"cleanup_completed": False, "error": str(e)}
            
    def update_memory_estimates(self, model_type: str, actual_usage: int):
        """Update memory estimates based on actual usage"""
        try:
            if model_type in self.model_memory_estimates:
                # Validate actual_usage is reasonable (between 100MB and 100GB)
                if not (100 <= actual_usage <= 100000):
                    logger.warning(f"Ignoring unrealistic memory usage report: {actual_usage}MB for {model_type}")
                    return
                
                # Use exponential moving average to update estimate
                alpha = 0.3
                old_estimate = self.model_memory_estimates[model_type]
                new_estimate = alpha * actual_usage + (1 - alpha) * old_estimate
                
                # Ensure the new estimate stays within reasonable bounds (100MB to 50GB)
                new_estimate = max(100, min(50000, int(new_estimate)))
                
                self.model_memory_estimates[model_type] = new_estimate
                
                logger.info(f"Updated memory estimate for {model_type}: {old_estimate}MB -> {new_estimate}MB")
                
        except Exception as e:
            logger.error(f"Error updating memory estimates: {e}")
            
    async def get_memory_summary(self) -> Dict[str, Any]:
        """Get comprehensive memory summary"""
        try:
            gpu_stats = await self.get_gpu_stats()
            cpu_stats = await self.get_cpu_stats()
            
            summary = {
                "timestamp": asyncio.get_event_loop().time(),
                "gpu": gpu_stats,
                "cpu": cpu_stats,
                "model_estimates": self.model_memory_estimates,
                "safety_margin_mb": self.safety_margin
            }
            
            # Calculate total available GPU memory
            if gpu_stats.get("available", False):
                total_gpu_memory = sum(device.get("memory_total_mb", 0) for device in gpu_stats.get("devices", []))
                total_free_memory = sum(device.get("memory_free_mb", 0) for device in gpu_stats.get("devices", []))
                summary["total_gpu_memory_mb"] = total_gpu_memory
                summary["total_free_gpu_memory_mb"] = total_free_memory
                
            return summary
            
        except Exception as e:
            logger.error(f"Error getting memory summary: {e}")
            return {"error": str(e)}
            
    async def _get_amd_gpu_stats(self) -> Dict[str, Any]:
        """Get AMD GPU statistics via ROCm SMI"""
        try:
            import subprocess
            import json
            import shlex
            import os.path
            
            # Try different ROCm versions with path validation
            hip_versions = ["6.4", "6.3", "6.2", "6.1", "6.0", "5.7"]
            
            for version in hip_versions:
                rocm_smi_path = rf"C:\Program Files\AMD\ROCm\{version}\bin\rocm-smi.exe"
                
                # Validate the executable path exists and is a file
                if not os.path.isfile(rocm_smi_path):
                    continue
                    
                try:
                    # Use safe command construction
                    cmd = [rocm_smi_path, "--showmeminfo", "vram", "--json"]
                    result = subprocess.run(cmd, 
                                          capture_output=True, text=True, timeout=10,
                                          creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        devices = []
                        
                        # Parse AMD GPU memory info
                        if isinstance(data, dict):
                            for device_id, device_info in data.items():
                                if isinstance(device_id, str) and device_id.startswith("card"):
                                    memory_info = device_info.get("Memory Info", {})
                                    vram_total = memory_info.get("VRAM Total Memory (B)", 0)
                                    vram_used = memory_info.get("VRAM Total Used Memory (B)", 0)
                                    
                                    if vram_total > 0:
                                        vram_total_mb = vram_total // 1024 // 1024
                                        vram_used_mb = vram_used // 1024 // 1024
                                        vram_free_mb = vram_total_mb - vram_used_mb
                                        
                                        devices.append({
                                            "index": len(devices),
                                            "name": f"AMD GPU {device_id}",
                                            "memory_total_mb": vram_total_mb,
                                            "memory_used_mb": vram_used_mb,
                                            "memory_free_mb": vram_free_mb,
                                            "memory_utilization_percent": (vram_used_mb / vram_total_mb * 100) if vram_total_mb > 0 else 0,
                                            "temperature_c": None,
                                            "gpu_utilization_percent": None,
                                            "memory_bandwidth_utilization_percent": None,
                                            "backend": f"ROCm {version}"
                                        })
                        
                        if devices:
                            return {
                                "available": True,
                                "count": len(devices),
                                "devices": devices,
                                "backend": f"AMD ROCm {version}"
                            }
                            
                except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
                    continue
                except Exception as e:
                    logger.debug(f"ROCm {version} SMI failed: {e}")
                    continue
            
            # Fallback: try rocm-smi in PATH with proper validation
            try:
                # Use which/where to find the command safely
                which_cmd = "where" if os.name == "nt" else "which"
                which_result = subprocess.run([which_cmd, "rocm-smi"], 
                                            capture_output=True, text=True, timeout=5)
                if which_result.returncode == 0:
                    cmd = ["rocm-smi", "--showmeminfo", "vram", "--json"]
                    result = subprocess.run(cmd, 
                                          capture_output=True, text=True, timeout=10,
                                          creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        # Similar parsing logic as above
                        logger.info("AMD GPU detected via PATH rocm-smi")
                        return {"available": True, "count": 1, "devices": [], "backend": "ROCm PATH"}
            except Exception:
                pass
                
            return {"available": False, "reason": "AMD ROCm SMI not available"}
            
        except Exception as e:
            logger.debug(f"AMD GPU stats error: {e}")
            return {"available": False, "error": str(e)}