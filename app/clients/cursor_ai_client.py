import json
from loguru import logger
import re
from typing import Dict, Any, List, Optional
from app.utils.field_mappings import field_mappings
from enum import Enum
from app.utils.test_templates import get_test_pattern, format_test_steps
import warnings
from datetime import datetime
from app.formatters.text_formatter import text_formatter

class AutomationStatus(Enum):
    MANUAL = "Manual"
    AUTOMATED = "Automated"
    NOT_APPLICABLE = "Not Applicable"
    
    @property
    def label(self):
        return self.value

class CursorAIClient:
    def __init__(self):
        """Initialize Cursor AI client"""
        logger.info("Cursor AI client initialized")
        
        # Initialize common test patterns
        self.test_patterns = {
            'validation': {
                'severity': 'S2 - Major',
                'priority': 'P2 - High',
                'automation': 'Manual',
                'can_automate': True,
                'keywords': ['must', 'should', 'validate', 'verify', 'ensure', 'check']
            },
            'functionality': {
                'severity': 'S2 - Major',
                'priority': 'P2 - High',
                'automation': 'Manual',
                'can_automate': True,
                'keywords': ['function', 'process', 'calculate', 'generate', 'create']
            },
            'ui': {
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium',
                'automation': 'Manual',
                'can_automate': True,
                'keywords': ['display', 'show', 'view', 'layout', 'design', 'appear']
            },
            'error': {
                'severity': 'S1 - Critical',
                'priority': 'P1 - Critical',
                'automation': 'Manual',
                'can_automate': True,
                'keywords': ['error', 'exception', 'fail', 'crash', 'invalid']
            },
            'enhancement': {
                'severity': 'S4 - Low',
                'priority': 'P4 - Low',
                'automation': 'Manual',
                'can_automate': False,
                'keywords': ['enhance', 'improve', 'optimize', 'nice to have']
            }
        }

        # Initialize step patterns
        self.step_patterns = {
            'positive': [
                "1. Set up test prerequisites",
                "2. Prepare valid test data",
                "3. Execute the test operation",
                "4. Verify successful response",
                "5. Validate expected outcome"
            ],
            'negative': [
                "1. Set up test prerequisites",
                "2. Prepare invalid test data",
                "3. Attempt the operation",
                "4. Verify error handling",
                "5. Validate error message"
            ],
            'validation': [
                "1. Set up validation test",
                "2. Prepare test data",
                "3. Submit for validation",
                "4. Verify validation rules",
                "5. Validate results"
            ],
            'business_rule': [
                "1. Set up business rule test",
                "2. Configure test conditions",
                "3. Execute business flow",
                "4. Verify rule application",
                "5. Validate outcomes"
            ],
            'user_flow': [
                "1. Set up user flow test",
                "2. Initialize user session",
                "3. Execute user actions",
                "4. Verify flow progression",
                "5. Validate end state"
            ],
            'data_validation': [
                "1. Set up data validation test",
                "2. Prepare test data set",
                "3. Execute validation rules",
                "4. Verify data integrity",
                "5. Validate results"
            ],
            'integration': [
                "1. Set up integration test",
                "2. Configure integration points",
                "3. Execute integration flow",
                "4. Verify data exchange",
                "5. Validate system state"
            ],
            'performance': [
                "1. Set up performance test",
                "2. Configure test parameters",
                "3. Execute load test",
                "4. Monitor performance metrics",
                "5. Validate results"
            ],
            'edge': [
                "1. Set up edge case test",
                "2. Prepare boundary conditions",
                "3. Execute edge case",
                "4. Verify system handling",
                "5. Validate stability"
            ]
        }

    def _extract_plain_text(self, doc_content) -> str:
        """Extract plain text from Atlassian Document Format with enhanced nested list support"""
        if not doc_content:
            return ""
            
        if isinstance(doc_content, str):
            return doc_content
            
        if isinstance(doc_content, dict):
            text_parts = []
            
            # Handle document structure
            if doc_content.get('type') == 'doc':
                content = doc_content.get('content', [])
            else:
                content = [doc_content]
            
            for block in content:
                block_type = block.get('type', '')
                
                if block_type == 'paragraph':
                    paragraph_text = []
                    for item in block.get('content', []):
                        if item.get('type') == 'text':
                            text = item.get('text', '')
                            marks = item.get('marks', [])
                            if any(mark.get('type') == 'strong' for mark in marks):
                                text = f"**{text}**"
                            paragraph_text.append(text)
                        elif item.get('type') == 'hardBreak':
                            paragraph_text.append('\n')
                    text_parts.append(''.join(paragraph_text))
                
                elif block_type == 'heading':
                    heading_text = []
                    level = block.get('attrs', {}).get('level', 1)
                    prefix = '#' * level + ' '
                    for item in block.get('content', []):
                        if item.get('type') == 'text':
                            text = item.get('text', '')
                            marks = item.get('marks', [])
                            if any(mark.get('type') == 'strong' for mark in marks):
                                text = f"**{text}**"
                            heading_text.append(text)
                    text_parts.append(f"\n{prefix}{''.join(heading_text)}\n")
                
                elif block_type == 'bulletList':
                    text_parts.append(self._extract_list_content(block, bullet_style='•'))
                
                elif block_type == 'orderedList':
                    start_number = block.get('attrs', {}).get('order', 1)
                    text_parts.append(self._extract_list_content(block, bullet_style='numbered', start_num=start_number))
                
                # Handle other block types
                elif block_type in ['codeBlock', 'blockquote']:
                    # Extract text from these blocks too
                    for item in block.get('content', []):
                        if item.get('type') == 'text':
                            text_parts.append(item.get('text', ''))

            return '\n'.join(text_parts)
        
        return str(doc_content)

    def _extract_list_content(self, list_block: Dict[str, Any], bullet_style: str = '•', start_num: int = 1) -> str:
        """Extract content from nested lists (ordered and bullet lists)"""
        list_items = []
        
        for i, item in enumerate(list_block.get('content', [])):
            if item.get('type') == 'listItem':
                item_parts = []
                
                # Determine bullet/number prefix
                if bullet_style == 'numbered':
                    prefix = f"{start_num + i}. "
                else:
                    prefix = f"{bullet_style} "
                
                # Extract content from this list item
                for content_block in item.get('content', []):
                    content_type = content_block.get('type', '')
                    
                    if content_type == 'paragraph':
                        para_text = []
                        for text_item in content_block.get('content', []):
                            if text_item.get('type') == 'text':
                                text = text_item.get('text', '')
                                marks = text_item.get('marks', [])
                                if any(mark.get('type') == 'strong' for mark in marks):
                                    text = f"**{text}**"
                                para_text.append(text)
                            elif text_item.get('type') == 'hardBreak':
                                para_text.append('\n')
                        if para_text:
                            item_parts.append(''.join(para_text))
                    
                    elif content_type == 'bulletList':
                        # Handle nested bullet lists
                        nested_content = self._extract_list_content(content_block, bullet_style='  - ')
                        if nested_content:
                            item_parts.append(f"\n{nested_content}")
                    
                    elif content_type == 'orderedList':
                        # Handle nested ordered lists
                        nested_start = content_block.get('attrs', {}).get('order', 1)
                        nested_content = self._extract_list_content(content_block, bullet_style='numbered', start_num=nested_start)
                        if nested_content:
                            item_parts.append(f"\n{nested_content}")
                
                # Combine all parts for this list item
                if item_parts:
                    full_item = f"{prefix}{''.join(item_parts)}"
                    list_items.append(full_item)
        
        return '\n'.join(list_items)

    def _extract_requirements(self, text: str) -> List[Dict[str, Any]]:
        """Extract detailed requirements with context"""
        requirements = []
        
        # Look for requirement patterns
        patterns = [
            (r'(?:must|should|shall|will)\s+([^.]+)', 'mandatory'),
            (r'(?:can|may|might|could)\s+([^.]+)', 'optional'),
            (r'(?:when|if)\s+([^,]+),\s+(?:then|system\s+(?:must|should|shall))\s+([^.]+)', 'conditional')
        ]
        
        for pattern, req_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if req_type == 'conditional':
                    requirements.append({
                        'type': req_type,
                        'condition': match.group(1).strip(),
                        'action': match.group(2).strip()
                    })
                else:
                    requirements.append({
                        'type': req_type,
                        'description': match.group(1).strip()
                    })
        
        return requirements

    def _extract_acceptance_criteria(self, text: str) -> List[Dict[str, Any]]:
        """Extract structured acceptance criteria with enhanced parsing for complex formats"""
        criteria = []
        
        if not text:
            return criteria

        # Look for "Acceptance Criteria:" section
        ac_match = re.search(r'Acceptance Criteria:\s*(.+?)(?=\n\n\n|\Z)', text, re.DOTALL | re.IGNORECASE)
        if ac_match:
            ac_text = ac_match.group(1)
        else:
            # If no explicit AC section, try to extract numbered/bulleted items
            ac_text = text

        # Enhanced pattern to extract numbered acceptance criteria with detailed sub-points
        # Pattern: 1. **Title** followed by bullet points
        numbered_pattern = r'(\d+)\.\s*\*\*([^*]+)\*\*\s*((?:\s*-\s+[^\n]+(?:\n|$))*)'
        numbered_matches = re.finditer(numbered_pattern, ac_text, re.MULTILINE)
        
        found_numbered = False
        for match in numbered_matches:
            found_numbered = True
            number = match.group(1)
            title = match.group(2).strip()
            details_text = match.group(3).strip()
            
            # Extract Given/When/Then patterns from bullet points
            gherkin_scenarios = []
            
            # Parse bullet points
            bullet_lines = [line.strip() for line in details_text.split('\n') if line.strip().startswith('-')]
            
            current_scenario = {}
            for bullet_line in bullet_lines:
                # Remove leading dash and whitespace
                bullet_text = bullet_line.lstrip('- ').strip()
                
                if bullet_text.startswith('Given'):
                    if current_scenario:  # Save previous scenario
                        gherkin_scenarios.append(current_scenario)
                    current_scenario = {'given': bullet_text[5:].strip(), 'when': '', 'then': '', 'and': []}
                elif bullet_text.startswith('When'):
                    current_scenario['when'] = bullet_text[4:].strip()
                elif bullet_text.startswith('Then'):
                    current_scenario['then'] = bullet_text[4:].strip()
                elif bullet_text.startswith('And'):
                    current_scenario['and'].append(bullet_text[3:].strip())
                else:
                    # Handle bullet points that don't start with Given/When/Then/And
                    # These might be additional details or conditions
                    if current_scenario and not current_scenario.get('given'):
                        current_scenario['given'] = bullet_text
                    elif current_scenario:
                        current_scenario['and'].append(bullet_text)
            
            # Add last scenario
            if current_scenario:
                gherkin_scenarios.append(current_scenario)
            
            criteria.append({
                'type': 'detailed_acceptance',
                'number': number,
                'title': title,
                'description': details_text,
                'gherkin_scenarios': gherkin_scenarios
            })
        
        # If no numbered criteria found, try other patterns
        if not found_numbered:
            # Try simple bullet patterns
            bullet_blocks = re.split(r'\n[-•*]\s+', text)
            for block in bullet_blocks[1:]:  # Skip first empty split
                block = block.strip()
                if block and len(block) > 10:  # Ignore very short items
                    criteria.append({
                        'type': 'standard',
                        'description': block
                    })
            
            # If still no criteria, treat whole text as one criterion
            if not criteria and text.strip():
                criteria.append({
                    'type': 'standard', 
                    'description': text.strip()
                })
        
        return criteria

    def _extract_business_rules(self, text: str) -> List[Dict[str, Any]]:
        """Extract business rules with conditions and actions"""
        rules = []
        
        # Skip if this looks like acceptance criteria (to avoid duplicates)
        if 'acceptance criteria:' in text.lower():
            return rules
        
        # Look for business rule patterns (but not from bullet points in acceptance criteria)
        patterns = [
            (r'if\s+([^,]+),\s+then\s+([^.]+)', 'conditional'),
            (r'only\s+(?:if|when)\s+([^,]+),\s+(?:can|should|must)\s+([^.]+)', 'restriction'),
            (r'must\s+(?:be|have)\s+([^.]+)', 'requirement'),
            (r'should\s+(?:be|have)\s+([^.]+)', 'guideline'),
            (r'cannot\s+([^.]+)', 'prohibition')
        ]
        
        # Split text into sections to avoid extracting from acceptance criteria
        text_sections = text.split('Acceptance Criteria:')[0] if 'Acceptance Criteria:' in text else text
        
        for pattern, rule_type in patterns:
            matches = re.finditer(pattern, text_sections, re.IGNORECASE)
            for match in matches:
                # Skip if this looks like it's from a bullet point in acceptance criteria
                context = text_sections[max(0, match.start() - 50):min(len(text_sections), match.end() + 50)]
                if re.search(r'[-•]\s*', context):
                    continue
                    
                if rule_type in ['conditional', 'restriction']:
                    rules.append({
                        'type': rule_type,
                        'condition': match.group(1).strip(),
                        'action': match.group(2).strip()
                    })
                else:
                    rules.append({
                        'type': rule_type,
                        'description': match.group(1).strip()
                    })
        
        return rules

    def _extract_data_requirements(self, text: str) -> List[Dict[str, Any]]:
        """Extract data requirements and validations"""
        data_reqs = []
        
        # Look for field/data patterns
        patterns = [
            (r'field\s+([^\s]+)\s+(?:must|should)\s+([^.]+)', 'field_validation'),
            (r'value\s+(?:must|should)\s+([^.]+)', 'value_validation'),
            (r'(?:input|enter)\s+([^.]+)', 'input_requirement'),
            (r'format\s+(?:must|should)\s+be\s+([^.]+)', 'format_requirement')
        ]
        
        for pattern, req_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if req_type == 'field_validation':
                    data_reqs.append({
                        'type': req_type,
                        'field': match.group(1).strip(),
                        'validation': match.group(2).strip()
                    })
                else:
                    data_reqs.append({
                        'type': req_type,
                        'description': match.group(1).strip()
                    })
        
        return data_reqs

    def _clean_scenario_text(self, text: str) -> str:
        """Clean up scenario text by removing unnecessary phrases and formatting"""
        return text_formatter.clean_scenario_text(text)

    def _format_steps(self, steps: List[str]) -> str:
        """Format steps with proper line breaks"""
        return text_formatter.format_steps(steps)

    def _generate_ac_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate intelligent scenarios from acceptance criteria with crisp descriptions"""
        scenarios = []
        
        for criterion in analysis.get('acceptance_criteria', []):
            if not isinstance(criterion, dict):
                continue
            
            criterion_type = criterion.get('type', 'standard')
            
            if criterion_type == 'detailed_acceptance':
                # Process detailed acceptance criteria with Gherkin scenarios
                title = criterion.get('title', '')
                gherkin_scenarios = criterion.get('gherkin_scenarios', [])
                
                # Clean title of markdown formatting and numbers
                clean_title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)  # Remove **bold**
                clean_title = re.sub(r'^\d+\.\s*', '', clean_title)     # Remove leading numbers
                clean_title = clean_title.strip()
                
                # Process each Gherkin scenario with crisp conversion
                if gherkin_scenarios:
                    for gherkin in gherkin_scenarios:
                        if isinstance(gherkin, dict) and gherkin.get('then'):
                            # Use the crisp Gherkin conversion method
                            scenario = self._generate_gherkin_scenario(clean_title, gherkin, clean_title)
                            if scenario:
                                scenarios.append(scenario)
                else:
                    # Fallback for titles without Gherkin scenarios
                    scenario = self._create_generic_functional_scenario(
                        f"Verify {clean_title}",
                        f"System correctly implements {clean_title.lower()} functionality."
                    )
                    if scenario:
                        scenarios.append(scenario)
                        
            else:
                # Handle standard criteria with intelligent processing
                raw_description = criterion.get('description', '')
                if not raw_description:
                    continue
                    
                # Clean up raw description to remove Gherkin syntax if present
                clean_description = self._clean_gherkin_from_description(raw_description)
                
                # Create crisp scenario from cleaned description
                scenario = self._create_generic_functional_scenario(
                    f"Verify {clean_description[:50]}{'...' if len(clean_description) > 50 else ''}",
                    f"System correctly implements {clean_description.lower()}."
                )
                if scenario:
                    scenarios.append(scenario)

        return scenarios

    def _clean_gherkin_from_description(self, description: str) -> str:
        """Aggressively clean Gherkin syntax and verbose content from descriptions"""
        if not description:
            return ""
        
        clean_desc = description
        
        # Remove Gherkin scenario markers and formatting
        clean_desc = re.sub(r'\*\*Scenario\*\*:.*?(?=\*\*|$)', '', clean_desc, flags=re.DOTALL)
        clean_desc = re.sub(r'Scenario:.*?(?=\n\n|$)', '', clean_desc, flags=re.DOTALL)
        
        # Remove all Gherkin keywords with their content
        gherkin_patterns = [
            r'\*\*Given\*\*.*?(?=\*\*|$)',
            r'\*\*When\*\*.*?(?=\*\*|$)', 
            r'\*\*Then\*\*.*?(?=\*\*|$)',
            r'\*\*And\*\*.*?(?=\*\*|$)',
            r'Given\s+.*?(?=When|Then|And|$)',
            r'When\s+.*?(?=Then|And|Given|$)',
            r'Then\s+.*?(?=And|Given|When|$)',
            r'And\s+.*?(?=Given|When|Then|$)'
        ]
        
        for pattern in gherkin_patterns:
            clean_desc = re.sub(pattern, '', clean_desc, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove markdown formatting
        clean_desc = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_desc)  # **text** -> text
        clean_desc = re.sub(r'\*([^*]+)\*', r'\1', clean_desc)      # *text* -> text
        clean_desc = re.sub(r'#+\s*', '', clean_desc)              # ### headers
        
        # Remove bullet points and numbering
        clean_desc = re.sub(r'^\s*[-*•]\s*', '', clean_desc, flags=re.MULTILINE)
        clean_desc = re.sub(r'^\s*\d+\.\s*', '', clean_desc, flags=re.MULTILINE)
        
        # Remove extra whitespace and line breaks
        clean_desc = re.sub(r'\n+', ' ', clean_desc)
        clean_desc = re.sub(r'\s+', ' ', clean_desc)
        
        # Clean up trailing punctuation and brackets
        clean_desc = re.sub(r'[)\]}\s]*$', '', clean_desc)
        
        return clean_desc.strip()

    def _generate_intelligent_scenario(self, title: str, description: str) -> Dict[str, Any]:
        """Generate intelligent test scenario based on title and context"""
        try:
            if not title:
                return None
                
            title_lower = title.lower()
            
            # Determine scenario type and generate appropriate test
            if 'full payment' in title_lower and ('devtech pay' in title_lower or 'payment system' in title_lower):
                return self._create_full_payment_scenario()
            elif 'split payment' in title_lower:
                return self._create_split_payment_scenario()
            elif 'auto-toggle' in title_lower or 'auto toggle' in title_lower:
                return self._create_auto_toggle_scenario()
            elif 'unavailable' in title_lower and 'payment' in title_lower:
                return self._create_unavailable_payment_scenario()
            elif 'failure' in title_lower and ('split' in title_lower or 'payment' in title_lower):
                return self._create_payment_failure_scenario()
            elif 'wallet' in title_lower or 'balance' in title_lower:
                return self._create_wallet_scenario(title)
            elif 'checkout' in title_lower:
                return self._create_checkout_scenario(title)
            else:
                # Generate generic functional scenario
                return self._create_generic_functional_scenario(title, description)
                
        except Exception as e:
            logger.error(f"Error generating intelligent scenario: {str(e)}")
            return None

    def _create_full_payment_scenario(self) -> Dict[str, Any]:
        """Create intelligent full payment scenario with crisp description"""
        return {
            'title': "Verify Full Payment with DevTech Pay",
            'description': "DevTech Pay processes full payment successfully when order amount is within available balance.",
            'type': 'functional',
            'severity': 'S1 - Critical',
            'priority': 'P1 - Critical'
        }

    def _create_split_payment_scenario(self) -> Dict[str, Any]:
        """Create intelligent split payment scenario with crisp description"""
        return {
            'title': "Verify Split Payment with DevTech Pay and Secondary Payment Method",
            'description': "Split payment functionality works correctly when order amount exceeds available DevTech Pay balance.",
            'type': 'functional', 
            'severity': 'S1 - Critical',
            'priority': 'P1 - Critical'
        }

    def _create_auto_toggle_scenario(self) -> Dict[str, Any]:
        """Create intelligent auto-toggle scenario with crisp description"""
        return {
            'title': "Verify DevTech Pay Auto-Toggle Functionality",
            'description': "DevTech Pay auto-toggle behavior works correctly at checkout with proper payment calculations.",
            'type': 'functional',
            'severity': 'S2 - Major', 
            'priority': 'P2 - High'
        }

    def _create_unavailable_payment_scenario(self) -> Dict[str, Any]:
        """Create intelligent unavailable payment method scenario with crisp description"""
        return {
            'title': "Verify Handling of Unavailable Payment Methods with DevTech Pay",
            'description': "System correctly restricts non-allowed payment methods when using DevTech Pay with clear error messaging.",
            'type': 'functional',
            'severity': 'S2 - Major',
            'priority': 'P2 - High'
        }

    def _create_payment_failure_scenario(self) -> Dict[str, Any]:
        """Create intelligent payment failure scenario with crisp description"""
        return {
            'title': "Verify Payment Failure Handling During Split Payment",
            'description': "System handles secondary payment failures during split payment with proper rollback and refund processing.",
            'type': 'error',
            'severity': 'S1 - Critical',
            'priority': 'P1 - Critical'
        }

    def _create_wallet_scenario(self, title: str) -> Dict[str, Any]:
        """Create intelligent wallet-related scenario with crisp description"""
        return {
            'title': f"Verify {title}",
            'description': "DevTech Pay wallet balance is displayed accurately with correct transaction history and updates.",
            'type': 'functional',
            'severity': 'S2 - Major',
            'priority': 'P2 - High'
        }

    def _create_checkout_scenario(self, title: str) -> Dict[str, Any]:
        """Create intelligent checkout scenario with crisp description"""
        return {
            'title': f"Verify {title}",
            'description': "Checkout process functions correctly with proper payment method selection and order processing.",
            'type': 'functional',
            'severity': 'S1 - Critical',
            'priority': 'P1 - Critical'
        }

    def _create_generic_functional_scenario(self, title: str, description: str) -> Dict[str, Any]:
        """Create generic functional scenario with crisp description"""
        # Create crisp description from the provided description
        clean_desc = description.strip() if description else title
        # Remove verbose language and focus on outcome
        clean_desc = clean_desc.replace("Test ", "").replace("Verify that ", "")
        
        # Ensure it starts with "Verify that" and is concise
        if not clean_desc.lower().startswith('verify'):
            clean_desc = f"Verify that {clean_desc.lower()}"
        
        return {
            'title': title,
            'description': clean_desc,
            'type': 'functional',
            'severity': 'S2 - Major',
            'priority': 'P2 - High'
        }

    def _generate_intelligent_scenario_from_text(self, text: str) -> Dict[str, Any]:
        """Generate intelligent scenario from raw text description with crisp description"""
        try:
            # Clean the text from any Gherkin syntax
            clean_text = self._clean_gherkin_from_description(text)
            
            # Extract core functionality from user story format
            core_functionality = self._extract_core_functionality(clean_text)
            if not core_functionality:
                core_functionality = clean_text[:100]  # Use first 100 chars as fallback
            
            # Generate smart title
            smart_title = self._generate_smart_scenario_title(core_functionality)
            
            # Create crisp description focused on business outcome
            crisp_description = self._create_crisp_business_description(core_functionality)
            
            return {
                'title': smart_title,
                'description': crisp_description,
                'type': 'functional',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
                
        except Exception as e:
            logger.error(f"Error generating scenario from text: {str(e)}")
            return None

    def _create_crisp_business_description(self, functionality: str) -> str:
        """Create crisp, business-focused description from functionality"""
        # Clean up the functionality text
        clean_func = functionality.strip()
        
        # Remove redundant prefixes
        clean_func = clean_func.replace("Test ", "").replace("Verify ", "")
        
        # Create business-focused description
        if 'filter' in clean_func.lower():
            return "System correctly applies filtering criteria and displays relevant results only."
        elif 'display' in clean_func.lower() or 'view' in clean_func.lower():
            return "System displays information accurately with proper formatting and data integrity."
        elif 'carousel' in clean_func.lower():
            return "Item carousel displays correctly with proper navigation and product information."
        elif 'shipment' in clean_func.lower():
            return "Shipment information is displayed accurately with correct status and details."
        elif 'payment' in clean_func.lower():
            return "Payment functionality processes transactions correctly with proper validation."
        else:
            # Generic crisp description
            return f"System correctly implements {clean_func.lower()} functionality with expected behavior."

    def _generate_steps_from_functionality(self, functionality: str) -> List[str]:
        """Generate appropriate test steps based on the functionality"""
        steps = []
        func_lower = functionality.lower()
        
        # Add login step
        steps.append("Log in as a user with appropriate credentials")
        
        # Add navigation step based on functionality context
        if 'shipment' in func_lower or 'shipsy' in func_lower:
            steps.append("Navigate to the shipment management section")
        elif 'marketplace' in func_lower:
            steps.append("Navigate to marketplace section")
        elif 'dashboard' in func_lower:
            steps.append("Navigate to the dashboard")
        else:
            steps.append("Navigate to the relevant section")
        
        # Add functionality-specific steps
        if 'view' in func_lower or 'display' in func_lower or 'see' in func_lower:
            steps.append(f"Attempt to {functionality.lower()}")
            steps.append("Verify that the information is displayed correctly")
            steps.append("Verify that all required data is visible")
            if 'filter' in func_lower or 'date' in func_lower:
                steps.append("Verify that filtering/date selection works correctly")
        elif 'create' in func_lower or 'add' in func_lower:
            steps.append(f"Attempt to {functionality.lower()}")
            steps.append("Verify that the creation process completes successfully")
            steps.append("Verify that the new item appears in the system")
        elif 'update' in func_lower or 'edit' in func_lower:
            steps.append(f"Attempt to {functionality.lower()}")
            steps.append("Verify that the update process completes successfully")
            steps.append("Verify that changes are saved and reflected correctly")
        else:
            steps.append(f"Execute the functionality: {functionality}")
            steps.append("Verify that the action completes successfully")
            steps.append("Verify that the expected results are achieved")
        
        # Add final validation step
        steps.append("Verify that the system state is correct after the operation")
        
        return steps

    def _generate_gherkin_scenario(self, title: str, gherkin: Dict[str, Any], parent_title: str) -> Dict[str, Any]:
        """Generate crisp scenario from Gherkin format - NO VERBOSE GHERKIN SYNTAX"""
        try:
            # Extract the core business intent from Gherkin without verbose syntax
            business_intent = self._extract_business_intent_from_gherkin(gherkin)
            
            # Create crisp title without Gherkin syntax
            clean_title = self._create_crisp_title_from_gherkin(gherkin, parent_title)
            
            # Create crisp description focused on what's being verified
            crisp_description = self._create_crisp_description_from_gherkin(gherkin)
            
            return {
                'title': clean_title,
                'description': crisp_description,
                'type': 'functional',
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            }
            
        except Exception as e:
            logger.error(f"Error generating scenario from Gherkin: {str(e)}")
            return None

    def _extract_business_intent_from_gherkin(self, gherkin: Dict[str, Any]) -> str:
        """Extract core business intent from Gherkin without verbose syntax"""
        # Focus on the 'then' clause as it contains the expected outcome
        if gherkin.get('then'):
            intent = gherkin['then'].strip()
            # Clean up common Gherkin language
            intent = intent.replace('I can see', 'displays')
            intent = intent.replace('I should see', 'shows')
            intent = intent.replace('the system should', 'system')
            return intent
        
        # Fallback to 'when' clause
        if gherkin.get('when'):
            return gherkin['when'].strip()
            
        return "functional behavior"

    def _create_crisp_title_from_gherkin(self, gherkin: Dict[str, Any], parent_title: str) -> str:
        """Create crisp, business-focused title from Gherkin"""
        # Extract the key action or verification point
        if gherkin.get('then'):
            then_clause = gherkin['then'].strip()
            # Extract core verification without verbose language
            if 'filtering' in then_clause:
                return "Verify item filtering functionality"
            elif 'carousel' in then_clause:
                return "Verify shipment item carousel display"
            elif 'display' in then_clause or 'see' in then_clause:
                return "Verify item display and information"
            else:
                # Use first few words of then clause, cleaned up
                words = then_clause.split()[:6]
                return f"Verify {' '.join(words).lower()}"
        
        # Fallback to action-based title from when clause
        if gherkin.get('when'):
            when_clause = gherkin['when'].strip()
            if 'shipping section' in when_clause:
                return "Verify shipping section functionality"
            else:
                words = when_clause.split()[:4]
                return f"Verify {' '.join(words).lower()} functionality"
        
        return "Verify functional requirement"

    def _create_crisp_description_from_gherkin(self, gherkin: Dict[str, Any]) -> str:
        """Create crisp, business-focused description from Gherkin"""
        # Focus on the business outcome, not the steps
        if gherkin.get('then'):
            then_clause = gherkin['then'].strip()
            
            # Create specific, crisp descriptions based on content
            if 'filtering' in then_clause and 'SKU' in then_clause:
                return "System correctly filters items based on unique SKUs and displays relevant products only."
            elif 'carousel' in then_clause:
                return "Shipment item carousel displays correctly with proper product information and quantities."
            elif 'quantity' in then_clause and 'product' in then_clause:
                return "Product quantities are accurately displayed with correct count information."
            else:
                # Generic crisp description
                clean_outcome = then_clause.replace('I can see', 'System displays')
                clean_outcome = clean_outcome.replace('I should see', 'System shows')
                return f"Verify that {clean_outcome.lower()}."
        
        # Fallback description
        return "System functionality works as expected according to business requirements."

    def _generate_error_scenario_for_criterion(self, title: str, description: str) -> Dict[str, Any]:
        """Generate error/negative test scenario for acceptance criterion with crisp description"""
        try:
            error_title = f"Error Handling for {title}"
            
            # Create crisp error description based on content
            if 'payment' in title.lower():
                crisp_description = "System handles payment errors gracefully with appropriate user feedback and recovery options."
            elif 'validation' in title.lower():
                crisp_description = "System validates input correctly and provides clear error messages for invalid data."
            elif 'authentication' in title.lower():
                crisp_description = "System handles authentication failures securely with proper error messaging."
            else:
                crisp_description = f"System handles errors gracefully during {title.lower()} operations with appropriate user guidance."
            
            return {
                'title': error_title,
                'description': crisp_description,
                'type': 'error',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            
        except Exception as e:
            logger.error(f"Error generating error scenario: {str(e)}")
            return None

    def _generate_boundary_scenario_for_criterion(self, title: str, description: str) -> Dict[str, Any]:
        """Generate boundary/edge case scenario for acceptance criterion with crisp description"""
        try:
            boundary_title = f"Boundary Testing for {title}"
            
            # Create crisp boundary description based on content
            if 'data' in title.lower() or 'input' in title.lower():
                crisp_description = "System correctly handles edge cases for data input limits and boundary conditions."
            elif 'performance' in title.lower():
                crisp_description = "System maintains acceptable performance under boundary load conditions."
            elif 'capacity' in title.lower():
                crisp_description = "System operates correctly at maximum capacity limits without degradation."
            else:
                crisp_description = f"System handles boundary conditions correctly for {title.lower()} functionality."
            
            return {
                'title': boundary_title,
                'description': crisp_description,
                'type': 'boundary',
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            }
            
        except Exception as e:
            logger.error(f"Error generating boundary scenario: {str(e)}")
            return None

    def _generate_generic_test_steps(self, description: str) -> List[str]:
        """Generate generic test steps for basic descriptions"""
        steps = ["Log in as a user with valid credentials"]
        
        # Add context-specific steps based on description keywords
        if 'wallet' in description.lower() or 'balance' in description.lower():
            steps.append("Navigate to wallet or account page")
        if 'checkout' in description.lower() or 'payment' in description.lower():
            steps.append("Navigate to checkout page")
        
        # Add action step
        steps.append(f"Perform the required action: {description}")
        
        # Add verification steps
        steps.extend([
            "Verify the action completes successfully",
            "Validate all expected outcomes",
            "Confirm system state is correct"
        ])
        
        return steps

    def _generate_base_scenario(self, description: str, analysis: Dict[str, Any], scenario_type: str) -> Dict[str, Any]:
        """Generate base scenario with intelligent steps and crisp description"""
        try:
            # Clean the description and create crisp version
            clean_description = self._clean_gherkin_from_description(description)
            
            # Create crisp business description
            if 'payment' in clean_description.lower():
                crisp_description = "Payment functionality processes transactions correctly with proper validation and user feedback."
            elif 'validation' in clean_description.lower():
                crisp_description = "System validates data according to business rules and provides appropriate feedback."
            elif 'authentication' in clean_description.lower():
                crisp_description = "Authentication system verifies user credentials securely and manages access appropriately."
            elif 'navigation' in clean_description.lower():
                crisp_description = "Navigation functionality provides seamless user experience with proper page transitions."
            elif 'display' in clean_description.lower() or 'view' in clean_description.lower():
                crisp_description = "System displays information accurately with proper formatting and complete data."
            elif 'create' in clean_description.lower() or 'add' in clean_description.lower():
                crisp_description = "Creation functionality allows users to add new items with proper validation and confirmation."
            elif 'update' in clean_description.lower() or 'edit' in clean_description.lower():
                crisp_description = "Update functionality modifies existing data correctly with validation and audit trail."
            elif 'filter' in clean_description.lower() or 'search' in clean_description.lower():
                crisp_description = "Filtering and search functionality returns accurate results based on specified criteria."
            else:
                # Generic crisp description
                crisp_description = f"System correctly implements the required functionality with expected behavior and proper user experience."
            
            # Generate smart title
            title = self._generate_smart_scenario_title(clean_description)
            
            return {
                'title': title,
                'description': crisp_description,
                'type': scenario_type,
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            
        except Exception as e:
            logger.error(f"Error generating base scenario: {str(e)}")
            return None

    def _format_scenario_description(self, scenario_type: str, description: str, steps: List[str]) -> str:
        """Format scenario description to be crisp and meaningful - no steps included"""
        # Clean and format the description to be concise and impactful
        clean_desc = description.replace("Test ", "").replace("Verify that the system correctly implements the requirement: ", "")
        clean_desc = clean_desc.replace("Test functionality: ", "").replace("functionality: ", "")
        clean_desc = clean_desc.replace("Test system behavior when ", "System behavior when ")
        clean_desc = clean_desc.replace("Test automatic toggling behavior of ", "Auto-toggle behavior of ")
        clean_desc = clean_desc.replace("Test ", "")
        
        # Ensure first letter is capitalized
        if clean_desc:
            clean_desc = clean_desc[0].upper() + clean_desc[1:] if len(clean_desc) > 1 else clean_desc.upper()
        
        # Add "Verify that" prefix if not already present
        if not clean_desc.lower().startswith('verify'):
            clean_desc = f"Verify that {clean_desc.lower()}"
        
        # Return only the clean description - NO STEPS
        return clean_desc

    def _get_prerequisites_for_action(self, action: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        """Get prerequisite steps for an action"""
        prerequisites = []
        
        # Add data setup steps
        if action['required_fields']:
            prerequisites.append(f"Prepare test data for {', '.join(action['required_fields'])}")
        
        # Add dependency setup steps
        for dep in action.get('dependencies', []):
            prerequisites.append(f"Set up {dep['type']} dependency: {dep['description']}")
        
        # Add business rule setup steps
        for rule in action['business_rules']:
            if rule.get('preconditions'):
                prerequisites.append(f"Configure business rule: {rule['description']}")
        
        return prerequisites

    def _get_action_steps(self, action: Dict[str, Any]) -> List[str]:
        """Get steps for executing an action"""
        steps = []
        
        # Add data input steps
        for field in action['required_fields']:
            steps.append(f"Enter valid data for {field}")
        
        # Add action execution step
        action_type = action['type']
        if action_type == 'create':
            steps.append(f"Click Create/Submit button")
        elif action_type == 'update':
            steps.append(f"Make the required changes")
            steps.append(f"Click Save/Update button")
        elif action_type == 'delete':
            steps.append(f"Select the item to delete")
            steps.append(f"Confirm deletion")
        elif action_type == 'view':
            steps.append(f"View the {action['description']}")
        
        return steps

    def _get_verification_steps(self, action: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        """Get verification steps for an action"""
        steps = []
        
        # Add basic verification
        steps.append(f"Verify the {action['type']} operation is successful")
        
        # Add data verification steps
        for field in action['required_fields']:
            steps.append(f"Verify {field} is correctly saved/updated")
        
        # Add business rule verification steps
        for rule in action['business_rules']:
            steps.append(f"Verify business rule: {rule['description']}")
        
        # Add UI verification steps
        if action['type'] in ['create', 'update']:
            steps.append("Verify success message is displayed")
            steps.append("Verify the changes are reflected in the UI")
        
        return steps

    def _is_action_related(self, description: str, action: Dict[str, Any]) -> bool:
        """Check if an action is related to a description"""
        description_lower = description.lower()
        action_desc_lower = action['description'].lower()
        
        # Check direct match
        if action_desc_lower in description_lower:
            return True
        
        # Check action type match
        action_type = action['type']
        if action_type in description_lower:
            return True
        
        # Check semantic similarity
        similarity = self._calculate_similarity(description_lower, action_desc_lower)
        return similarity > 0.5  # Threshold for similarity

    def _determine_action_type(self, description: str) -> str:
        """Determine the type of action from description"""
        description_lower = description.lower()
        
        if any(word in description_lower for word in ['create', 'add', 'new']):
            return 'create'
        elif any(word in description_lower for word in ['update', 'edit', 'modify']):
            return 'update'
        elif any(word in description_lower for word in ['delete', 'remove']):
            return 'delete'
        elif any(word in description_lower for word in ['view', 'see', 'display']):
            return 'view'
        elif any(word in description_lower for word in ['process', 'handle']):
            return 'process'
        else:
            return 'other'

    def _analyze_story_content(self, description: str, acceptance_criteria: str) -> Dict[str, Any]:
        """Enhanced story content analysis with better context understanding"""
        try:
            if not description:
                logger.error("Description is required for story analysis")
                return {}

            # Initialize analysis components with empty defaults
            components = {
                'user_journey': {'actors': [], 'goals': [], 'entry_points': [], 'exit_points': [], 'user_actions': [], 'system_responses': []},
                'business_context': {'domain': None, 'user_type': None, 'business_area': None, 'dependencies': [], 'constraints': []},
                'technical_requirements': {'ui_components': [], 'data_fields': [], 'integrations': [], 'performance': [], 'security': [], 'technical_constraints': []},
                'data_requirements': [],
                'validation_rules': [],
                'error_scenarios': [],
                'edge_cases': [],
                'dependencies': [],
                'preconditions': [],
                'acceptance_criteria': []
            }

            # Extract core components with error handling
            try:
                components['user_journey'] = self._extract_user_journey(description) or components['user_journey']
            except Exception as e:
                logger.error(f"Error extracting user journey: {str(e)}")

            try:
                components['business_context'] = self._extract_business_context(description) or components['business_context']
            except Exception as e:
                logger.error(f"Error extracting business context: {str(e)}")

            try:
                components['technical_requirements'] = self._extract_technical_requirements(description) or components['technical_requirements']
            except Exception as e:
                logger.error(f"Error extracting technical requirements: {str(e)}")

            try:
                components['data_requirements'] = self._extract_data_requirements(description) or []
            except Exception as e:
                logger.error(f"Error extracting data requirements: {str(e)}")

            try:
                components['validation_rules'] = self._extract_validation_rules(description + "\n" + (acceptance_criteria or "")) or []
            except Exception as e:
                logger.error(f"Error extracting validation rules: {str(e)}")

            try:
                components['error_scenarios'] = self._extract_error_scenarios(description + "\n" + (acceptance_criteria or "")) or []
            except Exception as e:
                logger.error(f"Error extracting error scenarios: {str(e)}")

            try:
                components['edge_cases'] = self._extract_edge_cases(description + "\n" + (acceptance_criteria or "")) or []
            except Exception as e:
                logger.error(f"Error extracting edge cases: {str(e)}")

            try:
                components['dependencies'] = self._extract_dependencies(description) or []
            except Exception as e:
                logger.error(f"Error extracting dependencies: {str(e)}")

            try:
                components['preconditions'] = self._extract_preconditions(description + "\n" + (acceptance_criteria or "")) or []
            except Exception as e:
                logger.error(f"Error extracting preconditions: {str(e)}")

            try:
                components['acceptance_criteria'] = self._extract_acceptance_criteria(acceptance_criteria or "") or []
            except Exception as e:
                logger.error(f"Error extracting acceptance criteria: {str(e)}")

            # Analyze relationships and dependencies with validation
            analysis = {
                'main_functionality': {},
                'user_flows': [],
                'data_flows': [],
                'validations': [],
                'error_scenarios': [],
                'business_rules': [],
                'user_actions': [],
                'system_responses': [],
                'acceptance_criteria': components['acceptance_criteria']
            }

            # Analyze main functionality
            try:
                analysis['main_functionality'] = self._analyze_main_functionality(components) or {}
            except Exception as e:
                logger.error(f"Error analyzing main functionality: {str(e)}")

            # Analyze user flows
            try:
                analysis['user_flows'] = self._extract_user_flows(description) or []
            except Exception as e:
                logger.error(f"Error analyzing user flows: {str(e)}")

            # Analyze data flows
            try:
                analysis['data_flows'] = self._extract_data_flows(description) or []
            except Exception as e:
                logger.error(f"Error analyzing data flows: {str(e)}")

            # Set validations
            try:
                analysis['validations'] = components['validation_rules']
            except Exception as e:
                logger.error(f"Error setting validations: {str(e)}")

            # Set error scenarios
            try:
                analysis['error_scenarios'] = components['error_scenarios']
            except Exception as e:
                logger.error(f"Error setting error scenarios: {str(e)}")

            # Extract business rules
            try:
                analysis['business_rules'] = self._extract_business_rules(description) or []
            except Exception as e:
                logger.error(f"Error extracting business rules: {str(e)}")

            # Set user actions from journey
            try:
                analysis['user_actions'] = components['user_journey']['user_actions']
            except Exception as e:
                logger.error(f"Error setting user actions: {str(e)}")

            # Set system responses from journey
            try:
                analysis['system_responses'] = components['user_journey']['system_responses']
            except Exception as e:
                logger.error(f"Error setting system responses: {str(e)}")

            # Validate final analysis
            if not any(analysis.values()):
                logger.warning("No analysis components were generated")
                return {}

            return analysis

        except Exception as e:
            logger.error(f"Error in story analysis: {str(e)}")
            return {}

    def _extract_user_journey(self, text: str) -> Dict[str, Any]:
        """Extract detailed user journey information"""
        journey = {
            'actors': [],
            'goals': [],
            'entry_points': [],
            'exit_points': [],
            'user_actions': [],
            'system_responses': []
        }
        
        # Extract actors (with roles and permissions)
        actor_patterns = [
            r'(?:as\s+(?:a|an)\s+)?(\w+(?:\s+\w+)*?)(?:\s+with\s+([\w\s,]+)\s+permissions?)?\s+(?:should|must|will|can)',
            r'(?:the\s+)?(\w+(?:\s+\w+)*?)(?:\s+who\s+(?:has|have)\s+([\w\s,]+))?\s+(?:should|must|will|can)'
        ]
        
        for pattern in actor_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                actor = {
                    'type': match.group(1).strip().lower(),
                    'permissions': [p.strip() for p in match.group(2).split(',')] if match.group(2) else []
                }
                if actor not in journey['actors']:
                    journey['actors'].append(actor)

        # Extract user goals
        goal_patterns = [
            r'(?:to|should|must|will|can)\s+((?:view|create|update|delete|manage|process|handle|review|approve|reject)\s+[\w\s]+)',
            r'(?:wants|needs)\s+to\s+([\w\s]+?)(?:\s+to\s+|$|\.|,)'
        ]
        
        for pattern in goal_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                goal = match.group(1).strip().lower()
                if goal not in journey['goals']:
                    journey['goals'].append(goal)

        # Extract entry points
        entry_patterns = [
            r'(?:from|on|in|at)\s+(?:the\s+)?([\w\s-]+?(?:page|screen|view|section|module))',
            r'(?:navigates?|goes?|visits?)\s+to\s+(?:the\s+)?([\w\s-]+?(?:page|screen|view|section|module))'
        ]
        
        for pattern in entry_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                entry_point = match.group(1).strip().lower()
                if entry_point not in journey['entry_points']:
                    journey['entry_points'].append(entry_point)

        # Extract user actions with context
        action_patterns = [
            (r'(?:clicks?|selects?|chooses?)\s+([\w\s-]+)', 'click'),
            (r'(?:enters?|inputs?|types?)\s+([\w\s-]+)', 'input'),
            (r'(?:uploads?|downloads?)\s+([\w\s-]+)', 'file'),
            (r'(?:submits?|saves?|confirms?)\s+([\w\s-]+)', 'submit'),
            (r'(?:views?|checks?|reviews?)\s+([\w\s-]+)', 'view')
        ]
        
        for pattern, action_type in action_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                action = {
                    'type': action_type,
                    'target': match.group(1).strip(),
                    'context': self._extract_action_context(match.group(0))
                }
                journey['user_actions'].append(action)

        # Extract system responses
        response_patterns = [
            (r'system\s+(?:should|must|will)\s+([\w\s-]+)', 'system'),
            (r'(?:displays?|shows?|presents?)\s+([\w\s-]+)', 'ui'),
            (r'(?:validates?|verifies?|checks?)\s+([\w\s-]+)', 'validation'),
            (r'(?:calculates?|processes?|generates?)\s+([\w\s-]+)', 'processing')
        ]
        
        for pattern, response_type in response_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                response = {
                    'type': response_type,
                    'action': match.group(1).strip(),
                    'context': self._extract_action_context(match.group(0))
                }
                journey['system_responses'].append(response)

        return journey

    def _extract_business_context(self, text: str) -> Dict[str, Any]:
        """Extract business context from text"""
        context = {
            'domain': None,
            'user_type': None,
            'business_area': None,
            'dependencies': [],
            'constraints': []
        }
        
        # Extract domain/area
        domain_patterns = [
            (r'(?:in|for|within)\s+the\s+([^.]+?)\s+(?:domain|area|module)', 'domain'),
            (r'(?:related\s+to|concerning)\s+([^.]+?)\s+(?:functionality|feature)', 'domain')
        ]
        
        for pattern, key in domain_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                context[key] = match.group(1).strip()
                break
        
        # Extract user type
        user_patterns = [
            r'(?:as\s+a|for\s+the)\s+([^.]+?)\s+(?:user|role|persona)',
            r'(buyer|seller|admin|customer|user)\s+(?:should|must|can|will)'
        ]
        
        for pattern in user_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if match.groups():  # Check if groups exist
                    context['user_type'] = match.group(1).strip()
                else:
                    # Fallback: extract first word from match
                    context['user_type'] = match.group(0).split()[0]
                break
        
        # Extract business area
        area_patterns = [
            r'in\s+the\s+([^.]+?)\s+(?:section|area|part)',
            r'under\s+([^.]+?)\s+(?:management|process|flow)'
        ]
        
        for pattern in area_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                context['business_area'] = match.group(1).strip()
                break
        
        # Extract dependencies
        dependency_patterns = [
            r'depends\s+on\s+([^.]+)',
            r'requires\s+([^.]+)',
            r'needs\s+([^.]+)\s+to\s+be'
        ]
        
        for pattern in dependency_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context['dependencies'].append(match.group(1).strip())
        
        # Extract constraints
        constraint_patterns = [
            r'must\s+(?:be|have)\s+([^.]+)',
            r'should\s+(?:be|have)\s+([^.]+)',
            r'only\s+(?:if|when)\s+([^.]+)',
            r'limited\s+to\s+([^.]+)'
        ]
        
        for pattern in constraint_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                context['constraints'].append(match.group(1).strip())
        
        return context

    def _analyze_main_functionality(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze main functionality with better context understanding"""
        try:
            if not components or not isinstance(components, dict):
                logger.error("Invalid components for main functionality analysis")
                return {}

            # Initialize with safe defaults
            functionality = {
                'primary_actions': [],
                'actors': [],
                'business_rules': [],
                'validations': [],
                'data_operations': [],
                'ui_components': [],
                'dependencies': []
            }

            # Extract actors safely
            user_journey = components.get('user_journey', {})
            if isinstance(user_journey, dict):
                functionality['actors'] = user_journey.get('actors', [])

            # Extract primary actions from user journey
            goals = user_journey.get('goals', []) if isinstance(user_journey, dict) else []
            
            for goal in goals:
                if not isinstance(goal, str):
                    logger.warning(f"Invalid goal format: {goal}")
                    continue
                    
                action = {
                    'type': self._determine_action_type(goal),
                    'description': goal,
                    'actors': [actor for actor in functionality['actors'] if self._is_action_applicable(goal, actor)],
                    'required_fields': self._extract_required_fields(goal, components),
                    'validation_rules': self._extract_applicable_validations(goal, components),
                    'business_rules': self._extract_applicable_rules(goal, components)
                }
                functionality['primary_actions'].append(action)

            # Extract UI components safely
            tech_reqs = components.get('technical_requirements', {})
            if isinstance(tech_reqs, dict):
                ui_components = tech_reqs.get('ui_components', [])
                if isinstance(ui_components, list):
                    functionality['ui_components'] = ui_components

            # Extract business rules safely
            business_rules = components.get('business_rules', [])
            if isinstance(business_rules, list):
                functionality['business_rules'] = business_rules

            # Extract validations safely
            validation_rules = components.get('validation_rules', [])
            if isinstance(validation_rules, list):
                functionality['validations'] = validation_rules

            # Extract data operations safely
            data_reqs = components.get('data_requirements', [])
            if isinstance(data_reqs, list):
                functionality['data_operations'] = [
                    req for req in data_reqs 
                    if isinstance(req, dict) and req.get('type') == 'operation'
                ]

            # Extract dependencies safely
            dependencies = components.get('dependencies', [])
            if isinstance(dependencies, list):
                functionality['dependencies'] = dependencies

            return functionality
            
        except Exception as e:
            logger.error(f"Error analyzing main functionality: {str(e)}")
            return {
                'primary_actions': [],
                'actors': [],
                'business_rules': [],
                'validations': [],
                'data_operations': [],
                'ui_components': [],
                'dependencies': []
            }

    def _extract_component_validations(self, component_desc: str, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract validations specific to a UI component"""
        try:
            if not isinstance(component_desc, str):
                return []
                
            validations = []
            component_desc_lower = component_desc.lower()
            
            # Extract from validation rules
            all_validations = components.get('validation_rules', [])
            for validation in all_validations:
                if not isinstance(validation, dict):
                    continue
                    
                validation_desc = validation.get('description', '').lower()
                if any(word in validation_desc for word in component_desc_lower.split()):
                    validations.append(validation)
            
            # Add common component validations
            if 'input' in component_desc_lower or 'field' in component_desc_lower:
                validations.append({
                    'type': 'ui_validation',
                    'description': 'Field should be properly rendered and interactive',
                    'severity': 'S3 - Moderate'
                })
                
            if 'button' in component_desc_lower:
                validations.append({
                    'type': 'ui_validation',
                    'description': 'Button should be properly rendered and clickable',
                    'severity': 'S3 - Moderate'
                })
                
            if 'form' in component_desc_lower:
                validations.append({
                    'type': 'ui_validation',
                    'description': 'Form should be properly rendered with all fields',
                    'severity': 'S3 - Moderate'
                })
            
            return validations
            
        except Exception as e:
            logger.error(f"Error extracting component validations: {str(e)}")
            return []

    def _generate_steps_from_criterion(self, criterion: str, analysis: Dict[str, Any]) -> List[str]:
        """Generate steps from acceptance criterion"""
        steps = []
        
        # Extract explicit steps if any
        explicit_steps = re.findall(r'\d+\.\s*([^\n]+)', criterion)
        if explicit_steps:
            for step in explicit_steps:
                steps.append(step.strip())
            return steps
            
        # Add login step if needed
        if any(word in criterion.lower() for word in ['login', 'user', 'account']):
            steps.append("Log in as a user with valid credentials")
            
        # Add navigation step if we can determine the page
        page = self._extract_page_from_description(criterion)
        if page:
            steps.append(f"Navigate to {page}")
            
        # Extract actions and verification steps
        actions = self._extract_action_steps_from_rule(criterion)
        verify_steps = self._extract_verification_steps_from_rule(criterion)
        
        if actions or verify_steps:
            steps.extend(actions)
            steps.extend(verify_steps)
        else:
            # Default steps if no specific actions found
            steps.append("Perform the required action")
            steps.append("Verify the expected outcome")
            
        return steps

    def _process_scenarios(self, scenarios: List[Dict[str, Any]], story: Dict) -> List[Dict[str, Any]]:
        """Process and deduplicate scenarios with enhanced validation"""
        try:
            if not scenarios or not isinstance(scenarios, list):
                logger.error("Invalid scenarios input")
                return []

            if not story or not isinstance(story, dict):
                logger.error("Invalid story input")
                return []

            processed = []
            seen_titles = set()
            seen_descriptions = set()
            
            # Get the creator/reporter to use as assignee
            story_fields = story.get('fields', {})
            creator = story_fields.get('creator', {}).get('name') if story_fields else None
            
            # Get story metadata for context
            story_type = story_fields.get('issuetype', {}).get('name', '')
            story_priority = story_fields.get('priority', {}).get('name', '')
            
            for scenario in scenarios:
                try:
                    # Validate scenario structure
                    if not isinstance(scenario, dict):
                        logger.warning("Invalid scenario format - skipping")
                        continue
                        
                    if not scenario.get('title') or not scenario.get('description'):
                        logger.warning("Scenario missing required fields - skipping")
                        continue
                    
                    # Clean up title and description
                    title = re.sub(r'\s+', ' ', scenario['title']).strip()
                    description = re.sub(r'\s+', ' ', scenario['description']).strip()
                    
                    # Normalize title and description for comparison
                    title_normalized = re.sub(r'^(verify|validate|check|test)\s+', '', title.lower())
                    description_normalized = description.lower()
                    
                    # Check for duplicates using both title and description
                    if title_normalized in seen_titles or description_normalized in seen_descriptions:
                        logger.info(f"Skipping duplicate scenario: {title}")
                        continue
                        
                    seen_titles.add(title_normalized)
                    seen_descriptions.add(description_normalized)
                    
                    # Determine scenario severity and priority based on type and story context
                    severity = self._determine_severity(scenario, story_type)
                    priority = self._determine_priority(scenario, story_priority)
                    
                    # Add metadata including assignee from creator
                    processed_scenario = {
                        'title': title,
                        'description': description,
                        'type': scenario.get('type', 'functional'),
                        'severity': severity,
                        'priority': priority,
                        'automation': scenario.get('automation', 'Manual'),
                        'assignee': creator,
                        'ticket_info': {
                            'key': story.get('key', ''),
                            'summary': story_fields.get('summary', ''),
                            'type': story_type,
                            'priority': story_priority
                        }
                    }
                    
                    # Add optional fields if present
                    if 'journey' in scenario:
                        processed_scenario['journey'] = scenario['journey']
                        
                    if 'automation_status' in scenario:
                        processed_scenario['automation_status'] = scenario['automation_status']
                    
                    processed.append(processed_scenario)
                    
                except Exception as e:
                    logger.error(f"Error processing scenario: {str(e)}")
                    continue
            
            # Sort scenarios by priority and severity
            processed.sort(key=lambda x: (
                self._priority_order(x['priority']),
                self._severity_order(x['severity'])
            ))
            
            return processed
            
        except Exception as e:
            logger.error(f"Error in scenario processing: {str(e)}")
            return []
            
    def _determine_severity(self, scenario: Dict[str, Any], story_type: str) -> str:
        """Determine scenario severity based on type and context"""
        # Default severity mapping
        type_severity_map = {
            'error_handling': 'S1 - Critical',
            'security': 'S1 - Critical',
            'data_validation': 'S2 - Major',
            'business_rule': 'S2 - Major',
            'functional': 'S2 - Major',
            'ui': 'S3 - Moderate',
            'enhancement': 'S4 - Low'
        }
        
        # Story type severity overrides
        story_severity_map = {
            'Bug': 'S2 - Major',
            'Security': 'S1 - Critical',
            'Task': 'S3 - Moderate'
        }
        
        # Get base severity from scenario type
        base_severity = type_severity_map.get(
            scenario.get('type', 'functional').lower(),
            'S3 - Moderate'
        )
        
        # Override with story-based severity if applicable
        if story_type in story_severity_map:
            if story_severity_map[story_type] < base_severity:
                return story_severity_map[story_type]
        
        return base_severity
        
    def _determine_priority(self, scenario: Dict[str, Any], story_priority: str) -> str:
        """Determine scenario priority based on type and context"""
        # Default priority mapping
        type_priority_map = {
            'error_handling': 'P1 - Critical',
            'security': 'P1 - Critical',
            'data_validation': 'P2 - High',
            'business_rule': 'P2 - High',
            'functional': 'P2 - High',
            'ui': 'P3 - Medium',
            'enhancement': 'P4 - Low'
        }
        
        # Story priority mapping
        story_priority_map = {
            'Highest': 'P1 - Critical',
            'High': 'P2 - High',
            'Medium': 'P3 - Medium',
            'Low': 'P4 - Low'
        }
        
        # Get base priority from scenario type
        base_priority = type_priority_map.get(
            scenario.get('type', 'functional').lower(),
            'P3 - Medium'
        )
        
        # Override with story-based priority if applicable
        if story_priority in story_priority_map:
            if story_priority_map[story_priority] < base_priority:
                return story_priority_map[story_priority]
        
        return base_priority
        
    def _priority_order(self, priority: str) -> int:
        """Get numeric order for priority sorting"""
        priority_order = {
            'P1 - Critical': 1,
            'P2 - High': 2,
            'P3 - Medium': 3,
            'P4 - Low': 4
        }
        return priority_order.get(priority, 5)
        
    def _severity_order(self, severity: str) -> int:
        """Get numeric order for severity sorting"""
        severity_order = {
            'S1 - Critical': 1,
            'S2 - Major': 2,
            'S3 - Moderate': 3,
            'S4 - Low': 4
        }
        return severity_order.get(severity, 5)

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using a simple algorithm"""
        # Convert texts to sets of words
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0

    def generate_test_scenarios(self, story: Dict, verbose: bool = False) -> str:
        """Generate comprehensive test scenarios using robust approach"""
        try:
            # Validate input story
            if not isinstance(story, dict):
                logger.error("Invalid story input: must be a dictionary")
                return json.dumps([])
                
            # Extract story details with validation
            story_fields = story.get('fields', {})
            if not story_fields:
                logger.error("Story fields not found")
                return json.dumps([])
                
            # Extract and validate description
            description = self._extract_plain_text(story_fields.get('description', ''))
            if not description:
                if verbose:
                    logger.warning("Story description is empty, using summary as fallback")
                description = self._extract_plain_text(story_fields.get('summary', ''))
                if not description:
                    logger.error("Neither description nor summary found in story")
                    return json.dumps([])

            # Use the new comprehensive approach as primary method
            scenarios = self.generate_comprehensive_scenarios(description)
            
            # If comprehensive approach doesn't generate scenarios, fall back to content-agnostic method
            if not scenarios:
                if verbose:
                    logger.info("Comprehensive approach produced no scenarios, falling back to content-agnostic method")
                scenarios = self.generate_content_agnostic_scenarios(description)
            
            # If still no scenarios, fall back to original method
            if not scenarios:
                if verbose:
                    logger.info("Content-agnostic approach produced no scenarios, falling back to original method")
                story_analysis = self._analyze_story_content(description, description)
                if story_analysis:
                    scenarios = self._generate_ac_scenarios(story_analysis)
            
            # Process scenarios with validation
            if not scenarios:
                if verbose:
                    logger.warning("No scenarios were generated")
                return json.dumps([])

            # Process scenarios (preserve existing processing)
            processed_scenarios = self._process_scenarios(scenarios, story)

            return json.dumps(processed_scenarios, indent=2)
            
        except Exception as e:
            logger.error(f"Failed to generate test scenarios: {str(e)}")
            return json.dumps([])

    def _format_scenario_title(self, action: str, context: Dict[str, Any] = None) -> str:
        """Format a scenario title to be clear and grammatically correct"""
        # Clean up the action text
        action = action.strip().lower()
        
        # Remove common verbs if they're at the start of the action
        common_verbs = ['see', 'verify', 'check', 'test', 'validate']
        for verb in common_verbs:
            if action.startswith(verb + ' '):
                action = action[len(verb):].strip()
        
        # Add appropriate verb based on the type of action
        if 'display' in action or 'show' in action or 'see' in action:
            title = f"Verify display of {action.replace('display', '').replace('show', '').replace('see', '').strip()}"
        elif 'enable' in action or 'disable' in action:
            title = f"Verify {action}"
        elif action.startswith('if') or action.startswith('when'):
            title = f"Verify behavior {action}"
        else:
            title = f"Verify ability to {action}"
            
        # Add context if available
        if context:
            if context.get('page'):
                title += f" on {context['page']}"
            if context.get('section'):
                title += f" in {context['section']}"
                
        return title.strip()

    def _generate_functionality_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on main functionality"""
        try:
            if not analysis or not isinstance(analysis, dict):
                logger.warning("Invalid analysis object for functionality scenarios")
                return []

            scenarios = []
            functionality = analysis.get('main_functionality', {})
            
            for action in functionality.get('primary_actions', []):
                if not isinstance(action, dict) or not action.get('description'):
                    continue
                    
                description = self._clean_scenario_text(action['description'])
                scenario = self._generate_base_scenario(description, analysis, 'functionality')
                if scenario:
                    scenarios.append(scenario)
                    
                    # Generate validation scenario if applicable
                    if action.get('validation_rules'):
                        validation_scenario = self._generate_base_scenario(description, analysis, 'validation')
                        if validation_scenario:
                            scenarios.append(validation_scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating functionality scenarios: {str(e)}")
            return []

    def _generate_action_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on user actions"""
        try:
            scenarios = []
            
            for action in analysis.get('user_actions', []):
                if not isinstance(action, dict):
                    continue
                    
                description = action.get('description', '')
                if not description:
                    continue
                    
                description = text_formatter.clean_scenario_text(description)
                steps = []
                
                # Add login step if needed
                if any(word in description.lower() for word in ['login', 'user', 'account']):
                    steps.append("Log in as appropriate user")
                
                # Add navigation step if context available
                context = action.get('context', {})
                if context.get('page'):
                    steps.append(f"Navigate to {context['page']}")
                
                # Add action steps
                steps.append(description)
                
                # Add verification
                steps.append("Verify the action is completed successfully")
                
                # Use centralized formatter instead of manual concatenation
                formatted_description = self._format_scenario_description('functional', description, steps)
                
                scenario = {
                    'title': f"Verify user can {description}",
                    'description': formatted_description,
                    'type': 'functional',
                    'severity': 'S2 - Major',
                    'priority': 'P2 - High'
                }
                scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating user action scenarios: {str(e)}")
            return []

    def _generate_rule_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on business rules with crisp descriptions"""
        scenarios = []
        
        for rule in analysis.get('business_rules', []):
            if not isinstance(rule, dict) or not rule.get('description'):
                continue
                
            description = rule.get('description', '')
            clean_desc = self._clean_gherkin_from_description(description)
            
            # Create crisp description based on rule type
            if 'validation' in clean_desc.lower():
                crisp_description = "Business rule validation ensures data integrity and compliance with defined requirements."
            elif 'filter' in clean_desc.lower():
                crisp_description = "Filtering business rule correctly applies criteria and displays relevant results only."
            elif 'authorization' in clean_desc.lower():
                crisp_description = "Authorization business rule enforces proper access control and permission validation."
            elif 'calculation' in clean_desc.lower():
                crisp_description = "Calculation business rule processes data accurately according to defined formulas."
            else:
                crisp_description = "Business rule is enforced correctly according to defined specifications and requirements."
            
            # Generate clean title
            clean_title = self._generate_smart_scenario_title(clean_desc)
            
            scenario = {
                'title': clean_title,
                'description': crisp_description,
                'type': 'business_rule',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _generate_validation_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate validation scenarios with crisp descriptions"""
        scenarios = []
        
        for validation in analysis.get('validations', []):
            if not isinstance(validation, dict) or not validation.get('description'):
                continue
                
            description = validation.get('description', '')
            clean_desc = self._clean_gherkin_from_description(description)
            
            # Create crisp validation description
            if 'required' in clean_desc.lower() or 'mandatory' in clean_desc.lower():
                crisp_description = "System validates required fields and prevents submission with missing mandatory data."
            elif 'format' in clean_desc.lower() or 'pattern' in clean_desc.lower():
                crisp_description = "System validates input format and ensures data meets specified pattern requirements."
            elif 'length' in clean_desc.lower() or 'size' in clean_desc.lower():
                crisp_description = "System validates data length and enforces appropriate size constraints."
            elif 'email' in clean_desc.lower():
                crisp_description = "System validates email format and ensures proper email address structure."
            elif 'phone' in clean_desc.lower():
                crisp_description = "System validates phone number format according to specified requirements."
            else:
                crisp_description = "System validates input data according to business rules with appropriate error messaging."
            
            # Generate clean title
            clean_title = self._generate_smart_scenario_title(clean_desc)
            
            scenario = {
                'title': clean_title,
                'description': crisp_description,
                'type': 'validation',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _generate_error_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate error scenarios with crisp descriptions"""
        scenarios = []
        
        for error in analysis.get('error_scenarios', []):
            if not isinstance(error, dict) or not error.get('description'):
                continue
                
            description = error.get('description', '')
            clean_desc = self._clean_gherkin_from_description(description)
            
            # Create crisp error description
            if 'network' in clean_desc.lower():
                crisp_description = "System handles network errors gracefully with appropriate retry mechanisms and user feedback."
            elif 'timeout' in clean_desc.lower():
                crisp_description = "System manages timeout scenarios correctly with proper error messaging and recovery options."
            elif 'authentication' in clean_desc.lower():
                crisp_description = "System handles authentication errors securely with clear messaging and proper access control."
            else:
                crisp_description = "System handles error conditions gracefully with appropriate user feedback and recovery guidance."
            
            # Generate clean title
            clean_title = self._generate_smart_scenario_title(clean_desc)
            
            scenario = {
                'title': clean_title,
                'description': crisp_description,
                'type': 'error',
                'severity': 'S1 - Critical',
                'priority': 'P1 - Critical'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _generate_flow_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on user flows"""
        try:
            scenarios = []
            flows = analysis.get('user_flows', [])
            
            for flow in flows:
                if not isinstance(flow, dict) or not flow.get('description'):
                    continue
                    
                description = self._clean_scenario_text(flow['description'])
                scenario = self._generate_base_scenario(description, analysis, 'flow')
                if scenario:
                    scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating flow scenarios: {str(e)}")
            return []

    def _generate_response_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on system responses"""
        try:
            scenarios = []
            responses = analysis.get('system_responses', [])
            
            for response in responses:
                if not isinstance(response, dict) or not response.get('description'):
                    continue
                    
                description = self._clean_scenario_text(response['description'])
                scenario = self._generate_base_scenario(description, analysis, 'response')
                if scenario:
                    scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating response scenarios: {str(e)}")
            return []

    def _generate_data_flow_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on data flows"""
        try:
            scenarios = []
            data_flows = analysis.get('data_flows', [])
            
            for flow in data_flows:
                if not isinstance(flow, dict) or not flow.get('description'):
                    continue
                    
                description = self._clean_scenario_text(flow['description'])
                scenario = self._generate_base_scenario(description, analysis, 'data_flow')
                if scenario:
                    scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating data flow scenarios: {str(e)}")
            return []

    def _generate_business_rule_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on business rules with crisp descriptions"""
        try:
            scenarios = []
            
            for rule in analysis.get('business_rules', []):
                if not isinstance(rule, dict) or not rule.get('description'):
                    continue
                    
                description = rule.get('description', '')
                clean_desc = self._clean_gherkin_from_description(description)
                
                # Create crisp business rule description
                if 'authorization' in clean_desc.lower():
                    crisp_description = "Authorization business rule enforces proper access control and security validation."
                elif 'validation' in clean_desc.lower():
                    crisp_description = "Validation business rule ensures data quality and compliance with requirements."
                elif 'calculation' in clean_desc.lower():
                    crisp_description = "Calculation business rule processes data accurately with correct formulas and logic."
                elif 'workflow' in clean_desc.lower():
                    crisp_description = "Workflow business rule manages process flow correctly with proper state transitions."
                else:
                    crisp_description = "Business rule enforces defined specifications and maintains system integrity."
                
                # Generate clean title
                clean_title = self._generate_smart_scenario_title(clean_desc)
                
                scenario = {
                    'title': clean_title,
                    'description': crisp_description,
                    'type': 'business_rule',
                    'severity': 'S2 - Major',
                    'priority': 'P2 - High'
                }
                scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating business rule scenarios: {str(e)}")
            return []

    def _generate_condition_specific_steps(self, condition: Dict[str, Any], functionality: Dict[str, Any], analysis: Dict[str, Any]) -> List[str]:
        """Generate steps for condition-specific scenarios"""
        steps = []
        
        # Add login step if needed
        if functionality.get('actor') in ['user', 'buyer', 'seller']:
            steps.append("1. Log in as a buyer")
        
        # Add navigation step if we can determine the page
        for action in analysis.get('user_actions', []):
            if action.get('context', {}).get('page'):
                steps.append(f"{len(steps) + 1}. Navigate to {action['context']['page']}")
                break
        
        # Add condition setup
        steps.append(f"{len(steps) + 1}. Set up condition: {condition.get('description', '')}")
        
        # Add main action steps
        for action in analysis.get('user_actions', []):
            if action['type'] in ['ui_action', 'form_action']:
                steps.append(f"{len(steps) + 1}. {action['description']}")
        
        # Add condition-specific verification
        steps.append(f"{len(steps) + 1}. Verify behavior when {condition.get('description', '')}")
        
        # Add final validation
        steps.append(f"{len(steps) + 1}. Validate the changes are saved correctly")
        
        return steps

    def _extract_specific_validations(self, text: str) -> List[Dict[str, Any]]:
        """Extract specific validation rules and criteria"""
        validations = []
        
        # Look for specific validation patterns
        patterns = [
            (r'(?:field|input)\s+([^\s]+)\s+(?:must|should)\s+([^.]+)', 'field_validation'),
            (r'(?:validate|verify|check)\s+(?:that\s+)?([^.]+)', 'logical_validation'),
            (r'(?:must|should)\s+(?:not|never)\s+([^.]+)', 'negative_validation'),
            (r'only\s+(?:if|when)\s+([^,]+),\s+(?:then|should|must)\s+([^.]+)', 'conditional_validation')
        ]
        
        for pattern, validation_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if validation_type == 'field_validation':
                    validations.append({
                        'type': validation_type,
                        'field': match.group(1).strip(),
                        'rule': match.group(2).strip(),
                        'context': self._extract_action_context(match.group(0))
                    })
                elif validation_type == 'conditional_validation':
                    validations.append({
                        'type': validation_type,
                        'condition': match.group(1).strip(),
                        'validation': match.group(2).strip(),
                        'context': self._extract_action_context(match.group(0))
                    })
                else:
                    validations.append({
                        'type': validation_type,
                        'rule': match.group(1).strip(),
                        'context': self._extract_action_context(match.group(0))
                    })
        
        return validations

    def _extract_action_context(self, text: str) -> Dict[str, Any]:
        """Extract action context from text"""
        context = {
            'page': None,
            'component': None,
            'action_type': None,
            'data_type': None,
            'user_role': None,
            'conditions': []
        }
        
        # Extract page context
        page_patterns = [
            r'(?:on|in|at|from)\s+(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+page|\s+screen|\s+view)',
            r'(?:navigate\s+to|go\s+to|visit)\s+(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+page|\s+screen|\s+view)',
            r'(?:in|on)\s+(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+section|\s+area|\s+module)'
        ]
        
        for pattern in page_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                context['page'] = match.group(1).strip()
                break
        
        # Extract component context
        component_patterns = [
            r'(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+button|\s+link|\s+field|\s+form|\s+input|\s+dropdown)',
            r'(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+modal|\s+dialog|\s+popup|\s+menu)',
            r'(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+section|\s+panel|\s+container|\s+box)'
        ]
        
        for pattern in component_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                context['component'] = match.group(1).strip()
                break
        
        # Extract action type
        action_patterns = {
            'create': r'(?:create|add|insert|new)',
            'read': r'(?:view|display|show|list)',
            'update': r'(?:update|edit|modify|change)',
            'delete': r'(?:delete|remove|clear)',
            'submit': r'(?:submit|send|post)',
            'validate': r'(?:validate|verify|check)',
            'navigate': r'(?:navigate|go|visit)',
            'search': r'(?:search|find|filter)',
            'select': r'(?:select|choose|pick)',
            'upload': r'(?:upload|attach|import)',
            'download': r'(?:download|export|save)'
        }
        
        for action_type, pattern in action_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                context['action_type'] = action_type
                break
        
        # Extract data type
        data_patterns = {
            'user': r'(?:user|account|profile)',
            'product': r'(?:product|item|goods)',
            'order': r'(?:order|purchase|transaction)',
            'payment': r'(?:payment|transaction|credit card)',
            'file': r'(?:file|document|image)',
            'settings': r'(?:settings|configuration|preferences)',
            'message': r'(?:message|notification|alert)',
            'comment': r'(?:comment|review|feedback)'
        }
        
        for data_type, pattern in data_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                context['data_type'] = data_type
                break
        
        # Extract user role
        role_patterns = [
            r'(?:as|for|by)\s+(?:a|an|the)\s+([a-zA-Z]+?)(?:\s+user|\s+role|\s+account)',
            r'(?:when|if)\s+(?:a|an|the)\s+([a-zA-Z]+?)\s+(?:user|role|account)'
        ]
        
        for pattern in role_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                context['user_role'] = match.group(1).strip().lower()
                break
        
        # Extract conditions
        condition_patterns = [
            r'(?:when|if)\s+([^,\.]+)',
            r'(?:only|unless)\s+([^,\.]+)',
            r'(?:after|before)\s+([^,\.]+)'
        ]
        
        for pattern in condition_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                condition = match.group(1).strip()
                if condition and condition not in context['conditions']:
                    context['conditions'].append(condition)
        
        return context

    def _extract_preconditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract preconditions from text"""
        preconditions = []
        
        # Look for precondition patterns
        patterns = [
            r'(?:prerequisite|before you begin|pre-condition)s?[:\s]+([^.]+)',
            r'(?:must|should|need to)\s+have\s+([^.]+)\s+before',
            r'(?:requires|requires that)\s+([^.]+)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                preconditions.append({
                    'type': 'prerequisite',
                    'description': match.group(1).strip()
                })
        
        return preconditions

    def _extract_user_flows(self, text: str) -> List[Dict[str, Any]]:
        """Extract user flows from text"""
        flows = []
        
        # Look for flow patterns
        patterns = [
            r'(?:user|customer)\s+(?:should|can|must|will)\s+([^.]+)',
            r'(?:when|after)\s+([^,]+),\s+(?:user|customer)\s+(?:should|can|must|will)\s+([^.]+)',
            r'(?:workflow|process|flow):\s*([^.]+)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) > 1:
                    flows.append({
                        'type': 'conditional_flow',
                        'condition': match.group(1).strip(),
                        'action': match.group(2).strip()
                    })
                else:
                    flows.append({
                        'type': 'basic_flow',
                        'description': match.group(1).strip()
                    })
        
        return flows

    def _extract_validation_rules(self, text: str) -> List[Dict[str, Any]]:
        """Extract validation rules from text"""
        validation_rules = []
        
        # Look for validation patterns
        patterns = [
            (r'(?:validate|verify|check|ensure)\s+(?:that|if)?\s+([^.]+)', 'validation'),
            (r'(?:must|should|shall)\s+(?:be|have)\s+([^.]+)', 'requirement'),
            (r'(?:only|must)\s+allow\s+([^.]+)', 'restriction'),
            (r'(?:field|input|value)\s+(?:must|should|shall)\s+([^.]+)', 'field_validation'),
            (r'(?:format|pattern)\s+(?:must|should|shall)\s+(?:be|match)\s+([^.]+)', 'format'),
            (r'(?:maximum|minimum|max|min)\s+(?:length|value|size)\s+(?:is|should be|must be)\s+([^.]+)', 'limit'),
            (r'(?:required|mandatory)\s+(?:field|input|value):\s*([^.]+)', 'required'),
            (r'(?:not\s+allowed|forbidden|prohibited):\s*([^.]+)', 'forbidden')
        ]
        
        for pattern, rule_type in patterns:
            try:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    validation_rules.append({
                        'type': rule_type,
                        'description': match.group(1).strip(),
                        'context': self._extract_action_context(match.group(0))
                    })
            except Exception as e:
                logger.error(f"Error processing validation pattern {pattern}: {str(e)}")
                continue

        # Look for specific validation keywords
        validation_keywords = [
            ('required', 'field is required'),
            ('unique', 'value must be unique'),
            ('numeric', 'value must be numeric'),
            ('email', 'valid email format'),
            ('date', 'valid date format'),
            ('phone', 'valid phone number format'),
            ('url', 'valid URL format'),
            ('password', 'password requirements'),
            ('length', 'length requirements'),
            ('range', 'value range requirements')
        ]
        
        for keyword, description in validation_keywords:
            if keyword.lower() in text.lower():
                context = text[max(0, text.lower().find(keyword) - 50):min(len(text), text.lower().find(keyword) + 50)]
                validation_rules.append({
                    'type': 'field_validation',
                    'description': description,
                    'context': self._extract_action_context(context)
                })
        
        # Add common validation rules based on context
        if any(word in text.lower() for word in ['save', 'submit', 'create', 'update']):
            validation_rules.append({
                'type': 'data_validation',
                'description': "All required fields must be filled",
                'context': {'operation': 'data_submission'}
            })
        
        if any(word in text.lower() for word in ['file', 'upload', 'image', 'document']):
            validation_rules.append({
                'type': 'file_validation',
                'description': "File type and size validation",
                'context': {'operation': 'file_upload'}
            })
        
        if any(word in text.lower() for word in ['login', 'password', 'credential']):
            validation_rules.append({
                'type': 'security_validation',
                'description': "Credential format and strength validation",
                'context': {'operation': 'authentication'}
            })
        
        return validation_rules

    def _extract_error_scenarios(self, text: str) -> List[Dict[str, Any]]:
        """Extract error scenarios from text"""
        error_scenarios = []
        
        # Look for error patterns
        patterns = [
            (r'(?:handle|manage|process)\s+(?:error|exception):\s*([^.]+)', 'error_handling'),
            (r'(?:system|service|operation)\s+(?:failure|fails)\s+(?:when|if)\s+([^.]+)', 'failure'),
            (r'(?:invalid|incorrect|wrong)\s+(?:input|data|value):\s*([^.]+)', 'invalid_input'),
            (r'(?:prevent|block|restrict)\s+([^.]+)', 'prevention'),
            (r'(?:validate|check|verify)\s+(?:that|if)\s+([^.]+)', 'validation'),
            (r'(?:error|warning)\s+message\s+(?:should|must|will)\s+([^.]+)', 'message'),
            (r'(?:timeout|connection lost|network error)\s+(?:when|if)\s+([^.]+)', 'connectivity'),
            (r'(?:recover|restore|resume)\s+(?:from|after)\s+([^.]+)', 'recovery')
        ]
        
        for pattern, error_type in patterns:
            try:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    error_scenarios.append({
                        'type': error_type,
                        'description': match.group(1).strip(),
                        'context': self._extract_action_context(match.group(0))
                    })
            except Exception as e:
                logger.error(f"Error processing error pattern {pattern}: {str(e)}")
                continue

        # Look for specific error conditions
        error_conditions = [
            'required field',
            'maximum length',
            'minimum length',
            'invalid format',
            'duplicate entry',
            'permission denied',
            'unauthorized access',
            'session expired',
            'data not found',
            'service unavailable'
        ]
        
        for condition in error_conditions:
            if condition.lower() in text.lower():
                context = text[max(0, text.lower().find(condition) - 50):min(len(text), text.lower().find(condition) + 50)]
                error_scenarios.append({
                    'type': 'error_handling',
                    'description': f"System handles {condition} error",
                    'context': self._extract_action_context(context)
                })
        
        # Add common error scenarios if relevant keywords are found
        if any(word in text.lower() for word in ['save', 'submit', 'update', 'create']):
            error_scenarios.append({
                'type': 'error_handling',
                'description': "System handles database transaction failure",
                'context': {'operation': 'data_persistence'}
            })
        
        if any(word in text.lower() for word in ['api', 'service', 'request', 'response']):
            error_scenarios.append({
                'type': 'error_handling',
                'description': "System handles API/service timeout",
                'context': {'operation': 'external_service'}
            })
        
        if any(word in text.lower() for word in ['file', 'upload', 'download', 'image']):
            error_scenarios.append({
                'type': 'error_handling',
                'description': "System handles file processing errors",
                'context': {'operation': 'file_handling'}
            })
        
        return error_scenarios

    def _extract_data_flows(self, text: str) -> List[Dict[str, Any]]:
        """Extract data flow and transformations"""
        flows = []
        
        # Look for data flow patterns
        patterns = [
            (r'data\s+(?:should|must|will)\s+([^.]+)', 'data_requirement'),
            (r'(?:save|store|update)\s+([^.]+)', 'data_operation'),
            (r'(?:retrieve|fetch|get)\s+([^.]+)', 'data_access'),
            (r'(?:transform|convert|format)\s+([^.]+)', 'data_transformation')
        ]
        
        for pattern, flow_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                flows.append({
                    'type': flow_type,
                    'description': match.group(1).strip(),
                    'context': self._extract_action_context(match.group(0))
                })
        
        return flows

    def _extract_technical_requirements(self, text: str) -> Dict[str, Any]:
        """Extract technical requirements from text"""
        requirements = {
            'ui_components': [],
            'data_fields': [],
            'integrations': [],
            'performance': [],
            'security': [],
            'technical_constraints': []
        }
        
        # Extract UI components
        ui_patterns = [
            r'(?:button|link|field|form|modal|dialog|dropdown|checkbox|radio|input|select|textarea)\s+(?:for|to)?\s+([\w\s-]+)',
            r'(?:page|screen|view|section|panel)\s+(?:for|to)?\s+([\w\s-]+)'
        ]
        
        for pattern in ui_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                component = {
                    'type': match.group(0).split()[0].lower(),
                    'purpose': match.group(1).strip(),
                    'validation_rules': []  # Will be populated by validation analysis
                }
                requirements['ui_components'].append(component)
        
        # Extract data fields
        field_patterns = [
            r'(?:field|input|data)\s+(?:for|of)?\s+([\w\s-]+)',
            r'([\w\s-]+?)\s+(?:field|input|data)',
            r'(?:enter|input|provide)\s+([\w\s-]+)'
        ]
        
        for pattern in field_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                field = {
                    'name': match.group(1).strip(),
                    'type': self._infer_field_type(match.group(1)),
                    'required': 'required' in text.lower() or 'mandatory' in text.lower(),
                    'validation_rules': []  # Will be populated by validation analysis
                }
                if field not in requirements['data_fields']:
                    requirements['data_fields'].append(field)
        
        # Extract integrations
        integration_patterns = [
            r'integrate\s+with\s+([\w\s-]+)',
            r'(?:call|use|consume)\s+([\w\s-]+?)\s+(?:API|service|endpoint)',
            r'(?:API|service|endpoint)\s+(?:for|to)\s+([\w\s-]+)'
        ]
        
        for pattern in integration_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                integration = {
                    'system': match.group(1).strip(),
                    'purpose': self._extract_integration_purpose(match.group(0)),
                    'requirements': []  # Will be populated by further analysis
                }
                requirements['integrations'].append(integration)
        
        # Extract performance requirements
        performance_patterns = [
            r'(?:load|response|processing)\s+time\s+(?:should|must|will)\s+(?:be|not exceed)\s+([\w\s-]+)',
            r'handle\s+([\d,]+)\s+(?:concurrent|simultaneous)\s+(?:users|requests|transactions)',
            r'(?:throughput|capacity)\s+of\s+([\d,]+)\s+(?:requests|transactions)\s+per\s+(?:second|minute|hour)'
        ]
        
        for pattern in performance_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                requirement = {
                    'type': 'performance',
                    'metric': match.group(0).split()[0].lower(),
                    'value': match.group(1).strip(),
                    'description': match.group(0).strip()
                }
                requirements['performance'].append(requirement)
        
        # Extract security requirements
        security_patterns = [
            r'(?:secure|encrypted|protected)\s+(?:using|with|by)\s+([\w\s-]+)',
            r'(?:authentication|authorization)\s+(?:using|with|by)\s+([\w\s-]+)',
            r'(?:role|permission|access)\s+based\s+([\w\s-]+)'
        ]
        
        for pattern in security_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                requirement = {
                    'type': 'security',
                    'mechanism': match.group(1).strip(),
                    'description': match.group(0).strip()
                }
                requirements['security'].append(requirement)
        
        # Extract technical constraints
        constraint_patterns = [
            r'must\s+use\s+([\w\s-]+)',
            r'(?:compatible|work)\s+with\s+([\w\s-]+)',
            r'(?:requires|needs)\s+([\w\s-]+)\s+(?:version|framework|library)',
            r'(?:limited|restricted)\s+to\s+([\w\s-]+)'
        ]
        
        for pattern in constraint_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                constraint = {
                    'type': 'technical',
                    'description': match.group(0).strip(),
                    'target': match.group(1).strip()
                }
                requirements['technical_constraints'].append(constraint)
        
        return requirements

    def _infer_field_type(self, field_name: str) -> str:
        """Infer the type of a field based on its name"""
        field_name_lower = field_name.lower()
        
        # Date/Time fields
        if any(word in field_name_lower for word in ['date', 'time', 'when', 'schedule']):
            return 'datetime'
        
        # Numeric fields
        if any(word in field_name_lower for word in ['amount', 'number', 'count', 'quantity', 'price']):
            return 'numeric'
        
        # Boolean fields
        if any(word in field_name_lower for word in ['is', 'has', 'can', 'should', 'flag']):
            return 'boolean'
        
        # Email fields
        if 'email' in field_name_lower:
            return 'email'
        
        # Phone fields
        if any(word in field_name_lower for word in ['phone', 'mobile', 'contact']):
            return 'phone'
        
        # File fields
        if any(word in field_name_lower for word in ['file', 'document', 'image', 'photo']):
            return 'file'
        
        # Default to text
        return 'text'

    def _extract_integration_purpose(self, text: str) -> str:
        """Extract the purpose of an integration from text"""
        purpose_patterns = [
            r'(?:to|for)\s+([\w\s-]+)',
            r'(?:that|which)\s+([\w\s-]+)',
            r'(?:when|while)\s+([\w\s-]+)'
        ]
        
        for pattern in purpose_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return 'general integration'

    def _extract_edge_cases(self, text: str) -> List[Dict[str, Any]]:
        """Extract edge cases and boundary conditions from text"""
        edge_cases = []
        
        # Look for edge case patterns
        patterns = [
            (r'(?:edge case|boundary condition|limit):\s*([^.]+)', 'boundary'),
            (r'(?:maximum|minimum|max|min)\s+(?:value|limit|size|length)\s+(?:is|should be|must be)\s+([^.]+)', 'limit'),
            (r'(?:when|if)\s+([^,]+?)\s+(?:reaches|exceeds|falls below|is less than|is more than)\s+([^.]+)', 'threshold'),
            (r'(?:handle|manage|process)\s+(?:special|exceptional|extreme)\s+(?:case|condition):\s*([^.]+)', 'special')
        ]
        
        for pattern, case_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if case_type == 'threshold':
                    edge_cases.append({
                        'type': case_type,
                        'condition': match.group(1).strip(),
                        'threshold': match.group(2).strip(),
                        'description': match.group(0).strip()
                    })
                else:
                    edge_cases.append({
                        'type': case_type,
                        'description': match.group(1).strip() if len(match.groups()) > 0 else match.group(0).strip()
                    })
        
        return edge_cases

    def _extract_dependencies(self, text: str) -> List[Dict[str, Any]]:
        """Extract dependencies from text"""
        dependencies = []
        
        # Look for dependency patterns
        patterns = [
            (r'(?:depends|dependent)\s+on\s+([^.]+)', 'system'),
            (r'requires?\s+([^.]+)', 'requirement'),
            (r'needs?\s+([^.]+)\s+(?:to|before)', 'prerequisite'),
            (r'(?:integration|connection)\s+with\s+([^.]+)', 'integration'),
            (r'(?:uses?|utilizes?)\s+([^.]+)', 'component')
        ]
        
        for pattern, dep_type in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                dependencies.append({
                    'type': dep_type,
                    'description': match.group(1).strip(),
                    'context': self._extract_action_context(match.group(0))
                })
        
        return dependencies

    def _is_action_applicable(self, action: str, actor: Dict[str, Any]) -> bool:
        """Check if an action is applicable to an actor based on their permissions"""
        action_lower = action.lower()
        
        # Map actions to required permissions
        permission_map = {
            'create': ['create', 'write', 'admin'],
            'update': ['update', 'write', 'admin'],
            'delete': ['delete', 'admin'],
            'view': ['read', 'view', 'write', 'admin'],
            'manage': ['write', 'admin'],
            'approve': ['approve', 'admin'],
            'reject': ['approve', 'admin']
        }
        
        # Determine required permissions for this action
        required_permissions = []
        for action_type, permissions in permission_map.items():
            if action_type in action_lower:
                required_permissions.extend(permissions)
        
        # If no specific permissions required, action is applicable
        if not required_permissions:
            return True
        
        # Check if actor has any of the required permissions
        actor_permissions = [p.lower() for p in actor.get('permissions', [])]
        return any(p in actor_permissions for p in required_permissions)

    def _generate_validation_scenarios_for_criterion(self, description: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate validation scenarios for an acceptance criterion with crisp descriptions"""
        scenarios = []
        
        # Extract validation rules from description
        validations = self._extract_applicable_validations(description, analysis.get('components', {}))
        
        for rule in validations:
            scenario = {
                'title': f"Verify {rule['field']} validation: {rule['rule']}",
                'description': f"System validates {rule['field']} according to {rule['rule']} and rejects invalid entries with appropriate error messages.",
                'type': 'validation',
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _generate_edge_case_scenarios_for_criterion(self, description: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate edge case scenarios for an acceptance criterion with crisp descriptions"""
        scenarios = []
        
        # Extract edge cases from description
        edge_cases = self._extract_edge_cases(description)
        
        for case in edge_cases:
            if case['type'] == 'boundary':
                title = f"Verify boundary handling: {self._clean_scenario_text(case['description'])}"
                desc = f"System correctly processes data at boundary conditions with proper validation and expected behavior."
            elif case['type'] == 'limit':
                title = f"Verify limit handling: {self._clean_scenario_text(case['description'])}"
                desc = f"System handles data at system limits correctly without performance degradation or errors."
            elif case['type'] == 'threshold':
                title = f"Verify threshold behavior: {self._clean_scenario_text(case['description'])}"
                desc = f"System responds appropriately when threshold conditions are met with correct state transitions."
            else:  # special case
                title = f"Verify edge case: {self._clean_scenario_text(case['description'])}"
                desc = f"System handles special edge case scenarios correctly with stable performance and data integrity."
            
            scenario = {
                'title': title,
                'description': desc,
                'type': 'edge_case',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _generate_boundary_scenarios_for_criterion(self, description: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate boundary condition scenarios for an acceptance criterion with crisp descriptions"""
        scenarios = []
        
        # Extract boundary conditions from description
        edge_cases = self._extract_edge_cases(description)
        boundary_cases = [case for case in edge_cases if case['type'] in ['boundary', 'limit', 'threshold']]
        
        for case in boundary_cases:
            # Generate scenarios for different boundary types
            for boundary_type in ['minimum', 'maximum', 'exact']:
                if boundary_type == 'minimum':
                    title = f"Verify minimum boundary: {self._clean_scenario_text(case['description'])}"
                    desc = f"System correctly processes data at minimum allowed values with proper validation."
                elif boundary_type == 'maximum':
                    title = f"Verify maximum boundary: {self._clean_scenario_text(case['description'])}"
                    desc = f"System correctly processes data at maximum allowed values without exceeding limits."
                else:  # exact
                    title = f"Verify exact boundary: {self._clean_scenario_text(case['description'])}"
                    desc = f"System handles exact boundary conditions with precise validation and expected results."
                
                scenario = {
                    'title': title,
                    'description': desc,
                    'type': 'boundary',
                    'severity': 'S3 - Moderate',
                    'priority': 'P3 - Medium'
                }
                scenarios.append(scenario)
        
        return scenarios

    def _generate_error_scenarios_for_criterion(self, description: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate error handling scenarios for an acceptance criterion with crisp descriptions"""
        scenarios = []
        
        # Extract error conditions from description
        error_scenarios = self._extract_error_scenarios(description)
        
        for error in error_scenarios:
            # Main error scenario
            error_scenario = {
                'title': f"Verify error handling: {error['type']}",
                'description': f"System properly handles {error['type']} errors with appropriate error messages and graceful degradation.",
                'type': 'error_handling',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            scenarios.append(error_scenario)
            
            # Recovery scenario if applicable
            if error.get('recoverable', False):
                recovery_scenario = {
                    'title': f"Verify error recovery: {error['type']}",
                    'description': f"System successfully recovers from {error['type']} errors and continues normal operation without data loss.",
                    'type': 'error_recovery',
                    'severity': 'S2 - Major',
                    'priority': 'P2 - High'
                }
                scenarios.append(recovery_scenario)
        
        return scenarios

    def _extract_required_fields(self, text: str, components: Dict[str, Any]) -> List[str]:
        """Extract required fields from text and components with enhanced validation"""
        try:
            if not text:
                logger.warning("Empty text provided for field extraction")
                return []

            if not isinstance(components, dict):
                logger.warning("Invalid components provided for field extraction")
                return []

            required_fields = set()  # Use set to avoid duplicates
            
            # Extract from text directly with error handling
            field_patterns = [
                r'(?:field|input)\s+([^\s]+)\s+(?:is|are)\s+required',
                r'required\s+(?:field|input)s?:\s*([^.]+)',
                r'(?:must|should)\s+(?:enter|provide|fill)\s+([^.]+)',
                r'(?:field|input)\s+([^\s]+)\s+(?:must|should|shall)\s+be\s+(?:filled|provided|entered)'
            ]
            
            for pattern in field_patterns:
                try:
                    matches = re.finditer(pattern, text, re.IGNORECASE)
                    for match in matches:
                        fields = match.group(1).strip().split(',')
                        for field in fields:
                            field = field.strip()
                            if field:
                                required_fields.add(field)
                except Exception as e:
                    logger.error(f"Error extracting fields with pattern {pattern}: {str(e)}")
            
            # Extract from data requirements
            try:
                for req in components.get('data_requirements', []):
                    if isinstance(req, dict):
                        if req.get('type') == 'field_validation' and req.get('field'):
                            required_fields.add(req['field'])
            except Exception as e:
                logger.error(f"Error extracting fields from data requirements: {str(e)}")
            
            # Extract from validation rules
            try:
                for rule in components.get('validation_rules', []):
                    if isinstance(rule, dict):
                        if rule.get('type') in ['required', 'field_validation']:
                            field = rule.get('field', '')
                            if field:
                                required_fields.add(field)
            except Exception as e:
                logger.error(f"Error extracting fields from validation rules: {str(e)}")
            
            # Extract from technical requirements
            try:
                tech_reqs = components.get('technical_requirements', {})
                for field in tech_reqs.get('data_fields', []):
                    if isinstance(field, dict) and field.get('required'):
                        field_name = field.get('name', '')
                        if field_name:
                            required_fields.add(field_name)
            except Exception as e:
                logger.error(f"Error extracting fields from technical requirements: {str(e)}")
            
            # Add common required fields based on context
            context_fields = {
                'login': ['username', 'password'],
                'register': ['email', 'password', 'confirm_password'],
                'payment': ['amount', 'payment_method'],
                'shipping': ['address', 'city', 'country']
            }
            
            try:
                text_lower = text.lower()
                for context, fields in context_fields.items():
                    if any(word in text_lower for word in [context, f"{context} form", f"{context} page"]):
                        required_fields.update(fields)
            except Exception as e:
                logger.error(f"Error adding context-based fields: {str(e)}")
            
            return sorted(list(required_fields))  # Convert set back to sorted list
            
        except Exception as e:
            logger.error(f"Error in field extraction: {str(e)}")
            return []

    def _extract_applicable_validations(self, text: str, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract applicable validation rules with enhanced validation and context awareness"""
        try:
            if not text:
                logger.warning("Empty text provided for validation extraction")
                return []

            if not isinstance(components, dict):
                logger.warning("Invalid components provided for validation extraction")
                return []

            validations = []
            text_lower = text.lower()
            
            # Get all validation rules with error handling
            try:
                all_rules = components.get('validation_rules', [])
                if not isinstance(all_rules, list):
                    logger.warning("Invalid validation rules format")
                    all_rules = []
            except Exception as e:
                logger.error(f"Error accessing validation rules: {str(e)}")
                all_rules = []
            
            # Filter rules that are applicable to this text
            for rule in all_rules:
                try:
                    if not isinstance(rule, dict):
                        continue
                        
                    rule_desc = rule.get('description', '').lower()
                    rule_context = rule.get('context', {})
                    
                    # Check if rule is applicable based on multiple criteria
                    is_applicable = False
                    
                    # Check for direct mention of fields
                    try:
                        fields = self._extract_required_fields(text, components)
                        if any(field.lower() in text_lower for field in fields):
                            is_applicable = True
                    except Exception as e:
                        logger.error(f"Error checking field mentions: {str(e)}")
                    
                    # Check for action type match
                    try:
                        if rule_context.get('action_type') and rule_context['action_type'].lower() in text_lower:
                            is_applicable = True
                    except Exception as e:
                        logger.error(f"Error checking action type: {str(e)}")
                    
                    # Check for component match
                    try:
                        if rule_context.get('component') and rule_context['component'].lower() in text_lower:
                            is_applicable = True
                    except Exception as e:
                        logger.error(f"Error checking component match: {str(e)}")
                    
                    # Check for semantic similarity
                    try:
                        if self._calculate_similarity(text_lower, rule_desc) > 0.3:  # Lower threshold for validation rules
                            is_applicable = True
                    except Exception as e:
                        logger.error(f"Error calculating similarity: {str(e)}")
                    
                    if is_applicable:
                        validations.append(rule)
                        
                except Exception as e:
                    logger.error(f"Error processing validation rule: {str(e)}")
                    continue
            
            # Add implicit validations based on context
            context_validations = {
                'save': {
                    'type': 'data_validation',
                    'description': 'All required fields must be filled',
                    'context': {'operation': 'data_submission'}
                },
                'email': {
                    'type': 'format_validation',
                    'description': 'Email format must be valid',
                    'context': {'field': 'email'}
                },
                'password': {
                    'type': 'security_validation',
                    'description': 'Password must meet security requirements',
                    'context': {'field': 'password'}
                },
                'number': {
                    'type': 'numeric_validation',
                    'description': 'Value must be a valid number',
                    'context': {'field_type': 'numeric'}
                },
                'date': {
                    'type': 'date_validation',
                    'description': 'Date/time format must be valid',
                    'context': {'field_type': 'datetime'}
                }
            }
            
            try:
                for context, validation in context_validations.items():
                    if any(word in text_lower for word in [context, f"{context} field", f"{context} input"]):
                        if validation not in validations:  # Avoid duplicates
                            validations.append(validation)
            except Exception as e:
                logger.error(f"Error adding context validations: {str(e)}")
            
            return validations
            
        except Exception as e:
            logger.error(f"Error in validation extraction: {str(e)}")
            return []

    def _extract_applicable_rules(self, text: str, components: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract applicable business rules from text and components"""
        try:
            if not text or not isinstance(components, dict):
                return []

            rules = []
            
            # Extract from business rules section
            if 'business_rules' in components:
                for rule in components['business_rules']:
                    if self._is_rule_applicable(text, rule):
                        rules.append(rule)
            
            # Extract from technical requirements
            if 'technical_requirements' in components:
                tech_rules = self._extract_technical_rules(text, components['technical_requirements'])
                rules.extend(tech_rules)
            
            return rules
            
        except Exception as e:
            logger.error(f"Error extracting applicable rules: {str(e)}")
            return []

    def _is_rule_applicable(self, text: str, rule: Dict[str, Any]) -> bool:
        """Check if a business rule is applicable to the given text"""
        try:
            if not isinstance(rule, dict) or 'description' not in rule:
                return False
                
            rule_text = rule['description'].lower()
            text = text.lower()
            
            # Check for direct keyword matches
            rule_keywords = set(rule_text.split())
            text_keywords = set(text.split())
            common_keywords = rule_keywords.intersection(text_keywords)
            
            # If significant keyword overlap, consider applicable
            if len(common_keywords) >= 2:
                return True
                
            # Check for semantic similarity
            similarity = self._calculate_similarity(text, rule_text)
            return similarity > 0.6
            
        except Exception as e:
            logger.error(f"Error checking rule applicability: {str(e)}")
            return False

    def _extract_technical_rules(self, text: str, tech_requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract technical rules from requirements"""
        try:
            if not isinstance(tech_requirements, dict):
                return []
                
            rules = []
            
            # Extract validation rules
            if 'validations' in tech_requirements:
                for validation in tech_requirements['validations']:
                    if isinstance(validation, dict) and 'rule' in validation:
                        rules.append({
                            'type': 'technical_validation',
                            'description': validation['rule'],
                            'severity': validation.get('severity', 'S3 - Moderate')
                        })
            
            # Extract security rules
            if 'security' in tech_requirements:
                for security_req in tech_requirements['security']:
                    if isinstance(security_req, dict) and 'requirement' in security_req:
                        rules.append({
                            'type': 'security_rule',
                            'description': security_req['requirement'],
                            'severity': 'S1 - Critical'
                        })
            
            return rules
            
        except Exception as e:
            logger.error(f"Error extracting technical rules: {str(e)}")
            return []

    def _extract_steps_from_text(self, text: str) -> List[str]:
        """Extract steps from text content"""
        steps = []
        
        # Try to find numbered steps
        numbered_steps = re.findall(r'(?:^|\n)\s*(\d+\.\s*[^\n]+)', text)
        if numbered_steps:
            return [step.strip() for step in numbered_steps]
            
        # Try to find bullet points
        bullet_steps = re.findall(r'(?:^|\n)\s*[•\-\*]\s*([^\n]+)', text)
        if bullet_steps:
            return [step.strip() for step in bullet_steps]
            
        # Split by sentences if no explicit steps found
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 5:  # Basic validation to avoid fragments
                # Convert sentence to action step
                step = sentence[0].upper() + sentence[1:]  # Capitalize first letter
                if not step.endswith(('.', '!', '?')):
                    step += '.'
                steps.append(step)
                
        return steps

    def _add_scenarios_to_collection(self, scenarios: List[Dict[str, Any]], source_type: str, all_scenarios: List[Dict[str, Any]], verbose: bool = False) -> int:
        """Add scenarios to collection if they don't already exist"""
        added_count = 0
        
        if not scenarios:
            return added_count
            
        for scenario in scenarios:
            if scenario and not self._scenario_exists(scenario, all_scenarios):
                all_scenarios.append(scenario)
                added_count += 1
        
        if verbose and added_count > 0:
            logger.info(f"Added {added_count} unique scenarios from {source_type}")
        
        return added_count

    def _extract_page_from_description(self, description: str) -> str:
        """Extract page information from description"""
        # Look for common page patterns
        page_patterns = [
            r'(?:on|in|at|from)\s+(?:the\s+)?([A-Za-z\s]+(?:page|screen|dashboard|view))',
            r'(?:the\s+)?([A-Za-z\s]+(?:page|screen|dashboard|view))\s+(?:should|must|will|to|for)',
            r'(?:access|view|open)\s+(?:the\s+)?([A-Za-z\s]+(?:page|screen|dashboard|view))'
        ]
        
        description_lower = description.lower()
        for pattern in page_patterns:
            match = re.search(pattern, description_lower)
            if match:
                return match.group(1).strip().title()
        
        return ""

    def _extract_action_steps_from_rule(self, description: str) -> List[str]:
        """Extract specific action steps from rule description"""
        steps = []
        description_lower = description.lower()
        
        # Extract actions based on common patterns
        if 'balance' in description_lower:
            if 'header' in description_lower:
                steps.append("Click on the balance section in the header")
            elif 'dashboard' in description_lower:
                steps.append("Locate the balance section on the dashboard")
            steps.append("Check if the balance is displayed correctly")
            
        if 'access' in description_lower:
            access_target = re.search(r'access\s+(?:their|the|)\s*([^\.]+)', description_lower)
            if access_target:
                steps.append(f"Attempt to access the {access_target.group(1).strip()}")
                
        if 'view' in description_lower:
            view_target = re.search(r'view\s+(?:their|the|)\s*([^\.]+)', description_lower)
            if view_target:
                steps.append(f"Attempt to view the {view_target.group(1).strip()}")
        
        # Add default step if no specific steps were extracted
        if not steps:
            steps.append("Perform the required action as per the business rule")
            
        return steps

    def _extract_verification_steps_from_rule(self, description: str) -> List[str]:
        """Extract specific verification steps from rule description"""
        steps = []
        description_lower = description.lower()
        
        # Add specific verification steps based on context
        if 'balance' in description_lower:
            steps.append("Verify that the balance is visible")
            steps.append("Validate that the displayed balance is accurate")
            steps.append("Confirm the balance format is correct (e.g., currency symbol, decimal places)")
            
        if 'access' in description_lower:
            steps.append("Verify that the access is granted as expected")
            steps.append("Validate that all required information is accessible")
            
        if 'view' in description_lower:
            steps.append("Verify that all information is displayed correctly")
            steps.append("Validate the accuracy of the displayed information")
            
        # Add data validation steps if relevant
        if any(word in description_lower for word in ['amount', 'balance', 'number', 'date', 'time']):
            steps.append("Verify the data format is correct")
            steps.append("Validate the data accuracy")
            
        return steps

    def _generate_validation_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate validation scenarios with crisp descriptions"""
        scenarios = []
        
        for validation in analysis.get('validations', []):
            if not isinstance(validation, dict) or not validation.get('description'):
                continue
                
            description = validation.get('description', '')
            clean_desc = self._clean_gherkin_from_description(description)
            
            # Create crisp validation description
            if 'required' in clean_desc.lower() or 'mandatory' in clean_desc.lower():
                crisp_description = "System validates required fields and prevents submission with missing mandatory data."
            elif 'format' in clean_desc.lower() or 'pattern' in clean_desc.lower():
                crisp_description = "System validates input format and ensures data meets specified pattern requirements."
            elif 'length' in clean_desc.lower() or 'size' in clean_desc.lower():
                crisp_description = "System validates data length and enforces appropriate size constraints."
            elif 'email' in clean_desc.lower():
                crisp_description = "System validates email format and ensures proper email address structure."
            elif 'phone' in clean_desc.lower():
                crisp_description = "System validates phone number format according to specified requirements."
            else:
                crisp_description = "System validates input data according to business rules with appropriate error messaging."
            
            # Generate clean title
            clean_title = self._generate_smart_scenario_title(clean_desc)
            
            scenario = {
                'title': clean_title,
                'description': crisp_description,
                'type': 'validation',
                'severity': 'S2 - Major',
                'priority': 'P2 - High'
            }
            scenarios.append(scenario)
        
        return scenarios

    def _extract_core_functionality(self, text: str) -> str:
        """Extract the core functionality from user story format (As a... I want to... So that...)"""
        if not text:
            return ""
        
        # Remove markdown formatting
        clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        
        # Extract the "I want to" part which contains the actual functionality
        want_pattern = r'I want to\s+(.*?)(?:\s+So that|$)'
        want_match = re.search(want_pattern, clean_text, re.IGNORECASE | re.DOTALL)
        
        if want_match:
            functionality = want_match.group(1).strip()
            # Clean up common phrases
            functionality = re.sub(r'\s+', ' ', functionality)
            functionality = functionality.replace('\n', ' ').strip()
            
            # Remove trailing punctuation and whitespace
            functionality = re.sub(r'[,.\s]+$', '', functionality)
            
            return functionality
        
        # If no "I want to" pattern found, try to extract meaningful functionality
        # Remove "As a [role]" part
        as_a_pattern = r'As\s+a\s+[^,]+,?\s*'
        clean_text = re.sub(as_a_pattern, '', clean_text, flags=re.IGNORECASE)
        
        # Remove "So that" part
        so_that_pattern = r'\s+So\s+that.*$'
        clean_text = re.sub(so_that_pattern, '', clean_text, flags=re.IGNORECASE | re.DOTALL)
        
        # Clean up and return
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text[:100] if len(clean_text) > 100 else clean_text

    def _generate_smart_scenario_title(self, functionality: str) -> str:
        """Generate a smart, concise test scenario title from functionality with aggressive cleaning"""
        if not functionality:
            return "Verify functionality"
        
        # First clean any Gherkin syntax from the title
        clean_func = self._clean_gherkin_from_description(functionality)
        
        # Additional cleaning for titles specifically
        clean_func = clean_func.lower().strip()
        
        # Remove verbose patterns commonly found in titles
        verbose_patterns = [
            r'verify\s+items?\s+filtering\s+based\s+on.*?title',
            r'filtering\s+functionality\s+correctly\s+applies',
            r'below\s+the\s+shipment\s+#\s+title',
            r'displays?\s+relevant\s+items?\s+only\.?$'
        ]
        
        for pattern in verbose_patterns:
            clean_func = re.sub(pattern, '', clean_func, flags=re.IGNORECASE)
        
        # Remove common prefixes
        prefixes_to_remove = ['to ', 'be able to ', 'ability to ', 'can ', 'should ', 'verify ', 'test ']
        for prefix in prefixes_to_remove:
            if clean_func.startswith(prefix):
                clean_func = clean_func[len(prefix):]
        
        # Extract core functionality
        if 'filter' in clean_func and 'sku' in clean_func:
            return "Verify SKU-based item filtering"
        elif 'carousel' in clean_func:
            return "Verify shipment item carousel"
        elif 'filter' in clean_func:
            return "Verify filtering functionality"
        elif any(word in clean_func for word in ['view', 'display', 'show', 'see']):
            if 'shipment' in clean_func:
                return "Verify shipment display"
            else:
                return "Verify information display"
        elif any(word in clean_func for word in ['create', 'add', 'insert']):
            return f"Verify creation functionality"
        elif any(word in clean_func for word in ['update', 'edit', 'modify']):
            return f"Verify update functionality"
        elif any(word in clean_func for word in ['delete', 'remove']):
            return f"Verify deletion functionality"
        else:
            # Use first meaningful words, cleaned up
            words = clean_func.split()[:4]
            meaningful_words = [w for w in words if len(w) > 2 and w not in ['the', 'and', 'for', 'with']]
            if meaningful_words:
                clean_func = ' '.join(meaningful_words)
                return f"Verify {clean_func}"
            else:
                return "Verify functionality"

    def generate_content_agnostic_scenarios(self, text: str) -> List[Dict[str, Any]]:
        """
        Content-agnostic scenario generation that works with any story format
        
        This system focuses on intent extraction rather than pattern matching:
        1. Normalize text content
        2. Extract core intent and entities  
        3. Classify functionality type
        4. Generate scenarios using templates
        5. Ensure consistent output format
        """
        try:
            if not text:
                return []
            
            # Layer 1: Text Normalization
            normalized_content = self._normalize_content(text)
            
            # Layer 2: Intent Extraction
            extracted_intent = self._extract_intent(normalized_content)
            
            # Layer 3: Scenario Generation
            scenarios = self._generate_scenarios_from_intent(extracted_intent)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error in content-agnostic generation: {str(e)}")
            return []

    def _normalize_content(self, text: str) -> Dict[str, Any]:
        """
        Layer 1: Normalize any text content to extract key information
        Works with user stories, acceptance criteria, technical specs, etc.
        """
        # Remove formatting and extract plain text
        plain_text = self._extract_plain_text(text) if isinstance(text, dict) else str(text)
        
        # Clean up the text
        clean_text = re.sub(r'\s+', ' ', plain_text).strip()
        clean_text = re.sub(r'[*#_\[\]()]+', '', clean_text)  # Remove markdown
        
        return {
            'original': text,
            'clean_text': clean_text,
            'length': len(clean_text),
            'sentences': [s.strip() for s in clean_text.split('.') if s.strip()]
        }

    def _extract_intent(self, normalized_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Layer 2: Extract user intent regardless of how it's written
        This is the core of the content-agnostic approach
        """
        text = normalized_content['clean_text'].lower()
        sentences = normalized_content['sentences']
        
        intent = {
            'action_type': self._classify_action_type(text),
            'domain': self._identify_domain(text),
            'entities': self._extract_entities(text),
            'actors': self._identify_actors(text),
            'objects': self._identify_objects(text),
            'context': self._extract_context(text),
            'requirements': self._extract_requirements(text)
        }
        
        return intent

    def _classify_action_type(self, text: str) -> str:
        """Classify the type of action/functionality regardless of format"""
        # Define action type patterns (order matters - most specific first)
        action_patterns = {
            'view_filtered': ['view.*based on', 'display.*based on', 'show.*based on', 'view.*filter', 'see.*filter', 'based on.*date', 'filtered by'],
            'view': ['view', 'display', 'show', 'see', 'look at', 'access', 'check'],
            'create': ['create', 'add', 'insert', 'new', 'generate', 'make'],
            'update': ['update', 'edit', 'modify', 'change', 'alter'],
            'delete': ['delete', 'remove', 'cancel', 'clear'],
            'process': ['process', 'handle', 'manage', 'execute'],
            'search': ['search', 'find', 'filter', 'query'],
            'validate': ['validate', 'verify', 'check', 'confirm'],
            'configure': ['configure', 'setup', 'set', 'customize'],
            'integrate': ['integrate', 'connect', 'sync', 'link']
        }
        
        for action_type, patterns in action_patterns.items():
            if any(re.search(pattern, text) for pattern in patterns):
                return action_type
        
        return 'general'

    def _identify_domain(self, text: str) -> str:
        """Identify the business domain/area"""
        domain_keywords = {
            'logistics': ['shipment', 'delivery', 'logistics', 'pickup', 'shipsy'],
            'marketplace': ['marketplace', 'seller', 'buyer', 'product'],
            'payment': ['payment', 'pay', 'transaction', 'billing'],
            'user_management': ['user', 'account', 'profile', 'authentication'],
            'inventory': ['inventory', 'stock', 'warehouse'],
            'orders': ['order', 'purchase', 'checkout'],
            'reporting': ['report', 'analytics', 'dashboard']
        }
        
        for domain, keywords in domain_keywords.items():
            if any(keyword in text for keyword in keywords):
                return domain
        
        return 'general'

    def _extract_entities(self, text: str) -> List[str]:
        """Extract key business entities (nouns)"""
        # Simple entity extraction - can be enhanced with NLP
        entity_patterns = [
            r'\b(shipment|order|product|user|payment|transaction|report|dashboard|inventory)\w*\b',
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'  # Proper nouns
        ]
        
        entities = []
        for pattern in entity_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities.extend([match.lower() for match in matches if isinstance(match, str)])
        
        return list(set(entities))

    def _identify_actors(self, text: str) -> List[str]:
        """Identify who performs the actions"""
        actor_patterns = [
            r'as\s+a\s+([^,]+)',
            r'(manager|admin|user|buyer|seller|customer|operator)\w*',
            r'(logistics|sales|support|finance)\s+(?:team|staff|manager|user)'
        ]
        
        actors = []
        for pattern in actor_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            actors.extend([match.strip().lower() for match in matches if match.strip()])
        
        return list(set(actors))

    def _identify_objects(self, text: str) -> List[str]:
        """Identify what objects/items are being acted upon"""
        # Prioritize business objects first
        business_objects = [
            'marketplace shipments', 'shipments', 'marketplace', 'orders', 'products', 
            'users', 'accounts', 'reports', 'dashboard', 'inventory', 'transactions',
            'payments', 'deliveries', 'pickups', 'logistics data'
        ]
        
        objects = []
        text_lower = text.lower()
        
        # Check for compound business objects first (more specific)
        for obj in sorted(business_objects, key=len, reverse=True):
            if obj in text_lower:
                objects.append(obj)
                break  # Take the most specific match
        
        # If no business objects found, use pattern matching
        if not objects:
            object_patterns = [
                r'view\s+([^,\s]+(?:\s+[^,\s]+){0,2})',  # What they want to view
                r'(shipments?|orders?|products?|users?|accounts?|reports?)',
                r'on\s+([A-Z][a-z]+)',  # System names like "Shipsy"
            ]
            
            for pattern in object_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    objects.extend([match.strip().lower() for match in matches if match.strip()])
                    break
        
        # Clean up and deduplicate
        cleaned_objects = []
        for obj in objects:
            obj_clean = obj.strip().lower()
            if obj_clean and obj_clean not in cleaned_objects and len(obj_clean) > 2:
                cleaned_objects.append(obj_clean)
        
        return cleaned_objects[:3]  # Limit to top 3 most relevant objects

    def _extract_context(self, text: str) -> Dict[str, Any]:
        """Extract contextual information"""
        return {
            'conditions': re.findall(r'(?:when|if|based on|where)\s+([^,\.]+)', text, re.IGNORECASE),
            'purposes': re.findall(r'(?:so that|to|in order to)\s+([^,\.]+)', text, re.IGNORECASE),
            'systems': re.findall(r'(?:on|in|using)\s+([A-Z][a-z]+)', text),
            'timeframes': re.findall(r'(daily|weekly|monthly|real-time|immediate)', text, re.IGNORECASE)
        }

    def _extract_requirements(self, text: str) -> List[str]:
        """Extract specific requirements or constraints"""
        req_patterns = [
            r'(?:must|should|shall|need to|require)\s+([^,\.]+)',
            r'(?:ensure|guarantee|verify)\s+([^,\.]+)'
        ]
        
        requirements = []
        for pattern in req_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            requirements.extend([match.strip() for match in matches if match.strip()])
        
        return requirements

    def _generate_scenarios_from_intent(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Layer 3: Generate test scenarios based on extracted intent
        This uses templates rather than hardcoded patterns
        """
        scenarios = []
        
        # Get the appropriate scenario template
        template = self._get_scenario_template(intent['action_type'], intent['domain'])
        
        # Generate primary scenario
        primary_scenario = self._build_scenario_from_template(template, intent)
        if primary_scenario:
            scenarios.append(primary_scenario)
        
        # Generate additional scenarios based on context
        if intent['context']['conditions']:
            boundary_scenario = self._generate_boundary_scenario(intent)
            if boundary_scenario:
                scenarios.append(boundary_scenario)
        
        if intent['action_type'] in ['create', 'update', 'delete']:
            error_scenario = self._generate_error_scenario(intent)
            if error_scenario:
                scenarios.append(error_scenario)
        
        return scenarios

    def _get_scenario_template(self, action_type: str, domain: str) -> Dict[str, Any]:
        """Get appropriate scenario template based on action and domain"""
        templates = {
            'view': {
                'title_format': "Verify viewing {objects} in {domain} system",
                'description_format': "View {objects} functionality in {domain} system",
                'base_steps': [
                    "Log in as {actor}",
                    "Navigate to {domain} section", 
                    "Locate the {objects} area",
                    "Attempt to view {objects}",
                    "Verify {objects} are displayed correctly",
                    "Verify all required information is visible"
                ]
            },
            'view_filtered': {
                'title_format': "Verify filtered view of {objects} in {domain} system",
                'description_format': "Filtered view functionality for {objects} in {domain}",
                'base_steps': [
                    "Log in as {actor}",
                    "Navigate to {domain} section",
                    "Locate the {objects} filtering options",
                    "Apply filter criteria",
                    "Verify filtered {objects} are displayed correctly",
                    "Verify filter works as expected"
                ]
            },
            'create': {
                'title_format': "Verify creating {objects} in {domain} system",
                'description_format': "Create {objects} functionality in {domain} system",
                'base_steps': [
                    "Log in as {actor}",
                    "Navigate to {domain} section",
                    "Locate create {objects} option",
                    "Fill in required information",
                    "Submit creation request",
                    "Verify {objects} are created successfully"
                ]
            },
            'general': {
                'title_format': "Verify {domain} functionality",
                'description_format': "{domain} system functionality",
                'base_steps': [
                    "Log in as appropriate user",
                    "Navigate to relevant section",
                    "Execute the required functionality",
                    "Verify the operation completes successfully",
                    "Verify expected results are achieved"
                ]
            }
        }
        
        return templates.get(action_type, templates['general'])

    def _build_scenario_from_template(self, template: Dict[str, Any], intent: Dict[str, Any]) -> Dict[str, Any]:
        """Build scenario from template with crisp description"""
        try:
            # Create crisp description based on action type and domain
            action_type = intent.get('action_type', 'general')
            domain = intent.get('domain', 'general')
            
            if action_type == 'view_filtered':
                crisp_description = f"System correctly filters and displays {domain} data based on specified criteria."
            elif action_type == 'view':
                crisp_description = f"System displays {domain} information accurately with proper formatting."
            elif action_type == 'create':
                crisp_description = f"System allows users to create new {domain} items with proper validation."
            elif action_type == 'update':
                crisp_description = f"System updates {domain} data correctly with validation and confirmation."
            elif action_type == 'search':
                crisp_description = f"System search functionality returns accurate {domain} results."
            else:
                crisp_description = f"System {action_type} functionality for {domain} works as expected."
            
            # Generate clean title
            entities = intent.get('entities', [])
            if entities:
                entity_str = ', '.join(entities[:2])  # Use first 2 entities
                title = f"Verify {action_type} for {entity_str}"
            else:
                title = f"Verify {action_type} functionality"
            
            return {
                'title': title,
                'description': crisp_description,
                'type': template.get('type', 'functional'),
                'severity': template.get('severity', 'S2 - Major'),
                'priority': template.get('priority', 'P2 - High')
            }
            
        except Exception as e:
            logger.error(f"Error building scenario from template: {str(e)}")
            return None

    def _generate_boundary_scenario(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate boundary scenario with crisp description"""
        try:
            domain = intent.get('domain', 'general')
            action_type = intent.get('action_type', 'general')
            
            # Create crisp boundary description
            if 'data' in domain or 'input' in domain:
                crisp_description = f"System correctly handles boundary conditions for data limits and edge cases."
            elif 'performance' in domain:
                crisp_description = f"System maintains performance standards under boundary load conditions."
            else:
                crisp_description = f"System handles {domain} boundary conditions correctly without degradation."
            
            title = f"Verify boundary conditions for {domain} {action_type}"
            
            return {
                'title': title,
                'description': crisp_description,
                'type': 'boundary',
                'severity': 'S3 - Moderate',
                'priority': 'P3 - Medium'
            }
            
        except Exception as e:
            logger.error(f"Error generating boundary scenario: {str(e)}")
            return None

    def _generate_error_scenario(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Generate error scenario with crisp description"""
        try:
            domain = intent.get('domain', 'general')
            action_type = intent.get('action_type', 'general')
            
            # Create crisp error description
            if 'payment' in domain:
                crisp_description = f"System handles payment errors gracefully with proper user feedback and recovery options."
            elif 'authentication' in domain:
                crisp_description = f"System manages authentication errors securely with appropriate access control."
            elif 'network' in domain:
                crisp_description = f"System handles network errors with retry mechanisms and user notifications."
            else:
                crisp_description = f"System handles {domain} errors gracefully with appropriate error messaging and recovery guidance."
            
            title = f"Verify error handling for {domain} {action_type}"
            
            return {
                'title': title,
                'description': crisp_description,
                'type': 'error',
                'severity': 'S1 - Critical',
                'priority': 'P1 - Critical'
            }
            
        except Exception as e:
            logger.error(f"Error generating error scenario: {str(e)}")
            return None

    def generate_comprehensive_scenarios(self, text: str) -> List[Dict[str, Any]]:
        """
        Generate comprehensive test scenarios like ChatGPT - covering positive, negative, and edge cases
        This is the most robust approach that works for any requirement regardless of project
        """
        try:
            if not text:
                return []
            
            # Extract the core business requirement
            requirement = self._extract_business_requirement(text)
            if not requirement:
                return []
            
            # Generate comprehensive scenario set
            all_scenarios = []
            
            # 1. Generate Positive Scenarios (Happy Path)
            positive_scenarios = self._generate_positive_scenarios(requirement)
            all_scenarios.extend(positive_scenarios)
            
            # 2. Generate Negative Scenarios (Error Cases)
            negative_scenarios = self._generate_negative_scenarios(requirement)
            all_scenarios.extend(negative_scenarios)
            
            # 3. Generate Edge Case Scenarios
            edge_scenarios = self._generate_edge_case_scenarios(requirement)
            all_scenarios.extend(edge_scenarios)
            
            # 4. Generate Boundary Scenarios
            boundary_scenarios = self._generate_boundary_scenarios(requirement)
            all_scenarios.extend(boundary_scenarios)
            
            return all_scenarios
            
        except Exception as e:
            logger.error(f"Error in comprehensive scenario generation: {str(e)}")
            return []

    def _extract_business_requirement(self, text: str) -> Dict[str, Any]:
        """Extract structured business requirement with deep understanding like ChatGPT"""
        # Clean text and extract plain content
        clean_text = self._extract_plain_text(text) if isinstance(text, dict) else str(text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Enhanced intelligent extraction
        requirement = {
            'actor': self._extract_actor_intelligent(clean_text),
            'action': self._extract_core_action_intelligent(clean_text),
            'object': self._extract_main_object_intelligent(clean_text),
            'conditions': self._extract_conditions_intelligent(clean_text),
            'purpose': self._extract_purpose(clean_text),
            'system': self._extract_system_name_intelligent(clean_text),
            'domain': self._identify_domain_intelligent(clean_text.lower()),
            'data_elements': self._extract_data_elements_intelligent(clean_text),
            'business_rules': self._extract_business_rules_simple(clean_text),
            'workflow_type': self._identify_workflow_type(clean_text),
            'business_context': self._extract_business_context_intelligent(clean_text)
        }
        
        return requirement

    def _extract_actor_intelligent(self, text: str) -> str:
        """Intelligently extract the actual business actor"""
        # First try standard patterns
        actor_patterns = [
            r'[Aa]s\s+a\s+([^,]+)',
            r'[Aa]s\s+an\s+([^,]+)',
        ]
        
        for pattern in actor_patterns:
            match = re.search(pattern, text)
            if match:
                actor = match.group(1).strip()
                # Clean up common words
                actor = re.sub(r'\s+(user|person|individual)$', '', actor, flags=re.IGNORECASE)
                return actor
        
        # Fallback to role detection
        roles = ['seller', 'buyer', 'customer', 'user', 'admin', 'manager', 'patient', 'doctor', 'employee', 'student', 'teacher']
        for role in roles:
            if role in text.lower():
                return role
        
        return "user"

    def _extract_core_action_intelligent(self, text: str) -> str:
        """Intelligently extract the core business action with context"""
        # Look for "I want to" pattern first - most reliable
        want_pattern = r'[Ii]\s+want\s+to\s+([^,\.]+?)(?:\s+so\s+that|\s*,|$)'
        want_match = re.search(want_pattern, text)
        if want_match:
            action = want_match.group(1).strip()
            return self._normalize_action(action)
        
        # Business-specific action patterns with context
        business_patterns = [
            # Financial actions
            (r'(transfer|send|move)\s+money\s+([^,\.]+)', 'transfer money'),
            (r'(deposit|withdraw)\s+([^,\.]+)', lambda m: f"{m.group(1)} funds"),
            (r'(pay|make\s+payment)\s+([^,\.]+)', 'make payment'),
            
            # E-commerce actions  
            (r'(add|put)\s+([^,\.]+?)\s+(?:to|in)\s+(?:cart|basket)', 'add to cart'),
            (r'(purchase|buy|order)\s+([^,\.]+)', 'purchase items'),
            (r'(checkout|complete\s+order)', 'complete checkout'),
            
            # Healthcare actions
            (r'(book|schedule|make)\s+([^,\.]+?)\s+(?:appointment|visit)', 'book appointment'),
            (r'(view|check|see)\s+([^,\.]+?)\s+(?:record|history|report)', 'view records'),
            
            # General business actions
            (r'(view|display|see)\s+([^,\.]+?)(?:\s+on\s+\w+|\s+based\s+on|\s+in|\s*,)', lambda m: f"view {m.group(2)}"),
            (r'(create|add|generate)\s+([^,\.]+)', lambda m: f"create {m.group(2)}"),
            (r'(update|modify|edit)\s+([^,\.]+)', lambda m: f"update {m.group(2)}"),
            (r'(approve|reject)\s+([^,\.]+)', lambda m: f"{m.group(1)} {m.group(2)}"),
        ]
        
        for pattern, action_template in business_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if callable(action_template):
                    return action_template(match)
                elif isinstance(action_template, str) and not action_template.startswith('{'):
                    return action_template
                else:
                    return f"{match.group(1)} {match.group(2)}".strip()
        
        return "perform action"

    def _normalize_action(self, action: str) -> str:
        """Normalize action to business-friendly format"""
        action = action.lower().strip()
        
        # Normalize common business actions
        normalizations = {
            'transfer money between my accounts': 'transfer money between accounts',
            'add products to my shopping cart': 'add products to cart', 
            'book medical appointments online': 'book medical appointments',
            'view marketplace shipments': 'view shipments',
            'manage my finances': 'manage finances'
        }
        
        for original, normalized in normalizations.items():
            if original in action:
                return normalized
                
        return action

    def _extract_main_object_intelligent(self, text: str) -> str:
        """Intelligently extract the main business object with context understanding"""
        text_lower = text.lower()
        
        # Domain-specific object patterns with priority
        business_object_patterns = [
            # Financial objects
            (r'transfer\s+money.*?between.*?(account[s]?)', 'money transfers'),
            (r'(transaction[s]?|payment[s]?|transfer[s]?)', lambda m: m.group(1)),
            (r'(deposit[s]?|withdrawal[s]?)', lambda m: m.group(1)),
            
            # E-commerce objects
            (r'add.*?(product[s]?).*?cart', 'shopping cart items'),
            (r'(shopping\s+cart|cart)', 'cart'),
            (r'(product[s]?|item[s]?)', lambda m: m.group(1)),
            (r'(order[s]?)', lambda m: m.group(1)),
            
            # Healthcare objects
            (r'book.*?(appointment[s]?|visit[s]?)', 'appointments'),
            (r'(medical\s+record[s]?|health\s+record[s]?)', 'medical records'),
            (r'(appointment[s]?|visit[s]?)', lambda m: m.group(1)),
            
            # Logistics objects
            (r'(marketplace\s+shipment[s]?|shipment[s]?)', lambda m: m.group(1)),
            (r'view.*?(shipment[s]?).*?on.*?(\w+)', lambda m: m.group(1)),
            
            # General business objects
            (r'view\s+([a-zA-Z\s]+?)(?:\s+on|\s+in|\s+based\s+on)', lambda m: m.group(1).strip()),
            (r'manage\s+([a-zA-Z\s]+?)(?:\s+on|\s+in|\s*,|$)', lambda m: m.group(1).strip()),
            (r'create\s+([a-zA-Z\s]+?)(?:\s+for|\s+in|\s*,)', lambda m: m.group(1).strip()),
        ]
        
        for pattern, obj_template in business_object_patterns:
            match = re.search(pattern, text_lower)
            if match:
                if callable(obj_template):
                    result = obj_template(match)
                    return result if result else "items"
                else:
                    return obj_template
        
        # Fallback to simple noun extraction
        nouns = re.findall(r'\b(account[s]?|product[s]?|item[s]?|order[s]?|appointment[s]?|shipment[s]?|record[s]?|transaction[s]?|payment[s]?)\b', text_lower)
        if nouns:
            return nouns[0]
            
        return "items"

    def _extract_conditions_intelligent(self, text: str) -> List[str]:
        """Extract conditions with better business context understanding"""
        conditions = []
        
        # Enhanced condition patterns
        condition_patterns = [
            r'based\s+on\s+(?:the\s+)?([^,\.]+)',
            r'when\s+([^,\.]+?)(?:\s+is\s+|\s+are\s+|\s*,)',
            r'if\s+([^,\.]+?)(?:\s+is\s+|\s+are\s+|\s*,)',
            r'after\s+([^,\.]+?)(?:\s+is\s+|\s+are\s+|\s*,)',
            r'with\s+([^,\.]+?)(?:\s+that\s+|\s*,)',
            r'for\s+([^,\.]+?)(?:\s+that\s+|\s*,)',
            r'where\s+([^,\.]+?)(?:\s+is\s+|\s+are\s+|\s*,)'
        ]
        
        for pattern in condition_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                condition = match.strip()
                if len(condition) > 3 and condition not in conditions:
                    conditions.append(condition)
        
        return conditions

    def _extract_system_name_intelligent(self, text: str) -> str:
        """Intelligently extract system/platform names"""
        # Look for explicit system names
        system_patterns = [
            r'on\s+([A-Z][a-zA-Z]+)',
            r'in\s+([A-Z][a-zA-Z]+)',
            r'using\s+([A-Z][a-zA-Z]+)',
            r'through\s+([A-Z][a-zA-Z]+)',
            r'via\s+([A-Z][a-zA-Z]+)'
        ]
        
        for pattern in system_patterns:
            match = re.search(pattern, text)
            if match:
                system = match.group(1)
                # Filter out common words that aren't system names
                if system.lower() not in ['the', 'and', 'or', 'as', 'to', 'for', 'with', 'that', 'this']:
                    return system
        
        # Infer system based on domain
        domain = self._identify_domain_intelligent(text.lower())
        system_mapping = {
            'logistics': 'logistics system',
            'payment': 'payment system', 
            'marketplace': 'marketplace platform',
            'user_management': 'user management system',
            'orders': 'order management system',
            'inventory': 'inventory system',
            'reporting': 'reporting system'
        }
        
        return system_mapping.get(domain, 'system')

    def _identify_domain_intelligent(self, text: str) -> str:
        """Intelligently identify business domain with better context"""
        # Enhanced domain detection with business context
        domain_indicators = {
            'logistics': [
                'shipment', 'delivery', 'logistics', 'pickup', 'shipsy', 'unplanned bucket',
                'warehouse', 'freight', 'cargo', 'shipping'
            ],
            'payment': [
                'payment', 'pay', 'transaction', 'billing', 'money', 'transfer', 'deposit',
                'withdraw', 'balance', 'bank', 'financial', 'devtech pay'
            ],
            'marketplace': [
                'marketplace', 'seller', 'buyer', 'product', 'merchant', 'vendor',
                'catalog', 'listing', 'commerce'
            ],
            'user_management': [
                'user', 'account', 'profile', 'authentication', 'login', 'register',
                'permission', 'role', 'access'
            ],
            'inventory': [
                'inventory', 'stock', 'warehouse', 'item', 'sku', 'quantity'
            ],
            'healthcare': [
                'medical', 'appointment', 'patient', 'doctor', 'hospital', 'clinic',
                'health', 'treatment', 'diagnosis'
            ],
            'ecommerce': [
                'cart', 'shopping', 'checkout', 'purchase', 'buy', 'order',
                'customer', 'product catalog'
            ],
            'orders': [
                'order', 'purchase', 'checkout', 'fulfillment', 'processing'
            ],
            'reporting': [
                'report', 'analytics', 'dashboard', 'metrics', 'data', 'chart'
            ]
        }
        
        # Score each domain
        domain_scores = {}
        for domain, keywords in domain_indicators.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                domain_scores[domain] = score
        
        # Return highest scoring domain
        if domain_scores:
            return max(domain_scores.items(), key=lambda x: x[1])[0]
        
        return 'general'

    def _extract_data_elements_intelligent(self, text: str) -> List[str]:
        """Extract data elements with better business context"""
        elements = []
        
        # Business-specific data patterns
        data_patterns = [
            # Financial data
            r'\b(amount|balance|price|cost|fee|rate|currency)\b',
            r'\b(account\s+number|routing\s+number|transaction\s+id)\b',
            
            # Date/time data
            r'\b(date|time|timestamp|schedule|deadline)\b',
            r'\b(pickup\s+date|delivery\s+date|appointment\s+date|due\s+date)\b',
            
            # Identity data
            r'\b(id|identifier|number|code|reference)\b',
            r'\b(name|title|description|comment|note)\b',
            
            # Status data
            r'\b(status|state|condition|flag|approval)\b',
            
            # Quantity data
            r'\b(quantity|count|volume|size|weight|dimension)\b',
            
            # Contact data
            r'\b(email|phone|address|contact)\b'
        ]
        
        for pattern in data_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            elements.extend([match.lower() for match in matches if isinstance(match, str)])
        
        # Add domain-specific data elements based on context
        if 'date' in text.lower() or 'time' in text.lower():
            elements.append('date')
        if 'money' in text.lower() or 'amount' in text.lower():
            elements.append('amount')
        if 'name' in text.lower() or 'title' in text.lower():
            elements.append('name')
            
        return list(set(elements))  # Remove duplicates

    def _identify_workflow_type(self, text: str) -> str:
        """Identify the type of business workflow"""
        workflow_indicators = {
            'approval': ['approve', 'approval', 'reject', 'review'],
            'creation': ['create', 'add', 'generate', 'new'],
            'viewing': ['view', 'display', 'see', 'show', 'check'],
            'modification': ['update', 'edit', 'modify', 'change'],
            'transaction': ['transfer', 'pay', 'purchase', 'buy', 'order'],
            'booking': ['book', 'schedule', 'reserve', 'appointment']
        }
        
        text_lower = text.lower()
        for workflow, keywords in workflow_indicators.items():
            if any(keyword in text_lower for keyword in keywords):
                return workflow
                
        return 'general'

    def _extract_business_context_intelligent(self, text: str) -> Dict[str, Any]:
        """Extract rich business context for better scenario generation"""
        context = {
            'has_approval_flow': any(word in text.lower() for word in ['approve', 'approval', 'reject']),
            'has_date_dependency': any(word in text.lower() for word in ['date', 'time', 'schedule', 'when']),
            'has_user_roles': any(word in text.lower() for word in ['seller', 'buyer', 'manager', 'admin', 'customer']),
            'has_system_integration': any(word in text.lower() for word in ['on ', 'in ', 'system', 'platform']),
            'has_validation_needs': any(word in text.lower() for word in ['format', 'valid', 'invalid', 'check']),
            'is_multi_step': 'and' in text.lower() or len(text.split(',')) > 2,
            'involves_data_entry': any(word in text.lower() for word in ['enter', 'input', 'provide', 'fill']),
            'involves_external_system': bool(re.search(r'on\s+[A-Z]\w+', text))
        }
        
        return context

    def _extract_actor(self, text: str) -> str:
        """Extract who is performing the action"""
        actor_patterns = [
            r'[Aa]s\s+a\s+([^,]+)',
            r'[Aa]s\s+an\s+([^,]+)',
            r'([A-Z][a-z]+\s+[Mm]anager)',
            r'(seller|buyer|user|admin|customer|operator)'
        ]
        
        for pattern in actor_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return "user"

    def _extract_core_action(self, text: str) -> str:
        """Extract the main action being performed"""
        # Look for "I want to" pattern first
        want_pattern = r'[Ii]\s+want\s+to\s+([^,\.]+?)(?:\s+so\s+that|\s*,|$)'
        want_match = re.search(want_pattern, text)
        if want_match:
            return want_match.group(1).strip()
        
        # Look for specific business actions
        business_action_patterns = [
            r'(view|display|show|see)\s+([^,\.]+?)(?:\s+on\s+[A-Z]\w+|\s+based\s+on|\s+in|\s*,)',
            r'(approve|reject)\s+([^,\.]+?)(?:\s+and|\s+with|\s*,)',
            r'(create|add|generate)\s+([^,\.]+?)(?:\s+for|\s+in|\s*,)',
            r'(update|modify|change)\s+([^,\.]+?)(?:\s+to|\s+for|\s*,)',
            r'(delete|remove)\s+([^,\.]+?)(?:\s+from|\s*,)'
        ]
        
        for pattern in business_action_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} {match.group(2)}".strip()
        
        # Fallback to action verbs only
        action_patterns = [
            r'(view|display|show|see)\s+([^,\.]+)',
            r'(create|add|generate)\s+([^,\.]+)',
            r'(update|modify|change)\s+([^,\.]+)',
            r'(delete|remove)\s+([^,\.]+)',
            r'(approve|reject|process)\s+([^,\.]+)'
        ]
        
        for pattern in action_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} {match.group(2)}".strip()
        
        return "perform action"

    def _extract_main_object(self, text: str) -> str:
        """Extract the main business object being acted upon"""
        # Priority business objects
        business_objects = [
            'marketplace shipments', 'shipments', 'orders', 'products', 'payments',
            'users', 'accounts', 'inventory', 'reports', 'transactions'
        ]
        
        text_lower = text.lower()
        for obj in sorted(business_objects, key=len, reverse=True):
            if obj in text_lower:
                return obj
        
        # Pattern-based extraction
        object_patterns = [
            r'view\s+([a-zA-Z\s]+?)(?:\s+on|\s+in|\s+for|\s*,)',
            r'approve\s+([a-zA-Z\s]+?)(?:\s+and|\s*,)',
            r'create\s+([a-zA-Z\s]+?)(?:\s+for|\s+in|\s*,)'
        ]
        
        for pattern in object_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return "items"

    def _extract_conditions(self, text: str) -> List[str]:
        """Extract conditions and constraints"""
        condition_patterns = [
            r'based\s+on\s+([^,\.]+)',
            r'when\s+([^,\.]+)',
            r'if\s+([^,\.]+)',
            r'after\s+([^,\.]+)',
            r'before\s+([^,\.]+)'
        ]
        
        conditions = []
        for pattern in condition_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            conditions.extend([match.strip() for match in matches])
        
        return conditions

    def _extract_purpose(self, text: str) -> str:
        """Extract the business purpose/goal"""
        purpose_patterns = [
            r'[Ss]o\s+that\s+([^\.]+)',
            r'[Tt]o\s+ensure\s+([^\.]+)',
            r'[Ii]n\s+order\s+to\s+([^\.]+)'
        ]
        
        for pattern in purpose_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return ""

    def _extract_system_name(self, text: str) -> str:
        """Extract system/platform names"""
        system_patterns = [
            r'on\s+([A-Z][a-z]+)',
            r'in\s+([A-Z][a-z]+)',
            r'using\s+([A-Z][a-z]+)'
        ]
        
        for pattern in system_patterns:
            match = re.search(pattern, text)
            if match:
                system = match.group(1)
                if len(system) > 2 and system not in ['As', 'The', 'And', 'Or']:
                    return system
        
        return "system"

    def _extract_data_elements(self, text: str) -> List[str]:
        """Extract data elements and fields"""
        data_patterns = [
            r'(date|time|id|name|status|amount|quantity|price)',
            r'(pickup\s+date|delivery\s+date|creation\s+date)',
            r'(seller|buyer|customer)\s+(id|name|details)'
        ]
        
        elements = []
        for pattern in data_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            elements.extend([match if isinstance(match, str) else ' '.join(match) for match in matches])
        
        return list(set(elements))

    def _extract_business_rules_simple(self, text: str) -> List[str]:
        """Extract simple business rules"""
        rules = []
        
        # Look for must/should statements
        rule_patterns = [
            r'must\s+([^\.]+)',
            r'should\s+([^\.]+)',
            r'only\s+([^\.]+)',
            r'cannot\s+([^\.]+)'
        ]
        
        for pattern in rule_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            rules.extend([match.strip() for match in matches])
        
        return rules

    def _generate_positive_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate positive/happy path scenarios using intelligent analysis like ChatGPT"""
        scenarios = []
        
        # Extract intelligent elements
        main_action = requirement['action']
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        workflow_type = requirement['workflow_type']
        business_context = requirement['business_context']
        
        # Generate main positive scenario with intelligent context
        main_scenario = self._create_intelligent_main_scenario(requirement)
        scenarios.append(main_scenario)
        
        # Generate workflow-specific scenarios
        workflow_scenarios = self._generate_workflow_specific_scenarios(requirement)
        scenarios.extend(workflow_scenarios)
        
        # Generate context-based scenarios
        context_scenarios = self._generate_context_based_scenarios(requirement)
        scenarios.extend(context_scenarios)
        
        return scenarios

    def _create_intelligent_main_scenario(self, requirement: Dict[str, Any]) -> Dict[str, Any]:
        """Create intelligent main scenario with crisp, business-focused descriptions"""
        main_action = requirement['action']
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        workflow_type = requirement['workflow_type']
        conditions = requirement['conditions']
        
        # Generate crisp, business-focused title and description
        if workflow_type == 'approval' and 'shipment' in business_object:
            title = f"Verify approved {business_object} appears in system for processing"
            description = f"Approved {business_object} are correctly processed and visible in {target_system} system for further workflow actions."
        elif workflow_type == 'transaction' and 'money' in main_action:
            title = f"Verify successful {main_action} between accounts"
            description = f"Money transfers between accounts execute successfully with valid credentials and sufficient balance."
        elif workflow_type == 'booking' and 'appointment' in business_object:
            title = f"Verify successful {business_object} booking"
            description = f"Users can successfully book {business_object} with available time slots and complete required information."
        elif workflow_type == 'creation' and 'cart' in business_object:
            title = f"Verify successful addition of items to {business_object}"
            description = f"Products are correctly added to {business_object} and displayed with accurate details and pricing."
        elif workflow_type == 'viewing' and conditions:
            # For viewing with conditions (like filtering)
            condition = conditions[0] if conditions else "criteria"
            # Clean the condition to remove Gherkin syntax
            clean_condition = self._clean_gherkin_from_description(condition)
            title = f"Verify {business_object} filtering and display"
            description = f"System correctly filters and displays {business_object} based on specified criteria with accurate results."
        else:
            title = f"Verify {main_action} functionality"
            description = f"System successfully processes {main_action} for {business_object} with expected results."
        
        return {
            "title": title,
            "description": description,
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }

    def _generate_workflow_specific_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios specific to the workflow type"""
        scenarios = []
        workflow_type = requirement['workflow_type']
        business_context = requirement['business_context']
        
        if workflow_type == 'approval':
            scenarios.extend(self._generate_approval_scenarios(requirement))
        elif workflow_type == 'transaction':
            scenarios.extend(self._generate_transaction_scenarios(requirement))
        elif workflow_type == 'booking':
            scenarios.extend(self._generate_booking_scenarios(requirement))
        elif workflow_type == 'creation':
            scenarios.extend(self._generate_creation_scenarios(requirement))
        elif workflow_type == 'viewing':
            scenarios.extend(self._generate_viewing_scenarios(requirement))
        
        return scenarios

    def _generate_approval_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate approval-specific scenarios with crisp descriptions"""
        scenarios = []
        business_object = requirement['object']
        target_system = requirement['system']
        domain = requirement['domain']
        
        # Unapproved scenario
        unapproved_scenario = {
            "title": f"Verify unapproved {business_object} are not processed",
            "description": f"Unapproved {business_object} remain excluded from {target_system} workflow until approval is granted.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(unapproved_scenario)
        
        return scenarios

    def _generate_transaction_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate transaction-specific scenarios with crisp descriptions"""
        scenarios = []
        main_action = requirement['action']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        
        # Insufficient balance scenario
        insufficient_scenario = {
            "title": f"Verify {main_action} fails with insufficient balance",
            "description": f"Transactions are rejected when account balance is insufficient, with clear error messaging to users.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(insufficient_scenario)
        
        return scenarios

    def _generate_booking_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate booking-specific scenarios with crisp descriptions"""
        scenarios = []
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        
        # Unavailable slot scenario
        unavailable_scenario = {
            "title": f"Verify {business_object} booking fails for unavailable slots",
            "description": f"System prevents booking of unavailable time slots and suggests alternative available options.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(unavailable_scenario)
        
        return scenarios

    def _generate_creation_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate creation-specific scenarios with crisp descriptions"""
        scenarios = []
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        
        # Multiple items scenario
        multiple_scenario = {
            "title": f"Verify multiple items can be added to {business_object}",
            "description": f"System handles multiple simultaneous additions to {business_object} with correct quantities and details.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(multiple_scenario)
        
        return scenarios

    def _generate_viewing_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate viewing-specific scenarios with crisp descriptions"""
        scenarios = []
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        conditions = requirement['conditions']
        
        # Condition-based viewing
        if conditions:
            for condition in conditions[:1]:  # Take first condition
                # Clean the condition first
                clean_condition = self._clean_gherkin_from_description(condition)
                
                condition_scenario = {
                    "title": f"Verify {business_object} filtering based on {clean_condition}",
                    "description": f"System correctly filters and displays {business_object} based on specified criteria with accurate results.",
                    "severity": "S3 - Moderate",
                    "priority": "P3 - Medium",
                    "automation": "Manual",
                    "journey": self._determine_journey_from_domain(domain)
                }
                scenarios.append(condition_scenario)
        
        return scenarios

    def _generate_context_based_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on business context"""
        scenarios = []
        business_context = requirement['business_context']
        business_object = requirement['object']
        target_system = requirement['system']
        domain = requirement['domain']
        data_elements = requirement['data_elements']
        
        # Date dependency scenarios
        if business_context['has_date_dependency'] and any('date' in elem for elem in data_elements):
            past_date_scenario = {
                "title": f"Verify past date handling for {business_object}",
                "description": f"Verify that when past dates are selected, the system handles them appropriately with proper validation and user feedback.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(past_date_scenario)
        
        # Validation scenarios
        if business_context['has_validation_needs']:
            validation_scenario = {
                "title": f"Verify data validation for {business_object}",
                "description": f"Verify that invalid data formats are rejected and appropriate validation messages are displayed to the user.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(validation_scenario)
        
        return scenarios

    def _generate_negative_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate intelligent negative scenarios with crisp descriptions"""
        scenarios = []
        
        main_action = requirement['action']
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        workflow_type = requirement['workflow_type']
        data_elements = requirement['data_elements']
        business_context = requirement['business_context']
        
        # Generate workflow-specific negative scenarios
        if workflow_type == 'transaction':
            # Invalid account scenario
            invalid_account_scenario = {
                "title": f"Verify {main_action} fails with invalid account details",
                "description": f"System rejects transactions with invalid account information and displays appropriate error messages.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(invalid_account_scenario)
        
        # Data format validation scenarios
        if data_elements:
            for data_element in data_elements[:2]:
                format_scenario = {
                    "title": f"Verify invalid {data_element} format is rejected",
                    "description": f"System validates {data_element} format and rejects invalid entries with clear validation messages.",
                    "severity": "S3 - Moderate",
                    "priority": "P3 - Medium",
                    "automation": "Manual",
                    "journey": self._determine_journey_from_domain(domain)
                }
                scenarios.append(format_scenario)
        
        # Authorization scenario - universal
        unauthorized_scenario = {
            "title": f"Verify unauthorized access is prevented",
            "description": f"System prevents unauthorized users from accessing {business_object} and displays access denied messages.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(unauthorized_scenario)
        
        return scenarios

    def _generate_edge_case_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate edge case scenarios with crisp descriptions"""
        scenarios = []
        
        main_action = requirement['action']
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        
        # Large volume scenario - universal pattern
        large_volume_scenario = {
            "title": f"Verify system handles large volume of {business_object}",
            "description": f"System maintains performance and accuracy when processing large quantities of {business_object}.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(large_volume_scenario)
        
        # Concurrent operations scenario - universal
        concurrent_scenario = {
            "title": f"Verify concurrent user operations",
            "description": f"System handles simultaneous {main_action} operations by multiple users without conflicts or data corruption.",
            "severity": "S3 - Moderate",
            "priority": "P3 - Medium",
            "automation": "Manual",
            "journey": self._determine_journey_from_domain(domain)
        }
        scenarios.append(concurrent_scenario)
        
        return scenarios

    def _generate_boundary_scenarios(self, requirement: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate boundary scenarios with crisp descriptions"""
        scenarios = []
        
        main_action = requirement['action']
        business_object = requirement['object']
        actor = requirement['actor']
        target_system = requirement['system']
        domain = requirement['domain']
        data_elements = requirement['data_elements']
        
        # Date/time boundary scenarios - only if date/time is involved
        if any('date' in elem.lower() or 'time' in elem.lower() for elem in data_elements):
            current_date_scenario = {
                "title": f"Verify current date handling for {business_object}",
                "description": f"System correctly processes {business_object} when current date/time is selected with accurate timestamp handling.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(current_date_scenario)
            
            timezone_scenario = {
                "title": f"Verify timezone handling for {business_object}",
                "description": f"System displays {business_object} correctly for users in different timezones with proper time conversion.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(timezone_scenario)
        
        # Numeric boundary scenarios - only if amounts/quantities are involved
        if any('amount' in elem.lower() or 'quantity' in elem.lower() or 'price' in elem.lower() for elem in data_elements):
            min_value_scenario = {
                "title": f"Verify minimum value boundary for {business_object}",
                "description": f"System correctly processes {business_object} at minimum allowed values without errors.",
                "severity": "S3 - Moderate",
                "priority": "P3 - Medium",
                "automation": "Manual",
                "journey": self._determine_journey_from_domain(domain)
            }
            scenarios.append(min_value_scenario)
        
        return scenarios

    def _determine_journey_from_domain(self, domain: str) -> str:
        """Determine appropriate journey based on domain - mapped to actual Jira options"""
        journey_mapping = {
            'logistics': 'Account',  # Map to existing journey since 'Logistics Management' doesn't exist
            'payment': 'Account',
            'marketplace': 'Seller Management',  # Better mapping for marketplace
            'user_management': 'Account',
            'orders': 'Purchase',  # Map to existing Purchase journey
            'inventory': 'Account',
            'healthcare': 'Account',
            'ecommerce': 'Purchase',  # Map to Purchase journey for e-commerce
            'reporting': 'Account'
        }
        
        return journey_mapping.get(domain, 'Account')

    def _generate_action_scenarios(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate scenarios based on user actions"""
        try:
            scenarios = []
            
            for action in analysis.get('user_actions', []):
                if not isinstance(action, dict):
                    continue
                    
                description = action.get('description', '')
                if not description:
                    continue
                    
                # Clean the description
                clean_desc = self._clean_gherkin_from_description(description)
                
                # Create crisp description based on action type
                if 'payment' in clean_desc.lower():
                    crisp_description = "Payment action completes successfully with proper transaction processing and confirmation."
                elif 'navigation' in clean_desc.lower():
                    crisp_description = "Navigation action provides seamless page transitions with correct content loading."
                elif 'validation' in clean_desc.lower():
                    crisp_description = "Validation action correctly checks input data and provides appropriate feedback."
                elif 'display' in clean_desc.lower():
                    crisp_description = "Display action shows accurate information with proper formatting and completeness."
                else:
                    crisp_description = "Action completes successfully according to business requirements with expected outcomes."
                
                # Generate clean title
                clean_title = self._generate_smart_scenario_title(clean_desc)
                
                scenario = {
                    'title': clean_title,
                    'description': crisp_description,
                    'type': 'functional',
                    'severity': 'S2 - Major',
                    'priority': 'P2 - High'
                }
                scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Error generating user action scenarios: {str(e)}")
            return []