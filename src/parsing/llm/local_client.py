"""
Local LLM Client - Session 73 REFACTOR

Native Ollama API with GBNF schema enforcement.

Key Changes (Session 73 — LLM Communication Overhaul):
- Replaced OpenAI SDK generic JSON mode with native Ollama schema enforcement
  (format=SCHEMA → GBNF grammar → token-level constraint)
- Added explicit num_ctx=4096 (Ollama default 2048 too small for invoices)
- Added json_repair fallback for malformed/truncated LLM output

Previous:
- Session 45: OpenAI SDK + response_format={"type": "json_object"}
- Session 50: Centralized config via settings.py

References:
- https://ollama.com/blog/structured-outputs (GBNF grammar)
- https://github.com/ollama/ollama/blob/main/docs/api.md

Created: 2026-01-22 (Session 43)
Refactored: 2026-02-19 (Session 73) - Native Ollama API + schema enforcement
"""

import json
import logging
from typing import Any, Dict, Optional

import requests as requests_lib

try:
    import json_repair

    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

# Import centralized settings (Session 50)
from parsing.settings import settings

logger = logging.getLogger(__name__)

# ===== JSON SCHEMA for Invoice Line Items =====
# Session 46: Changed numeric fields to STRING for raw extraction
# Session 47: Added tax_rate, tax_amount, gross_amount for VAT extraction
# Python will handle the cleaning/conversion (handles EU/US/HU formats)
INVOICE_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "List of extracted line items from invoice",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Product or service name"},
                    "quantity": {
                        "type": "string",
                        "description": "Quantity as raw string (e.g., '1,00', '5.0', '3 pcs')",
                    },
                    "unit_price": {
                        "type": "string",
                        "description": "Unit price as raw string (e.g., '1 489,00', '$50.00')",
                    },
                    "net_amount": {
                        "type": "string",
                        "description": "Net amount as raw string (e.g., '48 248,60', '100.00')",
                    },
                    # SESSION 47: VAT & Gross fields (all raw strings)
                    "tax_rate": {
                        "type": "string",
                        "description": "Tax/VAT rate as raw string (e.g., '10%', '27%', 'A', '0.19')",
                    },
                    "tax_amount": {
                        "type": "string",
                        "description": "Tax/VAT amount as raw string (e.g., '148,90', '1 234,00')",
                    },
                    "gross_amount": {
                        "type": "string",
                        "description": "Gross/total amount as raw string (e.g., '1 637,90', '5 678,00')",
                    },
                },
                # Core fields required, tax fields optional (not all invoices have them)
                "required": ["description", "quantity", "unit_price", "net_amount"],
            },
        }
    },
    "required": ["items"],
}


class OllamaClient:
    """
    Industry Standard Ollama Client using OpenAI SDK.

    This is the CORRECT way to interact with Ollama in 2024/2025:
    1. Use official openai Python package (handles retries, timeouts, errors)
    2. Point base_url to Ollama's OpenAI-compatible endpoint
    3. Use response_format={"type": "json_object"} for structured output
    4. Use Wrapper Object Pattern: {"items": [...]} not raw []

    If Ollama is not running or errors occur, returns None gracefully.
    """

    _error_count: int = 0
    _max_errors: int = 3
    _circuit_open: bool = False

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = None,
        connect_timeout: int = None,
    ):
        """
        Initialize Ollama client using OpenAI SDK.

        Args:
            base_url: Ollama OpenAI-compatible endpoint (from config.yaml if not specified)
            model: Model name (from config.yaml if not specified)
            timeout: Request timeout in seconds (from config.yaml if not specified)

        Configuration Priority:
            1. Explicit parameter
            2. Environment variable (LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT)
            3. config.yaml value
            4. Built-in default
        """
        # Use settings module (Session 50) - handles env var overrides
        self.base_url = (base_url or settings.llm.base_url).rstrip("/")
        self.model = model or settings.llm.model
        self.timeout = timeout or settings.llm.timeout
        self.connect_timeout = connect_timeout or settings.llm.connect_timeout
        self.num_ctx = settings.llm.num_ctx

        # Derive raw Ollama API base (strip /v1 suffix for native endpoint)
        self.raw_api_base = self.base_url.replace("/v1", "")

        logger.info(
            f"OllamaClient initialized: {self.model} @ {self.raw_api_base} (num_ctx={self.num_ctx})"
        )

    def generate_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        Generate JSON response using native Ollama API with schema enforcement.

        Session 73 approach (3 improvements over Session 45):
        1. Native format=SCHEMA → GBNF grammar → token-level JSON constraint
           (vs generic "json_object" which only guarantees syntactic JSON)
        2. Explicit num_ctx=4096 (vs Ollama default 2048)
        3. json_repair fallback for truncated/malformed output

        Args:
            system_prompt: System instructions (behavior, schema)
            user_prompt: User input (document text to extract from)
            temperature: Sampling temperature (0.0 = deterministic)

        Returns:
            Optional[Dict]: Parsed JSON response with "items" key, or None if error
        """
        if OllamaClient._circuit_open:
            logger.warning("Circuit breaker OPEN - skipping LLM call")
            return None

        try:
            api_url = f"{self.raw_api_base}/api/chat"

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": INVOICE_ITEMS_SCHEMA,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": self.num_ctx,
                },
            }

            logger.debug(f"Sending request to Ollama native API: {api_url}")
            logger.debug(f"Model: {self.model}, num_ctx: {self.num_ctx}")
            logger.debug(f"User Prompt Length: {len(user_prompt)} chars")

            response = requests_lib.post(
                api_url, json=payload, timeout=(self.connect_timeout, self.timeout)
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "")

            # Log token stats from native API (unavailable via OpenAI SDK)
            eval_count = data.get("eval_count", 0)
            eval_duration = data.get("eval_duration", 0)
            if eval_duration > 0:
                tok_per_sec = eval_count / (eval_duration / 1e9)
                logger.info(f"Ollama stats: {eval_count} tokens @ {tok_per_sec:.1f} tok/s")

            # ===== DEBUG LOGGING =====
            logger.debug("=" * 70)
            logger.debug("OLLAMA RAW CONTENT (Before JSON Parse):")
            logger.debug("=" * 70)
            logger.debug(content)
            logger.debug("=" * 70)

            # Parse JSON with json_repair fallback
            try:
                result = json.loads(content)
            except json.JSONDecodeError as je:
                if HAS_JSON_REPAIR:
                    logger.warning(f"json.loads failed ({je}), trying json_repair...")
                    result = json_repair.loads(content)
                    logger.info("json_repair recovered malformed JSON")
                else:
                    raise

            logger.info(f"Ollama response parsed successfully ({len(str(result))} chars)")
            OllamaClient._error_count = 0
            return result

        except Exception as e:
            error_type = type(e).__name__
            logger.warning(f"Ollama client error ({error_type}): {e}")
            OllamaClient._error_count += 1
            if OllamaClient._error_count >= OllamaClient._max_errors:
                OllamaClient._circuit_open = True
                logger.error(
                    f"Circuit breaker OPENED after {OllamaClient._error_count} consecutive errors"
                )
            return None

    def health_check(self) -> bool:
        """
        Check if Ollama is running and model is available.

        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            api_url = f"{self.raw_api_base}/api/chat"
            response = requests_lib.post(
                api_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                    "options": {"num_predict": 5},
                },
                timeout=(self.connect_timeout, 10),
            )
            response.raise_for_status()
            data = response.json()
            return bool(data.get("message", {}).get("content"))
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False


# ===== CONVENIENCE FUNCTION =====
def extract_invoice_items(
    ocr_text: str, header_total: float = None, currency: str = None
) -> Optional[Dict]:
    """
    Extract invoice line items using Ollama with structured output.

    This is a high-level convenience function that:
    1. Creates the client
    2. Builds the prompt with context
    3. Calls the LLM
    4. Returns structured {"items": [...]} response

    Args:
        ocr_text: Raw OCR text from invoice
        header_total: Expected total (for context injection)
        currency: Currency code (EUR, USD, HUF, etc.)

    Returns:
        Optional[Dict]: {"items": [{"description": ..., "quantity": ..., ...}, ...]}
    """
    client = OllamaClient()

    # Build system prompt with embedded schema
    system_prompt = f"""You are a data extraction assistant. Extract invoice line items into JSON.

OUTPUT FORMAT (strict):
{json.dumps(INVOICE_ITEMS_SCHEMA, indent=2)}

RULES:
1. Extract ALL line items (products/services)
2. DO NOT include subtotals, tax lines, or totals
3. Use exact numbers from the document
4. If quantity is not specified, use 1.0
5. Output MUST be valid JSON with "items" array"""

    # Build user prompt with context
    context = ""
    if header_total is not None:
        context = f"Expected total: {header_total:.2f} {currency or 'units'}\n\n"

    user_prompt = f"""{context}Extract all line items from this invoice text:

{ocr_text}"""

    return client.generate_json(system_prompt, user_prompt, temperature=0.0)
