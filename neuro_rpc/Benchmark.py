import time
import uuid

from neuro_rpc.RPCTracker import RPCTracker

class Benchmark(RPCTracker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.benchmark_results = {}
        self.benchmark_active = False
        self.benchmark_id = None
        self.benchmark_requests = {}  # Separate storage for benchmark requests

    def start_benchmark(self, benchmark_id=None):
        """Start collecting benchmark data"""
        self.benchmark_id = benchmark_id or str(uuid.uuid4())
        self.benchmark_active = True
        self.benchmark_results[self.benchmark_id] = {
            "samples": [],
            "start_time": time.time()
        }
        # Clear any old benchmark requests
        self.benchmark_requests = {}

        return self.benchmark_id

    def stop_benchmark(self, benchmark_id=None):
        """Stop collecting benchmark data and return results"""
        bid = benchmark_id or self.benchmark_id
        if bid and bid in self.benchmark_results:
            self.benchmark_results[bid]["end_time"] = time.time()
            self.benchmark_active = False
            return self.calculate_statistics(bid)
        return None

    # Override track_outgoing_request to store benchmark requests separately
    def track_outgoing_request(self, request, timeout=60):
        result = super().track_outgoing_request(request, timeout=timeout)

        # If benchmarking is active, keep a copy of the request data
        if self.benchmark_active and request.id is not None:
            self.benchmark_requests[request.id] = {
                "request": request,
                "timestamp": time.time() * 1000 # Convert to ms
            }

        return result

    # Override the track methods to collect benchmark data when active
    def track_incoming_response(self, response):
        result = super().track_incoming_response(response)

        if self.benchmark_active and response.id is not None:
            # Get request timestamp from outgoing_requests
            request_data = self.benchmark_requests.get(response.id)

            if request_data:
                request_time = request_data.get("timestamp")
                response_time = time.time() * 1000 # Convert to ms
                server_time = response.exec_time/1000 or 0 # Convert to ms

                self.benchmark_results[self.benchmark_id]["samples"].append({
                    "request_id": response.id,
                    "request_time": request_time,
                    "response_time": response_time,
                    "server_processing_time": server_time,
                    "total_latency": response_time - request_time,
                    "network_latency": (response_time - request_time) - server_time
                })

        return result

    def calculate_statistics(self, benchmark_id):
        """Calculate benchmark statistics including jitter"""
        if benchmark_id not in self.benchmark_results:
            return None

        data = self.benchmark_results[benchmark_id]
        samples = data["samples"]

        if not samples:
            return {"error": "No samples collected"}

        # Extract network latencies
        network_latencies = [s["network_latency"] for s in samples]

        # Extract total latencies
        total_latencies = [s["total_latency"] for s in samples]

        # Extract server processing time (exec_time)
        spt = [s["server_processing_time"] for s in samples]

        # Calculate jitter
        jitter = 0
        if len(network_latencies) > 1:
            differences = [abs(network_latencies[i] - network_latencies[i - 1]) for i in range(1, len(network_latencies))]
            jitter = sum(differences) / len(differences)

        return {
            "benchmark_id": benchmark_id,
            "sample_count": len(samples),
            "duration_seconds": data["end_time"] - data["start_time"],
            "min_total_latency_ms": min(total_latencies),
            "max_total_latency_ms": max(total_latencies),
            "avg_total_latency_ms": sum(total_latencies) / len(total_latencies),
            "min_network_latency_ms": min(network_latencies),
            "max_network_latency_ms": max(network_latencies),
            "avg_network_latency_ms": sum(network_latencies) / len(network_latencies),
            "network_jitter_ms": jitter,
            "min_server_processing_time_ms": min(spt),
            "max_server_processing_time_ms": max(spt),
            "avg_server_processing_time_ms": sum(spt) / len(spt),
            "samples": samples
        }


