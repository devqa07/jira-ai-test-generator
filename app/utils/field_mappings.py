from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache
import re
from loguru import logger

class Severity(Enum):
    CRITICAL = ("S1 - Critical", "10024")
    MAJOR = ("S2 - Major", "10025")
    MODERATE = ("S3 - Moderate", "10026")
    LOW = ("S4 - Low", "10027")

    def __init__(self, label: str, jira_id: str):
        self.label = label
        self.jira_id = jira_id

class Priority(Enum):
    LIVE = ("P0 - Live Issue", "1")
    CRITICAL = ("P1 - Critical", "2")
    HIGH = ("P2 - High", "3")
    MEDIUM = ("P3 - Medium", "4")
    LOW = ("P4 - Low", "5")

    def __init__(self, label: str, jira_id: str):
        self.label = label
        self.jira_id = jira_id

class AutomationStatus(Enum):
    MANUAL = ("Manual", "10097")
    AUTOMATED = ("Automated", "10098")
    IN_PROGRESS = ("In Progress", "10099")
    BLOCKED = ("Blocked", "10100")

    def __init__(self, label: str, jira_id: str):
        self.label = label
        self.jira_id = jira_id

class Journey(Enum):
    BACKOFFICE = ("Backoffice", "10068")
    BUYER = ("Buyer Management", "10059")
    ACCOUNT = ("Account", "10054")
    CATALOGUE = ("Catalogue", "10069")
    DISCOVERY = ("Discovery", "10063")
    SELLER = ("Seller Management", "10060")
    PURCHASE = ("Purchase", "10439")
    ENTERPRISE = ("Enterprise", "10440")
    RFQ = ("RFQ", "10441")

    def __init__(self, label: str, jira_id: str):
        self.label = label
        self.jira_id = jira_id

@dataclass
class FieldValidation:
    min_length: int = 0
    max_length: int = 255
    required: bool = True
    pattern: Optional[str] = None

class FieldMappings:
    def __init__(self):
        # Field validations
        self.validations = {
            'summary': FieldValidation(min_length=10, max_length=255, required=True),
            'description': FieldValidation(min_length=20, max_length=32768, required=True),
            'steps': FieldValidation(min_length=20, max_length=32768, required=True),
            'expected_result': FieldValidation(min_length=10, max_length=1024, required=True),
            'precondition': FieldValidation(min_length=10, max_length=1024, required=False)
        }

        # Custom field mappings
        self.custom_fields = {
            'severity': 'customfield_10062',
            'automation_status': 'customfield_10064',
            'journey': 'customfield_10037',
            'test_steps': 'customfield_10065',
            'expected_result': 'customfield_10066',
            'precondition': 'customfield_10067'
        }
        
        # Pre-compile validation patterns for better performance
        self._compiled_patterns = {}

    @lru_cache(maxsize=50)
    def get_severity(self, label: str) -> Optional[str]:
        """Get Jira ID for severity label with caching"""
        try:
            return next(s.jira_id for s in Severity if s.label == label)
        except StopIteration:
            logger.warning(f"Invalid severity label: {label}")
            return None

    @lru_cache(maxsize=50)
    def get_priority(self, label: str) -> Optional[str]:
        """Get Jira ID for priority label with caching"""
        try:
            return next(p.jira_id for p in Priority if p.label == label)
        except StopIteration:
            logger.warning(f"Invalid priority label: {label}")
            return None

    @lru_cache(maxsize=50)
    def get_automation_status(self, label: str) -> Optional[str]:
        """Get Jira ID for automation status label with caching"""
        try:
            return next(a.jira_id for a in AutomationStatus if a.label == label)
        except StopIteration:
            logger.warning(f"Invalid automation status label: {label}")
            return None

    @lru_cache(maxsize=50)
    def get_journey(self, label: str) -> Optional[str]:
        """Get Jira ID for journey label with caching"""
        try:
            return next(j.jira_id for j in Journey if j.label == label)
        except StopIteration:
            logger.warning(f"Invalid journey label: {label}")
            return None

    def validate_field(self, field_name: str, value: str) -> bool:
        """Validate field value against defined rules with optimized pattern checking"""
        if field_name not in self.validations:
            return True

        validation = self.validations[field_name]
        
        # Check if required
        if validation.required and not value:
            logger.error(f"{field_name} is required")
            return False
            
        # Skip other validations if empty and not required
        if not value:
            return True
            
        # Check length efficiently
        value_length = len(value)
        if value_length < validation.min_length:
            logger.error(f"{field_name} must be at least {validation.min_length} characters")
            return False
            
        if value_length > validation.max_length:
            logger.error(f"{field_name} must be at most {validation.max_length} characters")
            return False
            
        # Check pattern if defined (with caching)
        if validation.pattern:
            if field_name not in self._compiled_patterns:
                self._compiled_patterns[field_name] = re.compile(validation.pattern)
            
            if not self._compiled_patterns[field_name].match(value):
                logger.error(f"{field_name} does not match required pattern")
                return False
            
        return True

    @lru_cache(maxsize=20)
    def get_custom_field_id(self, field_name: str) -> Optional[str]:
        """Get custom field ID by name with caching"""
        return self.custom_fields.get(field_name)

    @lru_cache(maxsize=1)
    def get_all_severities(self) -> Dict[str, str]:
        """Get all severity mappings with caching"""
        return {s.label: s.jira_id for s in Severity}

    @lru_cache(maxsize=1)
    def get_all_priorities(self) -> Dict[str, str]:
        """Get all priority mappings with caching"""
        return {p.label: p.jira_id for p in Priority}

    @lru_cache(maxsize=1)
    def get_all_automation_statuses(self) -> Dict[str, str]:
        """Get all automation status mappings with caching"""
        return {a.label: a.jira_id for a in AutomationStatus}

    @lru_cache(maxsize=1)
    def get_all_journeys(self) -> Dict[str, str]:
        """Get all journey mappings with caching"""
        return {j.label: j.jira_id for j in Journey}
    
    def clear_cache(self) -> None:
        """Clear all method caches"""
        methods_to_clear = [
            self.get_severity,
            self.get_priority,
            self.get_automation_status,
            self.get_journey,
            self.get_custom_field_id,
            self.get_all_severities,
            self.get_all_priorities,
            self.get_all_automation_statuses,
            self.get_all_journeys
        ]
        
        for method in methods_to_clear:
            if hasattr(method, 'cache_clear'):
                method.cache_clear()
        
        # Clear compiled patterns
        self._compiled_patterns.clear()

# Initialize global instance (singleton pattern)
field_mappings = FieldMappings()