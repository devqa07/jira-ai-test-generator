import requests
import json
import base64
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps, lru_cache

from loguru import logger
from rich.console import Console
from rich.theme import Theme

from app.utils.field_mappings import FieldMappings, field_mappings
from app.clients.api_client import APIClient
from app.validators.field_validators import FieldValidator
from app.formatters.response_formatter import ResponseFormatter

# Configure custom theme for rich (singleton pattern)
_console_theme = Theme({
    "info": "cyan",
    "warning": "yellow", 
    "error": "red",
    "success": "green"
})
console = Console(theme=_console_theme)

# Configure logger once
logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{level}</level> | {message}", colorize=True)

def retry_on_failure(max_retries=3, delay=1):
    """Decorator to retry failed API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Failed to execute: {str(e)}")
                raise
        return wrapper
    return decorator

class JiraClient:
    def __init__(self, config):
        """Initialize Jira client with configuration"""
        self.config = config
        self.base_url = config['jira']['base_url']
        self.email = config['jira']['email']
        self.api_token = config['jira']['api_token']
        
        # Set up authentication and headers in one step
        self.headers = self._setup_authentication()
        
        # Initialize utilities
        self.field_mappings = FieldMappings()
        self.api_client = APIClient(self.base_url, self.headers)
        self.validator = FieldValidator()
        self.formatter = ResponseFormatter()
        
        # Track initialization
        self.quiet_mode = config.get('quiet_mode', False)
        if not self.quiet_mode:
            logger.info(f"Initialized Jira client for domain: {self.base_url}")
        
        # Consolidated cache structure
        self._cache = {
            'issue_types': {},
            'priorities': None,
            'link_types': None,
            'field_metadata': {},
            'current_user': None,
            'create_meta': {},
            'test_type': {}
        }
        
        # Initialize thread pool executor
        self.executor = ThreadPoolExecutor(max_workers=5)
    
    def _setup_authentication(self) -> Dict[str, str]:
        """Set up authentication headers in one step"""
        auth_string = f"{self.email}:{self.api_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Basic {auth_b64}'
        }

    def test_connection(self):
        """Test Jira connection and return user info"""
        return self.api_client.get('rest/api/3/myself')

    def get_issue(self, issue_key):
        """Get issue details from Jira"""
        FieldValidator.validate_issue_key(issue_key)
        try:
            logger.debug(f"Fetching issue details for {issue_key}")
            data = self.api_client.get(f'rest/api/3/issue/{issue_key}')
            logger.debug(f"Got issue data for {issue_key}: {data.get('key')} ({data.get('fields', {}).get('issuetype', {}).get('name')})")
            return data
        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            return None

    @retry_on_failure(max_retries=3, delay=1)
    def create_issue(self, fields, project_key=None):
        """Create a new issue in Jira with retry logic"""
        if project_key and 'project' not in fields:
            fields['project'] = {'key': project_key}
        return self.api_client.post('rest/api/3/issue', {'fields': fields})

    @lru_cache(maxsize=50)
    def get_issue_types(self, project_key):
        """Get available issue types for a project with enhanced caching"""
        if project_key not in self._cache['issue_types']:
            self._cache['issue_types'][project_key] = self.api_client.get('rest/api/3/issuetype')
        return self._cache['issue_types'][project_key]

    @lru_cache(maxsize=100)
    def get_create_meta(self, project_key, issue_type_id):
        """Get create metadata for issue type with enhanced caching and error handling"""
        cache_key = f"{project_key}_{issue_type_id}"
        if cache_key not in self._cache['create_meta']:
            params = {
                'projectKeys': project_key,
                'issuetypeIds': issue_type_id,
                'expand': 'projects.issuetypes.fields'
            }
            response = self.api_client.get('rest/api/3/issue/createmeta', params)
            
            # Validate response structure
            if not response.get('projects') or len(response['projects']) == 0:
                raise Exception(f"No projects found for project key {project_key}")
            
            project = response['projects'][0]
            if not project.get('issuetypes') or len(project['issuetypes']) == 0:
                raise Exception(f"No issue types found for project {project_key} and issue type {issue_type_id}")
            
            self._cache['create_meta'][cache_key] = project['issuetypes'][0]
        return self._cache['create_meta'][cache_key]

    def get_priorities(self):
        """Get available priorities with caching"""
        if self._cache['priorities'] is None:
            self._cache['priorities'] = self.api_client.get('rest/api/3/priority')
        return self._cache['priorities']

    def get_current_user(self):
        """Get current user information with caching"""
        if self._cache['current_user'] is None:
            self._cache['current_user'] = self.api_client.get('rest/api/3/myself')
        return self._cache['current_user']

    @staticmethod
    @lru_cache(maxsize=200)
    def _format_description(text):
        """Format text in Atlassian Document Format with caching"""
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": text
                        }
                    ]
                }
            ]
        }

    @staticmethod
    @lru_cache(maxsize=500)
    def _clean_title(title: str) -> str:
        """Clean up title by removing newlines and extra whitespace with caching"""
        if not title:
            return ""
        # Replace newlines with spaces and remove extra whitespace
        cleaned = ' '.join(title.replace('\n', ' ').split())
        # Truncate if too long (Jira has a 255 character limit)
        if len(cleaned) > 255:
            cleaned = cleaned[:252] + "..."
        return cleaned

    def create_test_cases_for_story(self, story_key: str, scenarios: List[Dict]) -> List[Dict]:
        """Create multiple test cases and link them to a story"""
        try:
            # Get project key from story
            project_key = story_key.split('-')[0]
            
            # Validate project field configuration first
            field_config = self.validate_project_fields(project_key)
            
            # Create each test case
            created_tests = []
            for scenario in scenarios:
                try:
                    # Base fields that are common to all projects
                    fields = {
                        'project': {'key': project_key},
                        'summary': self._clean_title(scenario['title']),
                        'description': self._format_description(scenario['description']),
                        'issuetype': {'id': field_config['test_type_id']},
                        'assignee': {'accountId': scenario['assignee_id']}  # Set assignee from scenario
                    }

                    # Add severity if available
                    if field_config['has_severity']:
                        fields['customfield_10031'] = {'value': scenario.get('severity', 'S3 - Moderate')}

                    # Add automation status only if field is available and project needs it
                    if field_config['has_automation_status'] and project_key in ['MBA', 'PLA', 'PU']:
                        fields['customfield_10064'] = {'value': scenario.get('automation_status', 'Manual')}

                    # Add journey only if field is available and project needs it
                    if field_config['has_journey'] and project_key in ['MBA', 'PLA', 'LFT', 'PU']:
                        fields['customfield_10037'] = {'id': self._get_journey_id(scenario.get('journey', 'Account'))}
                    
                    # Create test case
                    response = self.create_issue(fields, project_key)
                    test_key = response['key']
                    
                    # Link to story
                    self.create_link(test_key, story_key)
                    
                    created_tests.append({
                        'key': test_key,
                        'title': scenario['title'],
                        'linked': True
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to create test case: {str(e)}")
                    continue
            
            return created_tests
            
        except Exception as e:
            logger.error(f"Error in create_test_cases_for_story: {str(e)}")
            return []

    def _get_test_type(self, project_key):
        """Get Test Scenario type with caching"""
        if project_key not in self._cache['test_type']:
            issue_types = self.get_issue_types(project_key)
            self._cache['test_type'][project_key] = next(
                (t for t in issue_types if t['name'] == 'Test Scenario'),
                None
            )
        return self._cache['test_type'][project_key]

    def _determine_journey_type(self, story):
        """Determine journey type based on project key"""
        fields = story.get('fields', {})
        project_key = fields.get('project', {}).get('key', '')
        
        # Direct mapping of project to journey - use global field_mappings
        journey_map = {
            'PLA': field_mappings.get_journey('Seller Management'),  # Platform
            'MBA': field_mappings.get_journey('Buyer Management'),   # My Business Account
            'SEL': field_mappings.get_journey('Seller Management'),  # Seller
            'RFQ': field_mappings.get_journey('RFQ'),               # RFQ
            'BCK': field_mappings.get_journey('Backoffice'),        # Backoffice
            'ENT': field_mappings.get_journey('Enterprise'),        # Enterprise
            'PU': field_mappings.get_journey('Purchase'),           # Purchasing
            'FIN': field_mappings.get_journey('Account'),           # Finance
            'CMS': field_mappings.get_journey('Account'),           # Content Management
            'API': field_mappings.get_journey('Account'),           # API Management
            'SEC': field_mappings.get_journey('Account'),           # Security
            'OPS': field_mappings.get_journey('Account'),           # Operations
            'CRM': field_mappings.get_journey('Account'),           # Customer Relationship Management
            'LOG': field_mappings.get_journey('Account'),           # Logistics
            'PAY': field_mappings.get_journey('Account'),           # Payments
            'INV': field_mappings.get_journey('Account'),           # Inventory
            'REP': field_mappings.get_journey('Account')            # Reporting
        }
        
        return journey_map.get(project_key, field_mappings.get_journey('Account'))  # Default to Account journey

    def _print_status(self, message: str, status: str = "info"):
        """Print status message with appropriate styling"""
        status_icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌"
        }
        icon = status_icons.get(status, "•")
        console.print(f"{icon} {message}", style=status)

    def validate_project_fields(self, project_key: str, quiet: bool = False) -> Dict:
        """Validate project field configuration before creating test cases"""
        try:
            # Get issue type ID for Test Scenario
            issue_types = self.get_issue_types(project_key)
            test_type = next((t for t in issue_types if t['name'] == 'Test Scenario'), None)
            if not test_type:
                # List available issue types for debugging
                available_types = [t['name'] for t in issue_types] if issue_types else []
                raise Exception(
                    f"Test Scenario issue type not found in project {project_key}. "
                    f"Available issue types: {', '.join(available_types) if available_types else 'None'}"
                )

            # Get create metadata to check available fields
            create_meta = self.get_create_meta(project_key, test_type['id'])
            available_fields = create_meta.get('fields', {})

            # Check which fields are available
            field_config = {
                'has_automation_status': 'customfield_10064' in available_fields,
                'has_journey': 'customfield_10037' in available_fields,
                'has_severity': 'customfield_10031' in available_fields,
                'test_type_id': test_type['id']
            }

            if not quiet:
                logger.info(f"Project {project_key} field configuration:")
                logger.info(f"- Automation Status: {'✓' if field_config['has_automation_status'] else '✗'}")
                logger.info(f"- Journey: {'✓' if field_config['has_journey'] else '✗'}")
                logger.info(f"- Severity: {'✓' if field_config['has_severity'] else '✗'}")

            return field_config

        except Exception as e:
            logger.error(f"Error validating project fields: {str(e)}")
            raise

    def _bulk_create_test_cases(self, project_key: str, test_cases: List[Dict], story_key: str) -> List[Dict]:
        """Create test cases in bulk"""
        try:
            # Get issue type ID for "Test Scenario"
            issue_types = self.get_issue_types(project_key)
            test_type = next((t for t in issue_types if t['name'] == 'Test Scenario'), None)
            if not test_type:
                raise Exception("Test Scenario issue type not found")

            # Prepare bulk create payload
            bulk_payload = {
                "issueUpdates": [
                    {
                        "fields": {
                            "project": {"key": project_key},
                            "summary": test_case['title'][:255],
                            "description": self._format_description(test_case['description']),
                            "issuetype": {"id": test_type['id']},
                            **({"customfield_10031": {"value": test_case['severity']}} if 'severity' in test_case else {}),
                            **({"customfield_10064": {"value": test_case['automation']}} if 'automation' in test_case else {}),
                            **({"customfield_10037": {"id": self._get_journey_id(test_case['journey'])}} if 'journey' in test_case else {})
                        }
                    }
                    for test_case in test_cases
                ]
            }

            # Create test cases
            response = requests.post(
                f"{self.base_url}/rest/api/3/issue/bulk",
                headers=self.headers,
                json=bulk_payload
            )

            if response.status_code != 201:
                error_details = response.json() if response.text else "No error details available"
                raise Exception(f"Failed to create test cases in bulk: {error_details}")

            created_issues = response.json()['issues']
            return [
                {
                    'key': issue['key'],
                    'title': test_cases[i]['title'],
                    'linked': False
                }
                for i, issue in enumerate(created_issues)
            ]

        except Exception as e:
            self._print_status(f"Error in bulk creation: {str(e)}", "error")
            return []

    def _bulk_create_links(self, test_cases: List[Dict], story_key: str) -> List[Dict]:
        """Create links between test cases and story"""
        linked_tests = []
        for test in test_cases:
            try:
                if self.create_link(test['key'], story_key):
                    test['linked'] = True
                linked_tests.append(test)
            except Exception as e:
                self._print_status(f"Failed to link {test['key']}: {str(e)}", "warning")
                linked_tests.append({**test, 'linked': False})

        return linked_tests

    def get_link_types(self):
        """Get available issue link types with caching"""
        if self._cache['link_types'] is None:
            url = f"{self.api_client.base_url}/rest/api/3/issueLinkType"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            self._cache['link_types'] = data.get('issueLinkTypes', [])
            logger.info("Available link types:")
            for link_type in self._cache['link_types']:
                logger.info(f"- {link_type.get('name')} (inward: {link_type.get('inward')}, outward: {link_type.get('outward')})")
        return self._cache['link_types']

    def get_linked_test_cases(self, issue_key):
        """Get test cases linked to an issue"""
        try:
            url = f"{self.api_client.base_url}/rest/api/3/issue/{issue_key}"
            response = requests.get(
                url,
                headers=self.headers,
                params={
                    'fields': 'issuelinks',
                    'maxResults': 1  # Only check if any links exist
                }
            )
            response.raise_for_status()
            
            # Quick check if there are any links
            issue_links = response.json().get('fields', {}).get('issuelinks', [])
            if not issue_links:
                return []  # Return empty list if no links found
                
            # If links exist, then get test cases
            test_cases = []
            for link in issue_links:
                linked_issue = link.get('inwardIssue') or link.get('outwardIssue')
                if linked_issue and linked_issue.get('key', '').startswith(issue_key.split('-')[0]):
                    test_cases.append(linked_issue)
            
            return test_cases
            
        except Exception as e:
            logger.error(f"Failed to get linked test cases for {issue_key}: {str(e)}")
            return []  # Return empty list on error to allow process to continue

    def _bulk_update_assignees(self, test_keys, account_id):
        """Update assignees in bulk"""
        for test_key in test_keys:
            try:
                self.update_issue_assignee(test_key, account_id)
            except Exception as e:
                logger.warning(f"Failed to update assignee for {test_key}: {str(e)}")

    @retry_on_failure(max_retries=3, delay=1)
    def create_link(self, inward_key, outward_key, link_type="Relates"):
        """Create a link between two issues with retry logic"""
        try:
            # Validate issue keys
            if not inward_key or not outward_key:
                raise ValueError("Both inward and outward issue keys are required")
            
            for key in [inward_key, outward_key]:
                if not isinstance(key, str) or '-' not in key:
                    raise ValueError(f"Invalid issue key format: {key}. Expected format: PROJECT-NUMBER")
                
            # First verify both issues exist
            logger.debug(f"Verifying existence of issues before linking: {inward_key} and {outward_key}")
            inward_issue = self.get_issue(inward_key)
            outward_issue = self.get_issue(outward_key)
            
            if not inward_issue:
                raise ValueError(f"Inward issue {inward_key} not found")
            if not outward_issue:
                raise ValueError(f"Outward issue {outward_key} not found")
            
            # Check if link already exists to avoid duplicates
            existing_links = self.get_linked_test_cases(outward_key)
            if inward_key in existing_links:
                logger.info(f"Link between {inward_key} and {outward_key} already exists")
                return True
            
            logger.debug(f"Creating link from {inward_key} ({inward_issue.get('fields', {}).get('issuetype', {}).get('name')}) "
                       f"to {outward_key} ({outward_issue.get('fields', {}).get('issuetype', {}).get('name')})")
            
            url = f"{self.api_client.base_url}/rest/api/3/issueLink"
            payload = {
                "type": {"name": "Relates"},  # Always use "Relates" link type
                "inwardIssue": {"key": inward_key},
                "outwardIssue": {"key": outward_key}
            }
            
            logger.debug(f"Creating link with payload: {json.dumps(payload)}")
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            response_text = response.text if response.text else "No response body"
            logger.debug(f"Link creation response status: {response.status_code}")
            logger.debug(f"Link creation response: {response_text}")
            
            if response.status_code != 201 and response.status_code != 204:
                raise ValueError(f"Failed to create link: {response_text}")
                
            logger.info(f"Successfully linked {inward_key} to {outward_key} with type 'Relates'")
            return True
            
        except ValueError as ve:
            logger.error(f"Validation error in create_link: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Failed to create link between {inward_key} and {outward_key}: {str(e)}")
            raise

    def create_issue_link(self, inward_issue, outward_issue, link_type="Tests"):
        """Create a link between two issues"""
        try:
            url = f"{self.api_client.base_url}/rest/api/3/issueLink"
            payload = {
                "type": {"name": link_type},
                "inwardIssue": {"key": inward_issue},
                "outwardIssue": {"key": outward_issue}
            }
            
            logger.debug(f"Creating issue link. URL: {url}")
            logger.debug(f"Link payload: {json.dumps(payload)}")
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            logger.debug(f"Link response status: {response.status_code}")
            if response.status_code != 201 and response.status_code != 204:
                logger.debug(f"Link response content: {response.text}")
            
            response.raise_for_status()
            logger.info(f"Issue link created successfully between {inward_issue} and {outward_issue}")
            return True
        except requests.exceptions.HTTPError as error:
            error_message = error.response.json() if error.response.text else str(error)
            logger.error(f"Error creating issue link: {error_message}")
            raise Exception(f"Failed to create issue link: {error_message}")
        except Exception as e:
            logger.error(f"Unexpected error creating issue link: {str(e)}")
            raise
    
    def update_issue_assignee(self, issue_key, account_id):
        """Assign an issue to a specific user by account ID"""
        try:
            if not issue_key or '-' not in issue_key:
                raise ValueError(f"Invalid issue key format: {issue_key}")
                
            url = f"{self.api_client.base_url}/rest/api/3/issue/{issue_key}/assignee"
            payload = {"accountId": account_id}
            
            logger.debug(f"Updating assignee for {issue_key} to {account_id}")
            
            response = requests.put(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 404:
                raise Exception(f"Issue {issue_key} not found")
            elif response.status_code == 403:
                raise Exception(f"Permission denied to update assignee for {issue_key}")
                
            response.raise_for_status()
            logger.info(f"Successfully assigned {issue_key} to account {account_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to assign issue {issue_key}: {str(e)}")
            raise
    
    def update_issue_description(self, issue_key, description):
        """Update the description of an issue"""
        try:
            if not issue_key or '-' not in issue_key:
                raise ValueError(f"Invalid issue key format: {issue_key}")
                
            url = f"{self.api_client.base_url}/rest/api/3/issue/{issue_key}"
            payload = {
                "fields": {
                    "description": description
                }
            }
            
            logger.debug(f"Updating description for {issue_key}")
            
            response = requests.put(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 404:
                raise Exception(f"Issue {issue_key} not found")
            elif response.status_code == 403:
                raise Exception(f"Permission denied to update description for {issue_key}")
                
            response.raise_for_status()
            logger.info(f"Successfully updated description for {issue_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update description for {issue_key}: {str(e)}")
            raise

    def create_single_test_scenario(self, story_key, scenario_data):
        """Create a single test scenario and link it to a story"""
        try:
            project_key = story_key.split('-')[0]
            logger.info(f"Creating single test scenario for story {story_key}")
            
            # Get test type ID
            test_type = self._get_test_type(project_key)
            if not test_type:
                raise Exception(f"Test Scenario issue type not found in project {project_key}")

            # Get journey info
            journey_info = self._get_journey_info(project_key)
            
            # Get current user
            current_user = self.get_current_user()

            # Prepare fields
            fields = {
                'project': {'key': project_key},
                'issuetype': {'id': test_type['id']},
                'summary': scenario_data['title'],
                'description': self._format_description(scenario_data['description']),
                'assignee': {'id': current_user['accountId']},
                'customfield_10064': {'value': 'Manual'},
                'customfield_10037': {'id': journey_info['id']}
            }

            # Create test case
            response = requests.post(
                f"{self.api_client.base_url}/rest/api/3/issue",
                headers=self.headers,
                json={'fields': fields}
            )
            
            if response.status_code != 201:
                logger.error(f"Failed to create test scenario: {response.text}")
                raise Exception("Failed to create test scenario")

            test_case = response.json()
            logger.info(f"Created test scenario {test_case['key']}")

            # Link to story
            try:
                self._bulk_create_links([test_case], story_key)
            except Exception as e:
                logger.warning(f"Created test scenario but failed to link to story: {str(e)}")

            return test_case

        except Exception as e:
            logger.error(f"Error creating single test scenario: {str(e)}")
            raise

    def update_test_scenario(self, test_key, updates):
        """Update an existing test scenario"""
        FieldValidator.validate_issue_key(test_key)
        
        # Validate test exists and is correct type
        test_details = self.get_issue(test_key)
        if test_details['type'] != 'Test':
            raise ValueError(f"Issue {test_key} is not a test scenario")

        # Prepare fields
        fields = {}
        if 'title' in updates or 'summary' in updates:
            fields['summary'] = updates.get('title') or updates.get('summary')

        if 'description' in updates:
            fields['description'] = ResponseFormatter.format_description(updates['description'])

        if 'journey' in updates:
            project_key = FieldValidator.get_project_key(test_key)
            journey_info = FieldValidator.validate_journey_type(project_key)
            fields['customfield_10037'] = {'id': journey_info['id']}

        if 'automation_status' in updates:
            fields['customfield_10064'] = {'value': updates['automation_status']}

        if 'assignee' in updates:
            fields['assignee'] = {'id': updates['assignee']}

        if fields:
            self.api_client.put(f'rest/api/3/issue/{test_key}', {'fields': fields})
            logger.info(f"Updated test scenario {test_key}")
            return self.get_issue(test_key)
        return test_details

    def _get_journey_id(self, journey_name: str) -> str:
        """Get journey ID from journey name"""
        journey_mapping = {
            'Account': '10054',
            'Buyer Management': '10059',
            'Seller Management': '10060',
            'RFQ': '10441',
            'Backoffice': '10068',
            'Enterprise': '10440',
            'Purchase': '10439',
            'Discovery': '10063',
            'Catalogue': '10069'
        }
        
        # Default to Account if journey not found
        return journey_mapping.get(journey_name, '10054')  # Default to Account journey

    @retry_on_failure(max_retries=3, delay=1)
    def delete_issue(self, issue_key: str) -> bool:
        """Delete an issue from Jira"""
        try:
            response = self.api_client.delete(f'rest/api/3/issue/{issue_key}')
            return True
        except Exception as e:
            logger.error(f"Failed to delete issue {issue_key}: {str(e)}")
            return False

    def get_existing_test_cases(self, story_key: str, quiet: bool = False) -> List[Dict]:
        """Get existing test cases linked to a story"""
        try:
            # Search for test cases linked to this story
            jql = f'project = "{story_key.split("-")[0]}" AND "Linked Stories" ~ "{story_key}" AND issuetype = "Test Scenario"'
            
            search_results = self.search_issues(jql)
            test_cases = search_results.get('issues', [])
            
            if not quiet and test_cases:
                logger.debug(f"Found {len(test_cases)} existing test cases for {story_key}")
                
            return test_cases
            
        except Exception as e:
            if not quiet:
                logger.warning(f"Error getting existing test cases: {str(e)}")
            return []