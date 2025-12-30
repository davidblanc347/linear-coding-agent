"""Multi-LLM Integration Module for Chat Conversation.

Provides a unified interface for calling different LLM providers with streaming support:
- Ollama (local, free)
- Mistral API
- Anthropic API (Claude)
- OpenAI API

Example:
    >>> for token in call_llm("Hello world", "ollama", "qwen2.5:7b"):
    ...     print(token, end="", flush=True)
"""

import os
import json
import time
import logging
from typing import Iterator, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


def call_llm(
    prompt: str,
    provider: str,
    model: str,
    stream: bool = True,
    temperature: float = 0.7,
    max_tokens: int = 16384,
) -> Iterator[str]:
    """Call an LLM provider with unified interface.

    Args:
        prompt: The prompt to send to the LLM.
        provider: Provider name ("ollama", "mistral", "anthropic", "openai").
        model: Model name (e.g., "qwen2.5:7b", "mistral-small-latest", "claude-sonnet-4-5").
        stream: Whether to stream tokens (default: True).
        temperature: Temperature for generation (0-1).
        max_tokens: Maximum tokens to generate (default 16384 for philosophical discussions).

    Yields:
        Tokens as strings (when streaming).

    Raises:
        LLMError: If provider is invalid or API call fails.

    Example:
        >>> for token in call_llm("Test", "ollama", "qwen2.5:7b"):
        ...     print(token, end="")
    """
    provider = provider.lower()

    logger.info(f"[LLM Call] Provider: {provider}, Model: {model}, Stream: {stream}")
    start_time = time.time()

    try:
        if provider == "ollama":
            yield from _call_ollama(prompt, model, temperature, stream)
        elif provider == "mistral":
            yield from _call_mistral(prompt, model, temperature, max_tokens, stream)
        elif provider == "anthropic":
            yield from _call_anthropic(prompt, model, temperature, max_tokens, stream)
        elif provider == "openai":
            yield from _call_openai(prompt, model, temperature, max_tokens, stream)
        else:
            raise LLMError(f"Provider '{provider}' non supporté. Utilisez: ollama, mistral, anthropic, openai")

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[LLM Call] Error after {elapsed:.2f}s: {e}")
        raise

    elapsed = time.time() - start_time
    logger.info(f"[LLM Call] Completed in {elapsed:.2f}s")


def _call_ollama(prompt: str, model: str, temperature: float, stream: bool) -> Iterator[str]:
    """Call Ollama API with streaming support.

    Args:
        prompt: The prompt text.
        model: Ollama model name.
        temperature: Temperature (0-1).
        stream: Whether to stream.

    Yields:
        Tokens from the model.
    """
    import requests

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    url = f"{base_url}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": temperature,
        }
    }

    try:
        response = requests.post(url, json=payload, stream=stream, timeout=120)
        response.raise_for_status()

        if stream:
            # Stream mode: each line is a JSON object with "response" field
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token

                        # Check if done
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        else:
            # Non-stream mode
            data = response.json()
            yield data.get("response", "")

    except requests.exceptions.RequestException as e:
        raise LLMError(f"Ollama API error: {e}")


def _call_mistral(prompt: str, model: str, temperature: float, max_tokens: int, stream: bool) -> Iterator[str]:
    """Call Mistral API with streaming support.

    Args:
        prompt: The prompt text.
        model: Mistral model name.
        temperature: Temperature (0-1).
        max_tokens: Max tokens to generate.
        stream: Whether to stream.

    Yields:
        Tokens from the model.
    """
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise LLMError("MISTRAL_API_KEY not set in environment")

    try:
        from mistralai import Mistral
    except ImportError:
        raise LLMError("mistralai package not installed. Run: pip install mistralai")

    client = Mistral(api_key=api_key)

    messages = [{"role": "user", "content": prompt}]

    try:
        if stream:
            # Streaming mode
            stream_response = client.chat.stream(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            for chunk in stream_response:
                if chunk.data.choices:
                    delta = chunk.data.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        yield delta.content
        else:
            # Non-streaming mode
            response = client.chat.complete(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices:
                yield response.choices[0].message.content or ""

    except Exception as e:
        raise LLMError(f"Mistral API error: {e}")


def _call_anthropic(prompt: str, model: str, temperature: float, max_tokens: int, stream: bool) -> Iterator[str]:
    """Call Anthropic API (Claude) with streaming support.

    Args:
        prompt: The prompt text.
        model: Claude model name.
        temperature: Temperature (0-1).
        max_tokens: Max tokens to generate.
        stream: Whether to stream.

    Yields:
        Tokens from the model.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY not set in environment")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise LLMError("anthropic package not installed. Run: pip install anthropic")

    client = Anthropic(api_key=api_key)

    try:
        if stream:
            # Streaming mode
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        else:
            # Non-streaming mode
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            if response.content:
                yield response.content[0].text

    except Exception as e:
        raise LLMError(f"Anthropic API error: {e}")


def _call_openai(prompt: str, model: str, temperature: float, max_tokens: int, stream: bool) -> Iterator[str]:
    """Call OpenAI API with streaming support.

    Args:
        prompt: The prompt text.
        model: OpenAI model name.
        temperature: Temperature (0-1).
        max_tokens: Max tokens to generate.
        stream: Whether to stream.

    Yields:
        Tokens from the model.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY not set in environment")

    try:
        from openai import OpenAI
    except ImportError:
        raise LLMError("openai package not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key)

    messages = [{"role": "user", "content": prompt}]

    # Detect if model uses max_completion_tokens (o1, gpt-5.x) instead of max_tokens
    uses_completion_tokens = model.startswith("o1") or model.startswith("gpt-5")

    try:
        if stream:
            # Streaming mode
            if uses_completion_tokens:
                stream_response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    stream=True,
                )
            else:
                stream_response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

            for chunk in stream_response:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        yield delta.content
        else:
            # Non-streaming mode
            if uses_completion_tokens:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    stream=False,
                )
            else:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
            if response.choices:
                yield response.choices[0].message.content or ""

    except Exception as e:
        raise LLMError(f"OpenAI API error: {e}")
