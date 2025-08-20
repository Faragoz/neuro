from typing import Any
import json

from python.neuro_rpc import logger
from python.neuro_rpc.RPCHandler import RPCHandler, rpc_method

class RPCMethods(RPCHandler):
    """Container for Message methods with handler delegation."""

    def __init__(self, auto_register: bool = True):
        """
        Initialize the Message methods container.

        :param auto_register: Whether to automatically register methods with the handler
        """
        super().__init__()


        # Auto-register if specified
        if auto_register:
            self.register_methods(self)

    # Example Message methods
    @rpc_method(method_type="request")
    def echo(self, message: str) -> str:
        """Echo the input message."""
        #logger.debug(f"Echo request received: {message}")
        return message

    @rpc_method(method_type="response", name="echo")
    def handle_echo_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """Handle response from add request."""
        if error:
            logger.error(f"Echo operation failed: {error}")
        else:
            #logger.debug(f"Echo: size:{result.get("message")}")
            pass

    @rpc_method(method_type="request")
    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        #logger.debug(f"Add request: {a} + {b}")
        return a + b

    @rpc_method(method_type="response", name="add")
    def handle_add_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """Handle response from add request."""
        if error:
            logger.error(f"Add operation failed: {error}")
        else:
            logger.debug(f"Add operation result: {result}")

    @rpc_method(method_type="request")
    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a."""
        #logger.debug(f"Subtract request: {a} - {b}")
        return a - b

    @rpc_method(method_type="response", name="subtract")
    def handle_subtract_response(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """Handle response from subtract request."""
        if error:
            logger.error(f"Subtract operation failed: {error}")
        else:
            logger.debug(f"Subtract operation result: {result}")

    # Default handling
    @rpc_method(method_type="response", name="default")
    def default_response_handler(self, id: Any = None, result: Any = None, error: Any = None) -> None:
        """Default handler for responses without specific handlers."""
        if error:
            logger.warning(f"Unhandled response error for ID {id}: {error}")
        else:
            logger.debug(f"Unhandled response result for ID {id}: {result}")


# Example usage
if __name__ == "__main__":
    rpc = RPCMethods()

    # Test request processing
    print("\n--- Request Processing ---")
    request1 = {"jsonrpc": "2.0", "method": "echo", "params": {"message": "Hello, world!"}, "id": 1}
    response1 = rpc.process_message(request1)
    print(f"Echo request: {json.dumps(request1, indent=2)}")
    print(f"Response: {json.dumps(response1, indent=2)}")

    request2 = {"jsonrpc": "2.0", "method": "add", "params": {"a": 5, "b": 3}, "id": 2}
    response2 = rpc.process_message(request2)
    print(f"\nAdd request: {json.dumps(request2, indent=2)}")
    print(f"Response: {json.dumps(response2, indent=2)}")

    # Test response processing
    print("\n--- Response Processing ---")
    response_msg = {"jsonrpc": "2.0", "method": "add", "result": 8, "id": 3}
    print(f"Processing response: {json.dumps(response_msg, indent=2)}")
    rpc.process_message(response_msg)

    # Test error handling
    print("\n--- Error Handling ---")
    error_response = {"jsonrpc": "2.0", "method": "subtract", "error": {"code": -1, "message": "Test error"}, "id": 4}
    print(f"Processing error response: {json.dumps(error_response, indent=2)}")
    rpc.process_message(error_response)

    # Test method not found
    print("\n--- Method Not Found ---")
    unknown_request = {"jsonrpc": "2.0", "method": "unknown_method", "params": {}, "id": 5}
    response5 = rpc.process_message(unknown_request)
    print(f"Unknown method request: {json.dumps(unknown_request, indent=2)}")
    print(f"Response: {json.dumps(response5, indent=2)}")

    # Create custom request
    custom_request = rpc.create_request("multiply", {"a": 10, "b": 5})
    print(f"\nCreated custom request: {json.dumps(custom_request, indent=2)}")