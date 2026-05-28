import sys
import signal
import logging
from flask import Flask

import app.config as config
import app.routes as routes
from app.storage import StorageManager
from app.hardware import HardwareManager
from app.climate import ClimateLogicEngine

class ApplicationOrchestrator:
    def __init__(self):
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        
        self.flask_app = Flask(__name__, template_folder='../templates', static_folder='../static')
        
        # Instantiate objects cleanly via standard dependency injection pattern
        self.state = config.SystemState()
        self.storage = StorageManager(self.state)
        self.hardware = HardwareManager()
        self.engine = ClimateLogicEngine(self.state, self.storage, self.hardware)
        
        self.bootstrap_subsystems()
        self.wire_flask_context()

    def bootstrap_subsystems(self):
        """Loads and syncs memory configurations before starting threads."""
        self.storage.load_state()
        self.storage.load_history()
        self.storage.load_outside_history()
        self.storage.prune_history()
        self.storage.prune_outside_history()
        
        for job in self.state.schedule:
            self.storage.normalize_schedule_item(job)
            
        self.storage.save_state()
        self.storage.save_history()
        self.storage.save_outside_history()
        
        # Launch climate control loop engine
        self.engine.start_engine_loop()

    def wire_flask_context(self):
        """Injects running object instances straight into endpoints pointers contexts safely."""
        routes.state_ptr = self.state
        routes.storage_ptr = self.storage
        self.flask_app.register_blueprint(routes.api_blueprint)

    def register_signals(self):
        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

    def handle_exit(self, signum, frame):
        print("\nShutting down climate system. Releasing hardware locks cleanly...")
        self.hardware.cleanup()
        sys.exit(0)

    def run(self):
        self.register_signals()
        try:
            self.flask_app.run(host='0.0.0.0', port=5000, use_reloader=False)
        finally:
            self.hardware.cleanup()

if __name__ == '__main__':
    orchestrator = ApplicationOrchestrator()
    orchestrator.run()