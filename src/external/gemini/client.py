"""
Gemini client interface.
Only this file (and real implementation) touches the network.
"""
from abc import ABC, abstractmethod
from typing import Optional
import numpy as np
from src.external.gemini.types import GeminiRawResponse


class GeminiClientBase(ABC):
    """
    Abstract Gemini client.
    
    Contract:
    - analyze() returns raw text response or raises
    - Implementations handle auth, retries, timeouts internally
    - Caller wraps in try/except for ANY failure
    """
    
    @abstractmethod
    def analyze(
        self,
        scene_text: str,
        image: Optional[np.ndarray] = None
    ) -> GeminiRawResponse:
        """
        Send scene description (+ optional image) to Gemini.
        
        Args:
            scene_text: Formatted scene description string
            image: Optional RGB image array (H, W, 3)
            
        Returns:
            GeminiRawResponse with raw text
            
        Raises:
            TimeoutError: API call exceeded timeout
            ConnectionError: Network failure
            Exception: Any other API error
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if client is configured and ready"""
        pass


class RealGeminiClient(GeminiClientBase):
    """
    Real Gemini API client.
    
    Uses google-generativeai SDK.
    Only instantiated when gemini.enabled=true in config.
    """
    
    def __init__(self, config: dict):
        self.config = config
        gemini_cfg = config.get('gemini', {})
        
        self.model_name = gemini_cfg.get('model', 'gemini-2.0-flash')
        self.timeout_sec = gemini_cfg.get('timeout_ms', 3000) / 1000.0
        self.max_output_chars = gemini_cfg.get('max_output_chars', 6000)
        self.temperature = gemini_cfg.get('temperature', 0.0)
        
        # Lazy init — don't import SDK until first call
        self._client = None
        self._model = None
        self._init_error: Optional[str] = None
    
    def _lazy_init(self):
        """Initialize Gemini SDK on first use"""
        if self._client is not None or self._init_error is not None:
            return
        
        try:
            import google.generativeai as genai
            
            api_key = self.config.get('gemini', {}).get('api_key')
            if not api_key:
                # Try environment variable
                import os
                api_key = os.environ.get('GEMINI_API_KEY')
            
            if not api_key:
                self._init_error = "No Gemini API key configured"
                return
            
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.model_name)
            self._client = genai  # Store reference
            
            print(f"[GEMINI] Initialized model: {self.model_name}")
            
        except ImportError:
            self._init_error = "google-generativeai package not installed"
        except Exception as e:
            self._init_error = f"Gemini init failed: {e}"
    
    def analyze(
        self,
        scene_text: str,
        image: Optional[np.ndarray] = None
    ) -> GeminiRawResponse:
        """Call Gemini API with timeout"""
        import time
        
        self._lazy_init()
        
        if self._init_error:
            raise ConnectionError(self._init_error)
        
        start_time = time.time()
        
        try:
            # Build content parts
            parts = [scene_text]
            
            if image is not None:
                # Convert numpy array to PIL Image for Gemini
                from PIL import Image
                import io
                pil_image = Image.fromarray(image)
                parts.append(pil_image)
            
            # Call API
            response = self._model.generate_content(
                parts,
                generation_config={
                    'temperature': self.temperature,
                    'max_output_tokens': self.max_output_chars // 4,  # ~4 chars/token
                }
            )
            
            latency_ms = (time.time() - start_time) * 1000
            raw_text = response.text if response.text else ""
            
            return GeminiRawResponse(
                raw_text=raw_text,
                model=self.model_name,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            raise type(e)(f"Gemini API error after {latency_ms:.0f}ms: {e}")
    
    def is_available(self) -> bool:
        self._lazy_init()
        return self._init_error is None



