"""
AI Service Manager - Enhanced AI-First Approach with Robust Fallback
Coordinates between Enhanced AI, your current implementation, and manual fallback
"""
import json
import time
from typing import Dict, List, Any, Optional
from loguru import logger
from enum import Enum

from app.clients.cursor_ai_client import CursorAIClient
from app.clients.enhanced_ai_client import EnhancedAIClient
from app.generators.manual_test_creator import ManualTestCreator
from config.config import get_ai_config

class AIMode(Enum):
    LOCAL = "local"
    ENHANCED = "enhanced"
    HUGGINGFACE = "huggingface" 
    GROQ = "groq"
    AUTO = "auto"
    FALLBACK = "fallback"

class AIServiceManager:
    """
    Enhanced AI Service Manager with three-tier approach:
    1. Enhanced AI (Primary) - Free LLMs with ChatGPT-level prompting
    2. Current Implementation (Fallback) - Your existing CursorAIClient
    3. Manual Templates (Ultimate Fallback) - Always reliable
    """
    
    def __init__(self):
        self.config = get_ai_config()
        self.mode = AIMode(self.config.get('mode', 'local'))
        self.enable_fallback = self.config.get('enable_fallback', True)
        
        # Initialize AI services in order of preference
        self.enhanced_ai = EnhancedAIClient()  # Primary: Enhanced AI with free LLMs
        self.cursor_ai = CursorAIClient()       # Fallback: Your current implementation
        
        # For ManualTestCreator, we need a config object
        try:
            from config.config import Config
            config_obj = Config()
            self.manual_creator = ManualTestCreator(config_obj.config)  # Ultimate fallback: Manual templates
        except Exception as e:
            logger.warning(f"Failed to initialize ManualTestCreator: {str(e)}")
            self.manual_creator = None
        
        # Rate limiting for free services
        self.request_counts = {}
        self.last_reset = time.time()
        
        # Service health tracking
        self.service_health = {
            'enhanced_ai': True,
            'local': True,
            'huggingface': True,
            'manual': True
        }
        
        logger.info(f"AI Service Manager initialized - Enhanced AI Primary with fallbacks")

    def generate_test_scenarios(self, story: Dict, verbose: bool = False) -> str:
        """
        STREAMLINED: Generate test scenarios with minimal logging - just results
        """
        try:
            # Try Enhanced AI first (Primary) - SILENT
            enhanced_result = self.enhanced_ai.generate_comprehensive_test_scenarios(story, verbose)
            
            if enhanced_result:
                try:
                    scenarios = json.loads(enhanced_result) if isinstance(enhanced_result, str) else enhanced_result
                    if scenarios and len(scenarios) >= 3:
                        return enhanced_result
                except json.JSONDecodeError:
                    pass  # Silent failure, try fallback
            
            # Fallback to existing implementation - SILENT
            fallback_result = self.cursor_ai.generate_test_scenarios(story, verbose)
            
            if fallback_result:
                try:
                    scenarios = json.loads(fallback_result) if isinstance(fallback_result, str) else fallback_result
                    return fallback_result
                except json.JSONDecodeError:
                    pass  # Silent failure
            
            # Ultimate fallback - basic scenarios
            return self._generate_basic_scenarios(story)
            
        except Exception as e:
            if verbose:
                logger.error(f"AI Service Manager error: {str(e)}")
            # Return basic fallback even on errors
            return self._generate_basic_scenarios(story)

    def _try_enhanced_ai(self, story: Dict, verbose: bool = False) -> List[Dict]:
        """Try the Enhanced AI service (Primary method with free LLMs)"""
        try:
            logger.info("🚀 Using Enhanced AI Service with Free LLMs (ChatGPT-level)")
            result = self.enhanced_ai.generate_comprehensive_test_scenarios(story, verbose)
            
            if isinstance(result, str):
                scenarios = json.loads(result)
            else:
                scenarios = result
                
            if scenarios and len(scenarios) > 0:
                logger.success(f"✅ Enhanced AI generated {len(scenarios)} scenarios")
                self.service_health['enhanced_ai'] = True
                return scenarios
            else:
                logger.warning("⚠️ Enhanced AI returned empty results")
                self.service_health['enhanced_ai'] = False
                return []
                
        except Exception as e:
            logger.error(f"❌ Enhanced AI failed: {str(e)}")
            self.service_health['enhanced_ai'] = False
            return []

    def _try_local_ai(self, story: Dict, verbose: bool = False) -> List[Dict]:
        """Try your current CursorAIClient implementation"""
        try:
            logger.info("🔄 Using Current Implementation (CursorAIClient)")
            result = self.cursor_ai.generate_test_scenarios(story, verbose)
            
            if isinstance(result, str):
                scenarios = json.loads(result)
            else:
                scenarios = result
                
            if scenarios and len(scenarios) > 0:
                logger.success(f"✅ Current implementation generated {len(scenarios)} scenarios")
                self.service_health['local'] = True
                return scenarios
            else:
                logger.warning("⚠️ Current implementation returned empty results")
                self.service_health['local'] = False
                return []
                
        except Exception as e:
            logger.error(f"❌ Current implementation failed: {str(e)}")
            self.service_health['local'] = False
            return []

    def _try_manual_fallback(self, story: Dict, verbose: bool = False) -> str:
        """Ultimate fallback to manual template system"""
        try:
            if self.manual_creator is None:
                logger.warning("Manual creator not available, generating minimal scenarios")
                return self._generate_minimal_scenarios(story)
                
            logger.info("🔧 Using Manual Template Fallback")
            result = self.manual_creator.create_test_scenarios(story)
            
            if result:
                logger.success("✅ Manual templates generated scenarios")
                self.service_health['manual'] = True
                return result
            else:
                # Generate minimal default scenarios as absolute last resort
                return self._generate_minimal_scenarios(story)
                
        except Exception as e:
            logger.error(f"❌ Manual fallback failed: {str(e)}")
            return self._generate_minimal_scenarios(story)

    def _filter_unique_scenarios(self, new_scenarios: List[Dict], existing_scenarios: List[Dict]) -> List[Dict]:
        """Filter out scenarios that are too similar to existing ones"""
        unique_scenarios = []
        existing_titles = [s.get('title', '').lower() for s in existing_scenarios]
        
        for scenario in new_scenarios:
            title = scenario.get('title', '').lower()
            
            # Check if this scenario is significantly different
            is_unique = True
            for existing_title in existing_titles:
                similarity = self._calculate_title_similarity(title, existing_title)
                if similarity > 0.7:  # 70% similarity threshold
                    is_unique = False
                    break
            
            if is_unique:
                unique_scenarios.append(scenario)
                existing_titles.append(title)
        
        return unique_scenarios

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two scenario titles"""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        
        if not words1 or not words2:
            return 0.0
            
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0

    def _ensure_scenario_limits(self, scenarios: List[Dict], story: Dict) -> List[Dict]:
        """Ensure we have minimum scenarios and don't exceed maximum"""
        min_scenarios = self.config.get('min_scenarios', 3)
        max_scenarios = self.config.get('max_scenarios', 10)
        
        # If still below minimum, add basic template scenarios
        while len(scenarios) < min_scenarios:
            basic_scenario = self._generate_basic_scenario(story, len(scenarios) + 1)
            scenarios.append(basic_scenario)
            
        # Limit to maximum
        if len(scenarios) > max_scenarios:
            # Keep the most important scenarios (sort by priority/severity)
            scenarios = self._prioritize_scenarios(scenarios)[:max_scenarios]
            
        return scenarios

    def _generate_basic_scenario(self, story: Dict, index: int) -> Dict:
        """Generate a basic scenario when needed to meet minimum requirements"""
        title = story.get('fields', {}).get('summary', 'Test Story')
        
        scenario_types = [
            {
                'title': f"Verify {title} - Functional Test {index}",
                'description': f"Test core functionality of {title}",
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            },
            {
                'title': f"Verify {title} - Error Handling {index}",
                'description': f"Test error handling for {title}",
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            },
            {
                'title': f"Verify {title} - Boundary Test {index}",
                'description': f"Test boundary conditions for {title}",
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            }
        ]
        
        scenario_template = scenario_types[(index - 1) % len(scenario_types)]
        
        return {
            **scenario_template,
            'steps': [
                '1. Set up test environment',
                '2. Execute test steps',
                '3. Verify expected results',
                '4. Clean up test data'
            ],
            'automation': 'Manual'
        }

    def _generate_minimal_scenarios(self, story: Dict) -> str:
        """Generate absolute minimal scenarios as last resort"""
        title = story.get('fields', {}).get('summary', 'Test Story')
        
        minimal_scenarios = [{
            "title": f"Basic Test - {title}",
            "description": f"Basic functional test for {title}",
            "steps": [
                "1. Review requirements",
                "2. Execute test steps",
                "3. Verify results"
            ],
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium", 
            "automation": "Manual"
        }]
        
        logger.warning("Generated minimal fallback scenario")
        return json.dumps(minimal_scenarios, indent=2)

    def _prioritize_scenarios(self, scenarios: List[Dict]) -> List[Dict]:
        """Sort scenarios by priority and severity to keep the most important ones"""
        priority_order = {'P1 - Critical': 1, 'P2 - High': 2, 'P3 - Medium': 3, 'P4 - Low': 4}
        severity_order = {'S1 - Critical': 1, 'S2 - Major': 2, 'S3 - Moderate': 3, 'S4 - Low': 4}
        
        def scenario_score(scenario):
            priority = priority_order.get(scenario.get('priority', 'P3 - Medium'), 3)
            severity = severity_order.get(scenario.get('severity', 'S3 - Moderate'), 3)
            return priority + severity  # Lower score = higher priority
            
        return sorted(scenarios, key=scenario_score)

    def get_service_status(self) -> Dict[str, Any]:
        """Get status of all AI services"""
        return {
            'current_mode': self.mode.value,
            'fallback_enabled': self.enable_fallback,
            'service_health': self.service_health.copy(),
            'request_counts': self.request_counts.copy(),
            'primary_service': 'Enhanced AI (Free LLMs)',
            'fallback_services': ['Current Implementation', 'Manual Templates'],
            'config': {
                'min_scenarios': self.config.get('min_scenarios', 3),
                'max_scenarios': self.config.get('max_scenarios', 10),
                'free_tier_only': self.config.get('free_tier_only', True)
            }
        }

    def set_mode(self, mode: str) -> bool:
        """Change AI mode dynamically"""
        try:
            self.mode = AIMode(mode.lower())
            logger.info(f"AI mode changed to: {self.mode.value}")
            return True
        except ValueError:
            logger.error(f"Invalid AI mode: {mode}")
            return False 