# ========================================
# 文件名: PowerAgent/core/worker_utils.py
# (NEW FILE)
# ----------------------------------------
# core/worker_utils.py
# -*- coding: utf-8 -*-

"""
Utility functions shared by worker threads.
"""

import locale
import platform

def decode_output(output_bytes: bytes) -> str:
    """
    Attempts to decode bytes, prioritizing UTF-8, then system preferred,
    then 'mbcs' (Windows), finally falling back to latin-1 with replacements.
    """
    if not isinstance(output_bytes, bytes):
        print(f"Warning: decode_output received non-bytes type: {type(output_bytes)}. Returning as is.")
        if isinstance(output_bytes, str): return output_bytes
        try: return str(output_bytes)
        except: return repr(output_bytes)

    if not output_bytes: return ""

    # 1. Try UTF-8 (most common)
    try:
        decoded_str = output_bytes.decode('utf-8')
        # print("[Decode] Success with utf-8") # Optional debug print
        return decoded_str
    except UnicodeDecodeError:
        # print("[Decode] Failed utf-8, trying system preferred...") # Optional debug print
        pass # Continue to next attempt
    except Exception as e:
        print(f"Error decoding with utf-8: {e}, trying system preferred...")
        pass # Continue to next attempt

    # 2. Try system preferred encoding (e.g., locale settings)
    system_preferred = locale.getpreferredencoding(False)
    if system_preferred and system_preferred.lower() != 'utf-8': # Avoid trying UTF-8 again
        try:
            # Use replace to avoid crashing on the second attempt
            decoded_str = output_bytes.decode(system_preferred, errors='replace')
            print(f"[Decode] Success with system preferred: {system_preferred}") # Info print
            return decoded_str
        except UnicodeDecodeError:
             print(f"[Decode] Failed system preferred '{system_preferred}', trying mbcs (Windows) or fallback...")
             pass # Continue to next attempt
        except Exception as e:
            print(f"Error decoding with system preferred '{system_preferred}': {e}, trying mbcs (Windows) or fallback...")
            pass

    # 3. Try 'mbcs' (mainly for Windows ANSI compatibility)
    if platform.system() == 'Windows':
        try:
            # Use replace to avoid crashing here
            decoded_str = output_bytes.decode('mbcs', errors='replace')
            print("[Decode] Success with mbcs") # Info print
            return decoded_str
        except UnicodeDecodeError:
             print("[Decode] Failed mbcs, using final fallback latin-1...")
             pass # Continue to next attempt
        except Exception as e:
            print(f"Error decoding with mbcs: {e}, using final fallback latin-1...")
            pass

    # 4. Final fallback (Latin-1 rarely fails but might not be correct)
    print("[Decode] Using final fallback: latin-1")
    return output_bytes.decode('latin-1', errors='replace')