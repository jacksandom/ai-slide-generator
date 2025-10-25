"""Load testing for slide generation API."""
import pytest
import asyncio
import aiohttp
import time
import psutil
import concurrent.futures
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def mock_fast_responses(monkeypatch):
    """Mock fast API responses for performance testing."""
    # Create proper OpenAI-style response object
    mock_message = MagicMock()
    mock_message.content = '<!DOCTYPE html><html><head><title>Performance Test</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">Performance Test Slide</h1><p>Fast response for performance testing</p></body></html>'
    
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_serving_client = MagicMock()
    mock_serving_client.chat.completions.create.return_value = mock_response
    
    monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_serving_client)
    return {"serving_client": mock_serving_client}


@pytest.mark.performance
class TestPerformanceLoad:
    """Performance and load testing for the API."""
    
    BASE_URL = "http://testserver"  # TestClient uses this URL
    
    def test_single_request_baseline(self, client, mock_fast_responses):
        """Establish baseline performance for single request."""
        start_time = time.time()
        
        response = client.post("/chat", json={
            "message": "Create a slide about performance testing",
            "session_id": "perf_baseline"
        })
        
        end_time = time.time()
        response_time = end_time - start_time
        
        assert response.status_code == 200
        # Single request should complete quickly (under 10 seconds with mocked responses)
        assert response_time < 10.0
        
        print(f"Baseline single request time: {response_time:.2f}s")
        return response_time

    def test_sequential_requests_performance(self, client, mock_fast_responses):
        """Test performance of sequential requests."""
        session_id = "perf_sequential"
        request_times = []
        
        for i in range(5):
            start_time = time.time()
            
            response = client.post("/chat", json={
                "message": f"Performance test message {i}",
                "session_id": f"{session_id}_{i}"
            })
            
            end_time = time.time()
            request_time = end_time - start_time
            request_times.append(request_time)
            
            assert response.status_code == 200
        
        # Average request time should remain reasonable
        avg_time = sum(request_times) / len(request_times)
        max_time = max(request_times)
        
        assert avg_time < 15.0  # Average under 15 seconds
        assert max_time < 30.0  # No single request over 30 seconds
        
        print(f"Sequential requests - Average: {avg_time:.2f}s, Max: {max_time:.2f}s")

    def test_concurrent_requests_load(self, client, mock_fast_responses):
        """Test API performance under concurrent load."""
        num_concurrent = 5
        session_base = "perf_concurrent"
        
        def make_request(session_id):
            start_time = time.time()
            try:
                response = client.post("/chat", json={
                    "message": f"Concurrent test message for {session_id}",
                    "session_id": session_id
                })
                end_time = time.time()
                return {
                    "status": response.status_code,
                    "time": end_time - start_time,
                    "success": response.status_code == 200
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "status": 500,
                    "time": end_time - start_time,
                    "success": False,
                    "error": str(e)
                }
        
        # Execute concurrent requests using ThreadPoolExecutor
        start_total = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [
                executor.submit(make_request, f"{session_base}_{i}") 
                for i in range(num_concurrent)
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        end_total = time.time()
        
        total_time = end_total - start_total
        
        # Analyze results
        successful_requests = sum(1 for r in results if r["success"])
        avg_response_time = sum(r["time"] for r in results) / len(results)
        max_response_time = max(r["time"] for r in results)
        
        # Assertions
        assert successful_requests >= num_concurrent * 0.8  # At least 80% success rate
        assert total_time < 60  # All requests complete within 60 seconds
        assert avg_response_time < 20  # Average response time under 20 seconds
        
        print(f"Concurrent load test - {successful_requests}/{num_concurrent} successful")
        print(f"Total time: {total_time:.2f}s, Avg response: {avg_response_time:.2f}s")

    @pytest.mark.slow
    def test_memory_usage_baseline(self, client, mock_fast_responses):
        """Test memory usage doesn't grow unboundedly."""
        import gc
        
        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Send multiple requests to test memory usage
        session_base = "memory_test"
        for i in range(20):
            response = client.post("/chat", json={
                "message": f"Memory test message {i}",
                "session_id": f"{session_base}_{i}"
            })
            assert response.status_code == 200
            
            # Periodic garbage collection
            if i % 5 == 0:
                gc.collect()
        
        # Get final memory usage
        gc.collect()  # Force garbage collection
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory
        
        print(f"Memory usage - Initial: {initial_memory:.1f}MB, Final: {final_memory:.1f}MB")
        print(f"Memory growth: {memory_growth:.1f}MB")
        
        # Memory growth should be reasonable (less than 200MB for 20 requests)
        assert memory_growth < 200

    def test_api_response_time_consistency(self, client, mock_fast_responses):
        """Test that API response times are consistent."""
        session_id = "consistency_test"
        response_times = []
        
        # Make multiple requests and measure response times
        for i in range(10):
            start_time = time.time()
            
            response = client.post("/chat", json={
                "message": f"Consistency test {i}",
                "session_id": f"{session_id}_{i}"
            })
            
            end_time = time.time()
            response_time = end_time - start_time
            response_times.append(response_time)
            
            assert response.status_code == 200
        
        # Calculate statistics
        avg_time = sum(response_times) / len(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        variance = sum((t - avg_time) ** 2 for t in response_times) / len(response_times)
        std_dev = variance ** 0.5
        
        # Response times should be relatively consistent
        # Standard deviation should be less than 50% of average
        assert std_dev < (avg_time * 0.5)
        
        # No single request should be more than 3x the average
        assert max_time < (avg_time * 3)
        
        print(f"Response time consistency - Avg: {avg_time:.2f}s, StdDev: {std_dev:.2f}s")
        print(f"Min: {min_time:.2f}s, Max: {max_time:.2f}s")

    def test_slide_generation_performance(self, client, mock_fast_responses):
        """Test performance of slide generation operations."""
        session_id = "slide_gen_perf"
        
        # Test slide generation request
        start_time = time.time()
        response = client.post("/slides/generate", json={
            "topic": "Performance Testing",
            "slide_count": 3
        })
        gen_time = time.time() - start_time
        
        assert response.status_code == 200
        
        # Test slide retrieval
        start_time = time.time()
        response = client.get("/slides/html")
        retrieval_time = time.time() - start_time
        
        assert response.status_code == 200
        
        # Test slide export
        start_time = time.time()
        response = client.post("/slides/export")
        export_time = time.time() - start_time
        
        assert response.status_code == 200
        
        # Performance assertions
        assert gen_time < 30.0  # Slide generation under 30s
        assert retrieval_time < 5.0  # Slide retrieval under 5s
        assert export_time < 15.0  # Export under 15s
        
        print(f"Slide operations - Gen: {gen_time:.2f}s, Retrieval: {retrieval_time:.2f}s, Export: {export_time:.2f}s")

    @pytest.mark.slow
    def test_sustained_load_performance(self, client, mock_fast_responses):
        """Test performance under sustained load."""
        duration_minutes = 2  # 2-minute sustained load test
        end_time = time.time() + (duration_minutes * 60)
        
        request_count = 0
        successful_requests = 0
        response_times = []
        
        while time.time() < end_time:
            start_request = time.time()
            
            try:
                response = client.post("/chat", json={
                    "message": f"Sustained load test {request_count}",
                    "session_id": f"sustained_{request_count}"
                })
                
                end_request = time.time()
                request_time = end_request - start_request
                response_times.append(request_time)
                
                if response.status_code == 200:
                    successful_requests += 1
                    
            except Exception as e:
                print(f"Request failed: {e}")
            
            request_count += 1
            
            # Small delay to prevent overwhelming the system
            time.sleep(0.1)
        
        # Calculate performance metrics
        success_rate = successful_requests / request_count if request_count > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        throughput = successful_requests / (duration_minutes * 60)  # requests per second
        
        # Performance assertions
        assert success_rate >= 0.80  # At least 80% success rate
        assert avg_response_time < 25.0  # Average response time under 25s
        assert throughput > 0.01  # At least 0.01 requests per second
        
        print(f"Sustained load ({duration_minutes}min) - Success rate: {success_rate:.2%}")
        print(f"Throughput: {throughput:.3f} req/s, Avg response: {avg_response_time:.2f}s")


@pytest.mark.performance
class TestResourceUsage:
    """Test resource usage patterns and limits."""
    
    def test_cpu_usage_monitoring(self, client, mock_fast_responses):
        """Monitor CPU usage during operations."""
        process = psutil.Process()
        
        # Get baseline CPU usage
        initial_cpu = process.cpu_percent(interval=1)
        
        # Perform intensive operations
        for i in range(5):
            client.post("/chat", json={
                "message": f"CPU test message {i}",
                "session_id": f"cpu_test_{i}"
            })
        
        # Monitor CPU usage
        final_cpu = process.cpu_percent(interval=1)
        
        print(f"CPU usage - Initial: {initial_cpu:.1f}%, Final: {final_cpu:.1f}%")
        
        # CPU usage should remain reasonable (implementation-dependent)
        # This is more of a monitoring test than a strict assertion
        assert final_cpu < 100.0  # Should not peg CPU completely

    def test_file_descriptor_usage(self, client, mock_fast_responses):
        """Test that file descriptors are properly managed."""
        process = psutil.Process()
        
        # Get initial file descriptor count
        initial_fds = process.num_fds() if hasattr(process, 'num_fds') else 0
        
        # Perform operations that might open files/connections
        for i in range(10):
            client.post("/chat", json={
                "message": f"FD test {i}",
                "session_id": f"fd_test_{i}"
            })
            
            client.get("/slides/status")
            client.post("/slides/export")
        
        # Check final file descriptor count
        final_fds = process.num_fds() if hasattr(process, 'num_fds') else 0
        fd_growth = final_fds - initial_fds
        
        print(f"File descriptors - Initial: {initial_fds}, Final: {final_fds}")
        
        # File descriptor growth should be minimal
        if initial_fds > 0:  # Only test if we can measure FDs
            assert fd_growth < 50  # Should not leak many file descriptors
