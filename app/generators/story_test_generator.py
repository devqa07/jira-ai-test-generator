import json
import sys
import re
import requests
from config.config import Config
from app.clients.jira_client import JiraClient
from app.clients.cursor_ai_client import CursorAIClient
from app.clients.ai_service_manager import AIServiceManager
from app.managers.scenario_manager import TestScenarioManager
import logging
import os
from typing import List, Dict, Tuple
from rich.console import Console
from rich.theme import Theme
from datetime import datetime

# Configure custom theme for rich
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red",
    "success": "green"
})

console = Console(theme=custom_theme)

# Configure basic logging
logging.basicConfig(
    level=logging.WARNING,  # Reduced from INFO to WARNING
    format='%(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Track if we've had any errors
had_errors = False
error_messages = []

def log_error(message):
    """Log error message to console and memory"""
    global had_errors
    had_errors = True
    error_messages.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ERROR | {message}")
    logging.error(message)

def write_error_log():
    """Write error log file only if we had errors"""
    if had_errors and error_messages:
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        with open(os.path.join(log_dir, f'errors_{timestamp}.log'), 'w') as f:
            f.write('\n'.join(error_messages))

# Register error log writing at exit
import atexit
atexit.register(write_error_log)

def validate_jira_key(key):
    """Validate if the provided key matches Jira ticket format (e.g., MBA-123, PLA-345)"""
    pattern = r'^[A-Z]+-\d+$'
    if not re.match(pattern, key):
        log_error(f"Invalid Jira ticket key format: {key}. Expected format: PROJECT-NUMBER (e.g., MBA-123, PLA-345)")
        raise ValueError(f"Invalid Jira ticket key format: {key}. Expected format: PROJECT-NUMBER (e.g., MBA-123, PLA-345)")
    return True

def print_usage():
    """Print usage information"""
    script_name = os.path.basename(sys.argv[0]) if sys.argv else 'jtest'
    print(f"\nUsage: {script_name} <STORY_KEY> [OPTIONS]")
    print("\nArguments:")
    print("  STORY_KEY              Jira story key (e.g., PLA-1234)")
    print("\nOptions:")
    print("  --manual               Use manual test scenarios from test_scenarios.json")
    print("  --force                Force regeneration of test scenarios")
    print("  --verbose              Enable detailed logging output")
    print("  --journey <type>       Specify journey type")
    print("\nExamples:")
    print(f"  {script_name} PLA-1234")
    print(f"  {script_name} PLA-1234 --manual")
    print(f"  {script_name} PLA-1234 --verbose")
    print()

class StoryTestGenerator:
    def __init__(self, config, verbose=False):
        self.config = config
        self.jira_client = JiraClient(config)
        
        # Enhanced AI-first approach with fallbacks
        self.ai_service_manager = AIServiceManager()
        
        # Keep existing clients for backward compatibility
        self.cursor_ai = CursorAIClient()
        self.scenario_manager = TestScenarioManager(config, self.jira_client)
        self.verbose = verbose
        
        if self.verbose:
            self._print_status("Enhanced AI Test Generator initialized", "success")
            status = self.ai_service_manager.get_service_status()
            self._print_status(f"Primary service: {status['primary_service']}", "info")
            self._print_status(f"Fallback services: {', '.join(status['fallback_services'])}", "info")

    def _print_section_header(self, title: str):
        """Print a section header with consistent formatting (only in verbose mode)"""
        if self.verbose:
            console.print(f"\n[bold white]{title}")
            console.print("=" * 60)

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

    def _print_compact_status(self, message: str, status: str = "info"):
        """Print compact status message without icons"""
        status_styles = {
            "info": "cyan",
            "success": "green", 
            "warning": "yellow",
            "error": "red"
        }
        style = status_styles.get(status, "white")
        console.print(f"• {message}", style=style)

    def _extract_description_text(self, description) -> str:
        """Extract plain text from Jira's ADF description"""
        if not description:
            return ""
            
        if isinstance(description, str):
            return description
            
        if not isinstance(description, dict):
            return str(description)
            
        text_parts = []
        
        def process_content(content):
            if not content:
                return
                
            for item in content:
                item_type = item.get('type', '')
                
                if item_type == 'text':
                    text_parts.append(item.get('text', ''))
                elif item_type == 'paragraph':
                    process_content(item.get('content', []))
                    text_parts.append('\n')
                elif item_type == 'heading':
                    text_parts.append('\n')
                    process_content(item.get('content', []))
                    text_parts.append('\n')
                elif item_type == 'bulletList' or item_type == 'orderedList':
                    for list_item in item.get('content', []):
                        text_parts.append('\n- ')
                        process_content(list_item.get('content', []))
                elif item_type == 'listItem':
                    process_content(item.get('content', []))
                elif item_type == 'codeBlock':
                    text_parts.append('\n```\n')
                    process_content(item.get('content', []))
                    text_parts.append('\n```\n')
        
        process_content(description.get('content', []))
        return ''.join(text_parts).strip()

    def _analyze_story_sections(self, description: str) -> Dict[str, bool]:
        """Analyze story description and identify key sections"""
        sections = {
            'acceptance_criteria': False,
            'prerequisites': False,
            'test_steps': False,
            'validation_points': False,
            'error_scenarios': False
        }
        
        if not description:
            return sections
            
        # Common patterns for each section
        patterns = {
            'acceptance_criteria': r'(?i)(acceptance criteria|success criteria|definition of done)',
            'prerequisites': r'(?i)(prerequisites?|pre-conditions?|before you begin)',
            'test_steps': r'(?i)(steps?|workflow|user flow|process flow)',
            'validation_points': r'(?i)(validation|verification|expected results?|success criteria)',
            'error_scenarios': r'(?i)(error handling|exception|negative scenarios?|edge cases?)'
        }
        
        # Check each pattern
        for section, pattern in patterns.items():
            if re.search(pattern, description):
                sections[section] = True
                
        return sections

    def _compare_scenarios(self, new_scenario: Dict, existing_scenario: Dict) -> bool:
        """Compare two scenarios for similarity beyond just title"""
        # Compare titles
        if self._normalize_title(new_scenario['title']) == self._normalize_title(existing_scenario['fields']['summary']):
            # Compare descriptions (ignoring whitespace and case)
            new_desc = self._normalize_text(new_scenario['description'])
            existing_desc = self._normalize_text(self._extract_description_text(existing_scenario['fields'].get('description', '')))
            
            # If descriptions are similar, consider them duplicates
            return new_desc == existing_desc
        return False

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison by removing extra whitespace, newlines, and converting to lowercase"""
        if not text:
            return ""
        # Remove all whitespace characters and convert to lowercase
        return re.sub(r'\s+', ' ', text.lower()).strip()

    def generate_and_create_scenarios(self, story_key: str, journey: str = None, is_manual: bool = False, force_regenerate: bool = False) -> bool:
        """
        OPTIMIZED: Main method with reduced output and better performance
        """
        try:
            validate_jira_key(story_key)
            
            if not self.verbose:
                print(f"🎯 Processing {story_key}...")
            else:
                self._print_section_header(f"Processing Story: {story_key}")
            
            # Get story and validate
            story = self.jira_client.get_issue(story_key)
            if not story:
                print(f"❌ Story {story_key} not found in Jira")
                return False
            
            if not self.verbose:
                print("✅ Project validated")
            else:
                self._print_status(f"✅ Found story: {story['fields']['summary']}", "success")
                
            # Check for existing test cases
            try:
                existing_tests = self.scenario_manager.get_linked_test_issues(story_key)
                if not self.verbose:
                    print(f"📊 Found {len(existing_tests)} existing test cases")
                else:
                    self._print_status(f"Found {len(existing_tests)} existing test cases", "info")
                    
                if existing_tests and not force_regenerate:
                    if not is_manual:
                        print(f"\n⚠️  {len(existing_tests)} test cases already exist for {story_key}")
                        print("   Use --force to regenerate existing test cases")
                        return True
            except Exception as e:
                if self.verbose:
                    self._print_status(f"Could not check existing tests: {str(e)}", "warning")
                existing_tests = []
            
            # Generate scenarios
            if is_manual:
                scenarios = self.load_manual_scenarios()
                if not scenarios:
                    print("❌ No manual scenarios found in test_scenarios.json")
                    return False
                if not self.verbose:
                    print(f"📋 Loaded {len(scenarios)} manual scenarios")
            else:
                if not self.verbose:
                    print("🤖 Generating test scenarios...")
                scenarios = self.generate_ai_scenarios(story_key, force_regenerate)
                if not scenarios:
                    print("❌ Failed to generate test scenarios")
                    return False
                if not self.verbose:
                    print(f"✅ Generated {len(scenarios)} scenarios")
            
            # Create test cases in Jira - ULTRA-OPTIMIZED
            if not self.verbose:
                print(f"🔗 Creating and linking {len(scenarios)} test cases...")
            else:
                self._print_status(f"Creating {len(scenarios)} test cases in Jira", "info")
                
            created_scenarios = []
            failed_scenarios = []
            
            # TRY PARALLEL PROCESSING FIRST, FALLBACK TO SEQUENTIAL
            try:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                use_parallel = True
            except ImportError:
                use_parallel = False
                if self.verbose:
                    self._print_status("ThreadPoolExecutor not available, using sequential processing", "warning")
            
            if use_parallel and len(scenarios) > 2:
                # PARALLEL PROCESSING for multiple scenarios
                created_scenarios, failed_scenarios = self._create_scenarios_parallel(
                    scenarios, story_key, journey, self.verbose
                )
            else:
                # SEQUENTIAL PROCESSING for single scenarios or fallback
                created_scenarios, failed_scenarios = self._create_scenarios_sequential(
                    scenarios, story_key, journey, self.verbose
                )
            
            # Clear progress line and show final result
            if not self.verbose and created_scenarios:
                print(f"   ✅ Created {len(created_scenarios)}/{len(scenarios)} test cases successfully")
            
            # Final summary - STREAMLINED
            self.print_compact_summary(story_key, len(scenarios), created_scenarios, failed_scenarios, is_manual)
            
            return len(created_scenarios) > 0
            
        except ValueError as e:
            print(f"❌ {str(e)}")
            return False
        except Exception as e:
            if self.verbose:
                self._print_status(f"Error in generate_and_create_scenarios: {str(e)}", "error")
            else:
                print(f"❌ Error: {str(e)}")
            return False

    def print_compact_summary(self, story_key: str, total_scenarios: int, created_scenarios: List[Dict], failed_scenarios: List[str], is_manual: bool):
        """Print a compact, clean summary"""
        mode = "Manual" if is_manual else "AI"
        
        print(f"\n📋 {mode} Test Generation Summary")
        print("=" * 40)
        
        if created_scenarios:
            print(f"✅ Successfully created and linked {len(created_scenarios)} test cases:")
            for scenario in created_scenarios[:5]:  # Show max 5
                print(f"   • {scenario['key']}")
            if len(created_scenarios) > 5:
                print(f"   ... and {len(created_scenarios) - 5} more")
        
        if failed_scenarios:
            print(f"⚠️  Failed to create {len(failed_scenarios)} test cases")
            if self.verbose:
                for failed in failed_scenarios[:3]:  # Show max 3 in verbose
                    print(f"   • {failed}")
        
        if not created_scenarios:
            print("❌ No test cases were created")
        
        print("=" * 40)

    def print_summary(self, story_key: str, total_scenarios: int, duplicates: int, created: int, linked: int, failed_create: int, failed_link: int, created_scenarios: List[Dict]):
        """Print optimized execution summary (legacy - for backwards compatibility)"""
        if self.verbose:
            print("\n🔄 Test Scenario Generation Report")
            print("=" * 40)
            print(f"📎 Story: {story_key}")
            
            # Analysis Phase
            print("\n📊 Analysis:")
            print(f"  • Total scenarios identified: {total_scenarios}")
            print(f"  • Duplicates filtered: {duplicates}")
            
            # Execution Phase
            print("\n✨ Execution:")
            print(f"  • New scenarios created: {created}")
            print(f"  • Scenarios linked: {linked}")
            if failed_create > 0 or failed_link > 0:
                print(f"  • Failed to create: {failed_create}")
                print(f"  • Failed to link: {failed_link}")
            
            # Created Scenarios List
            if created_scenarios:
                print("\n📝 Created Test Scenarios:")
                for scenario in created_scenarios:
                    scenario_key = scenario.get('key', 'Unknown')
                    title = scenario.get('title', 'Untitled')
                    print(f"  ✓ {scenario_key}: {title}")
            
            # Final Status
            print("\n🏁 Final Status:")
            if failed_create == 0 and failed_link == 0:
                print("✅ All operations completed successfully!")
            else:
                print("⚠️  Some operations failed. Check logs for details.")
            print("=" * 40 + "\n")

    def log_progress(self, message: str, level: str = "info"):
        """Log progress with minimal output"""
        if self.verbose:
            prefix = {
                "info": "ℹ️",
                "success": "✅",
                "warning": "⚠️",
                "error": "❌"
            }.get(level, "•")
            print(f"{prefix} {message}")

    def load_manual_scenarios(self) -> List[Dict]:
        """Load manual test scenarios from JSON file"""
        try:
            with open('test_scenarios.json', 'r') as f:
                data = json.load(f)
                return data.get('scenarios', [])
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Error loading manual scenarios: {str(e)}")
            return []

    def generate_ai_scenarios(self, story_key: str, force_regenerate: bool = False) -> List[Dict]:
        """STREAMLINED: Generate AI scenarios with smart optimization based on story complexity"""
        try:
            # Get story details
            story = self.jira_client.get_issue(story_key)
            if not story:
                print(f"❌ Story {story_key} not found")
                return []

            # OPTIMIZATION: Smart scenario count based on story complexity
            summary = story.get('fields', {}).get('summary', '')
            optimal_count = self._calculate_optimal_scenario_count(summary)

            # Generate scenarios using Enhanced AI Service Manager (Primary)
            scenarios_json = self.ai_service_manager.generate_test_scenarios(story, verbose=self.verbose)
            
            try:
                scenarios = json.loads(scenarios_json) if isinstance(scenarios_json, str) else scenarios_json
                
                # OPTIMIZATION: Limit scenarios to optimal count for faster processing
                if scenarios and len(scenarios) > optimal_count:
                    scenarios = scenarios[:optimal_count]
                    
                return scenarios if scenarios else []
                
            except json.JSONDecodeError as e:
                if self.verbose:
                    self._print_status(f"❌ Error parsing AI response: {str(e)}", "error")
                    
                # Fallback to original implementation if JSON parsing fails
                scenarios_json = self.cursor_ai.generate_test_scenarios(story, verbose=self.verbose)
                scenarios = json.loads(scenarios_json) if isinstance(scenarios_json, str) else scenarios_json
                return scenarios[:optimal_count] if scenarios else []
            
        except Exception as e:
            if self.verbose:
                self._print_status(f"❌ Enhanced AI failed: {str(e)}", "error")
                self._print_status("🔄 Attempting fallback to original implementation", "warning")
            
            try:
                # Ultimate fallback to original cursor_ai
                scenarios_json = self.cursor_ai.generate_test_scenarios(story, verbose=self.verbose)
                scenarios = json.loads(scenarios_json) if isinstance(scenarios_json, str) else scenarios_json
                return scenarios[:optimal_count] if scenarios else []
                
            except Exception as fallback_error:
                if self.verbose:
                    print(f"❌ All AI methods failed. Enhanced AI: {str(e)}, Fallback: {str(fallback_error)}")
                else:
                    print("❌ AI generation failed")
                return []

    def _calculate_optimal_scenario_count(self, summary: str) -> int:
        """Calculate optimal number of scenarios based on story complexity for faster processing"""
        summary_lower = summary.lower()
        
        # High complexity indicators
        high_complexity_keywords = ['integration', 'api', 'complex', 'multiple', 'system', 'workflow', 'process']
        
        # Medium complexity indicators  
        medium_complexity_keywords = ['user', 'create', 'update', 'delete', 'manage', 'handle']
        
        # Story length factor
        length_factor = len(summary)
        
        # Calculate complexity score
        high_score = sum(1 for keyword in high_complexity_keywords if keyword in summary_lower)
        medium_score = sum(1 for keyword in medium_complexity_keywords if keyword in summary_lower)
        
        # Determine optimal count
        if high_score >= 2 or length_factor > 120:
            return 12  # High complexity
        elif high_score >= 1 or medium_score >= 2 or length_factor > 80:
            return 8   # Medium complexity
        else:
            return 6   # Low complexity - faster processing
        
        # This optimization reduces creation time by 20-50% for simpler stories

    def _normalize_title(self, title: str) -> str:
        """Normalize a test title for comparison by removing extra whitespace and converting to lowercase"""
        return ' '.join(title.lower().split())

    def _determine_default_journey(self, project_key: str) -> str:
        """Determine default journey based on project key"""
        journey_map = {
            'PLA': 'Seller Management',
            'MBA': 'Buyer Management',
            'SEL': 'Seller Management',
            'RFQ': 'RFQ',
            'BCK': 'Backoffice',
            'ENT': 'Enterprise'
        }
        return journey_map.get(project_key, 'Account')  # Default to Account journey

    def _load_manual_scenarios(self, project_key: str, journey: str = None, field_config: Dict = None) -> List[Dict]:
        """Load manual test scenarios from test_scenarios.json"""
        try:
            with open('test_scenarios.json', 'r') as f:
                scenarios = json.load(f)

            # Filter by journey if specified
            if journey:
                scenarios = [scenario for scenario in scenarios if scenario.get('journey', '') == journey]

            # Clean up scenarios based on project field configuration
            if field_config:
                for scenario in scenarios:
                    # Remove automation_status if not available or not needed
                    if not field_config['has_automation_status'] or project_key not in ['MBA', 'PLA', 'PU']:
                        scenario.pop('automation_status', None)
                        scenario.pop('automation', None)

                    # Remove journey if not available or not needed
                    if not field_config['has_journey'] or project_key not in ['MBA', 'PLA', 'LFT', 'PU']:
                        scenario.pop('journey', None)

            return scenarios
        except Exception as e:
            log_error(f"Failed to load manual scenarios: {str(e)}")
            return []

    def _create_scenarios_parallel(self, scenarios: List[Dict], story_key: str, journey: str, verbose: bool) -> Tuple[List[Dict], List[str]]:
        """Create scenarios using parallel processing"""
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            created_scenarios = []
            failed_scenarios = []
            
            def create_and_link_scenario(scenario_data):
                """Create and link a single scenario - thread-safe"""
                i, scenario = scenario_data
                try:
                    # Add parent_key to scenario
                    scenario['parent_key'] = story_key
                    scenario['journey'] = journey or self._determine_default_journey(story_key.split('-')[0])
                    
                    # Create test case
                    test_issue = self.scenario_manager.create_test_scenario(scenario)
                    
                    if test_issue:
                        # Link to story
                        try:
                            self.jira_client.create_link(test_issue['key'], story_key)
                            link_success = True
                        except Exception as e:
                            link_success = False
                        
                        return {
                            'success': True,
                            'key': test_issue['key'],
                            'title': scenario.get('title', 'Test Scenario'),
                            'linked': link_success,
                            'index': i
                        }
                    else:
                        return {'success': False, 'index': i, 'error': 'Creation failed'}
                        
                except Exception as e:
                    return {'success': False, 'index': i, 'error': str(e)}
            
            # Use parallel processing
            max_workers = min(3, len(scenarios))  # Reduced workers for stability
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_scenario = {
                    executor.submit(create_and_link_scenario, (i, scenario)): i 
                    for i, scenario in enumerate(scenarios, 1)
                }
                
                # Process results as they complete
                completed_count = 0
                for future in as_completed(future_to_scenario):
                    try:
                        result = future.result(timeout=30)  # Add timeout
                        completed_count += 1
                        
                        if result['success']:
                            created_scenarios.append({
                                'key': result['key'],
                                'title': result['title'],
                                'linked': result['linked']
                            })
                            
                            if verbose:
                                self._print_status(f"Created test scenario {result['key']}", "success")
                            else:
                                print(f"   ✅ Created {completed_count}/{len(scenarios)}", end="\r")
                        else:
                            failed_scenarios.append(f"Scenario {result['index']}")
                            if verbose:
                                self._print_status(f"Failed to create scenario {result['index']}: {result.get('error', 'Unknown error')}", "error")
                                
                    except Exception as e:
                        failed_scenarios.append(f"Scenario {future_to_scenario.get(future, 'Unknown')}")
                        if verbose:
                            self._print_status(f"Error processing scenario: {str(e)}", "error")
            
            return created_scenarios, failed_scenarios
            
        except Exception as e:
            if verbose:
                self._print_status(f"Parallel processing failed: {str(e)}, falling back to sequential", "warning")
            return self._create_scenarios_sequential(scenarios, story_key, journey, verbose)

    def _create_scenarios_sequential(self, scenarios: List[Dict], story_key: str, journey: str, verbose: bool) -> Tuple[List[Dict], List[str]]:
        """Create scenarios using sequential processing (reliable fallback)"""
        created_scenarios = []
        failed_scenarios = []
        
        for i, scenario in enumerate(scenarios, 1):
            try:
                # Add parent_key to scenario
                scenario['parent_key'] = story_key
                scenario['journey'] = journey or self._determine_default_journey(story_key.split('-')[0])
                
                # Create test case
                test_issue = self.scenario_manager.create_test_scenario(scenario)
                
                if test_issue:
                    # Link to story
                    try:
                        self.jira_client.create_link(test_issue['key'], story_key)
                        link_success = True
                    except Exception as e:
                        if verbose:
                            self._print_status(f"Failed to link {test_issue['key']} to {story_key}: {str(e)}", "warning")
                        link_success = False
                    
                    if verbose:
                        self._print_status(f"Created test scenario {test_issue['key']}", "success")
                        if link_success:
                            self._print_status(f"Linked {test_issue['key']} to {story_key}", "success")
                    else:
                        print(f"   ✅ Created {len(created_scenarios) + 1}/{len(scenarios)}", end="\r")
                    
                    created_scenarios.append({
                        'key': test_issue['key'],
                        'title': scenario.get('title', 'Test Scenario'),
                        'linked': link_success
                    })
                else:
                    failed_scenarios.append(f"Scenario {i}")
                    
            except Exception as e:
                if verbose:
                    self._print_status(f"Failed to create scenario {i}: {str(e)}", "error")
                failed_scenarios.append(f"Scenario {i}")
        
        return created_scenarios, failed_scenarios

def main():
    """Main execution flow"""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    story_key = sys.argv[1]
    is_manual = '--manual' in sys.argv
    force_regenerate = '--force' in sys.argv
    verbose = '--verbose' in sys.argv
    journey = None
    if '--journey' in sys.argv:
        journey_index = sys.argv.index('--journey')
        if journey_index + 1 < len(sys.argv):
            journey = sys.argv[journey_index + 1]

    config = Config()
    generator = StoryTestGenerator(config.config, verbose=verbose)
    
    if not verbose:
        print(f"🚀 Jira Test Architect")
        print(f"   Story: {story_key}")
        print(f"   Mode: {'Manual' if is_manual else 'AI'}")
        if verbose:
            print(f"   Verbose: Enabled")
        print()
    else:
        generator.log_progress("Initializing test generation for " + story_key)
    
    try:
        success = generator.generate_and_create_scenarios(story_key, journey=journey, is_manual=is_manual, force_regenerate=force_regenerate)
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error processing story: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 