from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import GameSession, GameType, GameCategory, GameConfiguration
from players.models import Player, PlayerAnswer
from .websocket_utils import broadcast_round_started, broadcast_round_ended, start_timer_broadcast
import json
import logging
from collections import Counter

logger = logging.getLogger('game_sessions')


def start_first_round_internal(game_session):
    """Internal function to start the first round - used by both start_game and start_round"""
    from django.utils import timezone
    
    # Start the first round
    game_session.current_round_number = 1
    game_session.is_round_active = True
    game_session.current_round_started_at = timezone.now()
    game_session.save()

    # Get the new round info
    round_info = game_session.get_current_round_info()
    if not round_info:
        return JsonResponse({'error': 'Could not generate round information'}, status=400)

    # Broadcast round started to all connected clients
    broadcast_round_started(game_session, round_info)

    # Start timer broadcasting
    start_timer_broadcast(game_session, round_info)

    import time
    return JsonResponse({
        'status': 'success',
        'round_number': round_info['round_number'],
        'prompt': f"{round_info['category'].name} that start with {round_info['prompt_letter']}",
        'letter': round_info['prompt_letter'],
        'category': round_info['category'].name,
        'time_seconds': game_session.configuration.round_time_seconds,
        'started_at': time.time()  # Current timestamp for synchronization
    })


def perform_automatic_scoring(game_session, answers):
    """Perform automatic scoring for answers using the new scoring system"""
    if not answers:
        return

    # Get scoring configuration
    config = game_session.configuration

    # Count answer frequencies for duplicate detection
    answer_counts = Counter()
    for answer in answers:
        # Normalize answer for comparison (lowercase, strip whitespace)
        normalized_answer = answer.answer_text.lower().strip()
        answer_counts[normalized_answer] += 1

    # Score each answer
    for answer in answers:
        normalized_answer = answer.answer_text.lower().strip()
        is_unique = answer_counts[normalized_answer] == 1

        # Determine points based on uniqueness and validity
        if answer.is_valid:
            if is_unique:
                points = config.unique_answer_points
                reason = "unique_correct_answer"
            else:
                points = config.valid_answer_points
                reason = "duplicate_correct_answer"
        else:
            points = config.invalid_answer_points
            reason = "invalid_answer"

        # Update answer record
        answer.is_unique = is_unique
        old_points = answer.points_awarded
        answer.points_awarded = points
        answer.save()

        # Award points using new scoring system
        points_difference = points - old_points
        if points_difference != 0:
            if points_difference > 0:
                answer.player.award_points(
                    points_difference,
                    reason=reason,
                    round_number=game_session.current_round_number,
                    related_answer=answer
                )
            else:
                answer.player.deduct_points(
                    abs(points_difference),
                    reason=f"correction_{reason}",
                    round_number=game_session.current_round_number
                )


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
        game_type_id = request.POST.get('game_type')
        selected_categories = request.POST.getlist('categories')
        num_rounds = int(request.POST.get('num_rounds', 10))
        round_time = int(request.POST.get('round_time', 30))

        # Create game session with counter system defaults
        game_session = GameSession.objects.create(
            current_round_number=0,
            is_round_active=False
        )

        # Create configuration
        game_type = GameType.objects.get(id=game_type_id)
        config = GameConfiguration.objects.create(
            game_session=game_session,
            game_type=game_type,
            num_rounds=num_rounds,
            round_time_seconds=round_time
        )

        # Add selected categories (optional - dynamic categories will be used if none selected)
        if selected_categories:
            categories = GameCategory.objects.filter(id__in=selected_categories)
            config.categories.set(categories)
        # If no categories selected, the dynamic category system will handle it automatically

        messages.success(request, f'Game created! Game code: {game_session.game_code}')
        return redirect('game_sessions:game_master', game_code=game_session.game_code)

    # GET request - show configuration form
    game_types = GameType.objects.filter(is_active=True)
    categories = GameCategory.objects.filter(is_active=True).select_related('game_type')

    context = {
        'game_types': game_types,
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

    if game_session.status != 'waiting':
        return JsonResponse({'error': 'Game is not in waiting state'}, status=400)

    if game_session.player_count == 0:
        return JsonResponse({'error': 'No players have joined yet'}, status=400)

    game_session.start_game()

    # Broadcast game activation to all connected clients
    from .websocket_utils import broadcast_to_game
    broadcast_to_game(game_session.game_code, 'game_started', {
        'game_status': 'active',
        'message': 'Game has started! Get ready for the first round.',
        'player_count': game_session.player_count
    })

    return JsonResponse({'status': 'success', 'message': 'Game started! Ready for first round.'})


@require_http_methods(["POST"])
def restart_game(request, game_code):
    """Restart the game session for development/testing"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    # Only allow restart if game is active or finished
    if game_session.status not in ['active', 'finished']:
        return JsonResponse({'error': 'Game can only be restarted when active or finished'}, status=400)

    game_session.restart_game()

    # Keep players but reset their scores and ensure they're connected
    for player in game_session.players.all():
        player.current_score = 0
        player.is_connected = True  # Mark all players as connected for restart
        player.save()

    # Broadcast game restart to all connected clients (redirect to lobby)
    from .websocket_utils import broadcast_to_game
    import time
    
    # First broadcast - immediate restart notification
    broadcast_to_game(game_session.game_code, 'game_update', {
        'game_status': 'waiting',
        'player_count': game_session.players.count(),
        'message': 'Game restarted! Ready for next game.',
        'current_round': None,  # Explicitly set to None to trigger lobby redirect
        'restart_timestamp': int(time.time())  # Add timestamp for uniqueness
    })
    
    # Second broadcast after short delay to ensure delivery
    import threading
    def delayed_broadcast():
        time.sleep(0.5)  # 500ms delay
        broadcast_to_game(game_session.game_code, 'game_restart_confirmation', {
            'game_status': 'waiting',
            'player_count': game_session.players.count(),
            'message': 'Game restarted! Please return to lobby if you haven\'t already.',
            'force_redirect': True,
            'restart_timestamp': int(time.time())
        })
    
    thread = threading.Thread(target=delayed_broadcast)
    thread.daemon = True
    thread.start()

    return JsonResponse({'status': 'success', 'message': 'Game restarted successfully.'})


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

        # Update or create configuration
        try:
            config = game_session.configuration
            config.game_type_id = game_type_id
            config.num_rounds = num_rounds
            config.round_time_seconds = round_time
            config.save()
        except GameConfiguration.DoesNotExist:
            game_type = GameType.objects.get(id=game_type_id)
            config = GameConfiguration.objects.create(
                game_session=game_session,
                game_type=game_type,
                num_rounds=num_rounds,
                round_time_seconds=round_time
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

    if game_session.status != 'active':
        return JsonResponse({'error': 'Game is not active'}, status=400)

    # End current round if active
    if game_session.is_round_active:
        game_session.is_round_active = False
        game_session.save()

    # Check if game is complete
    if game_session.current_round_number >= game_session.configuration.num_rounds:
        # Game is finished, return final scores
        final_scores = game_session.get_final_scores()
        game_session.status = 'finished'
        from django.utils import timezone
        game_session.ended_at = timezone.now()
        game_session.save()

        # Broadcast game completion to all connected clients
        from .websocket_utils import broadcast_to_game
        broadcast_to_game(game_session.game_code, 'game_complete', {
            'game_status': 'finished',
            'final_scores': final_scores,
            'message': 'Game completed! Here are the final scores.'
        })

        return JsonResponse({
            'status': 'game_complete',
            'final_scores': final_scores,
            'message': 'Game completed! Here are the final scores.'
        })

    # Check if this is the first round
    if game_session.current_round_number == 0:
        return start_first_round_internal(game_session)

    # Start next round - increment counter
    game_session.current_round_number += 1
    game_session.is_round_active = True
    from django.utils import timezone
    game_session.current_round_started_at = timezone.now()
    game_session.save()

    # Get the new round info
    round_info = game_session.get_current_round_info()
    if not round_info:
        return JsonResponse({'error': 'Could not generate round information'}, status=400)

    # Broadcast round started to all connected clients
    broadcast_round_started(game_session, round_info)

    # Start timer broadcasting
    start_timer_broadcast(game_session, round_info)

    import time

    return JsonResponse({
        'status': 'success',
        'round_number': round_info['round_number'],
        'prompt': f"{round_info['category'].name} that start with {round_info['prompt_letter']}",
        'letter': round_info['prompt_letter'],
        'category': round_info['category'].name,
        'time_seconds': game_session.configuration.round_time_seconds,
        'started_at': time.time()  # Current timestamp for synchronization
    })


@require_http_methods(["POST"])
def end_round(request, game_code):
    """End the current round and calculate scores"""
    game_session = get_object_or_404(GameSession, game_code=game_code)

    if not game_session.is_round_active:
        return JsonResponse({'error': 'No active round'}, status=400)

    # End the round
    game_session.is_round_active = False
    game_session.save()

    # Get current round info
    round_info = game_session.get_current_round_info()
    if not round_info:
        return JsonResponse({'error': 'Could not get round information'}, status=400)

    # First, get answers from cache and create PlayerAnswer objects if they don't exist
    from django.core.cache import cache
    from players.models import PlayerAnswer, Player
    
    cache_key = f'game_{game_session.game_code}_round_{game_session.current_round_number}_answers'
    cached_answers = cache.get(cache_key, {})
    
    # Create PlayerAnswer objects for any cached answers that don't exist in DB
    # Only process answers from currently connected players
    for player_id_str, answer_text in cached_answers.items():
        try:
            player_id = int(player_id_str)
            player = Player.objects.get(id=player_id, game_session=game_session, is_connected=True)
            
            # Check if answer already exists in database
            existing_answer = PlayerAnswer.objects.filter(
                player=player,
                round_number=game_session.current_round_number
            ).first()
            
            if not existing_answer and answer_text.strip():
                # Create new answer object
                PlayerAnswer.objects.create(
                    player=player,
                    round_number=game_session.current_round_number,
                    answer_text=answer_text.strip(),
                    is_valid=True,  # Will be validated during scoring
                    points_awarded=0
                )
                logger.info(f"Created PlayerAnswer for connected player {player.name}: {answer_text}")
        except (ValueError, Player.DoesNotExist) as e:
            logger.warning(f"Could not create PlayerAnswer for player_id {player_id_str} (player may be disconnected): {e}")
    
    # Clear the cache for this round
    cache.delete(cache_key)

    # Now get all answers for this round from database (only from connected players)
    answers = PlayerAnswer.objects.filter(
        player__game_session=game_session,
        player__is_connected=True,
        round_number=game_session.current_round_number
    ).select_related('player').order_by('?')  # Random order

    # Perform automatic scoring using new system
    perform_automatic_scoring(game_session, answers)

    answer_data = []
    for answer in answers:
        answer_data.append({
            'player_name': answer.player.name,
            'answer_text': answer.answer_text,
            'points_awarded': answer.points_awarded,
            'is_valid': answer.is_valid,
            'is_unique': getattr(answer, 'is_unique', False),
        })

    # Broadcast round ended to all connected clients
    broadcast_round_ended(game_session, round_info, answer_data)

    return JsonResponse({
        'status': 'success',
        'answers': answer_data,
        'round_number': game_session.current_round_number,
        'is_final_round': game_session.current_round_number >= game_session.configuration.num_rounds
    })



def join_game(request):
    """Join a game session"""
    if request.method == 'POST':
        game_code = request.POST.get('game_code', '').upper()
        player_name = request.POST.get('player_name', '').strip()

        if not game_code or not player_name:
            messages.error(request, 'Please provide both game code and your name.')
            return render(request, 'game_sessions/join_game.html')

        try:
            game_session = GameSession.objects.get(game_code=game_code)
        except GameSession.DoesNotExist:
            messages.error(request, 'Game not found. Please check the game code.')
            return render(request, 'game_sessions/join_game.html')

        if not game_session.can_join:
            messages.error(request, 'Cannot join this game. It may be full or already started.')
            return render(request, 'game_sessions/join_game.html')

        # Simple approach: always create a new player for development
        # We can add session-based reconnection later if needed
        player = Player.objects.create(
            name=player_name,
            game_session=game_session,
            session_key=None  # Not using sessions for now
        )

        # Broadcast player join to all connected clients
        connected_players = game_session.players.filter(is_connected=True).order_by('joined_at')
        player_count = connected_players.count()
        logger.info(f"Player {player_name} joined game {game_code}. Total players: {player_count}")

        # Get players data for broadcast
        players_data = []
        for p in connected_players:
            players_data.append({
                'id': p.id,
                'name': p.name,
                'joined_at': p.joined_at.strftime('%H:%M:%S'),
                'total_score': p.current_score,
            })

        from .websocket_utils import broadcast_to_game
        broadcast_data = {
            'game_status': game_session.status,
            'player_count': player_count,
            'players': players_data,
            'message': f'{player_name} joined the game!'
        }
        logger.info(f"Broadcasting player join: {broadcast_data}")
        broadcast_to_game(game_session.game_code, 'game_update', broadcast_data)

        messages.success(request, f'Joined game {game_code} as {player_name}!')
        return redirect('players:player_lobby_with_id', game_code=game_code, player_id=player.id)

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

    # Add current round info if there's an active round
    if game_session.is_round_active:
        round_info = game_session.get_current_round_info()
        if round_info:
            # Calculate time remaining
            from django.utils import timezone
            if game_session.current_round_started_at:
                elapsed = (timezone.now() - game_session.current_round_started_at).total_seconds()
                time_remaining = max(0, game_session.configuration.round_time_seconds - elapsed)
            else:
                time_remaining = game_session.configuration.round_time_seconds

            response_data['current_round'] = {
                'round_number': round_info['round_number'],
                'category': round_info['category'].name,
                'letter': round_info['prompt_letter'],
                'prompt': f"A {round_info['category'].name.lower()} that starts with '{round_info['prompt_letter']}'",
                'time_remaining': int(time_remaining)
            }

    return JsonResponse(response_data)


@require_http_methods(["POST"])
def validate_answer(request, game_code):
    """Validate a player's answer and update points"""
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

        # Find the player answer using round_number
        try:
            player = Player.objects.get(game_session=game_session, name=player_name)
            answer = PlayerAnswer.objects.get(
                player=player,
                round_number=game_session.current_round_number,
                answer_text=answer_text
            )

            # Update the answer validation
            answer.is_valid = is_valid
            answer.is_unique = False  # Reset unique status when manually validating

            # Calculate points difference for score adjustment
            old_points = answer.points_awarded
            points_difference = points_awarded - old_points

            # Update the answer record for consistency
            answer.points_awarded = points_awarded
            answer.save()
            
            # Use new scoring system to award/deduct points
            if points_difference != 0:
                if points_difference > 0:
                    player.award_points(
                        points_difference,
                        reason="manual_validation",
                        round_number=game_session.current_round_number,
                        related_answer=answer
                    )
                else:
                    player.deduct_points(
                        abs(points_difference),
                        reason="manual_correction",
                        round_number=game_session.current_round_number
                    )

            # Broadcast score update to all connected clients
            from .websocket_utils import broadcast_score_update
            reason = "Answer validation" if is_valid else "Answer correction"
            broadcast_score_update(game_session, player.name, points_awarded, reason)

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
