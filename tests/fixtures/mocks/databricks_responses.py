"""Mock Databricks API responses for testing."""

# Mock LLM serving endpoint responses
MOCK_LLM_RESPONSES = {
    "slide_generation": {
        "choices": [{
            "message": {
                "content": '''<!DOCTYPE html>
<html>
<head>
    <title>AI Overview</title>
</head>
<body style="width:1280px;height:720px;">
    <h1 style="color:#102025;">AI Overview</h1>
    <p>Artificial Intelligence is revolutionizing how we process information and make decisions.</p>
    <ul>
        <li>Machine Learning enables computers to learn from data</li>
        <li>Deep Learning uses neural networks for complex pattern recognition</li>
        <li>Natural Language Processing helps computers understand human language</li>
    </ul>
</body>
</html>'''
            }
        }]
    },
    "intent_detection": {
        "choices": [{
            "message": {
                "content": '''
{
    "intent": "CREATE_PRESENTATION",
    "entities": {
        "slide_count": 3,
        "topic": "machine learning",
        "style": "professional"
    },
    "confidence": 0.95
}
'''
            }
        }]
    },
    "planning_response": {
        "choices": [{
            "message": {
                "content": '''
Based on the user's request, I'll create 3 slides about machine learning:

1. Slide 1: Introduction to Machine Learning
2. Slide 2: Types of Machine Learning
3. Slide 3: Real-world Applications

I'll generate professional slides with clear structure and visual hierarchy.
'''
            }
        }]
    }
}

# Mock Genie SQL execution responses
MOCK_GENIE_RESPONSES = {
    "successful_query": {
        "statement_id": "test_statement_123",
        "status": {"state": "SUCCEEDED"},
        "result": {
            "data_array": [
                ["Technology", "Adoption Rate", "Growth"],
                ["AI", "75%", "25%"],
                ["Machine Learning", "68%", "30%"],
                ["Deep Learning", "45%", "40%"]
            ],
            "columns": [
                {"name": "Technology", "type": "string"},
                {"name": "Adoption Rate", "type": "string"}, 
                {"name": "Growth", "type": "string"}
            ]
        }
    },
    "failed_query": {
        "statement_id": "test_statement_456",
        "status": {"state": "FAILED"},
        "error": {
            "message": "Table not found: invalid_table",
            "error_code": "SEMANTIC_ERROR"
        }
    },
    "running_query": {
        "statement_id": "test_statement_789",
        "status": {"state": "RUNNING"},
        "result": None
    }
}

# Mock Vector Search responses (to be deprecated)
MOCK_VECTOR_SEARCH_RESPONSES = {
    "search_results": {
        "results": [
            {
                "id": "doc_1",
                "score": 0.95,
                "metadata": {"title": "AI Best Practices", "type": "document"},
                "content": "Best practices for implementing AI in enterprise environments..."
            },
            {
                "id": "doc_2", 
                "score": 0.87,
                "metadata": {"title": "Machine Learning Guide", "type": "tutorial"},
                "content": "Complete guide to machine learning implementation..."
            }
        ]
    }
}

# Complete mock configuration for different test scenarios
def get_mock_llm_client():
    """Returns a mock LLM client with predefined responses."""
    from unittest.mock import MagicMock
    
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MOCK_LLM_RESPONSES["slide_generation"]
    return mock_client

def get_mock_genie_client():
    """Returns a mock Genie client with predefined responses.""" 
    from unittest.mock import MagicMock
    
    mock_client = MagicMock()
    mock_client.execute_genie_request.return_value = MOCK_GENIE_RESPONSES["successful_query"]
    return mock_client
