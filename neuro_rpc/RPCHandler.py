import inspect
import json
import threading
import time
from typing import Callable, Dict, Any, Optional, Union

from neuro_rpc import logger
from neuro_rpc.RPCTracking import RPCTracker
from neuro_rpc.RPCMessage import RPCMessage, RPCRequest, RPCResponse

# RPC Methods Decorator
def rpc_method(method_type: str = "both", name: Optional[str] = None):
    """
    Decorator to mark methods for RPC registration.

    :param method_type: Type of method - "request", "response", or "both"
    :param name: Optional custom name for the RPC method
    """

    def decorator(func):
        func._is_rpc_method = True
        func._rpc_method_type = method_type
        func._rpc_method_name = name or func.__name__
        return func

    # Support using as @rpc_method or @rpc_method(type="request")
    if callable(method_type):
        func, method_type = method_type, "both"
        return decorator(func)
    return decorator


class RPCHandler(RPCMessage):
    """Handler for JSON-RPC 2.0 protocol operations."""

    # Standard JSON-RPC 2.0 error codes
    ERROR_CODES = {
        "PARSE_ERROR": {"code": -32700, "message": "Parse error"},
        "INVALID_REQUEST": {"code": -32600, "message": "Invalid Request"},
        "METHOD_NOT_FOUND": {"code": -32601, "message": "Method not found"},
        "INVALID_PARAMS": {"code": -32602, "message": "Invalid params"},
        "INTERNAL_ERROR": {"code": -32603, "message": "Internal error"},
        "METHOD_EXISTS": {"code": -32000, "message": "Method already exists"},
        "SERVER_ERROR": {"code": -32001, "message": "Server error"}
    }

    def __init__(self):
        """Initialize the RPC handler."""
        # Initializa RPC Message Protocol
        super().__init__()

        # Methods registry
        self.request_methods: Dict[str, Callable] = {}
        self.response_methods: Dict[str, Callable] = {}

        # Request ID counter for generating unique IDs
        self._request_id = 0

        # Create tracker instance for message tracking (pending requests/responses)
        self.tracker = RPCTracker(logger=logger)

    def register_methods(self, instance) -> None:
        """
        Register methods from an instance that are decorated with @rpc_method.

        :param instance: Object instance containing decorated methods
        """
        for name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
            if hasattr(method, "_is_rpc_method"):
                method_name = getattr(method, "_rpc_method_name", name)
                method_type = getattr(method, "_rpc_method_type", "both")

                if method_type in ["request", "both"]:
                    self.register_request(method_name, method)

                if method_type in ["response", "both"]:
                    self.register_response(method_name, method)

    def register_request(self, method_name: str, method: Callable) -> None:
        """
        Register a method to handle incoming JSON-RPC requests.

        :param method_name: Name of the JSON-RPC method
        :param method: Callable to execute for this method
        """
        if not callable(method):
            raise ValueError(f"Request handler for {method_name} must be callable")

        if method_name in self.request_methods:
            logger.warning(f"Overriding existing request method: {method_name}")

        self.request_methods[method_name] = method
        logger.debug(f"Registered request method: {method_name}")

    def register_response(self, method_name: str, method: Callable) -> None:
        """
        Register a method to handle incoming JSON-RPC responses.

        :param method_name: Name of the JSON-RPC method
        :param method: Callable to handle responses for this method
        """
        if not callable(method):
            raise ValueError(f"Response handler for {method_name} must be callable")

        if method_name in self.response_methods:
            logger.warning(f"Overriding existing response method: {method_name}")

        self.response_methods[method_name] = method
        logger.debug(f"Registered response method: {method_name}")

    def next_request_id(self) -> int:
        """Generate a new unique request ID."""
        self._request_id += 1
        return self._request_id

    def create_request(self, method: str, params: Any = None, id: Any = None) -> Dict[str, Any]:
        """
        Create a JSON-RPC 2.0 request object.

        :param id: ID to assign to the request (optional)
        :param method: Name of the method to call
        :param params: Parameters to pass to the method
        :return: JSON-RPC request dictionary
        """
        request_id = id if id is not None else self.next_request_id()

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id
        }

        # Track this outgoing request using the tracker
        self.tracker.track_outgoing_request(request_id, method)

        if params is not None:
            request["params"] = params

        return request

    def create_response(self, id: Any, result: Any = None, error: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a JSON-RPC 2.0 response object.

        :param id: ID from the request
        :param result: Result data (if successful)
        :param error: Error object (if failed)
        :return: JSON-RPC response dictionary
        """
        response = {
            "jsonrpc": "2.0",
            "id": id
        }

        success = error is None
        if error is not None:
            response["error"] = error
        else:
            response["result"] = result

        # Track this outgoing response
        self.tracker.track_outgoing_response(id, success=success)

        return response

    def create_error(self, error_type: str, data: Any = None, id: Any = None) -> Dict[str, Any]:
        """
        Create a JSON-RPC 2.0 error response.

        :param error_type: Error code key from ERROR_CODES
        :param data: Additional error data
        :param id: Request ID
        :return: JSON-RPC error response dictionary
        """
        error = self.ERROR_CODES.get(error_type, self.ERROR_CODES["INTERNAL_ERROR"]).copy()

        if data is not None:
            error["data"] = data

        return self.create_response(id, error=error)

    def process_message(self, message: Union[Dict[str, Any], str]) -> Optional[Dict[str, Any]]:
        """
        Process an incoming JSON-RPC 2.0 message.
        Automatically determines if it's a request or a response and handles it accordingly.

        :param message: The JSON-RPC message (dictionary or JSON string)
        :return: Response if it's a request, None if it's a response
        """
        # Parse JSON if string
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                return self.create_error("PARSE_ERROR")

        # Validate basic structure
        if not isinstance(message, dict) or "jsonrpc" not in message or message.get("jsonrpc") != "2.0":
            return self.create_error("INVALID_REQUEST")

        # Determine if it's a request or response
        if "method" in message and ("id" in message or "params" in message):
            # It's a request
            return self._process_request(message)
        elif "id" in message and ("result" in message or "error" in message):
            # It's a response
            self._process_response(message)
            return None  # No need to respond to a response
        else:
            # Invalid format
            return self.create_error("INVALID_REQUEST")

    def _process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an incoming request.

        :param request: The request dictionary
        :return: Response dictionary
        """
        method_name = request.get("method")
        request_id = request.get("id")

        if not method_name or not isinstance(method_name, str):
            return self.create_error("INVALID_REQUEST", id=request.get("id"))

        method = self.request_methods.get(method_name)
        if not method:
            return self.create_error("METHOD_NOT_FOUND", id=request.get("id"))

        # Track this incoming request if it has an ID (not a notification)
        if request_id is not None:
            self.tracker.track_incoming_request(request_id, method_name)

        params = request.get("params", {})

        try:
            # Check method signature to ensure we have the necessary parameters
            sig = inspect.signature(method)

            # For dict params, validate against required parameters
            if isinstance(params, dict):
                # Check for required parameters that are missing
                missing_params = []
                for param_name, param in sig.parameters.items():
                    if param.default == inspect.Parameter.empty and param_name not in params and param_name != 'self':
                        missing_params.append(param_name)

                if missing_params:
                    return self.create_error(
                        "INVALID_PARAMS",
                        data=f"Missing required parameters: {', '.join(missing_params)}",
                        id=request.get("id")
                    )
                result = method(**params)
            elif isinstance(params, list):
                # For list params, ensure we have enough positional arguments
                required_count = sum(1 for param in sig.parameters.values()
                                     if param.default == inspect.Parameter.empty and param.name != 'self')

                if len(params) < required_count:
                    return self.create_error(
                        "INVALID_PARAMS",
                        data=f"Method requires {required_count} positional arguments, got {len(params)}",
                        id=request.get("id")
                    )
                result = method(*params)
            else:
                # No parameters
                result = method()

            return self.create_response(request.get("id"), result=result)
        except Exception as e:
            logger.error(f"Error executing method {method_name}", exc_info=True)
            return self.create_error("INTERNAL_ERROR", data=str(e), id=request.get("id"))

    def _process_response(self, response: Dict[str, Any]) -> None:
        """
        Process an incoming response.

        :param response: The response dictionary
        """
        request_id = response.get("id")

        request_data = self.tracker.outgoing_requests.get(request_id)
        if request_data:
            method_name = request_data[1]  # Access the second element (index 1) which is method_name
        else:
            method_name = "default"

        success = "result" in response

        # Track this incoming response
        if request_id is not None:
            self.tracker.track_incoming_response(request_id, success=success)

        handler = self.response_methods.get(method_name)
        if not handler:
            # Try to use default handler if available
            handler = self.response_methods.get("default")
            if not handler:
                logger.warning(f"No response handler for method: {method_name}")
                return

        try:
            result = response.get("result")
            error = response.get("error")
            handler(id=response.get("id"), result=result, error=error)
        except Exception as e:
            logger.exception(f"Error handling response for {method_name}")