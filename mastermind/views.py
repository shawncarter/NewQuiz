"""
Mastermind Views

HTTP endpoints for mastermind functionality.
"""

import json
import logging
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from game_sessions.models import GameSession
from .services import MastermindService

logger = logging.getLogger('mastermind')


@require_http_methods(["POST"])
@csrf_exempt
def select_player(request, game_code):
    """API endpoint for GM to select a player for mastermind round"""
    try:
        game_session = get_object_or_404(GameSession, game_code=game_code)
        service = MastermindService(game_session)
        
        data = json.loads(request.body)
        player_id = data.get('player_id')
        round_number = data.get('round_number', game_session.current_round_number)
        
        if not player_id:
            return JsonResponse({'success': False, 'error': 'Player ID is required'}, status=400)
        
        result = service.select_player(round_number, player_id)
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse(result, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in select_player view: {e}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def ready_response(request, game_code):
    """API endpoint for player ready response"""
    try:
        game_session = get_object_or_404(GameSession, game_code=game_code)
        service = MastermindService(game_session)
        
        data = json.loads(request.body)
        is_ready = data.get('is_ready', False)
        round_number = data.get('round_number', game_session.current_round_number)
        
        result = service.player_ready_response(round_number, is_ready)
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse(result, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in ready_response view: {e}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def continue_to_next_player(request, game_code):
    """API endpoint for GM to continue to next player"""
    try:
        game_session = get_object_or_404(GameSession, game_code=game_code)
        service = MastermindService(game_session)
        
        data = json.loads(request.body)
        round_number = data.get('round_number', game_session.current_round_number)
        
        result = service.continue_to_next_player(round_number)
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse(result, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in continue_to_next_player view: {e}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def submit_rapid_fire_answers(request, game_code):
    """API endpoint for submitting rapid-fire answers"""
    try:
        game_session = get_object_or_404(GameSession, game_code=game_code)
        service = MastermindService(game_session)
        
        data = json.loads(request.body)
        player_id = data.get('player_id')
        answers = data.get('answers', [])
        round_number = data.get('round_number', game_session.current_round_number)
        
        if not player_id:
            return JsonResponse({'success': False, 'error': 'Player ID is required'}, status=400)
        
        if not answers:
            return JsonResponse({'success': False, 'error': 'Answers are required'}, status=400)
        
        result = service.submit_rapid_fire_answers(round_number, player_id, answers)
        
        if result['success']:
            return JsonResponse(result)
        else:
            return JsonResponse(result, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in submit_rapid_fire_answers view: {e}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@require_http_methods(["GET"])
def round_status(request, game_code):
    """Debug endpoint to check mastermind round status"""
    try:
        game_session = get_object_or_404(GameSession, game_code=game_code)
        service = MastermindService(game_session)
        
        round_number = request.GET.get('round_number', game_session.current_round_number)
        round_data = service.get_round_data(int(round_number))
        
        return JsonResponse({
            'game_code': game_code,
            'round_number': round_number,
            'round_data': round_data
        })
        
    except Exception as e:
        logger.error(f"Error in round_status view: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)