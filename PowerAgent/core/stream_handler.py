# ========================================
# 文件名: PowerAgent/core/stream_handler.py
# (CORRECTED - Improved termination logic & error handling)
# ----------------------------------------
# core/stream_handler.py
# -*- coding: utf-8 -*-

"""
Handles reading from subprocess streams asynchronously.
"""

import os
import platform
import traceback
import io
import time # Import time for sleep
from PySide6.QtCore import QObject, Signal, QThread

class StreamWorker(QObject):
     finished = Signal()
     output_ready = Signal(bytes) # Emits raw bytes

     def __init__(self, stream, stop_flag_func, line_list=None, filter_clixml=False):
         """
         Worker to read from a stream non-blockingly using os.read.

         Args:
             stream: The stream object (e.g., process.stdout, process.stderr).
             stop_flag_func: A callable function that returns True if the worker should stop (external signal).
             line_list (optional): A list to append raw chunks to (used for stderr checking later).
             filter_clixml (optional): If True on Windows, attempts to filter out CLIXML error messages.
         """
         super().__init__()
         self.stream = stream
         self.external_stop_flag_func = stop_flag_func # Rename for clarity
         self._should_stop = False # Internal flag for explicit stop
         self.line_list = line_list
         self.filter_clixml = filter_clixml and platform.system() == "Windows"
         self.stream_fd = -1
         self.stream_name = "Unknown" # For logging

         if hasattr(stream, 'fileno'):
             try:
                 self.stream_fd = stream.fileno()
                 # Determine stream name for logging
                 if stream is getattr(stream, '__stdout__', None): self.stream_name = "stdout"
                 elif stream is getattr(stream, '__stderr__', None): self.stream_name = "stderr"
                 else: self.stream_name = f"FD {self.stream_fd}"
             except (OSError, ValueError, io.UnsupportedOperation) as e:
                 print(f"[StreamWorker {self.stream_name}] Warning: Could not get fileno: {e}. os.read unavailable.")
         else:
              self.stream_name = type(stream).__name__
              print(f"[StreamWorker {self.stream_name}] Warning: Stream object has no fileno attribute.")


     def stop(self):
         """Signals the worker to stop its loop."""
         self._should_stop = True
         print(f"[StreamWorker {self.stream_name}] Stop signal received internally.")

     def run(self):
         """Reads from the stream and emits data until EOF or stop signal."""
         print(f"[StreamWorker {self.stream_name}] Reader thread started.")
         try:
             # Loop while neither external nor internal stop flag is set
             while not self.external_stop_flag_func() and not self._should_stop:
                 try:
                     chunk = None
                     read_attempted = False

                     if self.stream_fd != -1:
                         try:
                             # Use os.read for potentially better non-blocking behavior on pipes
                             chunk = os.read(self.stream_fd, 4096)
                             read_attempted = True
                         except BlockingIOError:
                             # This is expected if no data is available, sleep briefly
                             QThread.msleep(20) # Small sleep to yield CPU
                             continue
                         except (OSError, ValueError) as e:
                             # Errors like EBADF (bad file descriptor) likely mean the pipe closed
                             print(f"[StreamWorker {self.stream_name}] Stream read error (os.read): {e}. Stopping read.")
                             self._should_stop = True # Ensure loop exit
                             break # Exit loop
                     else:
                         # Fallback using stream.read() - potentially blocking
                         try:
                             # Check if stream is closed before attempting read
                             if hasattr(self.stream, 'closed') and self.stream.closed:
                                 print(f"[StreamWorker {self.stream_name}] Fallback stream detected as closed.")
                                 self._should_stop = True
                                 break
                             # This might block if stream doesn't support non-blocking reads
                             chunk = self.stream.read(4096)
                             read_attempted = True
                         except io.UnsupportedOperation:
                             print(f"[StreamWorker {self.stream_name}] Fallback stream read failed: Unsupported operation.")
                             self._should_stop = True
                             break
                         except Exception as read_err:
                             print(f"[StreamWorker {self.stream_name}] Fallback stream read error: {read_err}")
                             self._should_stop = True
                             break

                     # If read was attempted and returned no data, it usually means EOF
                     if read_attempted and not chunk:
                         print(f"[StreamWorker {self.stream_name}] EOF detected.")
                         self._should_stop = True
                         break # Exit loop

                     # If a chunk was successfully read
                     if chunk:
                         # Check flags again *after* potential blocking read
                         if self.external_stop_flag_func() or self._should_stop:
                              print(f"[StreamWorker {self.stream_name}] Stop flag set after read, discarding chunk.")
                              break

                         emit_chunk = True
                         if self.line_list is not None:
                             self.line_list.append(chunk) # Store raw chunk

                         if self.filter_clixml:
                             try:
                                 if chunk.strip().startswith(b"#< CLIXML"):
                                     emit_chunk = False
                                     # print(f"[StreamWorker {self.stream_name}] Filtered potential CLIXML block.") # Debug log
                             except Exception: pass # Ignore errors during filtering check

                         if emit_chunk:
                             try:
                                 self.output_ready.emit(chunk)
                             except RuntimeError: # Target object likely deleted
                                 print(f"[StreamWorker {self.stream_name}] Target for signal emission deleted. Stopping.")
                                 self._should_stop = True
                                 break
                     else:
                        # If no chunk was read (e.g., non-blocking read returned nothing), sleep briefly
                        QThread.msleep(20)

                 except Exception as e:
                     print(f"[StreamWorker {self.stream_name}] Unexpected error in read loop: {e}")
                     traceback.print_exc()
                     self._should_stop = True # Exit loop on unexpected error
                     break
         finally:
             print(f"[StreamWorker {self.stream_name}] Read loop finished (Should Stop: {self._should_stop}, External Stop: {self.external_stop_flag_func()}).")
             # Do NOT close the stream here - Popen manages the pipe lifecycle.
             # Let the command_executor handle closing if necessary (though usually not needed).
             try:
                 self.finished.emit()
                 print(f"[StreamWorker {self.stream_name}] Finished signal emitted.")
             except RuntimeError:
                 print(f"[StreamWorker {self.stream_name}] Warning: Could not emit finished signal (target likely deleted).")
             except Exception as sig_err:
                  print(f"[StreamWorker {self.stream_name}] Error emitting finished signal: {sig_err}")