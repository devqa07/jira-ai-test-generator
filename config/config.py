"""
Configuration for Jira Test Architect.
Loads sensitive data from environment variables with optimized caching and validation.
"""
import os
from typing import Dict, Any, Optional
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file once
load_dotenv()

@lru_cache(maxsize=1)
def get_env_var(var_name: str, default: Optional[str] = None, required: bool = True) -> str:
    """Get environment variable with caching and enhanced error handling"""
    value = os.getenv(var_name)
    if value is None:
        if default is not None:
            return default
        if required:
            raise ValueError(
                f"Environment variable {var_name} is not set.\n"
                f"Please set it in your .env file or environment."
            )
        return ""
    return value.strip()

@lru_cache(maxsize=1)
def validate_jira_config() -> Dict[str, str]:
    """Validate and return Jira configuration with caching"""
    config = {}
    
    # Required fields
    required_fields = {
        'base_url': 'JIRA_BASE_URL',
        'email': 'JIRA_EMAIL', 
        'api_token': 'JIRA_API_TOKEN'
    }
    
    for config_key, env_var in required_fields.items():
        try:
            value = get_env_var(env_var, required=True)
            if not value:
                raise ValueError(f"{env_var} cannot be empty")
            config[config_key] = value
        except ValueError as e:
            raise ValueError(f"Jira configuration error: {e}")
    
    # Validate URL format
    if not config['base_url'].startswith(('http://', 'https://')):
        raise ValueError("JIRA_BASE_URL must start with http:// or https://")
    
    # Remove trailing slash from URL
    config['base_url'] = config['base_url'].rstrip('/')
    
    return config

@lru_cache(maxsize=1)
def get_optional_config() -> Dict[str, Any]:
    """Get optional configuration settings with caching"""
    return {
        'debug': get_env_var('DEBUG', 'false', required=False).lower() in ('true', '1', 'yes'),
        'quiet_mode': get_env_var('QUIET_MODE', 'false', required=False).lower() in ('true', '1', 'yes'),
        'max_retries': int(get_env_var('MAX_RETRIES', '3', required=False)),
        'timeout': int(get_env_var('TIMEOUT', '30', required=False)),
        'cache_ttl': int(get_env_var('CACHE_TTL', '300', required=False)),  # 5 minutes default
        
        # AI Configuration Options
        'ai_mode': get_env_var('AI_MODE', 'local', required=False).lower(),  # local, huggingface, groq, fallback
        'enable_fallback': get_env_var('ENABLE_FALLBACK', 'true', required=False).lower() in ('true', '1', 'yes'),
        'cache_scenarios': get_env_var('CACHE_SCENARIOS', 'true', required=False).lower() in ('true', '1', 'yes'),
        'min_scenarios': int(get_env_var('MIN_SCENARIOS', '3', required=False)),
        'max_scenarios': int(get_env_var('MAX_SCENARIOS', '10', required=False)),
        
        # Free AI Service Options
        'huggingface_token': get_env_var('HUGGINGFACE_TOKEN', '', required=False),
        'groq_token': get_env_var('GROQ_TOKEN', '', required=False),
        'use_free_tier': get_env_var('USE_FREE_TIER', 'true', required=False).lower() in ('true', '1', 'yes'),
    }

@lru_cache(maxsize=1)  
def get_ai_config() -> Dict[str, Any]:
    """Get AI-specific configuration for free services"""
    optional_config = get_optional_config()
    
    return {
        'mode': optional_config['ai_mode'],
        'enable_fallback': optional_config['enable_fallback'],
        'cache_enabled': optional_config['cache_scenarios'],
        'min_scenarios': optional_config['min_scenarios'],
        'max_scenarios': optional_config['max_scenarios'],
        'free_tier_only': optional_config['use_free_tier'],
        
        # Free service endpoints
        'huggingface': {
            'token': optional_config['huggingface_token'],
            'model': get_env_var('HF_MODEL', 'microsoft/DialoGPT-medium', required=False),
            'inference_url': 'https://api-inference.huggingface.co/models/',
            'free_limit': 1000  # requests per hour
        },
        
        # Additional service configurations
        'groq_token': optional_config['groq_token'],
        
        # Local processing settings
        'local': {
            'max_memory_mb': int(get_env_var('MAX_MEMORY_MB', '512', required=False)),
            'enable_caching': True,
            'scenario_templates': get_env_var('SCENARIO_TEMPLATES', 'test_scenarios.json', required=False)
        }
    }

class Config:
    """Configuration manager with lazy loading and validation"""
    
    def __init__(self):
        """Initialize configuration manager"""
        self._config: Optional[Dict[str, Any]] = None
        self._validated = False
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get complete configuration with lazy loading and caching"""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> Dict[str, Any]:
        """Load and validate configuration"""
        try:
            # Get Jira configuration
            jira_config = validate_jira_config()
            
            # Get optional settings
            optional_config = get_optional_config()
            
            # Combine configurations
            complete_config = {
                'jira': jira_config,
                **optional_config
            }
            
            self._validated = True
            return complete_config
            
        except Exception as e:
            raise ValueError(f"Configuration loading failed: {e}")
    
    def validate(self) -> bool:
        """Validate configuration without loading it"""
        try:
            if not self._validated:
                self.config  # This will trigger validation
            return self._validated
        except Exception:
            return False
    
    def get_jira_config(self) -> Dict[str, str]:
        """Get only Jira configuration"""
        return self.config['jira']
    
    def is_debug_mode(self) -> bool:
        """Check if debug mode is enabled"""
        return self.config.get('debug', False)
    
    def is_quiet_mode(self) -> bool:
        """Check if quiet mode is enabled"""
        return self.config.get('quiet_mode', False)
    
    def get_timeout(self) -> int:
        """Get request timeout setting"""
        return self.config.get('timeout', 30)
    
    def get_max_retries(self) -> int:
        """Get maximum retry attempts"""
        return self.config.get('max_retries', 3)
    
    def get_cache_ttl(self) -> int:
        """Get cache time-to-live in seconds"""
        return self.config.get('cache_ttl', 300)
    
    def reload(self) -> None:
        """Force reload configuration from environment"""
        # Clear caches
        get_env_var.cache_clear()
        validate_jira_config.cache_clear()
        get_optional_config.cache_clear()
        
        # Reset internal state
        self._config = None
        self._validated = False
        
        # Reload environment variables
        load_dotenv(override=True)

# Create singleton instance for easy importing
config_instance = Config()

# Export key functions for easy importing
__all__ = ['Config', 'config', 'get_ai_config', 'get_optional_config', 'validate_jira_config']

# Jira Configuration
config = {
    "jira": {
        "base_url": "https://devtech.atlassian.net",
        "email": os.getenv("JIRA_EMAIL"),  # Must be set in environment
        "api_token": os.getenv("JIRA_API_TOKEN")  # Must be set in environment
    },
    "custom_fields": {
        "incident_severity": "customfield_10031",
        "automation_status": "customfield_10064",
        "business_journey": "customfield_10037"
    },
    
    # Project Configuration
    'projects': {
        'default_journey': 'Account',
        'supported_projects': [
            'ACC',  # Account Management
            'Mobile',  # Mobile App
            'ERP',   # ERP Management
            'B2B',  # B2B Apps
        ]
    },
    
    # Test Configuration
    'test': {
        # Severity Levels with their Jira IDs
        'severities': {
            'S1 - Critical': '10024',
            'S2 - Major': '10025',
            'S3 - Moderate': '10026',
            'S4 - Low': '10027'
        },
        # Priority Levels with their Jira IDs
        'priorities': {
            'P0 - Live Issue': '1',
            'P1 - Critical': '2',
            'P2 - High': '3',
            'P3 - Medium': '4',
            'P4 - Low': '5'
        },
        # Automation Status with their Jira IDs
        'automation_statuses': {
            'Manual': '10097',
            'Automated': '10098',
            'In Progress': '10099',
            'Blocked': '10100'
        },
        # Default values
        'default_severity': 'S3 - Moderate',
        'default_priority': 'P3 - Medium',
        'default_automation': 'Manual'
    }
}

class Config:
    """Configuration class that provides access to the config dictionary"""
    
    def __init__(self):
        self.config = config
    
    def get(self, key, default=None):
        """Get a configuration value"""
        return self.config.get(key, default)
    
    def get_custom_fields(self):
        """Get custom fields configuration"""
        return self.config.get('custom_fields', {})
    
    def get_projects_config(self):
        """Get projects configuration"""
        return self.config.get('projects', {})
    
    def get_test_config(self):
        """Get test configuration"""
        return self.config.get('test', {})