"""
@file RPCHandler.py
@brief Registration and dispatch of RPC request/response methods.
@details Implements a handler for JSON-Message 2.0 (similar to JSON-RPC 2.0), providing:
 - Method registration via the @rpc_method decorator.
 - Creation of request, response, and error messages.
 - Processing of incoming messages (both requests and responses).
 - Integration with Benchmark to track latency and round-trip times.
@note Acts as the bridge between raw JSON messages and Python method calls.
"""
import inspect
from typing import Callable, Dict, Any, Optional, Union

from python.neuro_rpc.Benchmark import Benchmark
from python.neuro_rpc.RPCMessage import RPCMessage, RPCRequest, RPCResponse, RPCError
from python.neuro_rpc.Logger import Logger
import uuid

# Message Methods Decorator
def rpc_method(method_type: str = "both", name: Optional[str] = None):
    """
    @brief Decorator to mark methods for RPC registration.
    @details Annotates a function so that RPCHandler.register_methods()
    can discover and register it as a request and/or response handler.
    @param method_type str One of {"request", "response", "both"} (default "both").
    @param name str Optional alias under which the method is registered.
    @return Callable Decorated function.
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
    """
    @brief Core handler for JSON-Message 2.0 operations.
    @details Manages registration of request/response handlers,
    creation of message objects, and routing of incoming messages.
    Integrates with Benchmark to track requests/responses.
    """

    def __init__(self):
        """
        @brief Initialize the RPCHandler.
        @details Creates registries for request/response methods,
        sets up a Benchmark tracker, and initializes a logger.
        """
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
        @brief Register decorated methods from an instance.
        @details Scans instance methods and registers those annotated with @rpc_method.
        @param instance Any Object instance containing decorated methods.
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
        @brief Register a request handler.
        @param method_name str Name of the RPC method.
        @param method Callable Function to call when this request is received.
        @raises ValueError If the provided method is not callable.
        """
        if not callable(method):
            raise ValueError(f"Request handler for {method_name} must be callable")

        if method_name in self.request_methods:
            self.logger.warning(f"Overriding existing request method: {method_name}")

        self.request_methods[method_name] = method
        #self.logger.debug(f"Registered request method: {method_name}")

    def register_response(self, method_name: str, method: Callable) -> None:
        """
        @brief Register a response handler.
        @param method_name str Name of the RPC method.
        @param method Callable Function to call when a response is received.
        @raises ValueError If the provided method is not callable.
        """
        if not callable(method):
            raise ValueError(f"Response handler for {method_name} must be callable")

        if method_name in self.response_methods:
            self.logger.warning(f"Overriding existing response method: {method_name}")

        self.response_methods[method_name] = method
        #self.logger.debug(f"Registered response method: {method_name}")

    def next_request_id(self) -> int:
        """
        @brief Generate a new request ID.
        @return int Incremental request ID.
        """
        self._request_id += 1
        return self._request_id

    def create_request(self, method, params=None, request_id=None):
        """
        @brief Create a JSON-Message request object.
        @param method str Method name to call.
        @param params dict|list Optional parameters for the request.
        @param request_id str Optional custom request ID (UUID by default).
        @return dict Serialized request object.
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
        @brief Create a JSON-Message response object.
        @param result Any The result to return.
        @param request_id str ID of the original request.
        @return dict Serialized response object.
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
        @brief Create a JSON-Message error object.
        @param error_type str|dict Error type (see RPCError constants).
        @param data Any Optional additional error details.
        @param id str Optional ID of the related request.
        @return dict Serialized error response object.
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
        @brief Process an incoming JSON-Message.
        @details Parses input (string/dict/RPCMessage), converts to RPCRequest or RPCResponse,
        and dispatches to the appropriate handler. Returns a response dict if needed.
        @param message dict|str|RPCMessage Incoming message.
        @return dict|None Response dict if request, None if response.
        @raises RPCError If message is invalid or cannot be parsed.
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
        @brief Process an incoming RPCRequest.
        @details Validates method existence and parameters, invokes callback, and returns a response dict.
        @param request dict|RPCRequest Incoming request.
        @return dict Serialized response or error.
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
        @brief Process an incoming RPCResponse.
        @details Routes result/error to the appropriate registered response handler.
        @param response dict|RPCResponse Incoming response.
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
