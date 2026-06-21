# =============================================================================
# MUSIFY LOGGING & PROCESS UTILITIES
# This module provides a centralized set of tools for logging, directory 
# management, and external command execution (like fluidsynth, abc2midi, etc).
# =============================================================================

import logging
import subprocess
import os
import sys
import inspect
from logging.handlers import RotatingFileHandler
import glob

# -----------------------------------------------------------------------------
# LOGGING SETUP
# -----------------------------------------------------------------------------

def setup_logging(log_file='output/log/app.log', file_level=logging.DEBUG, console_level=logging.WARNING,
                  max_bytes=5*1024*1024, backup_count=2):
    """
    Initializes a flexible logging system that writes to both a file and the console.
    
    - log_file: Where to save the log data.
    - file_level: Detail level for the file (default DEBUG captures everything).
    - console_level: Detail level for the terminal (default WARNING hides noise).
    - max_bytes / backup_count: Parameters for RotatingFileHandler to prevent logs
      from growing infinitely and filling up disk space.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    
    # Set Root Level to the lowest requested level to ensure no messages are dropped.
    root_logger.setLevel(min(file_level, console_level))
    
    # Clear existing handlers to prevent duplicate messages if setup is called twice.
    if root_logger.handlers:
        root_logger.handlers = []

    # Standard format: [Timestamp] - [Level] - [Message]
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # 1. ROTATING FILE HANDLER
    # Automatically creates new log files when the current one exceeds 'max_bytes'.
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 2. CONSOLE HANDLER
    # Sends output to stderr (standard error) so it doesn't interfere with stdout pipe data.
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    logging.info(f"Logging initialized. Log file: {log_file}")

def get_log_context(depth=1):
    """
    Uses Python's introspection (inspect) to determine which file and line 
    called the current function. 
    
    - depth: How many frames to look back in the stack. 
      depth=1 is the direct caller.
    """
    try:
        frame = inspect.currentframe()
        # Walk back 'depth'+1 steps to find the actual origin of the call.
        for i in range(depth+1):
            if frame:
                frame = frame.f_back
        
        if frame and frame.f_code:
            lineno = frame.f_lineno
            filename = os.path.basename(frame.f_code.co_filename)
            return f"[{filename}:{lineno}]"
    except Exception:
        pass
    return "[unknown:0]"

# -----------------------------------------------------------------------------
# DIRECTORY & FILE UTILITIES
# -----------------------------------------------------------------------------

def resolve_output_directory(arg_value, default_path, description):
    """
    Smart resolution of directory paths from Quarto filter arguments.
    
    - If arg_value is True, use the default path.
    - If arg_value is a string, use that specific path.
    - If False/None, generation is skipped for this asset type.
    """
    logging.info(f"{get_log_context(1)}: Resolving {description}. arg_value={arg_value}")
    
    if arg_value is True:
        path = default_path
    elif arg_value: # Catches non-empty strings provided by the user
        path = arg_value
    else:
        logging.info(f"Skipping {description} generation.")
        return False
        
    try:
        # Create the directory if it doesn't exist
        os.makedirs(path, exist_ok=True)
        return path
    except Exception as e:
        logging.error(f"Failed to create {description} at {path}: {e}")
        return False

def show_folder_contents(folder_path):
    """
    Executes 'ls' on a path and logs the results. 
    Extremely useful for debugging generation pipelines like ABC -> MIDI -> WAV.
    """
    try:
        # Use glob to handle patterns (like "resources/images/tune*")
        paths = glob.glob(folder_path)
        if not paths:
            logging.info(f"No files matching {folder_path}")
            return

        result = subprocess.run(["ls", "-AlthrF", "--color=auto"] + paths,
                                capture_output=True, text=True, check=True)
        logging.info(f"{get_log_context(1)}: folder contents: {folder_path}\n{result.stdout}")
    except Exception as e:
        logging.error(f"Error listing contents of {folder_path}: {e}")

# -----------------------------------------------------------------------------
# COMMAND EXECUTION
# -----------------------------------------------------------------------------

def run_command(cmd, description, timeout=10):
    """
    Wrapper around subprocess.run with unified logging and error handling.
    Captures stdout/stderr and logs them, handling timeouts and non-zero exits.
    """
    logging.info(f"{get_log_context(1)}: Executing {description}: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", shell=(sys.platform == "win32"), timeout=timeout)
        
        # Check for success
        is_success = (result.returncode == 0)
        
        stdout_output = result.stdout.strip()
        stderr_output = result.stderr.strip()
        
        if is_success:
            if stdout_output:
                logging.info(f"{description} stdout: {stdout_output}")
            if stderr_output:
                logging.info(f"{description} stderr: {stderr_output}")
            logging.info(f"{description} completed successfully (Exit code: {result.returncode}).")
            return True
        else:
            logging.error(f"{description} failed with exit code {result.returncode}.")
            logging.error(f"STDOUT: {stdout_output}")
            logging.error(f"STDERR: {stderr_output}")
            return False
            
    except subprocess.TimeoutExpired as e:
        logging.error(f"{description} timed out after {e.timeout}s.")
        return False
        
    except FileNotFoundError:
        logging.error(f"Executable for '{description}' ({cmd[0]}) not found. Is it installed?")
        return False
        
    except Exception as e:
        logging.error(f"Unexpected error running {description}: {e}")
        return False
