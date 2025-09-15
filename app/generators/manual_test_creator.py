import json
import sys
import os
import time
from config.config import Config
from app.clients.jira_client import JiraClient
from app.managers.scenario_manager import TestScenarioManager
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

# Logging is configured in jtest
# Just add console handler for this module
logger.add(
    sys.stderr,
    level="INFO",
    format="<level>{level}</level> | {message}",
    colorize=True,
    filter=lambda record: record["extra"].get("name") == __name__
)

class ManualTestCreator:
    def __init__(self, config: Dict, jira_client: JiraClient = None):
        """
        Initialize ManualTestCreator
        
        Args:
            config: Configuration dictionary
            jira_client: Optional existing JiraClient instance
        """
        self.config = config
        self.jira_client = jira_client if jira_client else JiraClient(config)
        self.test_scenario_manager = TestScenarioManager(config, self.jira_client)

    def validate_scenario(self, scenario: Dict) -> bool:
        """
        Validate a test scenario
        
        Args:
            scenario: Test scenario dictionary
            
        Returns:
            bool: True if valid, False otherwise
        """
        required_fields = ['title', 'description']
        for field in required_fields:
            if field not in scenario:
                logger.error(f"Missing required field: {field}")
                return False
                
        # Validate severity if present
        if 'severity' in scenario:
            valid_severities = [
                'S1',
                'S2',
                'S3',
                'S4'
            ]
            severity = scenario['severity'].split(' ')[0] if ' ' in scenario['severity'] else scenario['severity']
            if severity not in valid_severities:
                logger.error(f"Invalid severity: {scenario['severity']}")
                logger.error(f"Must be one of: S1, S2, S3, S4")
                return False

        # Validate priority if present
        if 'priority' in scenario:
            valid_priorities = [
                'P0',
                'P1',
                'P2',
                'P3',
                'P4'
            ]
            priority = scenario['priority'].split(' ')[0] if ' ' in scenario['priority'] else scenario['priority']
            if priority not in valid_priorities:
                logger.error(f"Invalid priority: {scenario['priority']}")
                logger.error(f"Must be one of: P0, P1, P2, P3, P4")
                return False
                
        # Validate automation status if present
        if 'automation' in scenario:
            valid_statuses = ['Manual', 'Automated', 'Not Applicable']
            if scenario['automation'] not in valid_statuses:
                logger.error(f"Invalid automation status: {scenario['automation']}")
                logger.error(f"Must be one of: {', '.join(valid_statuses)}")
                return False
                
        return True
        
    def load_scenarios(self) -> Optional[List[Dict]]:
        """
        Load test scenarios from test_scenarios.json
        
        Returns:
            List[Dict]: List of test scenarios or None if error
        """
        try:
            with open('test_scenarios.json', 'r') as f:
                scenarios = json.load(f)
                
            # Handle both single scenario and list of scenarios
            if isinstance(scenarios, dict):
                scenarios = [scenarios]
                
            # Validate each scenario
            valid_scenarios = []
            for scenario in scenarios:
                if self.validate_scenario(scenario):
                    valid_scenarios.append(scenario)
                else:
                    logger.error(f"Invalid scenario: {scenario}")
                    
            return valid_scenarios if valid_scenarios else None
            
        except FileNotFoundError:
            logger.error("test_scenarios.json not found")
            return None
        except json.JSONDecodeError:
            logger.error("Invalid JSON in test_scenarios.json")
            return None
        except Exception as e:
            logger.error(f"Error loading scenarios: {str(e)}")
            return None
            
    def create_manual_test_scenarios(self, story_key: str) -> bool:
        """
        Create test scenarios from test_scenarios.json
        
        Args:
            story_key: Jira story key
            
        Returns:
            bool: Success status
        """
        try:
            # Load scenarios
            scenarios = self.load_scenarios()
            if not scenarios:
                return False

            # Get current user info
            user_info = self.jira_client.get_current_user()
            if not user_info:
                raise Exception("Failed to get current user info")
                
            # Create test cases
            success = True
            for scenario in scenarios:
                try:
                    # Add story key and assignee to scenario
                    scenario['parent_key'] = story_key
                    scenario['assignee_id'] = user_info['accountId']
                    
                    # Create test case using scenario manager
                    issue_key = self.test_scenario_manager.create_test_scenario(scenario)
                    if not issue_key:
                        logger.error(f"Failed to create test case: {scenario['title']}")
                        success = False
                    else:
                        logger.info(f"Created test case: {scenario['title']} with key {issue_key}")
                        
                except Exception as e:
                    logger.error(f"Error creating test case: {str(e)}")
                    success = False
                    
            return success
            
        except Exception as e:
            logger.error(f"Error in create_manual_test_scenarios: {str(e)}")
            return False

    def _create_single_scenario(self, scenario, story_key, assignee_id):
        """Create a single test scenario"""
        try:
            scenario['parent_key'] = story_key
            scenario['assignee_id'] = assignee_id
            
            issue_key = self.test_scenario_manager.create_test_scenario(scenario)
            if issue_key:
                return {
                    'key': issue_key,
                    'title': scenario['title']
                }
            return None
        except Exception as e:
            logger.error(f"Failed to create scenario '{scenario['title']}': {str(e)}")
            raise

    def _print_summary(self, story_key, scenarios, created_scenarios, failed_scenarios):
        """Print creation summary"""
        print("\n=== Creation Summary ===")
        print(f"Story: {story_key}")
        print(f"Total scenarios: {len(scenarios)}")
        print(f"Successfully created: {len(created_scenarios)}")
        print(f"Failed to create: {len(failed_scenarios)}")
        
        if created_scenarios:
            print("\nCreated Test Scenarios:")
            for scenario in created_scenarios:
                print(f"  - {scenario['key']}: {scenario['title']}")
        
        if failed_scenarios:
            print("\nFailed Scenarios:")
            for scenario in failed_scenarios:
                print(f"  - {scenario['title']}: {scenario['error']}")

def main():
    if len(sys.argv) <= 1:
        print("Usage: python manual_test_creator.py <STORY-KEY>")
        print("Example: python manual_test_creator.py PLA-6346")
        sys.exit(1)
        
    creator = ManualTestCreator(config)
    success = creator.create_manual_test_scenarios(sys.argv[1].upper())
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()