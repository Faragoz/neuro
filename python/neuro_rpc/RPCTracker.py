"""
@file RPCTracker.py
@brief Message tracking utility for JSON-Message 2.0 protocol.
@details Tracks outgoing/incoming requests and responses, monitors for timeouts,
keeps statistics, and runs an optional background monitoring thread.
Designed for integration with RPCHandler and Benchmark to provide runtime visibility
of pending and completed RPC calls.
@note Thread-safe using locks; intended for long-running client/server sessions.
"""
import threading
import time

from python.neuro_rpc.RPCMessage import RPCRequest, RPCResponse
from python.neuro_rpc.Logger import Logger


class RPCTracker:
    """
    @brief Tracks request/response lifecycle for RPC messages.
    @details Maintains dictionaries of outgoing/incoming requests and responses,
    updates statistics, and detects timeouts via a background thread.
    """

    def __init__(self, monitor_interval=1, cleanup_interval=60, autostart=True):
        """
        @brief Initialize RPCTracker.
        @param monitor_interval int Interval in seconds to check for timeouts.
        @param cleanup_interval int Interval in seconds to clean old entries.
        @param autostart bool Whether to immediately start monitoring.
        """
        self.logger = Logger.get_logger(self.__class__.__name__)

        self.monitor_interval = monitor_interval
        self.cleanup_interval = cleanup_interval

        # Message tracking with thread safety
        self._tracking_lock = threading.Lock()

        # TODO: Delete all timestamps from variables
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

        # TODO: Delete auto-start
        # Auto-start
        if autostart:
            self.start_monitoring()

    def start_monitoring(self, timeout_callback=None):
        """
        @brief Start the background monitoring thread.
        @param timeout_callback Callable Optional callback called with a list of timed-out requests.
        @return bool True if started, False if already running.
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            if self.logger:
                self.logger.warning("Monitoring thread already thread_running")
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
            self.logger.debug("Message tracking monitor started")
        return True

    def stop_monitoring(self):
        """
        @brief Stop the background monitoring thread.
        @return bool True if stopped cleanly, False otherwise.
        """
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
                self.logger.debug("Message tracking monitor stopped")
            return True

    def _monitor_loop(self):
        """
        @brief Background loop that monitors timeouts and cleans old entries.
        @note Calls timeout_callback if provided.
        """
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

                # Periodically clean up old tracking metadata
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
                    self.logger.error(f"Error in Message tracking monitor: {e}")

                # Don't bombard with error messages if there's a persistent problem
                time.sleep(min(self.monitor_interval, 10))

    def track_outgoing_request(self, request: RPCRequest, timeout=60):
        """
        @brief Track an outgoing request.
        @param request RPCRequest Request object being sent.
        @param timeout int Timeout in seconds for this request.
        """
        with self._tracking_lock:
            #self.logger.debug(f"Tracking outgoing request [{timeout}s]: {request.to_dict()}")
            self.outgoing_requests[request.id] = (time.time(), request.method, timeout)
            self.stats["outgoing_requests_count"] += 1

    # TODO: Exec_time is only supported as client (python) - server (labview).
    #  incoming_request and outgoing_response doesn't (?) support exec_time.
    #  Check RPCRequest and related methods to add this functionality.
    def track_incoming_request(self, request: RPCRequest):
        """
        @brief Track an incoming request from server.
        @param request RPCRequest Request object received.
        """
        with self._tracking_lock:
            self.logger.debug(f"Tracking incoming request: {request}")
            self.incoming_requests[request.id] = (time.time(), request.method)
            self.stats["incoming_requests_count"] += 1

    def track_outgoing_response(self, response: RPCResponse):
        """
        @brief Track an outgoing response.
        @param response RPCResponse Response object being sent.
        """
        with self._tracking_lock:
            self.logger.debug(f"Tracking outgoing response: {response.id}, {response.is_success}")
            # Remove the incoming request that this response addresses
            if response.id in self.incoming_requests:
                del self.incoming_requests[response.id]
            # Track that we sent a response
            self.outgoing_responses[response.id] = (time.time(), response.is_success)
            self.stats["outgoing_responses_count"] += 1

    def track_incoming_response(self, response: RPCResponse):
        """
        @brief Track an incoming response from server.
        @param response RPCResponse Response object received.
        """
        with self._tracking_lock:
            #self.logger.debug(f"Tracking incoming response: {response.to_dict()}")
            '''self.incoming_responses[response.id] = (time.time(), response.is_success)

            total_time = (self.incoming_responses[response.id][0] - self.outgoing_requests[response.id][0])*1000
            exec_time = response.exec_time/1000
            self.logger.debug(f"Total time: {total_time} ms")
            self.logger.debug(f"Execution time: {exec_time} ms")
            self.logger.debug(f"Network roundtrip: {abs(total_time - exec_time)} ms")'''

            # Remove the outgoing request that this response addresses
            if response.id in self.outgoing_requests:
                del self.outgoing_requests[response.id]
                self.stats["incoming_responses_count"] += 1
            else:
                if self.logger:
                    self.logger.warning(f"Received response for unknown request ID: {response.id}")

    def get_statistics(self):
        """
        @brief Get current statistics snapshot.
        @return dict Copy of statistics counters.
        """
        with self._tracking_lock:
            # Create a copy to avoid threading issues
            return self.stats.copy()

    def clean_tracking_data(self, max_age_seconds=3600):
        """
        @brief Remove old tracking entries.
        @param max_age_seconds int Max age in seconds to keep entries.
        @return int Number of entries cleaned.
        """
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
        @brief Inspect current requests for timeouts and pending states.
        @return dict Dictionary with lists of timed-out and pending requests.
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
