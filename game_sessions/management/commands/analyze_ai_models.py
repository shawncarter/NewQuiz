from django.core.management.base import BaseCommand
from django.conf import settings
import openai
import json
import time
from game_sessions.ai_questions import generate_ai_question
from game_sessions.models import MultipleChoiceQuestion

class Command(BaseCommand):
    help = 'Analyze available OpenAI models and test question generation performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-count',
            type=int,
            default=10,
            help='Number of test questions per model (default: 10)',
        )

    def handle(self, *args, **options):
        test_count = options['test_count']
        
        if not settings.OPENAI_API_KEY:
            self.stdout.write(self.style.ERROR('No OpenAI API key configured'))
            return
        
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Get available models
        self.stdout.write('🔍 Fetching available OpenAI models...')
        try:
            models = client.models.list()
            
            # Filter for relevant models
            relevant_models = []
            for model in models.data:
                model_id = model.id
                if any(keyword in model_id.lower() for keyword in ['gpt-4', 'gpt-3.5', 'o1', 'o3']):
                    relevant_models.append({
                        'id': model_id,
                        'created': model.created,
                        'owned_by': model.owned_by
                    })
            
            self.stdout.write(f'📋 Found {len(relevant_models)} relevant models:')
            for model in sorted(relevant_models, key=lambda x: x['id']):
                self.stdout.write(f"  • {model['id']} (owned by: {model['owned_by']})")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to fetch models: {e}'))
            return
        
        # Test specific models for question generation
        test_models = ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo', 'o1-mini']
        available_test_models = [m for m in test_models if any(m == model['id'] for model in relevant_models)]
        
        if not available_test_models:
            self.stdout.write(self.style.WARNING('None of the preferred test models are available'))
            # Try the first few available models
            available_test_models = [model['id'] for model in relevant_models[:3]]
        
        self.stdout.write(f'\n🧪 Testing question generation with {test_count} questions per model...')
        self.stdout.write('=' * 80)
        
        results = {}
        
        for model_id in available_test_models:
            self.stdout.write(f'\n🤖 Testing model: {model_id}')
            
            # Track starting question count
            start_count = MultipleChoiceQuestion.objects.count()
            
            # Test with this model
            success_count = 0
            duplicate_count = 0
            error_count = 0
            total_tokens = 0
            
            # Temporarily modify the ai_questions module to use this specific model
            original_models = None
            
            for i in range(test_count):
                try:
                    # Create a test prompt
                    prompt = f"""Generate a multiple choice question for the category "Science".

Requirements:
- Return ONLY valid JSON format
- 4 answer choices exactly
- Make it moderately challenging but fair
- Ensure variety - avoid repeating common knowledge questions

Format:
{{
    "question": "Your question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "Science"
}}"""

                    # Test the model directly
                    if 'o1' in model_id:
                        # o1 models have different parameters
                        response = client.chat.completions.create(
                            model=model_id,
                            messages=[{"role": "user", "content": prompt}],
                            max_completion_tokens=300
                        )
                    else:
                        response = client.chat.completions.create(
                            model=model_id,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=300,
                            temperature=0.8
                        )
                    
                    # Track token usage
                    if hasattr(response, 'usage') and response.usage:
                        total_tokens += response.usage.total_tokens
                    
                    # Try to parse the response
                    ai_response = response.choices[0].message.content.strip()
                    
                    if not ai_response:
                        error_count += 1
                        continue
                    
                    try:
                        question_data = json.loads(ai_response)
                        
                        # Check if it would be a duplicate
                        from game_sessions.ai_questions import is_duplicate_question
                        if is_duplicate_question(question_data):
                            duplicate_count += 1
                        else:
                            success_count += 1
                            
                    except json.JSONDecodeError:
                        error_count += 1
                        
                except Exception as e:
                    error_count += 1
                    self.stdout.write(f'    Error on question {i+1}: {str(e)[:100]}...')
                
                # Small delay to avoid rate limits
                time.sleep(0.5)
            
            # Calculate results
            end_count = MultipleChoiceQuestion.objects.count()
            actual_created = end_count - start_count
            
            success_rate = (success_count / test_count) * 100 if test_count > 0 else 0
            duplicate_rate = (duplicate_count / test_count) * 100 if test_count > 0 else 0
            error_rate = (error_count / test_count) * 100 if test_count > 0 else 0
            
            avg_tokens = total_tokens / test_count if test_count > 0 else 0
            
            results[model_id] = {
                'success_count': success_count,
                'duplicate_count': duplicate_count,
                'error_count': error_count,
                'success_rate': success_rate,
                'duplicate_rate': duplicate_rate,
                'error_rate': error_rate,
                'avg_tokens_per_question': avg_tokens,
                'total_tokens': total_tokens
            }
            
            self.stdout.write(f'  ✅ Successful: {success_count}/{test_count} ({success_rate:.1f}%)')
            self.stdout.write(f'  🔄 Duplicates: {duplicate_count}/{test_count} ({duplicate_rate:.1f}%)')
            self.stdout.write(f'  ❌ Errors: {error_count}/{test_count} ({error_rate:.1f}%)')
            self.stdout.write(f'  🔢 Avg tokens/question: {avg_tokens:.1f}')
        
        # Summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write('📊 PERFORMANCE SUMMARY')
        self.stdout.write('=' * 80)
        
        best_success = max(results.items(), key=lambda x: x[1]['success_rate'])
        lowest_duplicate = min(results.items(), key=lambda x: x[1]['duplicate_rate'])
        most_efficient = min(results.items(), key=lambda x: x[1]['avg_tokens_per_question'])
        
        self.stdout.write(f'🏆 Best Success Rate: {best_success[0]} ({best_success[1]["success_rate"]:.1f}%)')
        self.stdout.write(f'🔄 Lowest Duplicate Rate: {lowest_duplicate[0]} ({lowest_duplicate[1]["duplicate_rate"]:.1f}%)')
        self.stdout.write(f'💰 Most Token Efficient: {most_efficient[0]} ({most_efficient[1]["avg_tokens_per_question"]:.1f} tokens/question)')
        
        # Cost estimates (approximate OpenAI pricing)
        cost_estimates = {
            'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},  # per 1K tokens
            'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},
            'gpt-4o': {'input': 0.0025, 'output': 0.01},
            'o1-mini': {'input': 0.003, 'output': 0.012}
        }
        
        self.stdout.write('\n💰 ESTIMATED COSTS (per 1000 questions):')
        for model_id, result in results.items():
            if model_id in cost_estimates:
                # Rough estimate: 50% input, 50% output tokens
                avg_tokens = result['avg_tokens_per_question']
                input_tokens = avg_tokens * 0.5
                output_tokens = avg_tokens * 0.5
                
                cost_per_question = (input_tokens * cost_estimates[model_id]['input'] / 1000) + \
                                  (output_tokens * cost_estimates[model_id]['output'] / 1000)
                cost_per_1000 = cost_per_question * 1000
                
                self.stdout.write(f'  {model_id}: ~${cost_per_1000:.2f} (${cost_per_question:.4f} per question)')
        
        self.stdout.write(f'\n🎯 RECOMMENDATION:')
        if results:
            # Score models: success rate - duplicate rate - (cost factor)
            best_model = None
            best_score = -1000
            
            for model_id, result in results.items():
                score = result['success_rate'] - (result['duplicate_rate'] * 2) - (result['error_rate'] * 3)
                if score > best_score:
                    best_score = score
                    best_model = model_id
            
            self.stdout.write(f'Use {best_model} for best balance of success rate, low duplicates, and efficiency.')
        
        self.stdout.write(f'\n📈 Total questions in database: {MultipleChoiceQuestion.objects.count()}')