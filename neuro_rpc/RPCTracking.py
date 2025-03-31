import threading
import time


class RPCTracker:
    """
    Dedicated class for tracking JSON-RPC 2.0 message flows.
    Handles request/response tracking, statistics and monitoring.
    """

    def __init__(self, logger=None, monitor_interval=60, cleanup_interval=300):
        """
        Initialize the RPC tracker.

        Args:
            logger: Logger instance for reporting issues
            monitor_interval: How often to check for timed-out requests (seconds)
            cleanup_interval: How often to clean old tracking data (seconds)
        """
        self.logger = logger
        self.monitor_interval = monitor_interval
        self.cleanup_interval = cleanup_interval

        # Message tracking with thread safety
        self._tracking_lock = threading.Lock()

        # Tracking dictionaries for each message type
        self.outgoing_requests = {}  # {id: (timestamp, method_name, timeout)}
        self.incoming_requests = {}  # {id: (timestamp, method_name)}
        self.outgoing_responses = {}  # {id: (timestamp, success)}
        self.incoming_responses = {}  # {id: (timestamp, success)}

        # Statistics
        self.stats = {
            "outgoing_requests_count": 0,
            "incoming_requests_count": 0,
            "outgoing_responses_count": 0,
            "incoming_responses_count": 0,
            "timed_out_requests": 0
        }

        # Monitoring thread control
        self._monitor_thread = None
        self._should_stop = threading.Event()

        # Callbacks
        self.timeout_callback = None

    def start_monitoring(self, timeout_callback=None):
        """
        Start the background monitoring thread.

        Args:
            timeout_callback: Function to call when timeouts are detected
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            if self.logger:
                self.logger.warning("Monitoring thread already running")
            return False

        self.timeout_callback = timeout_callback
        self._should_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="RPCTracker-Monitor",
            daemon=True  # Daemon thread won't prevent program exit
        )
        self._monitor_thread.start()

        if self.logger:
            self.logger.info("RPC tracking monitor started")
        return True

    def stop_monitoring(self):
        """Stop the background monitoring thread."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return False

        self._should_stop.set()
        self._monitor_thread.join(timeout=5.0)  # Wait up to 5 seconds for clean shutdown

        if self._monitor_thread.is_alive():
            if self.logger:
                self.logger.warning("Monitoring thread did not shut down cleanly")
            return False
        else:
            if self.logger:
                self.logger.info("RPC tracking monitor stopped")
            return True

    def _monitor_loop(self):
        """Background thread that periodically monitors messages and cleans up old data."""
        last_cleanup = time.time()

        while not self._should_stop.is_set():
            try:
                # Monitor for timed out requests
                results = self.monitor_messages()

                # Call timeout callback if configured
                if self.timeout_callback and results["timed_out_requests"]:
                    try:
                        self.timeout_callback(results["timed_out_requests"])
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Error in timeout callback: {e}")

                # Periodically clean up old tracking data
                now = time.time()
                if now - last_cleanup > self.cleanup_interval:
                    cleaned = self.clean_tracking_data(self.cleanup_interval)
                    if self.logger and cleaned > 0:
                        self.logger.debug(f"Cleaned {cleaned} old tracking entries")
                    last_cleanup = now

                # Wait for next interval or until stop is requested
                self._should_stop.wait(self.monitor_interval)

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in RPC tracking monitor: {e}")

                # Don't bombard with error messages if there's a persistent problem
                time.sleep(min(self.monitor_interval, 10))

    def track_outgoing_request(self, request_id, method_name, timeout=60):
        """Track a request we're sending to a remote service."""
        with self._tracking_lock:
            self.outgoing_requests[request_id] = (time.time(), method_name, timeout)
            self.stats["outgoing_requests_count"] += 1

    def track_incoming_request(self, request_id, method_name):
        """Track a request received from a client."""
        with self._tracking_lock:
            self.incoming_requests[request_id] = (time.time(), method_name)
            self.stats["incoming_requests_count"] += 1

    def track_outgoing_response(self, request_id, success=True):
        """Track a response we're sending to a client."""
        with self._tracking_lock:
            # Remove the incoming request that this response addresses
            if request_id in self.incoming_requests:
                del self.incoming_requests[request_id]

            # Track that we sent a response
            self.outgoing_responses[request_id] = (time.time(), success)
            self.stats["outgoing_responses_count"] += 1

    def track_incoming_response(self, request_id, success=True):
        """Track a response we've received from a remote service."""
        with self._tracking_lock:
            # Remove the outgoing request that this response addresses
            if request_id in self.outgoing_requests:
                del self.outgoing_requests[request_id]
                self.stats["incoming_responses_count"] += 1
            else:
                if self.logger:
                    self.logger.warning(f"Received response for unknown request ID: {request_id}")

    def get_statistics(self):
        """Get statistics about message handling."""
        with self._tracking_lock:
            # Create a copy to avoid threading issues
            return self.stats.copy()

    def clean_tracking_data(self, max_age_seconds=3600):
        """Clean up old tracking data."""
        now = time.time()
        cleaned = 0

        with self._tracking_lock:
            for storage in [self.outgoing_requests, self.incoming_requests,
                            self.outgoing_responses, self.incoming_responses]:
                for req_id, (timestamp, *_) in list(storage.items()):
                    if now - timestamp > max_age_seconds:
                        del storage[req_id]
                        cleaned += 1

        return cleaned

    def monitor_messages(self):
        """
        Monitor all message types, checking for issues like timed-out requests.

        :return: Dictionary with monitoring information
        """
        now = time.time()
        results = {
            "timed_out_requests": [],
            "pending_outgoing_requests": [],
            "pending_incoming_requests": []
        }

        # Check for timed-out outgoing requests
        with self._tracking_lock:
            for req_id, (timestamp, method, timeout) in list(self.outgoing_requests.items()):
                elapsed = now - timestamp
                if elapsed > timeout:
                    results["timed_out_requests"].append((req_id, method, elapsed))
                    del self.outgoing_requests[req_id]
                    self.stats["timed_out_requests"] += 1
                else:
                    results["pending_outgoing_requests"].append((req_id, method, elapsed))

            # Check for possibly abandoned incoming requests
            for req_id, (timestamp, method) in list(self.incoming_requests.items()):
                elapsed = now - timestamp
                results["pending_incoming_requests"].append((req_id, method, elapsed))

        # Log timeout warnings
        if self.logger:
            for req_id, method, elapsed in results["timed_out_requests"]:
                self.logger.warning(f"Request timed out: ID {req_id}, method {method}, elapsed {elapsed:.2f}s")

        return results
