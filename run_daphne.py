import os
import subprocess
import time
import signal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def kill_port_processes(port):
    """Kill any processes using the specified port"""
    try:
        # Find processes using the port
        result = subprocess.run(['lsof', '-ti', f':{port}'], 
                              capture_output=True, text=True, check=False)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                    print(f"Killed process {pid} using port {port}")
                except (ProcessLookupError, ValueError):
                    pass
            time.sleep(1)
    except FileNotFoundError:
        # lsof not available, try alternative approach
        try:
            result = subprocess.run(['netstat', '-tlnp'], 
                                  capture_output=True, text=True, check=False)
            for line in result.stdout.split('\n'):
                if f':{port} ' in line and 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) > 6 and '/' in parts[6]:
                        pid = parts[6].split('/')[0]
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                            print(f"Killed process {pid} using port {port}")
                        except (ProcessLookupError, ValueError):
                            pass
        except FileNotFoundError:
            print("Unable to check for existing processes on port 8000")

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, process_args):
        self.process_args = process_args
        self.process = None
        self.last_restart_time = 0
        self.start_server()

    def start_server(self):
        kill_port_processes(8000)
        print("Starting Daphne server...")
        self.process = subprocess.Popen(self.process_args)
        self.last_restart_time = time.time()

    def restart_server(self):
        if self.process:
            print("Restarting Daphne server...")
            self.process.terminate()
            self.process.wait()
        self.start_server()

    def on_modified(self, event):
        # Add a cooldown to prevent restart loops
        if time.time() - self.last_restart_time < 2:
            return

        if event.is_directory or not event.src_path.endswith('.py'):
            return

        # Ignore changes in venv or __pycache__ directories
        path = os.path.normpath(event.src_path)
        if 'venv' in path.split(os.sep) or '__pycache__' in path.split(os.sep):
            return

        print(f"Detected change in {event.src_path}, reloading...")
        self.restart_server()

if __name__ == "__main__":
    # Make sure you have 'watchdog' installed: pip install watchdog
    path = '.'
    process_args = ['daphne', '-b', '0.0.0.0', '-p', '8000', 'quiz_game.asgi:application']
    
    event_handler = ChangeHandler(process_args)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    
    observer.start()
    print(f"Watching for changes in {os.path.abspath(path)}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if event_handler.process:
            event_handler.process.terminate()
            event_handler.process.wait()
    observer.join()
