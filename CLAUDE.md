# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django-based multiplayer quiz game with WebSocket support for real-time gameplay. Players join game sessions using 6-character codes and participate in various round types including "Flower, Fruit, Vegetable" categorization games, multiple choice questions, and Mastermind specialist rounds.

## Development Commands

### Setup & Environment
```bash
# Initial setup
./setup_dev.sh                    # Full development environment setup
source venv/bin/activate          # Activate virtual environment

# Install Django dependencies (current requirements.txt contains system packages)
pip install django channels daphne channels-redis openai python-dotenv watchdog coverage

# Alternative: Install from requirements if Django deps are added
pip install -r requirements.txt   # Install dependencies (after adding Django packages)
```

### Running the Application
```bash
# Development server with WebSocket support (recommended)
python run_daphne.py              # Runs Daphne with auto-reload on file changes

# Alternative: Django dev server (HTTP only, no WebSockets)
python manage.py runserver        # Limited functionality, use for HTTP-only testing
```

### Database Management
```bash
python manage.py migrate          # Apply database migrations
python manage.py makemigrations   # Create new migrations
python manage.py check            # Validate Django configuration
```

### Testing
```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test game_sessions
python manage.py test players
python manage.py test mastermind

# Run individual test files
python manage.py test game_sessions.tests.GameSessionModelTests
python manage.py test game_sessions.test_services
python manage.py test players.test_additional_coverage

# Generate test coverage report
coverage run --source='.' manage.py test
coverage html                     # Generates htmlcov/ directory
```

### Management Commands
```bash
# Game data setup
python manage.py setup_game_data

# Question generation (requires OPENAI_API_KEY in .env)
python manage.py generate_sample_questions
python manage.py generate_bulk_questions
python manage.py test_ai_generation

# Analytics
python manage.py show_question_stats
python manage.py analyze_ai_models

# Mastermind-specific commands
python manage.py generate_mastermind_questions
python manage.py migrate_specialist_questions
```

## Architecture Overview

### Application Structure
- **quiz_game/**: Main Django project directory containing settings and ASGI configuration
- **game_sessions/**: Core game logic, WebSocket consumers, round handlers, and models
- **players/**: Player management, scoring, and answer tracking
- **mastermind/**: Specialist question handling for Mastermind-style rounds

### Key Architectural Components

#### WebSocket Communication
- **ASGI Application**: `quiz_game/asgi.py` configures WebSocket routing via Django Channels
- **Game Consumer**: `game_sessions/consumers.py` handles real-time game communication
- **Channel Layer**: In-memory channel layer for message passing between WebSocket connections

#### Round Handler System
- **Base Handler**: `game_sessions/round_handlers.py` provides abstract base class for round types
- **Polymorphic Design**: Each round type (flower_fruit_veg, multiple_choice, mastermind) has specialized handlers
- **Dynamic Round Generation**: Rounds generated on-demand using deterministic algorithms with game-code-based seeding

#### Data Models
- **GameSession**: Central model managing game state, round progression, and player coordination
- **Player**: Player instances linked to game sessions with scoring and connection tracking  
- **GameConfiguration**: Configurable game parameters (rounds, timing, scoring rules)
- **MultipleChoiceQuestion**: Question bank with AI generation support and usage tracking

#### Scoring System
- **Real-time Updates**: Player scores updated immediately via WebSocket broadcasts
- **Flexible Scoring**: Configurable points for unique answers, valid answers, and incorrect answers
- **Streak Tracking**: Correct answer streaks maintained per player

### Key Features

#### Game Management
- **Dynamic Game Codes**: 6-character alphanumeric codes generated for each session
- **Round Types**: Support for multiple game formats with extensible round handler architecture
- **Real-time Synchronization**: All players see consistent game state via WebSocket groups

#### Question Generation
- **AI Integration**: OpenAI API integration for generating multiple choice questions
- **Question Recycling**: Intelligent reuse of questions with usage tracking and cooldown periods
- **Category Management**: Flexible category system for organizing questions by topic

#### Developer Tools
- **Auto-reload**: `run_daphne.py` provides development server with automatic reloading
- **Test Coverage**: Comprehensive test suite with HTML coverage reporting
- **Game Restart**: Development-friendly game restart functionality preserving player connections

## Important Implementation Details

### Round System Design
- Rounds are generated dynamically using counter-based system (`current_round_number`)
- No database round objects - all round data computed on-demand for consistency
- Game code and round number used as deterministic seeds for reproducible content

### WebSocket Message Flow
1. Players connect via `/ws/game/{game_code}/`
2. Consumer joins game group and sends current game state
3. Game master actions broadcast updates to all players in group
4. Real-time score updates and round transitions handled via group messaging

### Database Schema
- SQLite for development with potential PostgreSQL production deployment
- Django ORM with migrations for schema management
- Foreign key relationships maintain referential integrity across game components

### Environment Configuration
- `.env` file support for API keys and configuration (see `.env.example` for template)
- `OPENAI_API_KEY` required for AI question generation
- `SECRET_KEY` for Django security (auto-generated fallback provided)
- `DEBUG=true` for development mode
- `ALLOWED_HOSTS` configurable for deployment (defaults include localhost and common dev IPs)

## Development Notes

### Project Setup Requirements
- **Important**: The current `requirements.txt` contains system-level packages, not Django project dependencies
- For a fresh setup, manually install: `django channels daphne channels-redis openai python-dotenv watchdog coverage`
- The `setup_dev.sh` script handles environment setup and basic configuration
- Virtual environment activation is required before running any Django commands

### Testing Patterns
- Test files follow Django conventions (`test_*.py` or `tests.py`)
- WebSocket testing requires special test client setup
- Coverage reports generated in `htmlcov/` directory

### Logging Configuration
- Comprehensive logging setup in `settings.py`
- Module-specific loggers for `game_sessions`, `players`, `mastermind`, and `websockets`
- Log output to both console and `quiz_game.log` file

### Code Organization
- Apps follow Django best practices with clear separation of concerns
- Round handlers use abstract base classes for consistent interfaces
- WebSocket consumers handle both connection management and game logic