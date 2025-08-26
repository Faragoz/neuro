"""
Message tracking utility for JSON-Message 2.0 protocol.

Tracks outgoing/incoming requests and responses, monitors for timeouts,
keeps statistics, and runs an optional background monitoring thread.
Designed for integration with RPCHandler and Benchmark to provide runtime
visibility of pending and completed RPC calls.

Notes:
    - Thread-safe using locks.
    - Intended for long-running client/server sessions.
"""
import threading
import time

from python.neuro_rpc.RPCMessage import RPCRequest, RPCResponse
from python.neuro_rpc.Logger import Logger


class RPCTracker:
    """
    Tracks request/response lifecycle for RPC messages.

    Maintains dictionaries of outgoing/incoming requests and responses,
    updates statistics, and detects timeouts via a background thread.
    """

    def __init__(self, monitor_interval=1, cleanup_interval=60, autostart=True):
        """
        Initialize RPCTracker.

        Args:
            monitor_interval (int): Interval in seconds to check for timeouts.
            cleanup_interval (int): Interval in seconds to clean old entries.
            autostart (bool): Whether to immediately start monitoring.
        """
        self.logger = Logger.get_logger(self.__class__.__name__)

        self.monitor_interval = monitor_interval
        self.cleanup_interval = cleanup_interval

        self._tracking_lock = threading.Lock()

        self.outgoing_requests = {}   # {id: (timestamp, method_name, timeout)}
        self.incoming_requests = {}   # {id: (timestamp, method_name)}
        self.outgoing_responses = {}  # {id: (timestamp, success)}
        self.incoming_responses = {}  # {id: (timestamp, success)}

        self.stats = {
            "outgoing_requests_count": 0,
            "incoming_requests_count": 0,
            "outgoing_responses_count": 0,
            "incoming_responses_count": 0,
            "timed_out_requests": 0
        }

        self._monitor_thread = None
        self._should_stop = threading.Event()

        self.timeout_callback = None

        if autostart:
            self.start_monitoring()

    def start_monitoring(self, timeout_callback=None):
        """
        Start the background monitoring thread.

        Args:
            timeout_callback (Callable, optional): Callback called with a list of timed-out requests.

        Returns:
            bool: True if started, False if already running.
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
            daemon=True
        )
        self._monitor_thread.start()

        if self.logger:
            self.logger.debug("Message tracking monitor started")
        return True

    def stop_monitoring(self):
        """
        Stop the background monitoring thread.

        Returns:
            bool: True if stopped cleanly, False otherwise.
        """
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            return False

        self._should_stop.set()
        self._monitor_thread.join(timeout=5.0)

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
        Background loop that monitors timeouts and cleans old entries.

        Notes:
            Calls ``timeout_callback`` if provided.
        """
        last_cleanup = time.time()

        while not self._should_stop.is_set():
            try:
                results = self.monitor_messages()

                if self.timeout_callback and results["timed_out_requests"]:
                    try:
                        self.timeout_callback(results["timed_out_requests"])
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Error in timeout callback: {e}")

                now = time.time()
                if now - last_cleanup > self.cleanup_interval:
                    cleaned = self.clean_tracking_data(self.cleanup_interval)
                    if self.logger and cleaned > 0:
                        self.logger.debug(f"Cleaned {cleaned} old tracking entries")
                    last_cleanup = now

                self._should_stop.wait(self.monitor_interval)

            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in Message tracking monitor: {e}")
                time.sleep(min(self.monitor_interval, 10))

    def track_outgoing_request(self, request: RPCRequest, timeout=60):
        """
        Track an outgoing request.

        Args:
            request (RPCRequest): Request object being sent.
            timeout (int): Timeout in seconds for this request.
        """
        with self._tracking_lock:
            self.outgoing_requests[request.id] = (time.time(), request.method, timeout)
            self.stats["outgoing_requests_count"] += 1

    def track_incoming_request(self, request: RPCRequest):
        """
        Track an incoming request from server.

        Args:
            request (RPCRequest): Request object received.
        """
        with self._tracking_lock:
            self.logger.debug(f"Tracking incoming request: {request}")
            self.incoming_requests[request.id] = (time.time(), request.method)
            self.stats["incoming_requests_count"] += 1

    def track_outgoing_response(self, response: RPCResponse):
        """
        Track an outgoing response.

        Args:
            response (RPCResponse): Response object being sent.
        """
        with self._tracking_lock:
            self.logger.debug(f"Tracking outgoing response: {response.id}, {response.is_success}")
            if response.id in self.incoming_requests:
                del self.incoming_requests[response.id]
            self.outgoing_responses[response.id] = (time.time(), response.is_success)
            self.stats["outgoing_responses_count"] += 1

    def track_incoming_response(self, response: RPCResponse):
        """
        Track an incoming response from server.

        Args:
            response (RPCResponse): Response object received.
        """
        with self._tracking_lock:
            if response.id in self.outgoing_requests:
                del self.outgoing_requests[response.id]
                self.stats["incoming_responses_count"] += 1
            else:
                if self.logger:
                    self.logger.warning(f"Received response for unknown request ID: {response.id}")

    def get_statistics(self):
        """
        Get current statistics snapshot.

        Returns:
            dict: Copy of statistics counters.
        """
        with self._tracking_lock:
            return self.stats.copy()

    def clean_tracking_data(self, max_age_seconds=3600):
        """
        Remove old tracking entries.

        Args:
            max_age_seconds (int): Max age in seconds to keep entries.

        Returns:
            int: Number of entries cleaned.
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
        Inspect current requests for timeouts and pending states.

        Returns:
            dict: Dictionary with lists of timed-out and pending requests.
        """
        now = time.time()
        results = {
            "timed_out_requests": [],
            "pending_outgoing_requests": [],
            "pending_incoming_requests": []
        }

        with self._tracking_lock:
            for req_id, (timestamp, method, timeout) in list(self.outgoing_requests.items()):
                elapsed = now - timestamp
                if elapsed > timeout:
                    results["timed_out_requests"].append((req_id, method, elapsed))
                    del self.outgoing_requests[req_id]
                    self.stats["timed_out_requests"] += 1
                else:
                    results["pending_outgoing_requests"].append((req_id, method, elapsed))

            for req_id, (timestamp, method) in list(self.incoming_requests.items()):
                elapsed = now - timestamp
                results["pending_incoming_requests"].append((req_id, method, elapsed))

        if self.logger:
            for req_id, method, elapsed in results["timed_out_requests"]:
                self.logger.warning(f"Request timed out: ID {req_id}, method {method}, elapsed {elapsed:.2f}s")

        return results
