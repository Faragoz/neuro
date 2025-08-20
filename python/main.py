from neuro_rpc.Logger import LoggerConfig, Logger
from neuro_rpc.Console import Console

if __name__ == '__main__':
    # Configuration for the server
    local = False

    if local:
        host = 'localhost'
    else:
        host = '172.16.100.9'

    server_config = {
        'host': host,
        'port': 6363
    }

    try:
        # server.send_and_receive(server.handler.create_request('echo', {'message', 'test'}))

        #LoggerConfig.configure_for_debugging('RPCHandler', Logger.INFO, False)

        # Create and run the interactive console
        console = Console(server_config)
        #Logger.print_loggers()
        console.run()


        #server.handler.process_message()
        #server.handler.process_message({'jsonrpc': '2.0', 'id': 1, 'result': 5})

        #server.handler.create_request("add", {"a":2, "b":3})
        #server.handler.tracker.get_statistics()
        #server.handler.tracker.monitor_messages()
    except Exception as e:
        print(f"An error occurred: {e}")
