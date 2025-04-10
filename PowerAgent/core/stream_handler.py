# ========================================
# 文件名: PowerAgent/core/stream_handler.py
# (CORRECTED)
# ----------------------------------------
# core/stream_handler.py
# -*- coding: utf-8 -*-

"""
Handles reading from subprocess streams asynchronously.
"""

import os
import platform
import traceback
# --- MODIFICATION START: Import io module ---
import io
# --- MODIFICATION END ---
from PySide6.QtCore import QObject, Signal, QThread

class StreamWorker(QObject):
     finished = Signal()
     output_ready = Signal(bytes) # Emits raw bytes

     def __init__(self, stream, stop_flag_func, line_list=None, filter_clixml=False):
         """
         Worker to read from a stream non-blockingly using os.read.

         Args:
             stream: The stream object (e.g., process.stdout, process.stderr).
             stop_flag_func: A callable function that returns True if the worker should stop.
             line_list (optional): A list to append raw chunks to (used for stderr checking later).
             filter_clixml (optional): If True on Windows, attempts to filter out CLIXML error messages.
         """
         super().__init__()
         self.stream = stream
         self.stop_flag_func = stop_flag_func
         self.line_list = line_list
         # Only enable CLIXML filtering on Windows
         self.filter_clixml = filter_clixml and platform.system() == "Windows"
         self.stream_fd = -1
         if hasattr(stream, 'fileno'):
             try:
                 self.stream_fd = stream.fileno()
             # --- MODIFICATION START: Use imported io module ---
             except (OSError, ValueError, io.UnsupportedOperation) as e:
             # --- MODIFICATION END ---
                 print(f"[StreamWorker] Warning: Could not get fileno for stream: {e}. os.read unavailable.")


     def run(self):
         """Reads from the stream and emits data until EOF or stop signal."""
         try:
             while not self.stop_flag_func():
                 try:
                     chunk = None
                     # Prefer os.read if fileno is valid, otherwise fallback (less reliable for non-blocking)
                     if self.stream_fd != -1:
                         try:
                             chunk = os.read(self.stream_fd, 4096)
                         except BlockingIOError:
                             # No data available right now with os.read, wait briefly
                             QThread.msleep(10)
                             continue
                         except (OSError, ValueError) as e:
                             # File descriptor might be closed or invalid
                             print(f"[StreamWorker] Stream read error (os.read) for FD {self.stream_fd}: {e}. Stopping stream read.")
                             break
                     else:
                         # Fallback for streams without fileno (less ideal for non-blocking)
                         # This part might block if the stream doesn't support non-blocking reads well
                         # Check stream read readiness if possible (platform dependent, difficult)
                         # For simplicity, we attempt read, which might block.
                         try:
                             # Check if stream has data (may not be reliable/supported)
                             # if hasattr(self.stream, 'peek') and not self.stream.peek():
                             #    QThread.msleep(10)
                             #    continue
                             chunk = self.stream.read(4096) # Might block
                         except io.UnsupportedOperation:
                             print(f"[StreamWorker] Fallback stream read failed: Unsupported operation.")
                             break # Cannot read from this stream type
                         except Exception as read_err:
                              print(f"[StreamWorker] Fallback stream read error: {read_err}")
                              break # Exit on other read errors

                         if not chunk and self.stream.closed: # Check if stream closed if read returns empty
                             print(f"[StreamWorker] Fallback stream closed.")
                             break

                     if chunk is None: # If read returned None (e.g., error occurred) or loop continued
                         QThread.msleep(10)
                         continue

                     if not chunk: # End of stream (read returned empty bytes)
                         print(f"[StreamWorker] EOF detected for FD {self.stream_fd if self.stream_fd != -1 else 'N/A'}.")
                         break

                     if not self.stop_flag_func(): # Check flag again after potentially blocking read
                         emit_chunk = True
                         if self.line_list is not None:
                             self.line_list.append(chunk) # Store raw chunk

                         # --- CLIXML Filtering (if enabled) ---
                         if self.filter_clixml:
                             try:
                                 # Basic check for typical CLIXML start sequence in PowerShell errors
                                 # This is heuristic and might filter too much/little
                                 if chunk.strip().startswith(b"#< CLIXML"):
                                     emit_chunk = False
                                     print("[StreamWorker] Filtered potential CLIXML block from stderr.")
                             except Exception as filter_err:
                                 # Ignore decoding errors during filtering check
                                 print(f"[StreamWorker] Warning: Error during CLIXML filter check: {filter_err}")
                                 pass
                         # --- End Filtering ---

                         if emit_chunk:
                             try:
                                 self.output_ready.emit(chunk)
                             except RuntimeError: # Target object likely deleted
                                 print("[StreamWorker] Target for signal emission seems to have been deleted. Stopping.")
                                 break
                 except Exception as e:
                     # Catch unexpected errors during the read loop
                     fd_info = self.stream_fd if self.stream_fd != -1 else 'N/A'
                     print(f"[StreamWorker] Unexpected error in read loop for FD {fd_info}: {e}")
                     traceback.print_exc()
                     break # Exit loop on unexpected error
         finally:
             # Ensure stream is closed (though Popen should handle it on process exit)
             try:
                 if hasattr(self.stream, 'closed') and not self.stream.closed:
                     self.stream.close()
             except Exception as close_err:
                  print(f"[StreamWorker] Error closing stream: {close_err}")
             # Signal that this specific stream worker is done
             try:
                 self.finished.emit()
             except RuntimeError:
                 pass # Target object likely deleted if main thread closed early