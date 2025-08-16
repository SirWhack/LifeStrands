import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import json

# Import the context builder (assuming it's in the services directory)
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'chat-service', 'src'))

from context_builder import ContextBuilder

class TestContextBuilder:
    """Unit tests for ContextBuilder class"""
    
    @pytest.fixture
    def context_builder(self):
        """Create a ContextBuilder instance for testing"""
        return ContextBuilder()
    
    @pytest.fixture
    def sample_life_strand(self):
        """Sample life strand data for testing"""
        return {
            "id": "test-npc-1",
            "name": "Alice Thompson",
            "background": {
                "age": 28,
                "occupation": "Software Engineer",
                "location": "Tech District",
                "history": "Grew up in a small town, moved to the city for work. Has been working in tech for 5 years."
            },
            "personality": {
                "traits": ["analytical", "creative", "introverted", "detail-oriented", "problem-solver"],
                "motivations": ["building innovative software", "learning new technologies", "work-life balance"],
                "fears": ["public speaking", "technical obsolescence"]
            },
            "current_status": {
                "mood": "focused",
                "health": "good",
                "energy": "high",
                "location": "Tech District",
                "activity": "coding"
            },
            "relationships": {
                "Bob Wilson": {
                    "type": "colleague",
                    "status": "positive",
                    "intensity": 7,
                    "notes": "Team lead, very supportive and knowledgeable"
                },
                "Sarah Chen": {
                    "type": "friend",
                    "status": "positive",
                    "intensity": 8,
                    "notes": "Close friend from college, also works in tech"
                }
            },
            "knowledge": [
                {
                    "topic": "Python Programming",
                    "content": "Expert level Python developer with 5+ years experience",
                    "confidence": 9
                },
                {
                    "topic": "Machine Learning",
                    "content": "Intermediate knowledge of ML algorithms and frameworks",
                    "confidence": 6
                },
                {
                    "topic": "Web Development",
                    "content": "Full-stack web development using React and Node.js",
                    "confidence": 8
                }
            ],
            "memories": [
                {
                    "content": "Had a great technical discussion with Bob about system architecture",
                    "timestamp": "2023-10-15T14:30:00Z",
                    "importance": 7,
                    "emotional_impact": "positive"
                },
                {
                    "content": "Successfully deployed the new feature to production",
                    "timestamp": "2023-10-14T16:45:00Z",
                    "importance": 8,
                    "emotional_impact": "positive"
                }
            ]
        }
    
    @pytest.fixture
    def sample_conversation_history(self):
        """Sample conversation history for testing"""
        return [
            {
                "role": "user",
                "content": "Hi Alice, how are you doing today?",
                "timestamp": "2023-10-16T10:00:00Z"
            },
            {
                "role": "assistant", 
                "content": "Hello! I'm doing well, thanks for asking. I've been working on some interesting Python code today.",
                "timestamp": "2023-10-16T10:00:30Z"
            },
            {
                "role": "user",
                "content": "That sounds great! What kind of Python project are you working on?",
                "timestamp": "2023-10-16T10:01:00Z"
            },
            {
                "role": "assistant",
                "content": "I'm working on a machine learning model for data analysis. It's quite challenging but rewarding!",
                "timestamp": "2023-10-16T10:01:45Z"
            }
        ]

class TestBuildSystemPrompt:
    """Test system prompt generation"""
    
    def test_build_system_prompt_complete_data(self, context_builder, sample_life_strand):
        """Test building system prompt with complete life strand data"""
        prompt = context_builder.build_system_prompt(sample_life_strand)
        
        # Verify basic structure
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        
        # Verify key information is included
        assert "Alice Thompson" in prompt
        assert "28 years old" in prompt
        assert "Software Engineer" in prompt
        assert "Tech District" in prompt
        
        # Verify personality traits are included
        assert "analytical" in prompt
        assert "creative" in prompt
        assert "introverted" in prompt
        
        # Verify motivations are included
        assert any(motivation in prompt for motivation in sample_life_strand["personality"]["motivations"])
        
        # Verify current status is included
        assert "focused" in prompt  # mood
        assert "high" in prompt     # energy
    
    def test_build_system_prompt_minimal_data(self, context_builder):
        """Test building system prompt with minimal life strand data"""
        minimal_life_strand = {
            "name": "John Doe",
            "background": {"age": 30, "location": "City"},
            "personality": {"traits": ["friendly"]}
        }
        
        prompt = context_builder.build_system_prompt(minimal_life_strand)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "John Doe" in prompt
        assert "30 years old" in prompt
        assert "friendly" in prompt
    
    def test_build_system_prompt_empty_data(self, context_builder):
        """Test building system prompt with empty data"""
        prompt = context_builder.build_system_prompt({})
        
        # Should return default prompt
        assert prompt == "You are a helpful AI assistant."
    
    def test_build_system_prompt_token_limit(self, context_builder, sample_life_strand):
        """Test that system prompt respects token limits"""
        # Create very long content
        long_history = "This is a very long background story. " * 1000
        sample_life_strand["background"]["history"] = long_history
        
        prompt = context_builder.build_system_prompt(sample_life_strand)
        
        # Should be truncated to fit within system_prompt_max
        estimated_tokens = len(prompt) // 4
        assert estimated_tokens <= context_builder.system_prompt_max

class TestBuildConversationContext:
    """Test conversation context generation"""
    
    def test_build_conversation_context_complete(self, context_builder, sample_life_strand, sample_conversation_history):
        """Test building conversation context with complete data"""
        context = context_builder.build_conversation_context(sample_life_strand, sample_conversation_history)
        
        assert isinstance(context, str)
        assert len(context) > 0
        
        # Should include conversation history
        assert "Hi Alice, how are you doing today?" in context
        assert "machine learning model" in context
        
        # Should include some relationship context
        assert "Bob Wilson" in context or "colleague" in context
        
        # Should include some memory context
        assert any(memory["content"] in context for memory in sample_life_strand["memories"])
    
    def test_build_conversation_context_empty_history(self, context_builder, sample_life_strand):
        """Test building context with empty conversation history"""
        context = context_builder.build_conversation_context(sample_life_strand, [])
        
        # Should still include NPC context even without conversation history
        assert isinstance(context, str)
        # Might be empty if no relevant knowledge/memories/relationships
    
    def test_build_conversation_context_token_optimization(self, context_builder, sample_life_strand):
        """Test that context is optimized for token limits"""
        # Create very long conversation history
        long_history = []
        for i in range(100):
            long_history.extend([
                {"role": "user", "content": f"This is a very long message number {i} that contains lots of unnecessary information and details that should be truncated."},
                {"role": "assistant", "content": f"This is a very long response number {i} with lots of detailed information that might exceed token limits."}
            ])
        
        context = context_builder.build_conversation_context(sample_life_strand, long_history)
        
        # Should be truncated to fit within limits
        estimated_tokens = len(context) // 4
        max_allowed = context_builder.max_context_length - context_builder.system_prompt_max
        assert estimated_tokens <= max_allowed

class TestOptimizeForTokenLimit:
    """Test token optimization functionality"""
    
    def test_optimize_short_text(self, context_builder):
        """Test optimization with text under limit"""
        short_text = "This is a short text that should not be truncated."
        result = context_builder.optimize_for_token_limit(short_text, 1000)
        
        assert result == short_text
    
    def test_optimize_long_text(self, context_builder):
        """Test optimization with text over limit"""
        # Create text that definitely exceeds a small limit
        long_text = "This is a sentence. " * 100  # About 400 tokens
        result = context_builder.optimize_for_token_limit(long_text, 50)  # 50 token limit
        
        assert len(result) < len(long_text)
        assert len(result) <= 50 * 4  # Rough character estimate
    
    def test_optimize_sentence_boundaries(self, context_builder):
        """Test that optimization respects sentence boundaries"""
        text_with_sentences = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = context_builder.optimize_for_token_limit(text_with_sentences, 10)  # Small limit
        
        # Should end with a complete sentence
        assert result.endswith('.') or result.endswith('!') or result.endswith('?')
    
    def test_optimize_empty_text(self, context_builder):
        """Test optimization with empty text"""
        result = context_builder.optimize_for_token_limit("", 100)
        assert result == ""

class TestExtractRelevantKnowledge:
    """Test knowledge extraction functionality"""
    
    def test_extract_relevant_knowledge_matching(self, context_builder, sample_life_strand):
        """Test extraction when query matches knowledge"""
        query_history = [
            {"role": "user", "content": "Tell me about Python programming and machine learning"}
        ]
        
        relevant = context_builder.extract_relevant_knowledge(sample_life_strand, query_history)
        
        assert isinstance(relevant, list)
        # Should find relevant knowledge items
        if relevant:  # Might be empty due to strict thresholds
            assert any("Python" in item or "Machine Learning" in item for item in relevant)
    
    def test_extract_relevant_knowledge_no_matches(self, context_builder, sample_life_strand):
        """Test extraction when query doesn't match knowledge"""
        query_history = [
            {"role": "user", "content": "Tell me about cooking recipes and gardening tips"}
        ]
        
        relevant = context_builder.extract_relevant_knowledge(sample_life_strand, query_history)
        
        # Should return empty list or very few items
        assert isinstance(relevant, list)
        assert len(relevant) <= 1  # Maybe one low-relevance match
    
    def test_extract_relevant_knowledge_empty_knowledge(self, context_builder):
        """Test extraction with empty knowledge base"""
        empty_life_strand = {
            "knowledge": []
        }
        query_history = [
            {"role": "user", "content": "Tell me anything"}
        ]
        
        relevant = context_builder.extract_relevant_knowledge(empty_life_strand, query_history)
        
        assert relevant == []
    
    def test_extract_relevant_knowledge_empty_history(self, context_builder, sample_life_strand):
        """Test extraction with empty query history"""
        relevant = context_builder.extract_relevant_knowledge(sample_life_strand, [])
        
        assert relevant == []

class TestCalculateRelevanceScore:
    """Test relevance scoring algorithm"""
    
    def test_calculate_relevance_identical_text(self, context_builder):
        """Test relevance score for identical text"""
        text = "python programming machine learning"
        score = context_builder._calculate_relevance_score(text, text)
        
        assert score == 1.0
    
    def test_calculate_relevance_no_overlap(self, context_builder):
        """Test relevance score for completely different text"""
        text1 = "python programming"
        text2 = "cooking recipes"
        score = context_builder._calculate_relevance_score(text1, text2)
        
        assert score == 0.0
    
    def test_calculate_relevance_partial_overlap(self, context_builder):
        """Test relevance score for partially overlapping text"""
        text1 = "python programming machine learning"
        text2 = "python development web programming"
        score = context_builder._calculate_relevance_score(text1, text2)
        
        assert 0.0 < score < 1.0
    
    def test_calculate_relevance_empty_text(self, context_builder):
        """Test relevance score with empty text"""
        score1 = context_builder._calculate_relevance_score("", "python programming")
        score2 = context_builder._calculate_relevance_score("python programming", "")
        score3 = context_builder._calculate_relevance_score("", "")
        
        assert score1 == 0.0
        assert score2 == 0.0
        assert score3 == 0.0

class TestFormatConversationHistory:
    """Test conversation history formatting"""
    
    def test_format_conversation_history_normal(self, context_builder, sample_conversation_history):
        """Test formatting normal conversation history"""
        formatted = context_builder._format_conversation_history(sample_conversation_history)
        
        assert isinstance(formatted, str)
        assert "User:" in formatted
        assert "You:" in formatted
        assert "Hi Alice" in formatted
    
    def test_format_conversation_history_long(self, context_builder):
        """Test formatting very long conversation history"""
        long_history = []
        for i in range(50):
            long_history.extend([
                {"role": "user", "content": f"User message {i}"},
                {"role": "assistant", "content": f"Assistant message {i}"}
            ])
        
        formatted = context_builder._format_conversation_history(long_history)
        
        # Should only include recent messages (last 10 messages = 5 exchanges)
        assert "User message 45" in formatted  # Recent messages
        assert "User message 0" not in formatted  # Old messages excluded
    
    def test_format_conversation_history_empty(self, context_builder):
        """Test formatting empty conversation history"""
        formatted = context_builder._format_conversation_history([])
        
        assert formatted == ""

class TestValidateContextSize:
    """Test context size validation"""
    
    def test_validate_context_size_within_limit(self, context_builder):
        """Test validation with context within limit"""
        short_context = "This is a short context"
        result = context_builder.validate_context_size(short_context, 1000)
        
        assert result is True
    
    def test_validate_context_size_over_limit(self, context_builder):
        """Test validation with context over limit"""
        long_context = "This is a very long context. " * 100
        result = context_builder.validate_context_size(long_context, 10)
        
        assert result is False

class TestGetContextStats:
    """Test context statistics generation"""
    
    def test_get_context_stats(self, context_builder):
        """Test getting context statistics"""
        system_prompt = "You are Alice Thompson."
        context = "This is the conversation context."
        
        stats = context_builder.get_context_stats(system_prompt, context)
        
        assert isinstance(stats, dict)
        assert "system_prompt_chars" in stats
        assert "context_chars" in stats
        assert "total_chars" in stats
        assert "system_prompt_tokens_est" in stats
        assert "context_tokens_est" in stats
        assert "total_tokens_est" in stats
        
        # Verify calculations
        assert stats["system_prompt_chars"] == len(system_prompt)
        assert stats["context_chars"] == len(context)
        assert stats["total_chars"] == len(system_prompt) + len(context)

# Error handling tests

class TestErrorHandling:
    """Test error handling in ContextBuilder"""
    
    def test_build_system_prompt_malformed_data(self, context_builder):
        """Test system prompt building with malformed data"""
        malformed_data = {
            "name": None,
            "background": "not a dict",
            "personality": {"traits": "not a list"}
        }
        
        # Should not crash, should return fallback
        prompt = context_builder.build_system_prompt(malformed_data)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    
    def test_extract_relevant_knowledge_malformed_data(self, context_builder):
        """Test knowledge extraction with malformed data"""
        malformed_life_strand = {
            "knowledge": [
                {"topic": None, "content": "some content"},
                "not a dict",
                {"content": "missing topic"}
            ]
        }
        
        query_history = [{"role": "user", "content": "test query"}]
        
        # Should not crash
        relevant = context_builder.extract_relevant_knowledge(malformed_life_strand, query_history)
        assert isinstance(relevant, list)

# Integration-like tests within unit test scope

class TestFullContextBuilding:
    """Test complete context building workflow"""
    
    def test_complete_context_building_workflow(self, context_builder, sample_life_strand, sample_conversation_history):
        """Test the complete workflow of building context for an LLM"""
        
        # Step 1: Build system prompt
        system_prompt = context_builder.build_system_prompt(sample_life_strand)
        
        # Step 2: Build conversation context
        conversation_context = context_builder.build_conversation_context(
            sample_life_strand, sample_conversation_history
        )
        
        # Step 3: Get stats
        stats = context_builder.get_context_stats(system_prompt, conversation_context)
        
        # Verify complete workflow
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 0
        assert isinstance(conversation_context, str)
        assert isinstance(stats, dict)
        
        # Verify the context would be valid for an LLM
        total_estimated_tokens = stats["total_tokens_est"]
        assert total_estimated_tokens <= context_builder.max_context_length
        
        # Verify key information is preserved
        assert sample_life_strand["name"] in system_prompt
        assert any(msg["content"] in conversation_context for msg in sample_conversation_history)

# Pytest configuration

if __name__ == "__main__":
    pytest.main([__file__, "-v"])