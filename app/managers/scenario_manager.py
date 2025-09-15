"""
Test Scenario Manager

This module handles the creation and management of test scenarios for Jira issues.
"""

import json
from typing import Dict, Any, List, Optional
from loguru import logger
from app.clients.jira_client import JiraClient
from app.formatters.text_formatter import text_formatter
from datetime import datetime, timedelta
from app.utils.utils import get_custom_field_id, convert_to_adf
import time
import re

class TestScenarioManager:
    def __init__(self, config, jira_client):
        """Initialize test scenario manager"""
        self.config = config
        self.jira_client = jira_client
        logger.debug(f"TestScenarioManager initialized with config: {config}")
        
        # Define journey mapping with correct IDs
        self.journey_map = {
            'Seller Management': '10060',
            'Buyer Management': '10059',
            'RFQ': '10441',
            'Backoffice': '10068',
            'Enterprise': '10440',
            'Account': '10054',  # Default journey
            'Catalogue': '10069',
            'Discovery': '10063',
            'Purchase': '10439',
            'Customer': '10054',  # Map Customer journey to Account as fallback
            'Finance': '10054',   # Map Finance to Account for now
            'Seller': '10060',    # Map to Seller Management
            'Buyer': '10059'      # Map to Buyer Management
        }

        # Define project-specific mandatory fields
        self.project_fields = {
            'FIN': {
                'required': ['summary', 'description', 'severity', 'priority', 'assignee'],
                'optional': []
            },
            'MBA': {
                'required': ['summary', 'description', 'severity', 'priority', 'assignee', 'automation_status', 'journey'],
                'optional': []
            },
            'PLA': {
                'required': ['summary', 'description', 'severity', 'priority', 'assignee', 'automation_status', 'journey'],
                'optional': []
            },
            'LFT': {
                'required': ['summary', 'description', 'severity', 'priority', 'assignee', 'journey'],
                'optional': ['automation_status']
            },
            'PU': {
                'required': ['summary', 'description', 'severity', 'priority', 'assignee', 'automation_status', 'journey'],
                'optional': []
            }
        }
    
    def create_test_scenario(self, scenario):
        """Create a test scenario in Jira"""
        try:
            # Get parent story info
            parent_key = scenario.get('parent_key')
            if not parent_key:
                raise ValueError("Parent story key is required")
            
            # Get project key from parent story
            project_key = parent_key.split('-')[0]
            
            # Get issue type ID for "Test Scenario"
            issue_types = self.jira_client.get_issue_types(project_key)
            test_type = next((t for t in issue_types if t['name'] == 'Test Scenario'), None)
            if not test_type:
                raise ValueError("Test Scenario issue type not found")

            # Add default values for missing required fields based on project
            if project_key in self.project_fields:
                required_fields = self.project_fields[project_key]['required']
                
                # Add default values for missing fields
                if 'severity' not in scenario and 'severity' in required_fields:
                    scenario['severity'] = 'S3 - Moderate'
                if 'priority' not in scenario and 'priority' in required_fields:
                    scenario['priority'] = 'P3 - Medium'
                if 'automation_status' not in scenario and 'automation_status' in required_fields:
                    scenario['automation_status'] = 'Manual'
                if 'journey' not in scenario and 'journey' in required_fields:
                    scenario['journey'] = 'Account'  # Default journey

            # Base fields that are common to all projects
            fields = {
                "project": {"key": project_key},
                "summary": self._clean_title(scenario['title']),
                "description": self._format_description_adf(scenario['description']),
                "issuetype": {"id": test_type['id']},
                "customfield_10031": self._map_severity(scenario.get('severity', 'S3 - Moderate')),  # Severity
            }

            # Add priority if required (all projects require it)
            fields["priority"] = self._map_priority(scenario.get('priority', 'P3 - Medium'))

            # Add assignee - use provided assignee_id or default to current user
            if 'assignee_id' in scenario:
                fields['assignee'] = {"accountId": scenario['assignee_id']}
            else:
                # Get current user and assign to them
                try:
                    current_user = self.jira_client.get_current_user()
                    if current_user and 'accountId' in current_user:
                        fields['assignee'] = {"accountId": current_user['accountId']}
                        logger.info(f"Assigned test scenario to current user: {current_user.get('displayName', 'Unknown')}")
                except Exception as e:
                    logger.warning(f"Failed to get current user for assignment: {str(e)}")

            # Add automation status if required by project
            if project_key in ['MBA', 'PLA', 'PU'] or (project_key == 'LFT' and 'automation_status' in scenario):
                fields["customfield_10064"] = {"value": scenario.get('automation_status', 'Manual')}

            # Add journey if required by project
            if project_key in ['MBA', 'PLA', 'LFT', 'PU']:
                journey = scenario.get('journey', 'Account')
                journey_id = self.journey_map.get(journey)
                if not journey_id:
                    logger.warning(f"Journey type '{journey}' not found, using Account journey")
                    journey_id = self.journey_map['Account']
                fields["customfield_10037"] = {"id": journey_id}

            # Create the test case
            response = self.jira_client.create_issue(fields, project_key)
            test_key = response['key']
            logger.info(f"Created test scenario {test_key}")
            print(f"✅ Created test scenario {test_key}")
            
            try:
                # Link to parent story using "Relates" type
                self.jira_client.create_link(test_key, parent_key)
                logger.info(f"Linked {test_key} to {parent_key}")
                print(f"✅ Successfully linked {test_key} to {parent_key}")
            except Exception as e:
                logger.error(f"Failed to link {test_key} to {parent_key}: {str(e)}")

            return {'key': test_key}

        except Exception as e:
            logger.error(f"Failed to create test scenario: {str(e)}")
            raise

    def _map_severity(self, severity):
        """Map severity string to object with valid Jira values"""
        severity_map = {
            "S1": "S1 - Critical",
            "S2": "S2 - Major",
            "S3": "S3 - Moderate",
            "S4": "S4 - Low"
        }
        
        if isinstance(severity, dict):
            if severity.get('value') in severity_map.values():
                return severity
            else:
                return {"value": "S3 - Moderate"}  # Default
                
        # Extract S1/S2/S3/S4 part if full format is provided
        severity_key = severity.split(' ')[0] if ' ' in severity else severity
        
        if severity_key in severity_map:
            return {"value": severity_map[severity_key]}
            
        return {"value": "S3 - Moderate"}  # Default

    def _map_priority(self, priority):
        """Map priority to valid Jira priority values"""
        priority_map = {
            "P0": "P0 - Live Issue",
            "P1": "P1 - Critical", 
            "P2": "P2 - High",
            "P3": "P3 - Medium",
            "P4": "P4 - Low"
        }
        
        if isinstance(priority, dict):
            if priority.get('name') in priority_map.values():
                return priority
            else:
                return {"name": "P3 - Medium"}  # Default
                
        # Extract P0/P1/P2/P3/P4 part if full format is provided
        priority_key = priority.split(' ')[0] if ' ' in priority else priority
        
        if priority_key in priority_map:
            return {"name": priority_map[priority_key]}
            
        return {"name": "P3 - Medium"}  # Default

    def _format_description_adf(self, text):
        """Format text in Atlassian Document Format - using simple format like original code"""
        # Use the simple ADF format that was working in the original code
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

    def update_description(self, issue_key, description):
        """Update the description of a test scenario"""
        try:
            logger.debug(f"Updating description for issue {issue_key}")
            description_adf = convert_to_adf(description)
            self.jira_client.update_issue_description(issue_key, description_adf)
            logger.info(f"Updated description for issue {issue_key}")
            return True
        except Exception as e:
            logger.error(f"Error updating description: {str(e)}", exc_info=True)
            raise

    def _clean_title(self, title):
        """Clean up title by removing newlines and extra whitespace"""
        if not title:
            return ""
        # Replace newlines with spaces and remove extra whitespace
        cleaned = ' '.join(title.replace('\n', ' ').split())
        # Truncate if too long (Jira has a 255 character limit)
        if len(cleaned) > 255:
            cleaned = cleaned[:252] + "..."
        return cleaned