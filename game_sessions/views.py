from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import GameSession, GameType, GameCategory, GameConfiguration
from players.models import Player, PlayerAnswer
# Removed unused websocket_utils imports - functions are imported locally where needed
import json
import logging
# Removed unused Counter import

logger = logging.getLogger('game_sessions')



def home(request):
    """Home page with options to create or join a game"""
    # Show recent games that are still active (for game master reconnection)
    recent_games = GameSession.objects.filter(
        status__in=['waiting', 'active']
    ).order_by('-created_at')[:5]

    context = {
        'recent_games': recent_games,
    }
    return render(request, 'game_sessions/home.html', context)


def create_game(request):
    """Create a new game session"""
    if request.method == 'POST':
        # Get form data
        game_type = request.POST.get('game_type')  # Now this is the actual round type
        selected_categories = request.POST.getlist('categories')
        num_rounds = int(request.POST.get('num_rounds', 10))
        round_time = int(request.POST.get('round_time', 30))

        # Create game session with counter system defaults
        game_session = GameSession.objects.create(
            current_round_number=0,
            is_round_active=False
        )

        # Generate round type sequence based on selected game type
        if game_type == 'flower_fruit_veg':
            sequence = ['flower_fruit_veg'] * num_rounds
        elif game_type == 'multiple_choice':
            sequence = ['multiple_choice'] * num_rounds
        else:
            # Default fallback
            sequence = ['flower_fruit_veg'] * num_rounds

        # Map the selected game type to the correct GameType record
        if game_type == 'flower_fruit_veg':
            game_type_obj, created = GameType.objects.get_or_create(
                name="Flower, Fruit & Veg",
                defaults={'description': "Players think of items in specific categories that start with a given letter"}
            )
        elif game_type == 'multiple_choice':
            game_type_obj, created = GameType.objects.get_or_create(
                name="Multiple Choice",
                defaults={'description': "Players answer multiple choice questions from various categories"}
            )
        else:
            # Default fallback to FFV
            game_type_obj, created = GameType.objects.get_or_create(
                name="Flower, Fruit & Veg",
                defaults={'description': "Players think of items in specific categories that start with a given letter"}
            )
            
        config = GameConfiguration.objects.create(
            game_session=game_session,
            game_type=game_type_obj,
            num_rounds=num_rounds,
            round_time_seconds=round_time,
            round_type_sequence=sequence
        )

        # Add selected categories (only for flower_fruit_veg games)
        if game_type == 'flower_fruit_veg' and selected_categories:
            categories = GameCategory.objects.filter(id__in=selected_categories)
            config.categories.set(categories)
        # If no categories selected, the dynamic category system will handle it automatically

        messages.success(request, f'Game created! Game code: {game_session.game_code}')
        return redirect('game_sessions:game_master', game_code=game_session.game_code)

    # GET request - show configuration form
    # Get all categories for Flower, Fruit & Veg games
    categories = GameCategory.objects.filter(is_active=True)

    context = {
        'categories': categories,
    }
    return render(request, 'game_sessions/create_game.html', context)


def game_master(request, game_code):
    """Game master view to manage the session"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    players = game_session.players.filter(is_connected=True).order_by('joined_at')

    # Get game configuration if it exists
    try:
        config = game_session.configuration
    except GameConfiguration.DoesNotExist:
        config = None

    # Get current round info using new counter system
    current_round_info = game_session.get_current_round_info()

    context = {
        'game_session': game_session,
        'players': players,
        'player_count': players.count(),
        'config': config,
        'current_round': current_round_info,  # Use dynamic round info
        'next_round': None,  # Not needed with counter system
    }

    # Choose template based on whether rounds have actually started
    # Only use the game_active.html template when rounds have begun
    if game_session.current_round_number > 0:
        return render(request, 'game_sessions/game_active.html', context)
    else:
        return render(request, 'game_sessions/game_master.html', context)


@require_http_methods(["POST"])
def start_game(request, game_code):
    """Start the game session"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    
    from .services import GameService
    game_service = GameService(game_session)
    result = game_service.start_game()
    
    if result['success']:
        return JsonResponse({'status': 'success', 'message': result['message']})
    else:
        return JsonResponse({'error': result['error']}, status=400)


@require_http_methods(["POST"])
def restart_game(request, game_code):
    """Restart the game session for development/testing"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    
    from .services import GameService
    game_service = GameService(game_session)
    result = game_service.restart_game()
    
    if result['success']:
        return JsonResponse({'status': 'success', 'message': result['message']})
    else:
        return JsonResponse({'error': result['error']}, status=400)


def configure_game(request, game_code):
    """Configure or reconfigure a game session"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # Only allow configuration if game is in waiting state
    if game_session.status != 'waiting':
        return JsonResponse({'error': 'Game can only be configured in waiting state'}, status=400)

    if request.method == 'POST':
        # Get form data
        game_type_id = request.POST.get('game_type')
        selected_categories = request.POST.getlist('categories')
        num_rounds = int(request.POST.get('num_rounds', 10))
        round_time = int(request.POST.get('round_time', 30))
        round_type_mode = request.POST.get('round_type_mode', 'category_letter')
        round_sequence = request.POST.get('round_sequence', '')

        # Get the selected GameType to determine sequence
        try:
            selected_game_type = GameType.objects.get(id=game_type_id)
            # Generate round type sequence based on selected GameType
            if selected_game_type.name == 'Flower, Fruit & Veg':
                sequence = ['flower_fruit_veg'] * num_rounds
            elif selected_game_type.name == 'Multiple Choice':
                sequence = ['multiple_choice'] * num_rounds
            else:
                # Default to flower_fruit_veg
                sequence = ['flower_fruit_veg'] * num_rounds
        except (GameType.DoesNotExist, ValueError):
            # Fallback to old logic if needed
            if round_type_mode == 'category_letter':
                sequence = ['flower_fruit_veg'] * num_rounds
            elif round_type_mode == 'multiple_choice':
                sequence = ['multiple_choice'] * num_rounds
            elif round_type_mode == 'mixed':
                # Alternate between the two types
                sequence = []
                for i in range(num_rounds):
                    if i % 2 == 0:
                        sequence.append('flower_fruit_veg')
                    else:
                        sequence.append('multiple_choice')
            elif round_type_mode == 'custom' and round_sequence:
                try:
                    sequence = json.loads(round_sequence)
                    # Ensure sequence matches number of rounds
                    if len(sequence) > num_rounds:
                        sequence = sequence[:num_rounds]
                    elif len(sequence) < num_rounds:
                        # Repeat the pattern to fill remaining rounds
                        while len(sequence) < num_rounds:
                            sequence.extend(json.loads(round_sequence))
                        sequence = sequence[:num_rounds]
                except (json.JSONDecodeError, ValueError):
                    # Fallback to category_letter if custom sequence is invalid
                    sequence = ['flower_fruit_veg'] * num_rounds
            else:
                # Default fallback
                sequence = ['flower_fruit_veg'] * num_rounds

        # Update or create configuration
        try:
            config = game_session.configuration
            config.game_type_id = game_type_id
            config.num_rounds = num_rounds
            config.round_time_seconds = round_time
            config.round_type_sequence = sequence
            config.save()
        except GameConfiguration.DoesNotExist:
            game_type = GameType.objects.get(id=game_type_id)
            config = GameConfiguration.objects.create(
                game_session=game_session,
                game_type=game_type,
                num_rounds=num_rounds,
                round_time_seconds=round_time,
                round_type_sequence=sequence
            )

        # Update selected categories
        if selected_categories:
            categories = GameCategory.objects.filter(id__in=selected_categories)
            config.categories.set(categories)
        else:
            config.categories.clear()

        messages.success(request, 'Game configuration updated!')
        return redirect('game_sessions:game_master', game_code=game_code)

    # GET request - show configuration form
    game_types = GameType.objects.filter(is_active=True)
    categories = GameCategory.objects.filter(is_active=True).select_related('game_type')

    # Get current configuration if it exists
    try:
        current_config = game_session.configuration
        current_categories = list(current_config.categories.values_list('id', flat=True))
    except GameConfiguration.DoesNotExist:
        current_config = None
        current_categories = []

    context = {
        'game_session': game_session,
        'game_types': game_types,
        'categories': categories,
        'current_config': current_config,
        'current_categories': current_categories,
    }
    return render(request, 'game_sessions/configure_game.html', context)


@require_http_methods(["POST"])
def start_round(request, game_code):
    """Start the next round using simple counter system"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    
    from .services import GameService
    game_service = GameService(game_session)
    result = game_service.start_round()
    
    if result['success']:
        return JsonResponse(result)
    else:
        return JsonResponse({'error': result['error']}, status=400)


@require_http_methods(["POST"])
def end_round(request, game_code):
    """End the current round and calculate scores"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    
    from .services import GameService
    game_service = GameService(game_session)
    result = game_service.end_round()
    
    if result['success']:
        return JsonResponse(result)
    else:
        return JsonResponse({'error': result['error']}, status=400)



def join_game(request):
    """Join a game session"""
    if request.method == 'POST':
        game_code = request.POST.get('game_code', '').upper()
        player_name = request.POST.get('player_name', '').strip()

        from .services import PlayerService
        result = PlayerService.join_game(game_code, player_name)
        
        if result['success']:
            messages.success(request, result['message'])
            return redirect('players:player_lobby_with_id', 
                          game_code=game_code, 
                          player_id=result['player'].id)
        else:
            messages.error(request, result['error'])
            return render(request, 'game_sessions/join_game.html')

    return render(request, 'game_sessions/join_game.html')


def game_status(request, game_code):
    """Get current game status for AJAX calls"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    response_data = {
        'game_status': game_session.status,
        'current_round_number': game_session.current_round_number,
        'is_round_active': game_session.is_round_active,
        'player_count': game_session.player_count,
    }

    # Add current round info if there's an active round or round has started
    if game_session.current_round_number > 0:
        # Use round handler to get consistent round info (with caching)
        from .round_handlers import get_round_handler
        round_handler = get_round_handler(game_session, game_session.current_round_number)
        round_info = round_handler.get_round_info()
        if round_info:
            response_data['current_round'] = {
                'round_number': round_info['round_number'],
                'round_type': round_info['round_type'],
                'time_remaining': int(round_info['time_remaining'])
            }
            if round_info['round_type'] == 'flower_fruit_veg':
                response_data['current_round'].update({
                    'category': round_info['category'].name,
                    'letter': round_info['prompt_letter'],
                    'prompt': f"A {round_info['category'].name.lower()} that starts with '{round_info['prompt_letter']}'",
                })
            elif round_info['round_type'] == 'multiple_choice':
                response_data['current_round'].update({
                    'question_text': round_info['question_text'],
                    'choices': round_info['choices'],
                    'category': round_info['category'],
                })

    return JsonResponse(response_data)


@require_http_methods(["POST"])
def validate_answer(request, game_code):
    """Validate a player's answer using round handler system"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    try:
        data = json.loads(request.body)
        player_name = data.get('player_name')
        answer_text = data.get('answer')  # JavaScript sends 'answer', model uses 'answer_text'
        is_valid = data.get('is_valid')
        points_awarded = data.get('points_awarded', 0)

        # Check if we have a current round using counter system
        if game_session.current_round_number == 0:
            return JsonResponse({'error': 'No round available for validation'}, status=400)
        
        # Get round handler and check if validation is supported
        from .round_handlers import get_round_handler
        round_handler = get_round_handler(game_session, game_session.current_round_number)
        
        if not round_handler.supports_manual_validation():
            return JsonResponse({'error': 'Manual validation not supported for this round type'}, status=400)

        # Find the player answer using round_number
        try:
            player = Player.objects.get(game_session=game_session, name=player_name)
            answer = PlayerAnswer.objects.get(
                player=player,
                round_number=game_session.current_round_number,
                answer_text=answer_text
            )

            # Use round handler to perform validation (handles all the scoring logic)
            if hasattr(round_handler, 'validate_answer_manually'):
                points_awarded = round_handler.validate_answer_manually(answer, is_valid)
            else:
                # Fallback for handlers without manual validation method
                answer.is_valid = is_valid
                answer.points_awarded = points_awarded
                answer.save()

            # Broadcast score update to all connected clients
            from .websocket_utils import broadcast_score_update
            reason = "Answer validation" if is_valid else "Answer correction"
            broadcast_score_update(game_session, player.name, points_awarded, reason)

            # Send individual player result for this specific validation
            from .websocket_utils import broadcast_individual_player_result
            broadcast_individual_player_result(game_session, player, answer, points_awarded, is_valid)

            return JsonResponse({
                'status': 'success',
                'message': f'Answer validated for {player_name}',
                'points_awarded': points_awarded
            })

        except (Player.DoesNotExist, PlayerAnswer.DoesNotExist):
            return JsonResponse({'error': 'Player or answer not found'}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_round_answers(request, game_code):
    """Get answers for the current round (for page refresh scenarios)"""
    game_session = get_object_or_404(GameSession, game_code=game_code)
    
    if game_session.current_round_number == 0:
        return JsonResponse({'status': 'success', 'answers': []})
    
    # Get current round info to include round type using consistent round handler
    from .round_handlers import get_round_handler
    round_handler = get_round_handler(game_session, game_session.current_round_number)
    round_info = round_handler.get_round_info() if game_session.current_round_number > 0 else None
    
    # Get answers for the current round
    answers = PlayerAnswer.objects.filter(
        player__game_session=game_session,
        round_number=game_session.current_round_number
    ).select_related('player').order_by('player__name')
    
    answers_data = []
    for answer in answers:
        answers_data.append({
            'player_name': answer.player.name,
            'answer_text': answer.answer_text,
            'answer': answer.answer_text,  # For compatibility
            'points_awarded': answer.points_awarded,
            'is_valid': answer.is_valid,
            'is_unique': answer.is_unique
        })
    
    response_data = {
        'status': 'success',
        'answers': answers_data,
        'round_number': game_session.current_round_number,
        'round_type': round_info['round_type'] if round_info else 'flower_fruit_veg'
    }
    
    # Add correct answer for multiple choice questions
    if round_info and round_info['round_type'] == 'multiple_choice':
        response_data['correct_answer'] = round_info.get('correct_answer')
    
    return JsonResponse(response_data)
