import os
import sys
import pytest


# Add chat-service src to path for importing ContextBuilder
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHAT_SRC = os.path.join(ROOT, "services", "chat-service", "src")
if CHAT_SRC not in sys.path:
    sys.path.insert(0, CHAT_SRC)

from context_builder import ContextBuilder  # type: ignore


@pytest.fixture
def context_builder() -> ContextBuilder:
    return ContextBuilder()


@pytest.fixture
def sample_life_strand():
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
def sample_conversation_history():
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

