#!/usr/bin/env python3

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from config.config import Config
from app.clients.jira_client import JiraClient
from app.clients.cursor_ai_client import CursorAIClient
from app.managers.scenario_manager import TestScenarioManager
from app.generators.story_test_generator import StoryTestGenerator
from app.generators.manual_test_creator import ManualTestCreator

console = Console()

# Project configuration
PROJECT_CONFIG = {
    'ACCOUNT': {'name': 'Sales Account', 'default_journey': 'Sales Account Management'},
    'MOBILE': {'name': 'Mobile App', 'default_journey': 'Mobile App Management'},
    'ERP': {'name': 'SME', 'default_journey': 'ERP Management'},
    'B2B': {'name': 'B2B Apps', 'default_journey': 'B2B Apps Management'}
}

def setup_logging(log_dir='logs'):
    """Configure logging with proper error handling"""
    try:
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Remove existing handlers
        logger.remove()
        
        # Add console handler with color for INFO and above
        logger.add(
            sys.stderr,
            level="INFO",
            format="<level>{level}</level> | {message}",
            colorize=True
        )
        
        # Add file handler ONLY for errors with rotation
        logger.add(
            os.path.join(log_dir, "errors_{time}.log"),
            level="ERROR",
            rotation="1 day",
            retention="3 days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            delay=True,  # Only create file when first record is emitted
            mode="w"    # Overwrite file instead of appending
        )
        
    except Exception as e:
        print(f"Failed to setup logging: {str(e)}", file=sys.stderr)
        sys.exit(1)

# Call setup_logging at the start
setup_logging()

def validate_story_key(story_key: str) -> tuple[str, str]:
    """
    Validate story key and return project info
    
    Args:
        story_key: Jira story key (e.g., PLA-1234)
        
    Returns:
        tuple: (project_key, journey_type)
        
    Raises:
        ValueError: If story key is invalid
    """
    if not story_key or '-' not in story_key:
        raise ValueError(
            f"Invalid story key format: {story_key}\n"
            "Expected format: PROJECT-NUMBER (e.g., PLA-1234)"
        )
    
    project = story_key.split('-')[0].upper()
    config = Config()
    
    # Check if project is supported
    if project not in config.config['projects']['supported_projects']:
        raise ValueError(
            f"Project {project} is not supported.\n"
            f"Supported projects: {', '.join(config.config['projects']['supported_projects'])}"
        )
    
    # Get project configuration
    if project not in PROJECT_CONFIG:
        logger.warning(f"Project {project} found in supported projects but missing configuration")
        return project, config.config['projects']['default_journey']
    
    return project, PROJECT_CONFIG[project]['default_journey']

def test_jira_connection(cfg):
    """Test JIRA connection with rich UI feedback"""
    console.print("\n[cyan]🔍 Testing JIRA Connection...[/cyan]")
    try:
        jira_client = JiraClient(cfg)
        user_info = jira_client.test_connection()
        if user_info:
            console.print("[green]✅ JIRA connection successful![/green]")
            console.print(f"   User: {user_info.get('displayName', 'Unknown')}")
            console.print(f"   Email: {user_info.get('emailAddress', 'Unknown')}")
            return True
        console.print("[red]❌ JIRA connection failed![/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌ JIRA connection error: {str(e)}[/red]")
        return False

def create_test_scenarios(story_key: str, is_manual: bool = False) -> bool:
    """
    Create test scenarios for a Jira story
    
    Args:
        story_key: Jira story key (e.g., PLA-1234)
        is_manual: Whether to use manual test scenarios from test_scenarios.json
        
    Returns:
        bool: Success status
    """
    console.print(f"\n[cyan]🎯 Processing {story_key}...[/cyan]")
    try:
        # Validate story key and get project info
        project_key, journey_type = validate_story_key(story_key)
        console.print(f"[green]✅ Project {project_key} validated[/green]")
        
        # Initialize configuration
        config = Config()
        
        # Test connection first
        if not test_jira_connection(config.config):
            console.print("[red]❌ Cannot proceed without JIRA connection[/red]")
            return False
        
        # Initialize Jira client
        jira_client = JiraClient(config.config)
        
        if is_manual:
            # Manual approach using test_scenarios.json
            creator = ManualTestCreator(config.config, jira_client)
            
            # Check if test_scenarios.json exists
            if not os.path.exists('test_scenarios.json'):
                console.print("\n[red]Error: test_scenarios.json not found[/red]")
                console.print("Please create test_scenarios.json with your test scenarios")
                console.print("\nExample format:")
                console.print('''{
    "title": "Test Scenario Title",
    "description": "Test steps and expected results",
    "severity": "S3 - Moderate",
    "automation": "Manual",
    "journey": "Account"
}''')
                return False
                
            success = creator.create_manual_test_scenarios(story_key)
            
        else:
            # AI-powered approach
            generator = StoryTestGenerator(config.config)
            success = generator.generate_and_create_scenarios(
                story_key,
                journey=journey_type,
                is_manual=False
            )
        
        return success
        
    except Exception as e:
        logger.error(str(e))
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        return False

def print_usage():
    """Print usage instructions with rich UI"""
    console.print(Panel.fit(
        "[bold cyan]JIRA AI Test Architect[/bold cyan]\nGenerate comprehensive test scenarios from JIRA stories",
        title="Usage",
        border_style="cyan"
    ))
    console.print("\n[bold]Commands:[/bold]")
    console.print("  python scripts/jira-test.py TICKET-KEY [OPTIONS]")
    console.print("\n[bold]Options:[/bold]")
    console.print("  --manual               Use manual test scenarios from test_scenarios.json")
    console.print("  --journey JOURNEY      Specify journey type (e.g., buyer, seller, account)")
    console.print("  --force                Force regenerate test scenarios")
    console.print("  --test-connection      Test JIRA connection only")
    console.print("\n[bold]Examples:[/bold]")
    console.print("  python scripts/jira-test.py MBA-1234              # Generate AI test scenarios")
    console.print("  python scripts/jira-test.py MBA-1234 --manual    # Use manual test scenarios")
    console.print("  python scripts/jira-test.py PLA-345 --journey buyer")
    console.print("  python scripts/jira-test.py MBA-1234 --force     # Force regenerate test scenarios")
    console.print("  python scripts/jira-test.py --test-connection    # Test JIRA connection only")
    console.print("\n[bold]Note:[/bold] The ticket key must be in the format PROJECT-NUMBER")

def main():
    """Main execution flow with enhanced features"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    # Handle test-connection flag
    if '--test-connection' in sys.argv:
        config = Config()
        ok = test_jira_connection(config.config)
        sys.exit(0 if ok else 1)

    story_key = sys.argv[1]
    is_manual = '--manual' in sys.argv
    force_regenerate = '--force' in sys.argv
    journey = None
    
    # Parse journey argument
    for i, arg in enumerate(sys.argv):
        if arg == '--journey' and i + 1 < len(sys.argv):
            journey = sys.argv[i + 1]
            break

    # Use the enhanced create_test_scenarios function for better UX
    if is_manual:
        success = create_test_scenarios(story_key, is_manual=True)
        sys.exit(0 if success else 1)
    
    # For AI-powered generation, use the original flow
    config = Config()
    generator = StoryTestGenerator(config.config)
    generator.log_progress("Initializing test generation for " + story_key)
    
    try:
        success = generator.generate_and_create_scenarios(story_key, journey=journey, is_manual=is_manual, force_regenerate=force_regenerate)
        if not success:
            sys.exit(1)
    except Exception as e:
        generator.log_progress(f"Error processing story: {str(e)}", "error")
        sys.exit(1)

if __name__ == "__main__":
    main() 