"""
Example RPC methods built on top of RPCHandler.

Provides a container of request/response methods for testing and demonstration.
Includes echo, add, subtract, and a default response handler.
Can be extended with custom RPC logic as needed.

Notes:
    - Uses the @rpc_method decorator to auto-register methods with RPCHandler.
"""
from typing import Any
import json

from python.neuro_rpc import logger
from python.neuro_rpc.RPCHandler import RPCHandler, rpc_method


class RPCMethods(RPCHandler):
    """
    Container for RPC methods.

    Extends RPCHandler and defines example request/response methods that are
    automatically registered at initialization if ``auto_register=True``.
    """

    def __init__(self, auto_register: bool = True):
        """
        Initialize the RPCMethods container.

        Args:
            auto_register (bool): If True, automatically registers decorated methods.
        """
        super().__init__()

        if auto_register:
            self.register_methods(self)

    @rpc_method(method_type="request")
    def echo(self, message: str) -> str:
        """
        RPC request method: echo a message.

        Args:
            message (str): String to echo back.

        Returns:
            str: The same message received.
        """
        return message

    @rpc_method(method_type="response", name="echo")
    def handle_echo_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """
        Response handler for echo.

        Args:
            id (Any, optional): ID of the corresponding request.
            result (Any, optional): Result content.
            error (Any, optional): Error object if the request failed.
        """
        if error:
            logger.error(f"Echo operation failed: {error}")
        else:
            pass

    @rpc_method(method_type="request")
    def add(self, a: float, b: float) -> float:
        """
        RPC request method: add two numbers.

        Args:
            a (float): First number.
            b (float): Second number.

        Returns:
            float: Sum of a and b.
        """
        return a + b

    @rpc_method(method_type="response", name="add")
    def handle_add_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """
        Response handler for add.

        Args:
            id (Any, optional): ID of the corresponding request.
            result (Any, optional): Result (sum).
            error (Any, optional): Error object if the request failed.
        """
        if error:
            logger.error(f"Add operation failed: {error}")
        else:
            logger.debug(f"Add operation result: {result}")

    @rpc_method(method_type="request")
    def subtract(self, a: float, b: float) -> float:
        """
        RPC request method: subtract b from a.

        Args:
            a (float): Minuend.
            b (float): Subtrahend.

        Returns:
            float: Result of a - b.
        """
        return a - b

    @rpc_method(method_type="response", name="subtract")
    def handle_subtract_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """
        Response handler for subtract.

        Args:
            id (Any, optional): ID of the corresponding request.
            result (Any, optional): Result (difference).
            error (Any, optional): Error object if the request failed.
        """
        if error:
            logger.error(f"Subtract operation failed: {error}")
        else:
            logger.debug(f"Subtract operation result: {result}")

    @rpc_method(method_type="response", name="default")
    def default_response_handler(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """
        Default response handler.

        Invoked if no specific handler is registered for a response.

        Args:
            id (Any, optional): ID of the response.
            result (Any, optional): Result payload if success.
            error (Any, optional): Error payload if failure.
        """
        if error:
            logger.warning(f"Unhandled response error for ID {id}: {error}")
        else:
            logger.debug(f"Unhandled response result for ID {id}: {result}")


if __name__ == "__main__":
    rpc = RPCMethods()

    print("\n--- Request Processing ---")
    request1 = {"jsonrpc": "2.0", "method": "echo", "params": {"message": "Hello, world!"}, "id": 1}
    response1 = rpc.process_message(request1)
    print(f"Echo request: {json.dumps(request1, indent=2)}")
    print(f"Response: {json.dumps(response1, indent=2)}")

    request2 = {"jsonrpc": "2.0", "method": "add", "params": {"a": 5, "b": 3}, "id": 2}
    response2 = rpc.process_message(request2)
    print(f"\nAdd request: {json.dumps(request2, indent=2)}")
    print(f"Response: {json.dumps(response2, indent=2)}")

    print("\n--- Response Processing ---")
    response_msg = {"jsonrpc": "2.0", "method": "add", "result": 8, "id": 3}
    print(f"Processing response: {json.dumps(response_msg, indent=2)}")
    rpc.process_message(response_msg)

    print("\n--- Error Handling ---")
    error_response = {"jsonrpc": "2.0", "method": "subtract", "error": {"code": -1, "message": "Test error"}, "id": 4}
    print(f"Processing error response: {json.dumps(error_response, indent=2)}")
    rpc.process_message(error_response)

    print("\n--- Method Not Found ---")
    unknown_request = {"jsonrpc": "2.0", "method": "unknown_method", "params": {}, "id": 5}
    response5 = rpc.process_message(unknown_request)
    print(f"Unknown method request: {json.dumps(unknown_request, indent=2)}")
    print(f"Response: {json.dumps(response5, indent=2)}")

    custom_request = rpc.create_request("multiply", {"a": 10, "b": 5})
    print(f"\nCreated custom request: {json.dumps(custom_request, indent=2)}")
