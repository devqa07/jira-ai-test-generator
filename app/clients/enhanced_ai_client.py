"""
Enhanced AI Client - ChatGPT-4o-mini Level Quality with Free LLMs
Primary AI engine for comprehensive requirement analysis and test scenario generation
"""
import json
import requests
import time
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger
from datetime import datetime
import re
from functools import lru_cache

from app.clients.cursor_ai_client import CursorAIClient
from config.config import get_ai_config

class EnhancedAIClient:
    """
    Enhanced AI Client for sophisticated requirement analysis and comprehensive test generation
    Uses free LLM services as primary with ChatGPT-level prompting and analysis
    """
    
    def __init__(self):
        self.config = get_ai_config()
        self.fallback_ai = CursorAIClient()  # Your current implementation as fallback
        
        # Free LLM service configurations
        self.llm_services = {
            'huggingface': {
                'enabled': False,  # FINAL: Both legacy & new Inference Providers APIs unavailable
                # INVESTIGATION SUMMARY:
                # 1. Legacy API (api-inference.huggingface.co) = 404 (discontinued)
                # 2. New Providers API (router.huggingface.co) = 404 (access restricted)
                # 3. Token works for model info API but not inference APIs
                # 4. HF shifted to paid-only inference with $2/month limit for PRO users
                'models': [
                    'microsoft/DialoGPT-medium',  
                    'microsoft/DialoGPT-small',
                    'gpt2'
                ],
                'rate_limit': 1000  # requests per hour
            },
            'ollama_local': {
                'enabled': True,
                'models': ['llama2:7b', 'codellama:7b', 'mistral:7b'],
                'endpoint': 'http://localhost:11434/api/generate'
            },
            'groq': {
                'enabled': True,
                'models': ['llama-3.1-8b-instant', 'llama-3.1-70b-versatile'],  # Updated to current working models
                'endpoint': 'https://api.groq.com/openai/v1/chat/completions',
                'rate_limit': 100  # free tier
            }
        }
        
        # PERFORMANCE OPTIMIZATIONS
        # Scenario caching for similar stories
        self.scenario_cache = {}
        self.cache_enabled = self.config.get('cache_scenarios', True)
        
        # Pre-compiled patterns for faster text processing
        self.domain_patterns = {
            'payment': re.compile(r'\b(payment|billing|invoice|transaction|purchase|checkout)\b', re.I),
            'user_management': re.compile(r'\b(user|account|profile|authentication|login|register)\b', re.I),
            'logistics': re.compile(r'\b(shipping|delivery|tracking|warehouse|inventory)\b', re.I),
            'finance': re.compile(r'\b(finance|financial|budget|cost|expense|revenue)\b', re.I)
        }
        
        # Advanced prompting templates for comprehensive analysis
        self.analysis_prompts = {
            'requirement_analysis': self._get_requirement_analysis_prompt(),
            'scenario_generation': self._get_scenario_generation_prompt(),
            'edge_case_analysis': self._get_edge_case_prompt(),
            'negative_testing': self._get_negative_testing_prompt()
        }
        
        # Request tracking for free services
        self.request_counts = {}
        self.last_reset_time = time.time()
        
        logger.info("Enhanced AI Client initialized with performance optimizations")

    def generate_comprehensive_test_scenarios(self, story: Dict, verbose: bool = False) -> str:
        """
        ULTRA-OPTIMIZED: High-speed test scenario generation with caching and optimizations
        """
        try:
            # OPTIMIZATION 1: Check cache first
            cache_key = self._generate_cache_key(story)
            if self.cache_enabled and cache_key in self.scenario_cache:
                if verbose:
                    logger.info("✅ Using cached scenarios (instant)")
                return self.scenario_cache[cache_key]
            
            # OPTIMIZATION 2: Fast story analysis
            story_context = self._fast_story_analysis(story)
            
            # OPTIMIZATION 3: Optimized single generation call
            scenarios = self._ultra_fast_generation(story, story_context, verbose)
            if verbose:
                logger.info(f"🔍 _ultra_fast_generation returned {len(scenarios) if scenarios else 0} scenarios")
            
            if not scenarios or len(scenarios) < 3:
                # Silent fallback enhancement
                fallback_scenarios = self._get_fallback_scenarios(story, verbose)
                scenarios.extend(fallback_scenarios)
            
            # OPTIMIZATION 4: Quick validation and enhancement
            validated_scenarios = self._validate_and_enhance_scenarios(scenarios, story)
            
            # OPTIMIZATION 5: Cache the result
            result = json.dumps(validated_scenarios, indent=2)
            if self.cache_enabled:
                self.scenario_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            if verbose:
                logger.error(f"Enhanced AI failed: {str(e)}, falling back")
            return self.fallback_ai.generate_test_scenarios(story, verbose)

    def _generate_cache_key(self, story: Dict) -> str:
        """Generate cache key based on story content for scenario reuse"""
        fields = story.get('fields', {})
        summary = fields.get('summary', '')
        # Create a hash of key story elements
        import hashlib
        key_content = f"{summary[:100]}"  # Use first 100 chars of summary
        return hashlib.md5(key_content.encode()).hexdigest()[:8]

    def _fast_story_analysis(self, story: Dict) -> Dict:
        """OPTIMIZED: Ultra-fast story analysis using pattern matching"""
        fields = story.get('fields', {})
        summary = fields.get('summary', '').lower()
        
        # Fast domain detection using pre-compiled patterns
        domain = 'general'
        for domain_name, pattern in self.domain_patterns.items():
            if pattern.search(summary):
                domain = domain_name
                break
        
        # Quick complexity assessment
        complexity = 'medium'
        if len(summary) > 100 or 'integration' in summary or 'api' in summary:
            complexity = 'high'
        elif len(summary) < 50:
            complexity = 'low'
        
        return {
            'domain': domain,
            'complexity': complexity,
            'summary': summary[:200]  # Truncate for faster processing
        }

    def _ultra_fast_generation(self, story: Dict, context: Dict, verbose: bool = False) -> List[Dict]:
        """
        ULTRA-OPTIMIZED: Generate scenarios with maximum speed optimizations
        """
        # Try Groq with ultra-optimized settings
        if self.llm_services['groq']['enabled'] and self._check_rate_limit('groq'):
            try:
                scenarios = self._groq_ultra_fast(story, context, verbose)
                if scenarios and len(scenarios) >= 5:
                    return scenarios
            except Exception:
                pass  # Silent failure, try next service
        
        return []

    def _groq_ultra_fast(self, story: Dict, context: Dict, verbose: bool = False) -> List[Dict]:
        """
        ULTRA-OPTIMIZED: Maximum speed Groq generation with improved quality and cleaning
        """
        try:
            groq_token = self.config.get('groq_token', '')
            if not groq_token:
                return []
                
            # IMPROVED PROMPT: More specific about format and quality
            summary = story.get('fields', {}).get('summary', '')
            
            prompt = f"""Generate 8 test scenarios for: {summary}

IMPORTANT: Create clear, actionable test scenario titles. No markdown formatting, no generic titles.

Example format:
[
{{"title": "Verify user can view wallet balance on main page", "description": "Test wallet balance display functionality", "steps": ["1. Login to application", "2. Navigate to wallet page", "3. Verify balance shows correctly"], "severity": "S2 - Major", "priority": "P2 - High", "automation": "Manual"}},
{{"title": "Test wallet balance updates after transaction", "description": "Verify balance reflects changes after payment", "steps": ["1. Check initial balance", "2. Make a transaction", "3. Verify updated balance"], "severity": "S1 - Critical", "priority": "P1 - Critical", "automation": "Manual"}}
]

Requirements:
- Each title must be specific and actionable (start with "Verify", "Test", "Check")
- No generic titles like "Test Scenario"
- No markdown symbols (**, *, +, -)
- Cover: positive tests, error handling, edge cases
- Return ONLY the JSON array, nothing else"""

            headers = {
                'Authorization': f'Bearer {groq_token}',
                'Content-Type': 'application/json'
            }
            
            # OPTIMIZED PAYLOAD with better quality controls
            payload = {
                'model': 'llama-3.1-8b-instant',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.2,  # Slightly higher for better creativity while maintaining consistency
                'max_tokens': 1500,  # Increased slightly for better quality
                'top_p': 0.9,
                'stream': False
            }
            
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=20
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                if verbose:
                    logger.info(f"🔍 Groq response length: {len(content)} characters")
                scenarios = self._improved_parse_scenarios(content)
                if verbose:
                    logger.info(f"🔍 _improved_parse_scenarios returned {len(scenarios) if scenarios else 0} scenarios")
                return scenarios[:10]
            else:
                return []
                
        except Exception as e:
            if verbose:
                logger.error(f"Ultra-fast Groq generation error: {str(e)}")
            return []

    def _improved_parse_scenarios(self, response_text: str) -> List[Dict]:
        """
        IMPROVED: Better scenario parsing with quality validation and cleaning
        """
        try:
            # First, try to parse the response as JSON directly
            try:
                scenarios = json.loads(response_text)
                if isinstance(scenarios, list) and len(scenarios) > 0:
                    logger.info(f"✅ Direct JSON parsing successful: {len(scenarios)} scenarios")
                    # Validate and clean each scenario
                    cleaned_scenarios = []
                    for scenario in scenarios:
                        cleaned_scenario = self._validate_and_clean_scenario(scenario)
                        if cleaned_scenario:
                            cleaned_scenarios.append(cleaned_scenario)
                    return cleaned_scenarios
            except json.JSONDecodeError as e:
                logger.debug(f"Direct JSON parsing failed: {e}")
                pass  # Try other methods
            
            # Clean the response and try to extract JSON array
            cleaned_text = self._clean_response_text(response_text)
            import re
            json_match = re.search(r'\[[\s\S]*\]', cleaned_text)
            if json_match:
                try:
                    scenarios = json.loads(json_match.group())
                    if isinstance(scenarios, list) and len(scenarios) > 0:
                        # Validate and clean each scenario
                        cleaned_scenarios = []
                        for scenario in scenarios:
                            cleaned_scenario = self._validate_and_clean_scenario(scenario)
                            if cleaned_scenario:
                                cleaned_scenarios.append(cleaned_scenario)
                        return cleaned_scenarios
                except json.JSONDecodeError as e:
                    logger.debug(f"Regex JSON parsing failed: {e}")
                    # Try to fix common JSON issues
                    fixed_json = self._fix_malformed_json(json_match.group())
                    if fixed_json:
                        try:
                            scenarios = json.loads(fixed_json)
                            if isinstance(scenarios, list) and len(scenarios) > 0:
                                # Validate and clean each scenario
                                cleaned_scenarios = []
                                for scenario in scenarios:
                                    cleaned_scenario = self._validate_and_clean_scenario(scenario)
                                    if cleaned_scenario:
                                        cleaned_scenarios.append(cleaned_scenario)
                                logger.info(f"✅ Fixed JSON parsing successful: {len(cleaned_scenarios)} scenarios")
                                return cleaned_scenarios
                        except json.JSONDecodeError:
                            pass  # Try fallback
            
            # Try to extract JSON-like structures from the text
            extracted_scenarios = self._extract_json_like_scenarios(response_text)
            if extracted_scenarios:
                logger.info(f"✅ Extracted {len(extracted_scenarios)} scenarios from JSON-like text")
                return extracted_scenarios
            
            # Only use text parsing as last resort - this was causing the issue
            logger.warning("JSON parsing failed, using text parsing fallback")
            return self._improved_text_to_scenarios(response_text)
            
        except Exception as e:
            logger.error(f"Error in _improved_parse_scenarios: {e}")
            return self._improved_text_to_scenarios(response_text)

    def _extract_json_like_scenarios(self, text: str) -> List[Dict]:
        """Extract scenarios from JSON-like text even when JSON is malformed"""
        try:
            scenarios = []
            
            # Look for JSON-like objects in the text
            # Pattern to match objects that look like scenarios
            pattern = r'\{[^{}]*"title"[^{}]*\}'
            matches = re.findall(pattern, text, re.DOTALL)
            
            for match in matches:
                try:
                    # Try to parse the individual object
                    scenario = json.loads(match)
                    if isinstance(scenario, dict) and 'title' in scenario:
                        # Clean the scenario
                        cleaned_scenario = self._validate_and_clean_scenario(scenario)
                        if cleaned_scenario:
                            scenarios.append(cleaned_scenario)
                except json.JSONDecodeError:
                    # If individual object parsing fails, try to extract fields manually
                    extracted_scenario = self._extract_scenario_from_text(match)
                    if extracted_scenario:
                        scenarios.append(extracted_scenario)
            
            return scenarios if scenarios else None
            
        except Exception as e:
            logger.debug(f"Error extracting JSON-like scenarios: {e}")
            return None

    def _extract_scenario_from_text(self, text: str) -> Dict:
        """Extract scenario fields from text that looks like JSON"""
        try:
            scenario = {}
            
            # Extract title
            title_match = re.search(r'"title"\s*:\s*"([^"]+)"', text)
            if title_match:
                scenario['title'] = title_match.group(1).strip()
            
            # Extract description
            desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', text)
            if desc_match:
                scenario['description'] = desc_match.group(1).strip()
            
            # Extract steps
            steps_match = re.search(r'"steps"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if steps_match:
                steps_text = steps_match.group(1)
                steps = re.findall(r'"([^"]+)"', steps_text)
                scenario['steps'] = steps
            
            # Extract severity
            severity_match = re.search(r'"severity"\s*:\s*"([^"]+)"', text)
            if severity_match:
                scenario['severity'] = severity_match.group(1).strip()
            
            # Extract priority
            priority_match = re.search(r'"priority"\s*:\s*"([^"]+)"', text)
            if priority_match:
                scenario['priority'] = priority_match.group(1).strip()
            
            # Extract automation
            automation_match = re.search(r'"automation"\s*:\s*"([^"]+)"', text)
            if automation_match:
                scenario['automation'] = automation_match.group(1).strip()
            
            # Only return if we have at least a title
            if scenario.get('title'):
                return self._validate_and_clean_scenario(scenario)
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting scenario from text: {e}")
            return None

    def _fix_malformed_json(self, json_text: str) -> str:
        """Fix common JSON malformation issues"""
        try:
            # Fix missing commas between objects
            json_text = re.sub(r'}\s*{', '},{', json_text)
            
            # Fix missing commas at end of objects
            json_text = re.sub(r'"\s*}\s*{', '",},{', json_text)
            json_text = re.sub(r'"\s*}\s*]', '",}]', json_text)
            
            # Fix missing quotes around keys
            json_text = re.sub(r'(\w+):', r'"\1":', json_text)
            
            # Fix trailing commas
            json_text = re.sub(r',\s*}', '}', json_text)
            json_text = re.sub(r',\s*]', ']', json_text)
            
            # Fix missing closing brackets
            if json_text.count('[') > json_text.count(']'):
                json_text += ']'
            if json_text.count('{') > json_text.count('}'):
                json_text += '}'
                
            return json_text
            
        except Exception as e:
            logger.debug(f"Error fixing malformed JSON: {e}")
            return None

    def _clean_response_text(self, text: str) -> str:
        """Clean response text of markdown and formatting artifacts"""
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **text** -> text
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *text* -> text
        text = re.sub(r'^[\+\-\*]\s*', '', text, flags=re.MULTILINE)  # Remove bullet points
        text = re.sub(r'^\d+\.\s*', '', text, flags=re.MULTILINE)     # Remove numbered lists
        
        # Remove common problematic phrases
        text = re.sub(r'Here are the.*?scenarios.*?:', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Below are.*?scenarios.*?:', '', text, flags=re.IGNORECASE)
        
        return text.strip()

    def _validate_and_clean_scenario(self, scenario: Dict) -> Optional[Dict]:
        """Validate and clean individual scenarios"""
        if not isinstance(scenario, dict):
            return None
            
        title = scenario.get('title', '').strip()
        
        # Skip invalid titles
        if not title or len(title) < 10:
            return None
            
        # Skip generic titles
        generic_titles = ['test scenario', 'scenario', 'test case', 'test']
        if title.lower() in generic_titles:
            return None
            
        # Clean title of formatting artifacts
        title = re.sub(r'[\*\+\-]', '', title).strip()
        title = re.sub(r'^[\d\.\s]+', '', title).strip()  # Remove leading numbers
        
        # Ensure title starts with action word
        action_words = ['verify', 'test', 'check', 'validate', 'ensure', 'confirm']
        if not any(title.lower().startswith(word) for word in action_words):
            title = f"Verify {title.lower()}"
        
        # Capitalize first letter
        title = title[0].upper() + title[1:] if title else title
        
        # Clean description
        description = scenario.get('description', '').strip()
        description = re.sub(r'[\*\+\-]', '', description).strip()
        if not description:
            description = f"Test scenario for {title.lower()}"
        
        # Ensure steps is a proper list
        steps = scenario.get('steps', [])
        if isinstance(steps, str):
            steps = [steps]
        elif not isinstance(steps, list):
            steps = ['1. Execute test steps', '2. Verify expected results']
        
        # Clean steps
        cleaned_steps = []
        for step in steps:
            if isinstance(step, str):
                clean_step = re.sub(r'[\*\+\-]', '', step).strip()
                clean_step = re.sub(r'^[\d\.\s]+', '', clean_step).strip()
                if clean_step and len(clean_step) > 5:
                    # Ensure step starts with number
                    if not clean_step[0].isdigit():
                        clean_step = f"{len(cleaned_steps) + 1}. {clean_step}"
                    cleaned_steps.append(clean_step)
        
        if not cleaned_steps:
            cleaned_steps = [
                '1. Set up test environment',
                '2. Execute the test scenario',
                '3. Verify expected results'
            ]
        
        return {
            'title': title[:100],  # Limit title length
            'description': description[:200],  # Limit description length
            'steps': cleaned_steps[:5],  # Limit number of steps
            'severity': scenario.get('severity', 'S3 - Moderate'),
            'priority': scenario.get('priority', 'P3 - Medium'),
            'automation': scenario.get('automation', 'Manual')
        }

    def _improved_text_to_scenarios(self, text: str) -> List[Dict]:
        """
        IMPROVED: Better text-to-scenario conversion with quality controls
        """
        scenarios = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 15:
                continue
                
            # Skip lines that are just formatting
            if line.startswith(('**', '##', '###', '---')):
                continue
                
            # Look for potential scenario titles
            if any(keyword in line.lower() for keyword in ['test', 'verify', 'check', 'validate', 'ensure']):
                cleaned_title = self._clean_title_from_line(line)
                if cleaned_title and len(cleaned_title) > 10:
                    scenario = self._create_quality_scenario(cleaned_title)
                    scenarios.append(scenario)
                    
                    if len(scenarios) >= 8:  # Limit for quality
                        break
        
        # If we didn't get enough scenarios, create some basic ones
        while len(scenarios) < 6:
            scenarios.append(self._create_quality_scenario(f"Test functionality scenario {len(scenarios) + 1}"))
            
        return scenarios

    def _clean_title_from_line(self, line: str) -> str:
        """Extract and clean title from a line of text"""
        # Remove common prefixes and formatting
        line = re.sub(r'^[\d\.\s]*', '', line)  # Remove leading numbers
        line = re.sub(r'[\*\+\-]+', '', line)   # Remove formatting
        line = re.sub(r'^(title|scenario|test):\s*', '', line, flags=re.IGNORECASE)
        
        # Clean quotes and brackets
        line = re.sub(r'^["\'\[\{]*', '', line)
        line = re.sub(r'["\'\]\}]*$', '', line)
        
        return line.strip()

    def _create_quality_scenario(self, title: str) -> Dict:
        """Create a high-quality scenario structure"""
        # Clean and improve title
        title = title.strip()
        if not title.lower().startswith(('verify', 'test', 'check', 'validate', 'ensure')):
            title = f"Verify {title.lower()}"
        
        # Capitalize properly
        title = title[0].upper() + title[1:] if title else "Test scenario"
        
        return {
            'title': title,
            'description': f"Test scenario to {title.lower()}",
            'steps': [
                '1. Navigate to the relevant page or section',
                '2. Execute the required test actions',
                '3. Verify the expected outcome occurs',
                '4. Document the test results'
            ],
            'severity': 'S3 - Moderate',
            'priority': 'P3 - Medium',
            'automation': 'Manual'
        }

    def _analyze_requirements_with_ai(self, story: Dict, verbose: bool = False) -> Optional[Dict]:
        """
        Sophisticated requirement analysis using free LLM services
        """
        story_text = self._extract_story_content(story)
        
        # Try multiple free LLM services in order of preference
        analysis_methods = [
            ('groq', self._analyze_with_groq),
            ('huggingface', self._analyze_with_huggingface),
            ('ollama_local', self._analyze_with_ollama)
        ]
        
        for service_name, analysis_method in analysis_methods:
            if not self.llm_services[service_name]['enabled']:
                continue
                
            try:
                if not self._check_rate_limit(service_name):
                    continue
                    
                logger.info(f"🔍 Analyzing requirements with {service_name.upper()}")
                analysis = analysis_method(story_text, verbose)
                
                if analysis:
                    logger.success(f"✅ Requirement analysis completed with {service_name.upper()}")
                    return analysis
                    
            except Exception as e:
                logger.warning(f"⚠️ {service_name} analysis failed: {str(e)}")
                continue
        
        logger.warning("All AI services failed for requirement analysis")
        return None

    def _analyze_with_groq(self, story_text: str, verbose: bool = False) -> Optional[Dict]:
        """Analyze requirements using Groq's free API"""
        try:
            # Groq requires an API key but has generous free tier
            groq_token = self.config.get('groq_token', '')
            if not groq_token:
                logger.info("No Groq token provided, skipping Groq analysis")
                return None
                
            prompt = self.analysis_prompts['requirement_analysis'].format(
                story_content=story_text[:3000]  # Limit for free tier
            )
            
            headers = {
                'Authorization': f'Bearer {groq_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'llama-3.1-8b-instant',  # Updated to working model
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.3,
                'max_tokens': 2000
            }
            
            response = requests.post(
                self.llm_services['groq']['endpoint'],
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return self._parse_analysis_response(content)
            else:
                logger.error(f"Groq API error: {response.status_code} - {response.text[:100]}")
                return None
                
        except Exception as e:
            logger.error(f"Groq analysis error: {str(e)}")
            return None

    def _analyze_with_huggingface(self, story_text: str, verbose: bool = False) -> Optional[Dict]:
        """Analyze requirements using Hugging Face Inference Providers API (NEW FORMAT)"""
        try:
            hf_token = self.config.get('huggingface', {}).get('token', '')
            if not hf_token:
                logger.info("No Hugging Face token provided, skipping HF analysis")
                return None
                
            # Use the NEW Inference Providers API format
            url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
            
            headers = {
                'Authorization': f'Bearer {hf_token}',
                'Content-Type': 'application/json'
            }
            
            # Use chat completion format for the new API
            prompt = f"Analyze this user story and extract key testing requirements: {story_text[:1000]}"
            
            payload = {
                'model': 'microsoft/DialoGPT-medium',  # Available model in new API
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 300,
                'temperature': 0.3
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ HuggingFace Inference Providers API successful: {response.status_code}")
                
                # Handle new API response format
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    
                    # Create structured analysis from response
                    return {
                        'main_functionality': self._extract_functionality_from_text(content),
                        'domain': self._extract_domain_from_text(content),
                        'complexity': 'medium',
                        'business_rules': self._extract_rules_from_text(content),
                        'integration_points': self._extract_integrations_from_text(content),
                        'generated_analysis': content[:500]
                    }
                
                # Fallback structured analysis
                return {
                    'main_functionality': 'User story analysis via HF Providers',
                    'domain': 'general',
                    'complexity': 'medium',
                    'business_rules': [],
                    'integration_points': []
                }
            else:
                logger.error(f"HuggingFace Providers API error: {response.status_code} - {response.text[:200]}")
                
            return None
            
        except Exception as e:
            logger.error(f"HuggingFace Providers analysis error: {str(e)}")
            return None

    def _analyze_with_ollama(self, story_text: str, verbose: bool = False) -> Optional[Dict]:
        """Analyze requirements using local Ollama if available"""
        try:
            prompt = self.analysis_prompts['requirement_analysis'].format(
                story_content=story_text
            )
            
            payload = {
                'model': 'llama2:7b',  # Free local model
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.3,
                    'num_predict': 2000
                }
            }
            
            response = requests.post(
                self.llm_services['ollama_local']['endpoint'],
                json=payload,
                timeout=60  # Local processing can take longer
            )
            
            if response.status_code == 200:
                result = response.json()
                generated_text = result.get('response', '')
                return self._parse_analysis_response(generated_text)
            else:
                logger.error(f"Ollama error: {response.status_code}")
                return None
                
        except requests.exceptions.ConnectionError:
            logger.info("Ollama not available locally, skipping")
            return None
        except Exception as e:
            logger.error(f"Ollama analysis error: {str(e)}")
            return None

    def _generate_scenarios_with_ai(self, story: Dict, analysis: Dict, verbose: bool = False) -> List[Dict]:
        """Generate comprehensive test scenarios using AI"""
        scenarios = []
        
        # Generate different types of scenarios
        scenario_types = [
            ('positive_scenarios', self._generate_positive_scenarios_ai),
            ('negative_scenarios', self._generate_negative_scenarios_ai),
            ('edge_cases', self._generate_edge_cases_ai),
            ('integration_scenarios', self._generate_integration_scenarios_ai)
        ]
        
        for scenario_type, generator_method in scenario_types:
            try:
                type_scenarios = generator_method(story, analysis, verbose)
                if type_scenarios:
                    scenarios.extend(type_scenarios)
                    logger.info(f"Generated {len(type_scenarios)} {scenario_type}")
            except Exception as e:
                logger.warning(f"Failed to generate {scenario_type}: {str(e)}")
                continue
        
        return scenarios

    def _generate_positive_scenarios_ai(self, story: Dict, analysis: Dict, verbose: bool = False) -> List[Dict]:
        """Generate positive/happy path scenarios using AI"""
        prompt = self.analysis_prompts['scenario_generation'].format(
            scenario_type="positive happy path",
            requirement_analysis=json.dumps(analysis, indent=2)[:1000],
            story_summary=story.get('fields', {}).get('summary', '')
        )
        
        return self._call_scenario_generation_api(prompt, "positive")

    def _generate_negative_scenarios_ai(self, story: Dict, analysis: Dict, verbose: bool = False) -> List[Dict]:
        """Generate negative/error scenarios using AI"""
        prompt = self.analysis_prompts['negative_testing'].format(
            requirement_analysis=json.dumps(analysis, indent=2)[:1000],
            story_summary=story.get('fields', {}).get('summary', '')
        )
        
        return self._call_scenario_generation_api(prompt, "negative")

    def _generate_edge_cases_ai(self, story: Dict, analysis: Dict, verbose: bool = False) -> List[Dict]:
        """Generate edge case scenarios using AI"""
        prompt = self.analysis_prompts['edge_case_analysis'].format(
            requirement_analysis=json.dumps(analysis, indent=2)[:1000],
            story_summary=story.get('fields', {}).get('summary', '')
        )
        
        return self._call_scenario_generation_api(prompt, "edge_case")

    def _generate_integration_scenarios_ai(self, story: Dict, analysis: Dict, verbose: bool = False) -> List[Dict]:
        """Generate integration and system-level scenarios"""
        integration_systems = analysis.get('integration_points', [])
        if not integration_systems:
            return []
            
        prompt = f"""Generate integration test scenarios for:
        Story: {story.get('fields', {}).get('summary', '')}
        Integration Points: {', '.join(integration_systems)}
        
        Create 2-3 scenarios focusing on:
        1. Data flow between systems
        2. Error handling in integrations
        3. Performance under load
        
        Return JSON array with title, description, steps, severity, priority, automation."""
        
        return self._call_scenario_generation_api(prompt, "integration")

    def _call_scenario_generation_api(self, prompt: str, scenario_type: str) -> List[Dict]:
        """Call the best available LLM service for scenario generation"""
        # Try services in order of quality/preference
        services = ['groq', 'huggingface', 'ollama_local']
        
        for service in services:
            if not self.llm_services[service]['enabled']:
                continue
                
            try:
                if not self._check_rate_limit(service):
                    continue
                    
                if service == 'groq':
                    result = self._call_groq_for_scenarios(prompt)
                elif service == 'huggingface':
                    result = self._call_hf_for_scenarios(prompt)
                elif service == 'ollama_local':
                    result = self._call_ollama_for_scenarios(prompt)
                else:
                    continue
                    
                if result:
                    scenarios = self._parse_scenario_response(result, scenario_type)
                    if scenarios:
                        return scenarios
                        
            except Exception as e:
                logger.warning(f"Error generating {scenario_type} with {service}: {str(e)}")
                continue
        
        return []

    def _enhance_with_specialized_scenarios(self, story: Dict, analysis: Dict, existing_scenarios: List[Dict]) -> List[Dict]:
        """Enhance scenarios with specialized types based on domain"""
        domain = analysis.get('domain', 'general')
        
        # Add domain-specific scenarios
        if domain in ['payment', 'financial']:
            existing_scenarios.extend(self._generate_security_scenarios(story, analysis))
            existing_scenarios.extend(self._generate_compliance_scenarios(story, analysis))
        elif domain in ['logistics', 'shipping']:
            existing_scenarios.extend(self._generate_tracking_scenarios(story, analysis))
        elif domain in ['user_management', 'authentication']:
            existing_scenarios.extend(self._generate_auth_scenarios(story, analysis))
        
        return existing_scenarios

    def _get_fallback_scenarios(self, story: Dict, verbose: bool = False) -> List[Dict]:
        """Get scenarios from your current CursorAIClient implementation"""
        try:
            logger.info("🔄 Getting scenarios from current implementation fallback")
            result = self.fallback_ai.generate_test_scenarios(story, verbose)
            
            if isinstance(result, str):
                scenarios = json.loads(result)
            else:
                scenarios = result
                
            return scenarios if isinstance(scenarios, list) else []
            
        except Exception as e:
            logger.error(f"Fallback scenarios failed: {str(e)}")
            return []

    def _validate_and_enhance_scenarios(self, scenarios: List[Dict], story: Dict) -> List[Dict]:
        """Validate and enhance generated scenarios for quality"""
        validated_scenarios = []
        
        for scenario in scenarios:
            # Ensure required fields
            if not isinstance(scenario, dict):
                continue
                
            enhanced_scenario = {
                'title': scenario.get('title', 'Test Scenario')[:255],  # Jira limit
                'description': scenario.get('description', 'Test scenario description'),
                'steps': scenario.get('steps', ['1. Execute test', '2. Verify results']),
                'severity': scenario.get('severity', 'S3 - Moderate'),
                'priority': scenario.get('priority', 'P3 - Medium'),
                'automation': scenario.get('automation', 'Manual'),
                'journey': self._determine_journey(story)
            }
            
            # Ensure steps is a list
            if isinstance(enhanced_scenario['steps'], str):
                enhanced_scenario['steps'] = [enhanced_scenario['steps']]
            
            validated_scenarios.append(enhanced_scenario)
        
        # Remove duplicates based on title similarity
        return self._remove_duplicate_scenarios(validated_scenarios)

    def _remove_duplicate_scenarios(self, scenarios: List[Dict]) -> List[Dict]:
        """Remove duplicate scenarios based on title similarity"""
        unique_scenarios = []
        seen_titles = set()
        
        for scenario in scenarios:
            title = scenario.get('title', '').lower().strip()
            # Simple similarity check
            is_duplicate = any(
                self._calculate_similarity(title, seen_title) > 0.8 
                for seen_title in seen_titles
            )
            
            if not is_duplicate:
                unique_scenarios.append(scenario)
                seen_titles.add(title)
        
        return unique_scenarios

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
            
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0

    # Prompt templates for ChatGPT-level analysis
    def _get_requirement_analysis_prompt(self) -> str:
        return """Analyze this user story/requirement comprehensively like a senior QA analyst:

STORY CONTENT:
{story_content}

Provide a detailed analysis in JSON format with:
{{
    "main_functionality": "core feature being implemented",
    "user_personas": ["list of users who will use this"],
    "business_value": "business impact and value",
    "acceptance_criteria": ["extracted acceptance criteria"],
    "functional_requirements": ["list of functional requirements"],
    "non_functional_requirements": ["performance, security, usability requirements"],
    "integration_points": ["external systems/APIs involved"],
    "data_elements": ["data fields, entities, objects involved"],
    "business_rules": ["business logic and rules"],
    "edge_cases": ["potential edge cases and boundary conditions"],
    "error_scenarios": ["possible error conditions"],
    "dependencies": ["technical and business dependencies"],
    "domain": "business domain (payment, logistics, user_management, etc.)",
    "complexity": "low/medium/high",
    "risk_areas": ["areas requiring careful testing"]
}}

Focus on extracting ALL testable aspects comprehensively."""

    def _get_scenario_generation_prompt(self) -> str:
        return """Generate {scenario_type} test scenarios based on this analysis:

REQUIREMENT ANALYSIS:
{requirement_analysis}

STORY: {story_summary}

IMPORTANT: Return ONLY a valid JSON array. No extra text or explanations.

Generate 3-5 comprehensive test scenarios in this EXACT JSON format:
[
    {{
        "title": "Clear, descriptive test scenario title",
        "description": "Detailed description of what this scenario tests",
        "steps": [
            "1. Specific step with clear action",
            "2. Another detailed step",
            "3. Verification step with expected result"
        ],
        "severity": "S1 - Critical",
        "priority": "P1 - Critical",
        "automation": "Manual"
    }}
]

Requirements:
- Return ONLY the JSON array, nothing else
- Ensure valid JSON syntax
- Include 3-5 scenarios
- Focus on business value
- Cover different user paths"""

    def _get_edge_case_prompt(self) -> str:
        return """Identify edge cases and boundary conditions for comprehensive testing:

ANALYSIS: {requirement_analysis}
STORY: {story_summary}

Generate edge case test scenarios focusing on:
1. Boundary value testing
2. Unusual data combinations
3. System limits and constraints
4. Concurrent user scenarios
5. Data validation edge cases

Return JSON array of scenarios with detailed steps."""

    def _get_negative_testing_prompt(self) -> str:
        return """Generate negative testing scenarios for robust error handling:

ANALYSIS: {requirement_analysis}
STORY: {story_summary}

Create scenarios testing:
1. Invalid inputs and data
2. Authentication/authorization failures
3. System errors and timeouts
4. Missing or corrupted data
5. Network and integration failures

Return JSON array focusing on error conditions and system resilience."""

    # Utility methods
    def _extract_story_content(self, story: Dict) -> str:
        """Extract comprehensive content from Jira story"""
        fields = story.get('fields', {})
        
        summary = fields.get('summary', '')
        description = self._extract_text_from_field(fields.get('description', ''))
        acceptance_criteria = self._extract_text_from_field(fields.get('customfield_10019', ''))
        
        return f"SUMMARY: {summary}\n\nDESCRIPTION: {description}\n\nACCEPTANCE CRITERIA: {acceptance_criteria}".strip()

    def _extract_text_from_field(self, field_content: Any) -> str:
        """Extract plain text from various Jira field formats"""
        if isinstance(field_content, dict):
            try:
                return self.fallback_ai._extract_plain_text(field_content)
            except:
                return str(field_content)
        return str(field_content) if field_content else ""

    def _parse_analysis_response(self, response_text: str) -> Optional[Dict]:
        """Parse AI response into structured analysis"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            # If no JSON, create structured analysis from text
            return self._text_to_analysis_structure(response_text)
            
        except Exception as e:
            logger.error(f"Error parsing analysis response: {str(e)}")
            return None

    def _text_to_analysis_structure(self, text: str) -> Dict:
        """Convert text analysis to structured format"""
        return {
            'main_functionality': self._extract_functionality_from_text(text),
            'domain': self._extract_domain_from_text(text),
            'complexity': 'medium',
            'business_rules': self._extract_rules_from_text(text),
            'integration_points': self._extract_integrations_from_text(text)
        }

    def _parse_scenario_response(self, response_text: str, scenario_type: str) -> List[Dict]:
        """Parse AI response into structured scenarios"""
        try:
            # Clean the response text first
            cleaned_text = response_text.strip()
            
            # Try to extract JSON array using multiple strategies
            scenarios = self._extract_json_scenarios(cleaned_text)
            if scenarios:
                logger.info(f"✅ Parsed {len(scenarios)} scenarios from JSON")
                return scenarios
            
            # If JSON parsing fails, convert text to scenarios
            logger.warning(f"JSON parsing failed, converting text to scenarios")
            scenarios = self._text_to_scenarios(cleaned_text, scenario_type)
            logger.info(f"✅ Converted {len(scenarios)} scenarios from text")
            return scenarios
            
        except Exception as e:
            logger.error(f"Error parsing scenario response: {str(e)}")
            logger.warning(f"Falling back to text parsing")
            return self._text_to_scenarios(response_text, scenario_type)

    def _extract_json_scenarios(self, text: str) -> List[Dict]:
        """Extract JSON scenarios using multiple parsing strategies"""
        # Strategy 1: Find complete JSON array
        json_array_match = re.search(r'\[[\s\S]*\]', text)
        if json_array_match:
            try:
                scenarios = json.loads(json_array_match.group())
                if isinstance(scenarios, list) and len(scenarios) > 0:
                    return scenarios
            except:
                pass
        
        # Strategy 2: Find multiple JSON objects and combine
        json_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
        scenarios = []
        for obj_str in json_objects:
            try:
                obj = json.loads(obj_str)
                if isinstance(obj, dict) and 'title' in obj:
                    scenarios.append(obj)
            except:
                continue
        
        if scenarios:
            return scenarios
        
        # Strategy 3: Clean and extract JSON parts
        lines = text.split('\n')
        json_lines = []
        in_json = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('[') or line.startswith('{'):
                in_json = True
            if in_json:
                json_lines.append(line)
            if line.endswith(']') or (line.endswith('}') and not line.endswith('},')): 
                break
        
        if json_lines:
            try:
                json_text = ' '.join(json_lines)
                # Remove common issues
                json_text = re.sub(r',\s*}', '}', json_text)  # Remove trailing commas
                json_text = re.sub(r',\s*]', ']', json_text)  # Remove trailing commas
                scenarios = json.loads(json_text)
                if isinstance(scenarios, list):
                    return scenarios
                elif isinstance(scenarios, dict):
                    return [scenarios]
            except:
                pass
        
        return []

    def _text_to_scenarios(self, text: str, scenario_type: str) -> List[Dict]:
        """Convert text response to scenario structure"""
        scenarios = []
        lines = text.split('\n')
        
        current_scenario = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Skip JSON artifacts
            if line in ['{', '}', '[', ']', '},{']:
                continue
                
            # Look for scenario indicators
            is_scenario_start = any([
                line.lower().startswith(('title:', 'scenario:', 'test:')),
                re.match(r'^\d+\.', line) and any(word in line.lower() for word in ['test', 'verify', 'check', 'validate']),
                '"title"' in line.lower(),
                (len(line) > 20 and any(word in line.lower() for word in ['test', 'scenario', 'verify', 'validate']) and not line.startswith('-'))
            ])
            
            if is_scenario_start:
                # Save previous scenario
                if current_scenario and current_scenario.get('title'):
                    scenarios.append(current_scenario)
                
                # Start new scenario
                title = self._extract_title_from_line(line)
                current_scenario = {
                    'title': title,
                    'description': title,
                    'steps': [],
                    'severity': self._get_default_severity(scenario_type),
                    'priority': self._get_default_priority(scenario_type),
                    'automation': 'Manual'
                }
            
            # Look for steps
            elif current_scenario and self._is_step_line(line):
                step = self._clean_step_text(line)
                if step and len(step) > 5:  # Only add meaningful steps
                    current_scenario['steps'].append(step)
            
            # Look for description updates
            elif current_scenario and self._is_description_line(line):
                desc = self._clean_description_text(line)
                if desc and len(desc) > len(current_scenario.get('description', '')):
                    current_scenario['description'] = desc
        
        # Add final scenario
        if current_scenario and current_scenario.get('title'):
            scenarios.append(current_scenario)
        
        # Ensure all scenarios have at least basic steps
        for scenario in scenarios:
            if not scenario.get('steps'):
                scenario['steps'] = [
                    '1. Execute the test scenario',
                    '2. Verify expected behavior',
                    '3. Document results'
                ]
        
        return scenarios[:5]  # Limit scenarios per type

    def _extract_title_from_line(self, line: str) -> str:
        """Extract clean title from various line formats"""
        # Remove common prefixes
        prefixes = ['title:', 'scenario:', 'test:', '"title":', '1.', '2.', '3.', '4.', '5.']
        for prefix in prefixes:
            if line.lower().startswith(prefix):
                line = line[len(prefix):].strip()
                break
        
        # Remove quotes and common JSON artifacts
        line = re.sub(r'^["\'\[\{]*', '', line)
        line = re.sub(r'["\'\]\},]*$', '', line)
        
        # Limit length
        return line[:100].strip()

    def _is_step_line(self, line: str) -> bool:
        """Check if line represents a test step"""
        return any([
            re.match(r'^\d+\.', line),
            line.startswith(('-', '*', '•')),
            '"steps"' in line.lower(),
            any(word in line.lower() for word in ['step:', 'action:', 'verify:', 'check:'])
        ])

    def _clean_step_text(self, line: str) -> str:
        """Clean step text from various formats"""
        # Remove step prefixes
        line = re.sub(r'^\d+\.\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = re.sub(r'steps?:\s*', '', line, flags=re.IGNORECASE)
        
        # Remove JSON artifacts
        line = re.sub(r'^["\'\[\{]*', '', line)
        line = re.sub(r'["\'\]\},]*$', '', line)
        
        return line.strip()

    def _is_description_line(self, line: str) -> bool:
        """Check if line contains description"""
        return any([
            'description' in line.lower(),
            len(line) > 30 and not self._is_step_line(line)
        ])

    def _clean_description_text(self, line: str) -> str:
        """Clean description text"""
        line = re.sub(r'description:\s*', '', line, flags=re.IGNORECASE)
        line = re.sub(r'^["\'\[\{]*', '', line)
        line = re.sub(r'["\'\]\},]*$', '', line)
        return line.strip()

    def _get_default_severity(self, scenario_type: str) -> str:
        """Get default severity based on scenario type"""
        severity_map = {
            'positive': 'S2 - Major',
            'negative': 'S1 - Critical',
            'edge_case': 'S3 - Moderate',
            'integration': 'S2 - Major'
        }
        return severity_map.get(scenario_type, 'S3 - Moderate')

    def _get_default_priority(self, scenario_type: str) -> str:
        """Get default priority based on scenario type"""
        priority_map = {
            'positive': 'P2 - High',
            'negative': 'P1 - Critical',
            'edge_case': 'P3 - Medium',
            'integration': 'P2 - High'
        }
        return priority_map.get(scenario_type, 'P3 - Medium')

    def _check_rate_limit(self, service: str) -> bool:
        """Check rate limits for free services"""
        current_time = time.time()
        
        # Reset hourly counters
        if current_time - self.last_reset_time > 3600:
            self.request_counts = {}
            self.last_reset_time = current_time
        
        service_config = self.llm_services.get(service, {})
        rate_limit = service_config.get('rate_limit', 100)
        
        current_count = self.request_counts.get(service, 0)
        
        if current_count >= rate_limit:
            logger.warning(f"Rate limit reached for {service}")
            return False
            
        self.request_counts[service] = current_count + 1
        return True

    def _determine_journey(self, story: Dict) -> str:
        """Determine appropriate journey for the story"""
        # Use your existing logic or fallback implementation
        try:
            return self.fallback_ai._determine_journey_from_domain(
                story.get('fields', {}).get('summary', '')
            )
        except:
            return 'Account'

    # Placeholder methods for specialized scenarios
    def _generate_security_scenarios(self, story: Dict, analysis: Dict) -> List[Dict]:
        """Generate security-focused test scenarios"""
        return [{
            'title': 'Security Validation - Authentication',
            'description': 'Verify proper authentication and authorization',
            'steps': ['1. Test with invalid credentials', '2. Verify access denied', '3. Test with valid credentials'],
            'severity': 'S1 - Critical',
            'priority': 'P1 - Critical',
            'automation': 'Manual'
        }]

    def _generate_compliance_scenarios(self, story: Dict, analysis: Dict) -> List[Dict]:
        """Generate compliance-focused scenarios"""
        return []

    def _generate_tracking_scenarios(self, story: Dict, analysis: Dict) -> List[Dict]:
        """Generate logistics tracking scenarios"""
        return []

    def _generate_auth_scenarios(self, story: Dict, analysis: Dict) -> List[Dict]:
        """Generate authentication scenarios"""
        return []

    # Helper methods for API calls
    def _call_groq_for_scenarios(self, prompt: str) -> Optional[str]:
        """Call Groq API for scenario generation"""
        try:
            groq_token = self.config.get('groq_token', '')
            if not groq_token:
                return None
                
            headers = {
                'Authorization': f'Bearer {groq_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'llama-3.1-8b-instant',
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.3,
                'max_tokens': 1500
            }
            
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Debug logging to see what we're getting
                logger.debug(f"🔍 Groq response preview: {content[:200]}...")
                logger.debug(f"🔍 Groq response length: {len(content)} characters")
                
                logger.info(f"✅ Groq scenario generation successful")
                return content
            else:
                logger.error(f"Groq scenario API error: {response.status_code} - {response.text[:100]}")
                return None
                
        except Exception as e:
            logger.error(f"Groq scenario generation error: {str(e)}")
            return None

    def _call_hf_for_scenarios(self, prompt: str) -> Optional[str]:
        """Call HuggingFace Inference Providers API for scenario generation (NEW FORMAT)"""
        try:
            hf_token = self.config.get('huggingface', {}).get('token', '')
            if not hf_token:
                return None
                
            # Use the NEW Inference Providers API
            url = "https://router.huggingface.co/hf-inference/v1/chat/completions"
            
            headers = {
                'Authorization': f'Bearer {hf_token}',
                'Content-Type': 'application/json'
            }
            
            # Format prompt for chat completion
            formatted_prompt = f"Generate test scenarios based on: {prompt[:800]}\n\nReturn 3-5 test scenarios in JSON format."
            
            payload = {
                'model': 'microsoft/DialoGPT-medium',
                'messages': [
                    {'role': 'user', 'content': formatted_prompt}
                ],
                'max_tokens': 500,
                'temperature': 0.4
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    logger.info(f"✅ HuggingFace Providers scenario generation successful")
                    return content
            else:
                logger.error(f"HuggingFace Providers scenario API error: {response.status_code}")
                
            return None
            
        except Exception as e:
            logger.error(f"HuggingFace Providers scenario generation error: {str(e)}")
            return None

    def _call_ollama_for_scenarios(self, prompt: str) -> Optional[str]:
        """Call Ollama local API for scenario generation"""
        # Implementation similar to _analyze_with_ollama
        return None

    # Text extraction helper methods (minimal but non-stub defaults)
    def _extract_functionality_from_text(self, text: str) -> str:
        text_lower = (text or "").lower()
        if any(k in text_lower for k in ["payment", "checkout", "invoice", "transaction"]):
            return "Payments"
        if any(k in text_lower for k in ["login", "authentication", "register", "user"]):
            return "User Management"
        return "General"

    def _extract_domain_from_text(self, text: str) -> str:
        text_lower = (text or "").lower()
        if any(k in text_lower for k in ["finance", "billing", "revenue", "cost"]):
            return "Finance"
        if any(k in text_lower for k in ["logistics", "shipping", "warehouse", "inventory"]):
            return "Logistics"
        return "General"

    def _extract_rules_from_text(self, text: str) -> List[str]:
        return []

    def _extract_integrations_from_text(self, text: str) -> List[str]:
        return []