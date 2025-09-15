"""
Centralized Text Formatting Module

This module provides a single source of truth for all text formatting
operations in the Jira test case generation system.
"""

import re
from typing import List, Dict, Any
from functools import lru_cache
from loguru import logger


class TextFormatter:
    """Centralized text formatter for test scenarios and descriptions"""
    
    def __init__(self):
        """Initialize text formatter with compiled regex patterns for better performance"""
        # Initialize logger
        self.logger = logger
        
        # Pre-compile regex patterns for better performance
        self._patterns = {
            'whitespace': re.compile(r'\s+'),
            'scenario_prefix': re.compile(r'^(verify|validate|check|test)\s+', re.IGNORECASE),
            'extra_spaces': re.compile(r'\s{2,}'),
            'newline_normalization': re.compile(r'\n+'),
            'step_numbering': re.compile(r'^\d+\.\s*'),
            'bullet_points': re.compile(r'^[-*•]\s*'),
            'common_prefixes': re.compile(r'^(to|that|if|when|the|a|an)\s+', re.IGNORECASE)
        }
        
        # Pre-defined step formatting templates
        self._step_templates = {
            'numbered': "{}. {}",
            'bulleted': "• {}",
            'plain': "{}"
        }

    def format_steps(self, steps: List[str], style: str = 'numbered') -> str:
        """Format steps with proper line breaks and numbering/bullets"""
        if not steps:
            return ""
        
        formatted_steps = []
        template = self._step_templates.get(style, self._step_templates['numbered'])
        
        for i, step in enumerate(steps, 1):
            if not step or not step.strip():
                continue
                
            # Clean the step text
            clean_step = self._patterns['whitespace'].sub(' ', step.strip())
            
            # Apply formatting based on style
            if style == 'numbered':
                formatted_step = template.format(i, clean_step)
            elif style == 'bulleted':
                formatted_step = template.format(clean_step)
            else:
                formatted_step = clean_step
                
            formatted_steps.append(formatted_step)
        
        return '\n'.join(formatted_steps)
    
    @lru_cache(maxsize=500)
    def format_scenario_description(self, scenario_type: str, description: str, steps: tuple) -> str:
        """
        Format scenario description to be crisp and meaningful - NO STEPS INCLUDED
        Returns clean, business-focused descriptions only
        """
        # Clean and format the description to be concise and impactful
        clean_description = self._create_impactful_description(description, scenario_type)
        
        # Return only the clean description - NO STEPS EVER
        return clean_description
    
    def _create_impactful_description(self, description: str, scenario_type: str) -> str:
        """Create a concise, impactful description with 'Verify that' prefix"""
        # Remove redundant prefixes and verbose language
        clean_desc = description.replace("Test ", "").replace("Verify that the system correctly implements the requirement: ", "")
        clean_desc = clean_desc.replace("Test functionality: ", "").replace("functionality: ", "")
        clean_desc = clean_desc.replace("Test system behavior when ", "System behavior when ")
        clean_desc = clean_desc.replace("Test automatic toggling behavior of ", "Auto-toggle behavior of ")
        clean_desc = clean_desc.replace("Test ", "")
        
        # Ensure first letter is capitalized
        if clean_desc:
            clean_desc = clean_desc[0].upper() + clean_desc[1:] if len(clean_desc) > 1 else clean_desc.upper()
        
        # Add "Verify that" prefix
        if not clean_desc.lower().startswith('verify'):
            clean_desc = f"Verify that {clean_desc.lower()}"
        
        return clean_desc.strip()
    
    @lru_cache(maxsize=1000)
    def clean_scenario_text(self, text: str) -> str:
        """Clean up scenario text by removing unnecessary phrases and formatting with caching"""
        if not text:
            return ""
        
        # Normalize whitespace
        text = self._patterns['whitespace'].sub(' ', text.strip())
        
        # Remove common scenario prefixes
        text = self._patterns['scenario_prefix'].sub('', text)
        
        # Remove common language prefixes
        text = self._patterns['common_prefixes'].sub('', text)
        
        # Final cleanup
        return text.strip()
    
    def convert_to_adf(self, text: str) -> Dict[str, Any]:
        """
        Convert text to Atlassian Document Format - CRISP DESCRIPTIONS ONLY
        
        Args:
            text: Plain text description
            
        Returns:
            ADF formatted dictionary with clean description only
        """
        # Use only the description part, ignore any steps sections
        description = text.split("\n\nSteps:\n")[0].strip()

        content = []

        # Add description as a paragraph
        content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": description
                }
            ]
        })

        return {"version": 1, "type": "doc", "content": content}
    
    def format_with_bullets(self, description: str) -> str:
        """
        Format a description as bullet points with bold text
        
        Args:
            description: Text to format as bullets
            
        Returns:
            Formatted text with bullet points
        """
        # Split description into lines
        lines = description.strip().split('\n')
        formatted_text = ""
        
        for line in lines:
            line = line.strip()
            if line:
                # Format each line as a bullet point with bold text
                formatted_text += f"• **{line}**\n"
        
        return formatted_text
    
    def extract_plain_text_from_adf(self, adf_content: Dict[str, Any]) -> str:
        """
        Extract plain text from Atlassian Document Format
        
        Args:
            adf_content: ADF formatted content
            
        Returns:
            Plain text string
        """
        if not isinstance(adf_content, dict):
            return str(adf_content)

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
                    elif item.get('type') == 'orderedList':
                        for i, list_item in enumerate(item.get('content', []), 1):
                            text.append(f'\n{i}. ')
                            text.extend(process_content(list_item.get('content', [])))
                    elif item.get('type') == 'paragraph':
                        text.extend(process_content(item.get('content', [])))
                        text.append('\n')
                return text

            text_content = process_content(adf_content.get('content', []))
            
        except Exception as e:
            self.logger.warning(f"Error extracting description text: {str(e)}")
            return str(adf_content)

        return ''.join(text_content).strip()
    
    def normalize_text_for_comparison(self, text: str) -> str:
        """Normalize text for comparison purposes with aggressive normalization"""
        if not text:
            return ""
        
        # Convert to lowercase and normalize whitespace
        normalized = self._patterns['whitespace'].sub(' ', text.lower().strip())
        
        # Remove common prefixes and suffixes
        normalized = self._patterns['scenario_prefix'].sub('', normalized)
        normalized = self._patterns['common_prefixes'].sub('', normalized)
        
        return normalized

    @lru_cache(maxsize=200)
    def extract_key_phrases(self, text: str) -> set:
        """Extract key phrases from text for semantic comparison with caching"""
        if not text:
            return set()
        
        # Normalize text
        normalized = self.normalize_text_for_comparison(text)
        
        # Split into words and filter out common words
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'among', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'can', 'that', 'this', 'these', 'those'
        }
        
        words = normalized.split()
        key_phrases = {word for word in words if len(word) > 2 and word not in common_words}
        
        return key_phrases

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using key phrase overlap"""
        if not text1 or not text2:
            return 0.0
        
        phrases1 = self.extract_key_phrases(text1)
        phrases2 = self.extract_key_phrases(text2)
        
        if not phrases1 or not phrases2:
            return 0.0
        
        intersection = len(phrases1.intersection(phrases2))
        union = len(phrases1.union(phrases2))
        
        return intersection / union if union > 0 else 0.0

    @lru_cache(maxsize=100)
    def format_test_title(self, action: str, context: str = "") -> str:
        """Format a test title to be clear and descriptive with caching"""
        if not action:
            return ""
        
        # Clean up the action text
        clean_action = self.clean_scenario_text(action)
        
        # Ensure proper verb prefix
        if not any(clean_action.lower().startswith(verb) for verb in ['verify', 'test', 'check', 'validate']):
            clean_action = f"Verify {clean_action}"
        
        # Add context if provided
        if context:
            clean_action = f"{clean_action} {context}"
        
        # Capitalize first letter and ensure reasonable length
        title = clean_action[0].upper() + clean_action[1:] if clean_action else ""
        
        # Truncate if too long (keeping it under 100 chars for readability)
        if len(title) > 100:
            title = title[:97] + "..."
        
        return title

    def format_multiline_text(self, text: str, max_line_length: int = 80) -> str:
        """Format text to have reasonable line lengths for better readability"""
        if not text:
            return ""
        
        # Split by existing newlines first
        paragraphs = text.split('\n')
        formatted_paragraphs = []
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                formatted_paragraphs.append("")
                continue
            
            # Wrap long lines
            words = paragraph.split()
            current_line = []
            current_length = 0
            
            for word in words:
                word_length = len(word)
                
                if current_length + word_length + 1 <= max_line_length:
                    current_line.append(word)
                    current_length += word_length + 1
                else:
                    if current_line:
                        formatted_paragraphs.append(' '.join(current_line))
                    current_line = [word]
                    current_length = word_length
            
            if current_line:
                formatted_paragraphs.append(' '.join(current_line))
        
        return '\n'.join(formatted_paragraphs)

    def clean_step_text(self, step: str) -> str:
        """Clean individual step text for better formatting"""
        if not step:
            return ""
        
        # Remove existing numbering/bullets
        clean = self._patterns['step_numbering'].sub('', step)
        clean = self._patterns['bullet_points'].sub('', clean)
        
        # Normalize whitespace
        clean = self._patterns['whitespace'].sub(' ', clean.strip())
        
        # Ensure sentence case
        if clean and not clean[0].isupper():
            clean = clean[0].upper() + clean[1:]
        
        return clean

    def validate_text_quality(self, text: str, min_length: int = 10, max_length: int = 1000) -> Dict[str, Any]:
        """Validate text quality and provide suggestions"""
        if not text:
            return {
                'valid': False,
                'issues': ['Text is empty'],
                'suggestions': ['Provide descriptive text']
            }
        
        issues = []
        suggestions = []
        
        # Length checks
        if len(text) < min_length:
            issues.append(f'Text too short (minimum {min_length} characters)')
            suggestions.append('Add more descriptive details')
        
        if len(text) > max_length:
            issues.append(f'Text too long (maximum {max_length} characters)')
            suggestions.append('Consider breaking into smaller sections')
        
        # Quality checks
        words = text.split()
        if len(words) < 3:
            issues.append('Text contains too few words')
            suggestions.append('Add more descriptive words')
        
        # Check for repeated words
        word_counts = {}
        for word in words:
            word_lower = word.lower()
            word_counts[word_lower] = word_counts.get(word_lower, 0) + 1
        
        repeated_words = [word for word, count in word_counts.items() if count > 3 and len(word) > 3]
        if repeated_words:
            issues.append(f'Repeated words found: {", ".join(repeated_words[:3])}')
            suggestions.append('Vary word usage for better readability')
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'suggestions': suggestions,
            'word_count': len(words),
            'character_count': len(text)
        }


# Create a singleton instance for easy importing
text_formatter = TextFormatter() 