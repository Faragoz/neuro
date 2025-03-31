import threading

def print_active_threads():
    active_threads = threading.enumerate()
    print(f"Total active threads: {len(active_threads)}")

    print("\nThread details:")
    for thread in active_threads:
        print(f"  • Name: {thread.name}, Daemon: {thread.daemon}, Alive: {thread.is_alive()}")
