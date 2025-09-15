from loguru import logger
import json
from typing import Dict, Any, Optional, List
from functools import lru_cache
from datetime import datetime, timedelta

class ResponseFormatter:
    def __init__(self):
        self.field_cache = {}
        self.cache_expiry = {}
        self.cache_duration = timedelta(minutes=30)

    @staticmethod
    def format_description(text: str) -> Dict[str, Any]:
        """Format text in Atlassian Document Format with support for rich text"""
        if isinstance(text, dict):
            return text  # Already in ADF format
            
        # Split text into paragraphs
        paragraphs = text.split('\n\n')
        content = []
        
        for para in paragraphs:
            if not para.strip():
                continue
                
            # Check for headings
            if para.startswith('#'):
                level = len(para.split()[0])  # Count # symbols
                content.append({
                    "type": "heading",
                    "attrs": {"level": min(level, 6)},
                    "content": [{
                        "type": "text",
                        "text": para.lstrip('#').strip()
                    }]
                })
            # Check for bullet points
            elif para.strip().startswith('- '):
                items = []
                for line in para.split('\n'):
                    if line.strip().startswith('- '):
                        items.append({
                            "type": "listItem",
                            "content": [{
                                "type": "paragraph",
                                "content": [{
                                    "type": "text",
                                    "text": line.strip('- ').strip()
                                }]
                            }]
                        })
                content.append({
                    "type": "bulletList",
                    "content": items
                })
            # Regular paragraph
            else:
                content.append({
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": para
                    }]
                })

        return {
            "type": "doc",
            "version": 1,
            "content": content
        }

    @staticmethod
    def extract_description_text(description: Dict[str, Any]) -> str:
        """Extract plain text from Atlassian Document Format with support for rich text"""
        if not isinstance(description, dict):
            return str(description)

        text_content = []
        try:
            def process_content(content_list):
                text = []
                for item in content_list:
                    if item.get('type') == 'text':
                        text.append(item.get('text', ''))
                    elif item.get('type') == 'heading':
                        text.append('\n' + '#' * item.get('attrs', {}).get('level', 1) + ' ')
                        text.extend(process_content(item.get('content', [])))
                        text.append('\n')
                    elif item.get('type') == 'bulletList':
                        for list_item in item.get('content', []):
                            text.append('\n- ')
                            text.extend(process_content(list_item.get('content', [])))
                    elif item.get('type') == 'paragraph':
                        text.extend(process_content(item.get('content', [])))
                        text.append('\n')
                return text

            text_content = process_content(description.get('content', []))
            
        except Exception as e:
            logger.warning(f"Error extracting description text: {str(e)}")
            return str(description)

        return ''.join(text_content).strip()

    @lru_cache(maxsize=100)
    def format_issue_data(self, issue_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format issue data for display/output with caching"""
        fields = issue_data.get('fields', {})
        
        # Format dates
        created = fields.get('created')
        updated = fields.get('updated')
        if created:
            created = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%Y-%m-%d %H:%M:%S")
        if updated:
            updated = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%f%z").strftime("%Y-%m-%d %H:%M:%S")
            
        return {
            "issue_key": issue_data.get('key'),
            "project": fields.get('project', {}).get('key'),
            "summary": fields.get('summary'),
            "status": fields.get('status', {}).get('name'),
            "type": fields.get('issuetype', {}).get('name'),
            "priority": fields.get('priority', {}).get('name'),
            "severity": fields.get('customfield_10062', {}).get('value'),  # Severity field
            "assignee": fields.get('assignee', {}).get('displayName'),
            "reporter": fields.get('reporter', {}).get('displayName'),
            "description": self.extract_description_text(fields.get('description', {})),
            "created": created,
            "updated": updated,
            "labels": fields.get('labels', []),
            "components": [comp.get('name') for comp in fields.get('components', [])],
            "epic_link": fields.get('customfield_10014'),  # Epic Link field
            "sprint": self._extract_sprint_info(fields.get('customfield_10020', [])),  # Sprint field
            "story_points": fields.get('customfield_10026'),  # Story Points field
            "environment": fields.get('environment'),
            "fix_versions": [ver.get('name') for ver in fields.get('fixVersions', [])]
        }

    def _extract_sprint_info(self, sprint_field: List[Any]) -> Optional[Dict[str, Any]]:
        """Extract sprint information from the sprint field"""
        if not sprint_field:
            return None
            
        try:
            # Get the most recent sprint
            latest_sprint = sprint_field[-1]
            if isinstance(latest_sprint, str):
                # Parse the sprint string format
                sprint_data = {}
                for item in latest_sprint.strip('[]').split(','):
                    if '=' in item:
                        key, value = item.split('=', 1)
                        sprint_data[key.strip()] = value.strip()
                return {
                    'name': sprint_data.get('name'),
                    'state': sprint_data.get('state'),
                    'start_date': sprint_data.get('startDate'),
                    'end_date': sprint_data.get('endDate')
                }
            return latest_sprint
        except Exception as e:
            logger.warning(f"Error extracting sprint info: {str(e)}")
            return None

    def format_test_scenario_fields(self, project_key: str, test_data: Dict[str, Any], 
                                  test_type_id: str, journey_info: Dict[str, Any], 
                                  user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Format fields for test scenario creation with validation"""
        # Validate required fields
        if not all([project_key, test_data, test_type_id, journey_info, user_info]):
            raise ValueError("Missing required fields for test scenario creation")
            
        # Get cached field values or format new ones
        cache_key = f"{project_key}_{test_type_id}"
        if cache_key in self.field_cache:
            if datetime.now() - self.cache_expiry[cache_key] < self.cache_duration:
                return self.field_cache[cache_key]
                
        formatted_fields = {
            'project': {'key': project_key},
            'issuetype': {'id': test_type_id},
            'summary': test_data['title'],
            'description': self.format_description(test_data['description']),
            'assignee': {'id': user_info['accountId']},
            'customfield_10064': {'value': test_data.get('automation', 'Manual')},  # Automation Status
            'customfield_10037': {'id': journey_info['id']},  # Journey field
            'customfield_10062': {'value': test_data.get('severity', 'S3 - Moderate')},  # Severity
            'priority': {'name': test_data.get('priority', 'P3 - Medium')},  # Priority
            'labels': test_data.get('labels', ['automated-test']),
            'components': [{'name': comp} for comp in test_data.get('components', [])],
        }
        
        # Cache the formatted fields
        self.field_cache[cache_key] = formatted_fields
        self.cache_expiry[cache_key] = datetime.now()
        
        return formatted_fields 