"""
Message and error classes for JSON-Message 2.0 protocol.

Provides base classes for JSON-Message 2.0 communication (similar to JSON-RPC 2.0):
    - RPCError: structured error objects.
    - RPCMessage: base class for all messages.
    - RPCRequest: request with method, params, and id.
    - RPCResponse: response with result or error.

Notes:
    - Ensures compatibility with NeuroRPC stack (Client, RPCHandler, Benchmark).
"""
from typing import Any, Dict, Optional, Union, List
import json


class RPCError(Exception):
    """
    Exception class for JSON-Message 2.0 errors.

    Encapsulates standard and implementation-specific error codes as structured
    dictionaries, used for request/response validation.
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
        Initialize RPCError with a given type and optional metadata.

        Args:
            error_type (str | dict): One of the error constants or a full error dict.
            data (Any, optional): Additional metadata attached as "metadata" field.
        """
        if isinstance(error_type, dict):
            self.error_type = None
            self.error = error_type.copy()
            if data is not None:
                self.error["metadata"] = data
        else:
            self.error_type = error_type
            self.error = self._create_error(error_type, data)

        super().__init__(f"{self.error['code']}: {self.error['message']} - {data if data else ''}")

    def _create_error(self, error_type: str, data: Any = None) -> Dict[str, Any]:
        """
        Create a standard error object from a type and metadata.

        Args:
            error_type (str): Error type name (must map to a class constant).
            data (Any, optional): Optional metadata.

        Returns:
            dict: Error object with code, message, and optional metadata.
        """
        error = getattr(self, error_type, self.INTERNAL_ERROR).copy()

        if data is not None:
            error["metadata"] = data

        return error


class RPCMessage:
    """
    Base class for JSON-Message 2.0 messages.

    Defines the ``jsonrpc`` version and common serialization/deserialization helpers.
    """

    def __init__(self):
        """Initialize with version '2.0'."""
        self.jsonrpc = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the message to a dictionary.

        Returns:
            dict: Dictionary containing the ``jsonrpc`` version.
        """
        return {"jsonrpc": self.jsonrpc}

    def to_json(self) -> str:
        """
        Serialize the message to a JSON string.

        Returns:
            str: JSON string with message content.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCMessage':
        """
        Validate and create a message from dictionary.

        Args:
            data (dict): Dictionary to parse.

        Returns:
            RPCMessage: Instance of the base class.

        Raises:
            RPCError: If input is not a dict or version is invalid.
        """
        if not isinstance(data, dict):
            raise RPCError(RPCError.INVALID_REQUEST, "Data must be a dictionary")
        if data.get("jsonrpc") != "2.0":
            raise RPCError(RPCError.INVALID_REQUEST, "Invalid JSON-Message version")
        return cls()

    @classmethod
    def from_json(cls, json_str: str) -> 'RPCMessage':
        """
        Create message from JSON string.

        Args:
            json_str (str): Input JSON string.

        Returns:
            RPCMessage: Parsed object.

        Raises:
            RPCError: If parsing fails.
        """
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError:
            raise RPCError(RPCError.PARSE_ERROR, "Invalid JSON string")


class RPCRequest(RPCMessage):
    """
    JSON-Message 2.0 Request.

    Contains method name, parameters, and identifier (id). Supports both positional
    (list) and named (dict) parameters.
    """

    def __init__(self, method: str, id: Any = None, params: Optional[Union[Dict, List]] = None):
        """
        Args:
            method (str): Method name to call.
            id (Any, optional): Identifier for correlation (None for notifications).
            params (dict | list, optional): Parameters for the call.
        """
        super().__init__()
        self.method = method
        self.id = id
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the request to a dictionary.

        Returns:
            dict: Request with jsonrpc, method, id, and params.
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
        Create a request from dictionary.

        Args:
            data (dict): Input dictionary.

        Returns:
            RPCRequest: Parsed request.

        Raises:
            RPCError: If validation fails.
        """
        RPCMessage.from_dict(data)

        if "method" not in data or not isinstance(data["method"], str):
            raise RPCError(RPCError.INVALID_REQUEST, "Request must include a valid method name")

        method = data["method"]
        id = data.get("id")
        params = data.get("params")

        return cls(method=method, id=id, params=params)

    @property
    def is_notification(self) -> bool:
        """
        Check if this request is a notification.

        Notifications do not have an id and therefore do not expect a response.

        Returns:
            bool: True if id is None.
        """
        return self.id is None


class RPCResponse(RPCMessage):
    """
    JSON-Message 2.0 Response.

    Contains either a ``result`` or an ``error``, but never both.
    Optionally includes execution time (exec_time) for benchmarking.
    """

    def __init__(
        self,
        id: Any,
        result: Any = None,
        error: Optional[Dict[str, Any]] = None,
        exec_time: Optional[int] = None,
    ):
        """
        Args:
            id (Any): ID of the original request.
            result (Any, optional): Result of the request.
            error (dict, optional): Error object.
            exec_time (int, optional): Execution time (μs, provided by server).

        Raises:
            RPCError: If both result and error are provided.
        """
        super().__init__()
        self.id = id

        if error is not None and result is not None:
            raise RPCError("INVALID_REQUEST", "Response cannot contain both result and error")

        self.result = result
        self.error = error
        self.exec_time = exec_time

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the response to a dictionary.

        Returns:
            dict: Response with jsonrpc, id, and either result or error.
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
        Create a response from dictionary.

        Args:
            data (dict): Input dictionary.

        Returns:
            RPCResponse: Parsed response.

        Raises:
            RPCError: If validation fails.
        """
        RPCMessage.from_dict(data)

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
        Check if this response is an error response.

        Returns:
            bool: True if error is not None.
        """
        return self.error is not None

    @property
    def is_success(self) -> bool:
        """
        Check if this response is a success response.

        Returns:
            bool: True if error is None.
        """
        return self.error is None
