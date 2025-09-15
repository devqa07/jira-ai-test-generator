from app.utils.field_mappings import field_mappings
from loguru import logger
import re
from app.formatters.text_formatter import text_formatter

def get_custom_field_id(field_type, field_value):
    """Get the ID for a custom field value"""
    mapping = field_mappings.get(field_type)
    if not mapping:
        error_msg = f"Unknown field type: {field_type}"
        logger.error(error_msg)
        raise Exception(error_msg)

    field_id = mapping.get(field_value.strip())
    if not field_id:
        error_msg = f"Unknown value for {field_type}: {field_value}"
        logger.error(error_msg + f". Available values: {list(mapping.keys())}")
        raise Exception(error_msg)

    return field_id


def convert_to_adf(text):
    """
    Convert text to Atlassian Document Format with proper formatting for test scenarios.
    Handles description and steps sections with proper line breaks.
    """
    return text_formatter.convert_to_adf(text)

def process_bold_text(text):
    """Process bold text marked with ** in the content"""
    result = []
    # Pattern to find text surrounded by **
    pattern = r'\*\*(.*?)\*\*'
    
    # Split the text by bold markers
    parts = re.split(pattern, text)
    
    # Find all bold sections
    bold_parts = re.findall(pattern, text)
    
    # Reconstruct the text with proper ADF formatting
    for i, part in enumerate(parts):
        if part:
            result.append({"type": "text", "text": part})
        
        # Add bold part if available
        if i < len(bold_parts):
            result.append({"type": "text", "text": bold_parts[i], "marks": [{"type": "strong"}]})
    
    return result

def format_description_with_bullets(description):
    """Format description with bullet points - uses centralized formatter"""
    return text_formatter.format_with_bullets(description)
