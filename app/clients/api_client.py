import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger
import json

class APIClient:
    def __init__(self, base_url, headers, default_timeout=30, max_retries=3):
        self.base_url = base_url.rstrip('/')
        self.headers = headers
        self.default_timeout = default_timeout
        
        # Initialize session with connection pooling
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        # Mount adapter with retry strategy and connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=100,  # Maintain up to 100 connections
            pool_maxsize=100,     # Maximum 100 connections per pool
            pool_block=False      # Don't block when pool is full
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(headers)

    def _handle_response(self, response, error_map=None):
        """Handle API response and common error codes"""
        try:
            error_map = error_map or {
                401: "Authentication failed. Please check your credentials.",
                403: "Permission denied. Please check your access rights.",
                404: "Resource not found.",
                429: "Rate limit exceeded. Please try again later.",
                500: "Internal server error.",
                503: "Service unavailable."
            }

            if response.status_code not in [200, 201, 204]:
                error_body = response.json() if response.text else "No error body"
                error_msg = error_map.get(
                    response.status_code,
                    f"Unexpected status code {response.status_code}"
                )
                logger.error(f"API Error: {error_msg}. Response: {error_body}")
                response.raise_for_status()

            return response.json() if response.text else None

        except requests.exceptions.JSONDecodeError:
            logger.error(f"Invalid JSON response: {response.text}")
            raise
        except Exception as e:
            logger.error(f"Error handling response: {str(e)}")
            raise

    def get(self, endpoint, params=None):
        """Make GET request with connection pooling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"GET {url}")
        response = self.session.get(url, params=params, timeout=self.default_timeout)
        return self._handle_response(response)

    def post(self, endpoint, data, params=None):
        """Make POST request with connection pooling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"POST {url}")
        logger.debug(f"Request data: {json.dumps(data)}")
        response = self.session.post(url, json=data, params=params, timeout=self.default_timeout)
        return self._handle_response(response)

    def put(self, endpoint, data, params=None):
        """Make PUT request with connection pooling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"PUT {url}")
        logger.debug(f"Request data: {json.dumps(data)}")
        response = self.session.put(url, json=data, params=params, timeout=self.default_timeout)
        return self._handle_response(response)

    def delete(self, endpoint, params=None):
        """Make DELETE request with connection pooling"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        logger.debug(f"DELETE {url}")
        response = self.session.delete(url, params=params, timeout=self.default_timeout)
        return self._handle_response(response)

    def __del__(self):
        """Cleanup session on object destruction"""
        self.session.close() 