"""HTTP client utilities with retry logic and rate limiting."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings
from app.logging import get_logger

logger = get_logger("http")


class HttpClient:
    """HTTP client with built-in retry logic and rate limiting."""

    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize HTTP client.

        Args:
            base_url: Base URL for all requests
            headers: Default headers to include with requests
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

        # Create httpx client with HTTP/2 support
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout,
            http2=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

        logger.debug(f"Initialized HTTP client for {base_url}")

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> HttpClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    @retry(
        reraise=True,
        wait=wait_exponential_jitter(initial=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a GET request with retry logic.

        Args:
            path: URL path to request
            params: Query parameters
            headers: Additional headers for this request

        Returns:
            JSON response data

        Raises:
            httpx.HTTPError: On HTTP errors after retries
            httpx.TimeoutException: On timeout after retries
        """
        request_headers = {**self.headers}
        if headers:
            request_headers.update(headers)

        logger.debug(f"GET {path} with params={params}")

        try:
            response = self.client.get(path, params=params, headers=request_headers)

            # Handle rate limiting (429 Too Many Requests)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2.0
                logger.warning(f"Rate limited (429), sleeping {delay}s before retry")
                time.sleep(delay)
                # Retry the request
                response = self.client.get(path, params=params, headers=request_headers)

            # Raise for HTTP errors
            response.raise_for_status()

            # Parse JSON response
            try:
                data = response.json()
                logger.debug(f"GET {path} completed successfully")
                return data
            except ValueError as e:
                logger.error(f"Failed to parse JSON response from {path}: {e}")
                raise httpx.RequestError(f"Invalid JSON response: {e}") from e

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {path}: {e}")
            raise
        except httpx.TimeoutException as e:
            logger.error(f"Timeout error for {path}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error for {path}: {e}")
            raise

    def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            path: URL path to request
            json_data: JSON data to send in request body
            data: Form data to send in request body
            params: Query parameters
            headers: Additional headers for this request

        Returns:
            JSON response data
        """
        request_headers = {**self.headers}
        if headers:
            request_headers.update(headers)

        logger.debug(f"POST {path}")

        response = self.client.post(
            path,
            json=json_data,
            data=data,
            params=params,
            headers=request_headers,
        )
        response.raise_for_status()

        return response.json()
