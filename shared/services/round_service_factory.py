"""
Round Service Factory

Factory class for creating round service instances with proper dependencies
and configuration for different game session requirements.
"""

from typing import Optional
from .round_service import RoundService
from .round_generator_service import RoundGeneratorService


class RoundServiceFactory:
    """Factory for creating round service instances"""
    
    @staticmethod
    def create_round_service(game_session) -> RoundService:
        """
        Create a round service for the given game session.
        
        Args:
            game_session: GameSession instance
            
        Returns:
            Configured RoundService instance
        """
        return RoundService(game_session)
    
    @staticmethod
    def create_round_generator(game_session) -> RoundGeneratorService:
        """
        Create a round generator for the given game session.
        
        Args:
            game_session: GameSession instance
            
        Returns:
            Configured RoundGeneratorService instance
        """
        return RoundGeneratorService(game_session)


# Convenience functions for easy access
def get_round_service(game_session) -> RoundService:
    """Get round service instance for a game session"""
    return RoundServiceFactory.create_round_service(game_session)


def get_round_generator(game_session) -> RoundGeneratorService:
    """Get round generator instance for a game session"""
    return RoundServiceFactory.create_round_generator(game_session)