"""
@file RPCMessage.py
@brief Message and error classes for JSON-Message 2.0 protocol.
@details Provides base classes for JSON-Message 2.0 communication (similar to JSON-RPC 2.0):
 - RPCError: structured error objects.
 - RPCMessage: base class for all messages.
 - RPCRequest: request with method, params, and id.
 - RPCResponse: response with result or error.
@note Ensures compatibility with NeuroRPC stack (Client, RPCHandler, Benchmark).
"""
from typing import Any, Dict, Optional, Union, List
import json

class RPCError(Exception):
    """
    @brief Exception class for JSON-Message 2.0 errors.
    @details Encapsulates standard and implementation-specific error codes
    as structured dictionaries, used for request/response validation.
    """

    # Standard JSON-Message 2.0 error codes
    PARSE_ERROR = {"code": -32700, "message": "Parse error"}
    INVALID_REQUEST = {"code": -32600, "message": "Invalid Request"}
    METHOD_NOT_FOUND = {"code": -32601, "message": "Method not found"}
    INVALID_PARAMS = {"code": -32602, "message": "Invalid params"}
    INTERNAL_ERROR = {"code": -32603, "message": "Internal error"}

    # Implementation-defined error codes
    METHOD_EXISTS = {"code": -32000, "message": "Method already exists"}
    SERVER_ERROR = {"code": -32001, "message": "Client error"}

    def __init__(self, error_type=None, data: Any = None):
        """
        @brief Initialize RPCError with a given type and optional metadata.
        @param error_type str|dict One of the error constants or a full error dict.
        @param data Any Optional additional metadata (attached as "metadata" field).
        """
        if isinstance(error_type, dict):
            # Direct error dictionary provided
            self.error_type = None  # No type name when direct dict is used
            self.error = error_type.copy()  # Use the provided error dict
            if data is not None:
                self.error["metadata"] = data
        else:
            # String identifier provided
            self.error_type = error_type
            self.error = self._create_error(error_type, data)

        super().__init__(f"{self.error['code']}: {self.error['message']} - {data if data else ''}")

    def _create_error(self, error_type: str, data: Any = None) -> Dict[str, Any]:
        """
        @brief Create a standard error object from a type and metadata.
        @param error_type str Error type name (must map to a class constant).
        @param data Any Optional metadata.
        @return dict Error object with code, message, and optional metadata.
        """
        error = getattr(self, error_type, self.INTERNAL_ERROR).copy()

        if data is not None:
            error["metadata"] = data

        return error

class RPCMessage:
    """
    @brief Base class for JSON-Message 2.0 messages.
    @details Defines the `jsonrpc` version and common serialization/deserialization helpers.
    """

    def __init__(self):
        """@brief Initialize with version '2.0'."""
        self.jsonrpc = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        """
        @brief Serialize the message to a dictionary.
        @return dict Dictionary containing the jsonrpc version.
        """
        return {"jsonrpc": self.jsonrpc}

    def to_json(self) -> str:
        """
        @brief Serialize the message to a JSON string.
        @return str JSON string with message content.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCMessage':
        """
        @brief Validate and create a message from dictionary.
        @param data dict Dictionary to parse.
        @return RPCMessage Instance of the base class.
        @raises RPCError If input is not dict or version is invalid.
        """
        if not isinstance(data, dict):
            raise RPCError(RPCError.INVALID_REQUEST, "Data must be a dictionary")
        if data.get("jsonrpc") != "2.0":
            raise RPCError(RPCError.INVALID_REQUEST, "Invalid JSON-Message version")
        return cls()

    @classmethod
    def from_json(cls, json_str: str) -> 'RPCMessage':
        """
        @brief Create message from JSON string.
        @param json_str str Input JSON string.
        @return RPCMessage Parsed object.
        @raises RPCError If parsing fails.
        """
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError:
            raise RPCError(RPCError.PARSE_ERROR, "Invalid JSON string")

class RPCRequest(RPCMessage):
    """
    @brief JSON-Message 2.0 Request.
    @details Contains method name, parameters, and identifier (id).
    Supports both positional (list) and named (dict) parameters.
    """

    def __init__(self, method: str, id: Any = None, params: Optional[Union[Dict, List]] = None):
        """
        @param method str Method name to call.
        @param id Any Optional identifier for correlation (can be None for notifications).
        @param params dict|list Optional parameters for the call.
        """
        super().__init__()
        self.method = method
        self.id = id
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        """
        @brief Serialize the request to a dictionary.
        @return dict Request with jsonrpc, method, id, and params.
        """
        request = super().to_dict()
        request["method"] = self.method

        if self.id is not None:
            request["id"] = self.id

        if self.params is not None:
            request["params"] = self.params

        return request

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCRequest':
        """
        @brief Create a request from dictionary.
        @param data dict Input dictionary.
        @return RPCRequest Parsed request.
        @raises RPCError If validation fails.
        """
        RPCMessage.from_dict(data)  # Validate base message

        if "method" not in data or not isinstance(data["method"], str):
            raise RPCError(RPCError.INVALID_REQUEST, "Request must include a valid method name")

        method = data["method"]
        id = data.get("id")
        params = data.get("params")

        return cls(method=method, id=id, params=params)

    @property
    def is_notification(self) -> bool:
        """
        @brief Check if this request is a notification.
        @details Notifications do not have an id and therefore do not expect a response.
        @return bool True if id is None.
        """
        return self.id is None

class RPCResponse(RPCMessage):
    """
    @brief JSON-Message 2.0 Response.
    @details Contains either a `result` or an `error`, but never both.
    Optionally includes execution time (exec_time) for benchmarking.
    """

    def __init__(self, id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None, exec_time: Optional[int] = None,):
        """
        @param id Any ID of the original request.
        @param result Any Optional result of the request.
        @param error dict Optional error object.
        @param exec_time int Optional execution time (μs, provided by server).
        @raises RPCError If both result and error are provided.
        """
        super().__init__()
        self.id = id

        # A response must have either result or error, but not both
        if error is not None and result is not None:
            raise RPCError("INVALID_REQUEST", "Response cannot contain both result and error")

        self.result = result
        self.error = error
        self.exec_time = exec_time

    def to_dict(self) -> Dict[str, Any]:
        """
        @brief Serialize the response to a dictionary.
        @return dict Response with jsonrpc, id, and either result or error.
        """
        response = super().to_dict()
        response["id"] = self.id

        if self.error is not None:
            response["error"] = self.error
        else:
            response["result"] = self.result

        if self.exec_time is not None:
            response["exec_time"] = self.exec_time

        return response

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCResponse':
        """
        @brief Create a response from dictionary.
        @param data dict Input dictionary.
        @return RPCResponse Parsed response.
        @raises RPCError If validation fails.
        """
        RPCMessage.from_dict(data)  # Validate base message

        if "id" not in data:
            raise RPCError(RPCError.INVALID_REQUEST, "Response must include an ID")

        if "result" in data and "error" in data:
            raise RPCError(RPCError.INVALID_REQUEST, "Response cannot contain both result and error")

        if "result" not in data and "error" not in data:
            raise RPCError(RPCError.INVALID_REQUEST, "Response must contain either result or error")

        id = data["id"]
        result = data.get("result")
        error = data.get("error")
        exec_time = data.get("exec_time", 0)

        return cls(id=id, result=result, error=error, exec_time=exec_time)

    @property
    def is_error(self) -> bool:
        """
        @brief Check if this response is an error response.
        @return bool True if error is not None.
        """
        return self.error is not None

    @property
    def is_success(self) -> bool:
        """
        @brief Check if this response is a success response.
        @return bool True if error is None.
        """
        return self.error is None
