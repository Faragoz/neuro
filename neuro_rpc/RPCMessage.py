from typing import Any, Dict, Optional, Union, List
import json


class RPCError(Exception):
    """Exception class for JSON-RPC 2.0 errors."""

    # Standard JSON-RPC 2.0 error codes
    PARSE_ERROR = {"code": -32700, "message": "Parse error"}
    INVALID_REQUEST = {"code": -32600, "message": "Invalid Request"}
    METHOD_NOT_FOUND = {"code": -32601, "message": "Method not found"}
    INVALID_PARAMS = {"code": -32602, "message": "Invalid params"}
    INTERNAL_ERROR = {"code": -32603, "message": "Internal error"}

    # Implementation-defined error codes
    METHOD_EXISTS = {"code": -32000, "message": "Method already exists"}
    SERVER_ERROR = {"code": -32001, "message": "Server error"}

    def __init__(self, error_type: str, data: Any = None):
        self.error_type = error_type
        self.error = self._create_error(error_type, data)
        super().__init__(f"{self.error['code']}: {self.error['message']} - {data if data else ''}")

    def _create_error(self, error_type: str, data: Any = None) -> Dict[str, Any]:
        """Create a standard error object."""
        error = getattr(self, error_type, self.INTERNAL_ERROR).copy()

        if data is not None:
            error["data"] = data

        return error


class RPCMessage:
    """Base class for JSON-RPC 2.0 messages."""

    def __init__(self):
        self.jsonrpc = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert the message to a dictionary."""
        return {"jsonrpc": self.jsonrpc}

    def to_json(self) -> str:
        """Convert the message to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCMessage':
        """Create message from dictionary."""
        if not isinstance(data, dict):
            raise RPCError("INVALID_REQUEST", "Data must be a dictionary")
        if data.get("jsonrpc") != "2.0":
            raise RPCError("INVALID_REQUEST", "Invalid JSON-RPC version")
        return cls()

    @classmethod
    def from_json(cls, json_str: str) -> 'RPCMessage':
        """Create message from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError:
            raise RPCError("PARSE_ERROR", "Invalid JSON string")


class RPCRequest(RPCMessage):
    """Class representing a JSON-RPC 2.0 request."""

    def __init__(self, method: str, id: Any = None, params: Optional[Union[Dict, List]] = None):
        super().__init__()
        self.method = method
        self.id = id
        self.params = params

    def to_dict(self) -> Dict[str, Any]:
        """Convert the request to a dictionary."""
        request = super().to_dict()
        request["method"] = self.method

        if self.id is not None:
            request["id"] = self.id

        if self.params is not None:
            request["params"] = self.params

        return request

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCRequest':
        """Create request from dictionary."""
        super().from_dict(data)  # Validate base message

        if "method" not in data or not isinstance(data["method"], str):
            raise RPCError("INVALID_REQUEST", "Request must include a valid method name")

        method = data["method"]
        id = data.get("id")
        params = data.get("params")

        return cls(method=method, id=id, params=params)

    @property
    def is_notification(self) -> bool:
        """Check if this request is a notification (no ID)."""
        return self.id is None


class RPCResponse(RPCMessage):
    """Class representing a JSON-RPC 2.0 response."""

    def __init__(self, id: Any, result: Any = None, error: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.id = id

        # A response must have either result or error, but not both
        if error is not None and result is not None:
            raise RPCError("INVALID_REQUEST", "Response cannot contain both result and error")

        self.result = result
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert the response to a dictionary."""
        response = super().to_dict()
        response["id"] = self.id

        if self.error is not None:
            response["error"] = self.error
        else:
            response["result"] = self.result

        return response

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RPCResponse':
        """Create response from dictionary."""
        super().from_dict(data)  # Validate base message

        if "id" not in data:
            raise RPCError("INVALID_REQUEST", "Response must include an ID")

        id = data["id"]

        if "result" in data and "error" in data:
            raise RPCError("INVALID_REQUEST", "Response cannot contain both result and error")

        if "result" not in data and "error" not in data:
            raise RPCError("INVALID_REQUEST", "Response must contain either result or error")

        result = data.get("result")
        error = data.get("error")

        return cls(id=id, result=result, error=error)

    @property
    def is_error(self) -> bool:
        """Check if this response is an error response."""
        return self.error is not None

    @property
    def is_success(self) -> bool:
        """Check if this response is a success response."""
        return self.error is None
