from app.utils.field_mappings import field_mappings
from loguru import logger
from functools import lru_cache
from typing import Dict, Any, Optional

class FieldValidator:
    _journey_cache = {}
    _field_cache = {}

    @staticmethod
    @lru_cache(maxsize=128)
    def validate_field(field_type: str, field_value: str) -> str:
        """Validate and get ID for a field value with caching"""
        mapping = field_mappings.get(field_type)
        if not mapping:
            raise ValueError(f"Unknown field type: {field_type}")

        if isinstance(field_value, str):
            field_value = field_value.strip()

        field_id = mapping.get(field_value)
        if not field_id:
            available = list(mapping.keys())
            raise ValueError(f"Invalid value for {field_type}: {field_value}. Available values: {available}")

        return field_id

    @staticmethod
    @lru_cache(maxsize=128)
    def validate_issue_key(key: str) -> bool:
        """Validate Jira issue key format with caching"""
        if not key or '-' not in key:
            raise ValueError(f"Invalid issue key format: {key}. Expected format: PROJECT-NUMBER (e.g., PROJ-123)")
        return True

    @staticmethod
    @lru_cache(maxsize=128)
    def get_project_key(issue_key: str) -> Optional[str]:
        """Extract project key from issue key with caching"""
        if not FieldValidator.validate_issue_key(issue_key):
            return None
        return issue_key.split('-')[0]

    @staticmethod
    def validate_journey_type(project_key: str) -> Dict[str, str]:
        """Get journey mapping based on project key with caching"""
        if project_key in FieldValidator._journey_cache:
            return FieldValidator._journey_cache[project_key]

        journey_map = {
            'PLA': {'type': 'Seller Management', 'id': '10060'},  # Seller Squad
            'MBA': {'type': 'Buyer Management', 'id': '10059'},   # Mobile Buyer App
            'PU': {'type': 'Purchase', 'id': '10439'},           # SME
            'B2B': {'type': 'Account', 'id': '10054'},           # B2B Apps
            'LFT': {'type': 'Account', 'id': '10054'},           # Logistics and Ops
            'RFQ': {'type': 'RFQ', 'id': '10441'},               # Request for Quotation
            'BCK': {'type': 'Backoffice', 'id': '10068'},        # Backoffice
            'ENT': {'type': 'Enterprise', 'id': '10440'},        # Enterprise
            'FIN': {'type': 'Account', 'id': '10054'},           # Finance
            'CMS': {'type': 'Account', 'id': '10054'},           # Content Management
            'API': {'type': 'Account', 'id': '10054'},           # API Management
            'CRM': {'type': 'Account', 'id': '10054'},           # Customer Relationship Management
            'REP': {'type': 'Account', 'id': '10054'}            # Reporting
        }
        
        # Cache and return journey based on project key
        result = journey_map.get(project_key, {'type': 'Account', 'id': '10054'})  # Default to Account journey
        FieldValidator._journey_cache[project_key] = result
        return result

    @staticmethod
    def clear_caches() -> None:
        """Clear all caches - useful for testing or when field mappings change"""
        FieldValidator._journey_cache.clear()
        FieldValidator._field_cache.clear()
        FieldValidator.validate_field.cache_clear()
        FieldValidator.validate_issue_key.cache_clear()
        FieldValidator.get_project_key.cache_clear()

    @staticmethod
    def validate_severity(severity: str) -> Dict[str, str]:
        """Validate severity value"""
        valid_severities = {
            "S1 - Critical": "10001",
            "S2 - Major": "10002",
            "S3 - Moderate": "10003",
            "S4 - Low": "10004"
        }
        
        if severity not in valid_severities:
            raise ValueError(f"Invalid severity: {severity}. Must be one of: {list(valid_severities.keys())}")
        
        return {"value": severity, "id": valid_severities[severity]}

    @staticmethod
    def validate_priority(priority: str) -> Dict[str, str]:
        """Validate priority value"""
        valid_priorities = {
            "P0 - Live Issue": "10001",
            "P1 - Critical": "10002",
            "P2 - High": "10003",
            "P3 - Medium": "10004",
            "P4 - Low": "10005"
        }
        
        if priority not in valid_priorities:
            raise ValueError(f"Invalid priority: {priority}. Must be one of: {list(valid_priorities.keys())}")
        
        return {"value": priority, "id": valid_priorities[priority]} 