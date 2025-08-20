import inspect
from typing import Callable, Dict, Any, Optional, Union

from python.neuro_rpc.Benchmark import Benchmark
from python.neuro_rpc.RPCMessage import RPCMessage, RPCRequest, RPCResponse, RPCError
from python.neuro_rpc.Logger import Logger
import uuid

# Message Methods Decorator
def rpc_method(method_type: str = "both", name: Optional[str] = None):
    """
    Decorator to mark methods for Message registration.

    :param method_type: Type of method - "request", "response", or "both"
    :param name: Optional custom name for the Message method
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
    """Handler for JSON-Message 2.0 protocol operations."""

    def __init__(self):
        """Initialize the Message handler."""
        # Initialize Message Message Protocol
        super().__init__()

        # Methods registry
        self.request_methods: Dict[str, Callable] = {}
        self.response_methods: Dict[str, Callable] = {}

        # Request ID counter for generating unique IDs
        self._request_id = 0

        # Create tracker instance for message tracking (pending requests/responses)
        #self.tracker = RPCTracker()
        self.tracker = Benchmark()

        # Logger
        self.logger = Logger.get_logger(self.__class__.__name__)

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

        self.logger.debug(f"Registered request methods: {list(self.request_methods.keys())}")
        self.logger.debug(f"Registered response methods: {list(self.response_methods.keys())}")

    def register_request(self, method_name: str, method: Callable) -> None:
        """
        Register a method to handle incoming JSON-Message requests.

        :param method_name: Name of the JSON-Message method
        :param method: Callable to execute for this method
        """
        if not callable(method):
            raise ValueError(f"Request handler for {method_name} must be callable")

        if method_name in self.request_methods:
            self.logger.warning(f"Overriding existing request method: {method_name}")

        self.request_methods[method_name] = method
        #self.logger.debug(f"Registered request method: {method_name}")

    def register_response(self, method_name: str, method: Callable) -> None:
        """
        Register a method to handle incoming JSON-Message responses.

        :param method_name: Name of the JSON-Message method
        :param method: Callable to handle responses for this method
        """
        if not callable(method):
            raise ValueError(f"Response handler for {method_name} must be callable")

        if method_name in self.response_methods:
            self.logger.warning(f"Overriding existing response method: {method_name}")

        self.response_methods[method_name] = method
        #self.logger.debug(f"Registered response method: {method_name}")

    def next_request_id(self) -> int:
        """Generate a new unique request ID."""
        self._request_id += 1
        return self._request_id

    def create_request(self, method, params=None, request_id=None):
        """
        Creates a JSON-Message request message

        Args:
            method (str): The method name to call
            params (dict, optional): Parameters to pass to the method
            request_id: Optional custom ID for the request

        Returns:
            dict: A JSON-Message request object
        """
        if request_id is None:
            request_id = str(uuid.uuid4()) #self.next_request_id()

        # Create a proper RPCRequest object
        request = RPCRequest(method=method, id=request_id, params=params)
        request_dict = request.to_dict()

        # If we have a tracker, track this outgoing request
        if self.tracker:
            self.tracker.track_outgoing_request(request)

        return request_dict

    def create_response(self, result, request_id):
        """
        Creates a JSON-Message response message

        Args:
            result: The result of the method call
            request_id: The ID of the request this response corresponds to

        Returns:
            dict: A JSON-Message response object
        """
        # Create a proper RPCResponse object
        response = RPCResponse(result=result, id=request_id)
        response_dict = response.to_dict()

        # If we have a tracker, track this outgoing response
        if self.tracker:
            self.tracker.track_outgoing_response(response)

        return response_dict

    def create_error(self, error_type, data=None, id=None):
        """
        Creates a JSON-Message error response

        Args:
            error_type: The error type (from RPCError constants)
            data: Optional additional error metadata
            id: The ID this error is responding to

        Returns:
            dict: A JSON-Message error response object
        """
        # Create an RPCError object
        error = RPCError(error_type=error_type, data=data)

        # Create an RPCResponse with the error
        response = RPCResponse(error=error.error, id=id)

        # If we have a tracker, track this outgoing response
        if self.tracker:
            self.tracker.track_outgoing_response(response)

        return response.to_dict()

    def process_message(self, message: Union[Dict[str, Any], str, RPCMessage]) -> Optional[Dict[str, Any]]:
        """
        Process an incoming JSON-Message 2.0 message.
        Automatically determines if it's a request or a response and handles it accordingly.

        :param message: The JSON-Message message (dict, JSON string, or RPCMessage object)
        :return: Response if it's a request, None if it's a response
        """
        try:
            # Handle different input types
            if isinstance(message, str):
                try:
                    import json
                    message = json.loads(message)#RPCMessage.from_json(message).to_dict()
                except Exception as e:
                    self.logger.error(f"JSON parse error: {e}")
                    return self.create_error(RPCError.PARSE_ERROR)

            if isinstance(message, dict):
                # Convert dict to appropriate RPCMessage object
                if "method" in message:
                    try:
                        rpc_message = RPCRequest.from_dict(message)
                    except Exception:
                        return self.create_error(RPCError.INVALID_REQUEST)
                elif "result" in message or "error" in message:
                    try:
                        rpc_message = RPCResponse.from_dict(message)
                    except Exception:
                        return self.create_error(RPCError.INVALID_REQUEST)
                else:
                    return self.create_error(RPCError.INVALID_REQUEST)

            else:
                return self.create_error(RPCError.INVALID_REQUEST)

            # Process based on message type
            if isinstance(rpc_message, RPCRequest):
                '''if rpc_message.id is not None:
                    self.tracker.track_incoming_request(rpc_message)'''
                return self._process_request(rpc_message)
            elif isinstance(rpc_message, RPCResponse):
                '''if rpc_message.id is not None:
                    self.tracker.track_incoming_response(rpc_message)'''
                self._process_response(rpc_message)
                return None  # No need to respond to a response
            else:
                return self.create_error(RPCError.INVALID_REQUEST)
        except Exception as e:
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            return self.create_error(RPCError.INTERNAL_ERROR, data=str(e))

    def _process_request(self, request: Union[Dict[str, Any], RPCRequest]) -> Dict[str, Any]:
        """
        Process an incoming request.

        :param request: The request object or dictionary
        :return: Response dictionary
        """
        # Convert dict to RPCRequest if needed
        if isinstance(request, dict):
            try:
                request = RPCRequest.from_dict(request)
            except Exception:
                return self.create_error(RPCError.INVALID_REQUEST)

        method = request.method
        request.id = request.id

        if not method or not isinstance(method, str):
            return self.create_error(RPCError.INVALID_REQUEST, id=request.id)

        callback = self.request_methods.get(method)
        if not callback:
            return self.create_error(RPCError.METHOD_NOT_FOUND, id=request.id)

        params = request.params or {}

        try:
            # Check method signature to ensure we have the necessary parameters
            sig = inspect.signature(callback)

            # Execute method with appropriate parameters
            if isinstance(params, dict):
                # Check for required parameters that are missing
                missing_params = []
                for param_name, param in sig.parameters.items():
                    if param.default == inspect.Parameter.empty and param_name not in params and param_name != 'self':
                        missing_params.append(param_name)

                if missing_params:
                    error_data = f"Missing required parameters: {', '.join(missing_params)}"
                    return self.create_error(RPCError.INVALID_PARAMS, data=error_data, id=request.id)
                result = callback(**params)
            elif isinstance(params, list):
                # For list params, ensure we have enough positional arguments
                required_count = sum(1 for param in sig.parameters.values()
                                     if param.default == inspect.Parameter.empty and param.name != 'self')

                if len(params) < required_count:
                    error_data = f"Method requires {required_count} positional arguments, got {len(params)}"
                    return self.create_error(RPCError.INVALID_PARAMS, data=error_data, id=request.id)
                result = callback(*params)
            else:
                # No parameters
                result = callback()

            # Track for incoming request
            if request.id is not None:
                self.tracker.track_incoming_request(request)

            response = self.create_response(result=result, request_id=request.id)
            return response
        except Exception as e:
            self.logger.error(f"Error executing method {method}", exc_info=True)
            return self.create_error(RPCError.INTERNAL_ERROR, data=str(e), id=request.id)

    def _process_response(self, response: Union[Dict[str, Any], RPCResponse]) -> None:
        """
        Process an incoming response.

        :param response: The response object or dictionary
        """
        # Convert dict to RPCResponse if needed
        if isinstance(response, dict):
            try:
                response = RPCResponse.from_dict(response)
            except Exception:
                self.logger.error("Invalid response format")
                return
        request_data = self.tracker.outgoing_requests.get(response.id)
        if request_data:
            method_name = request_data[1]  # Access the second element (index 1) which is method_name
        else:
            method_name = "default"

        handler = self.response_methods.get(method_name)
        if not handler:
            # Try to use default handler if available
            handler = self.response_methods.get("default")
            if not handler:
                self.logger.warning(f"No response handler for method: {method_name}")
                return

        try:
            if response.is_success:
                result = response.result
                error = None
            else:
                result = None
                error = response.error

            # Track this incoming response
            if response.id is not None:
                self.tracker.track_incoming_response(response)

            handler(id=response.id, result=result, error=error)
        except Exception as e:
            self.logger.exception(f"Error handling response for {method_name}")
