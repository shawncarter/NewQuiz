"""
AI Question Service Factory

Factory class for creating appropriate AI question service instances
based on question type and requirements.

Updated to support both legacy separate services and new unified service.
"""

from typing import Optional, List, Union
from .ai_question_service import AIQuestionService
from .multiple_choice_ai_service import MultipleChoiceAIService
from .specialist_ai_service import SpecialistAIService
from .unified_ai_service import UnifiedAIService


# Configuration flag to control which service approach to use
USE_UNIFIED_SERVICE = False  # Set to False to use legacy separate services (TEMP FIX for MultipleChoiceQuestion compatibility)


class AIQuestionServiceFactory:
    """Factory for creating AI question service instances"""
    
    @staticmethod
    def create_multiple_choice_service(models_to_try: Optional[List[str]] = None) -> Union[MultipleChoiceAIService, UnifiedAIService]:
        """
        Create a service for generating multiple choice questions.
        
        Args:
            models_to_try: List of OpenAI models to try in order
            
        Returns:
            AI service instance for general questions
        """
        if USE_UNIFIED_SERVICE:
            return UnifiedAIService(models_to_try=models_to_try)
        else:
            return MultipleChoiceAIService(models_to_try=models_to_try)
    
    @staticmethod
    def create_specialist_service(models_to_try: Optional[List[str]] = None) -> Union[SpecialistAIService, UnifiedAIService]:
        """
        Create a service for generating specialist questions.
        
        Args:
            models_to_try: List of OpenAI models to try in order
            
        Returns:
            AI service instance for specialist questions
        """
        if USE_UNIFIED_SERVICE:
            return UnifiedAIService(models_to_try=models_to_try)
        else:
            return SpecialistAIService(models_to_try=models_to_try)
    
    @staticmethod
    def create_unified_service(models_to_try: Optional[List[str]] = None) -> UnifiedAIService:
        """
        Create a unified service that handles both general and specialist questions.
        
        Args:
            models_to_try: List of OpenAI models to try in order
            
        Returns:
            UnifiedAIService instance
        """
        return UnifiedAIService(models_to_try=models_to_try)
    
    @staticmethod
    def get_service_for_question_type(question_type: str, 
                                    models_to_try: Optional[List[str]] = None) -> AIQuestionService:
        """
        Get appropriate service based on question type.
        
        Args:
            question_type: 'multiple_choice', 'general', or 'specialist'
            models_to_try: List of OpenAI models to try in order
            
        Returns:
            Appropriate AI service instance
            
        Raises:
            ValueError: If question_type is not supported
        """
        if question_type in ['multiple_choice', 'general']:
            return AIQuestionServiceFactory.create_multiple_choice_service(models_to_try)
        elif question_type == 'specialist':
            return AIQuestionServiceFactory.create_specialist_service(models_to_try)
        else:
            raise ValueError(f"Unsupported question type: {question_type}")
    
    @staticmethod
    def set_unified_mode(enabled: bool):
        """
        Configure whether to use unified service or legacy separate services
        
        Args:
            enabled: True to use unified service, False for legacy services
        """
        global USE_UNIFIED_SERVICE
        USE_UNIFIED_SERVICE = enabled
    
    @staticmethod
    def is_unified_mode() -> bool:
        """Check if unified service mode is enabled"""
        return USE_UNIFIED_SERVICE


# Convenience functions for easy access
def get_multiple_choice_service(models_to_try: Optional[List[str]] = None) -> Union[MultipleChoiceAIService, UnifiedAIService]:
    """Get multiple choice AI service instance"""
    return AIQuestionServiceFactory.create_multiple_choice_service(models_to_try)


def get_specialist_service(models_to_try: Optional[List[str]] = None) -> Union[SpecialistAIService, UnifiedAIService]:
    """Get specialist AI service instance"""
    return AIQuestionServiceFactory.create_specialist_service(models_to_try)


def get_unified_service(models_to_try: Optional[List[str]] = None) -> UnifiedAIService:
    """Get unified AI service instance that handles both question types"""
    return AIQuestionServiceFactory.create_unified_service(models_to_try)


def set_unified_service_mode(enabled: bool):
    """
    Set whether to use unified service or legacy separate services
    
    Args:
        enabled: True to use unified service, False for legacy services
    """
    AIQuestionServiceFactory.set_unified_mode(enabled)


def is_unified_service_mode() -> bool:
    """Check if unified service mode is enabled"""
    return AIQuestionServiceFactory.is_unified_mode()