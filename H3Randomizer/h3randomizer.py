import random
import time
import threading
import pymem.process
from pymem import Pymem
import pymem.exception
from pymem.ressources.structure import MODULEINFO

from H3Randomizer_CPP import *
from mainwindow import *

# def create_message(p: Process, text: str):
#    base_addr = p.get_modules()[0]

#    text_str = ""
#    for c in text:
#        text_str += c
#        text_str += "\x00"

#    for _x in range((124 - len(text_str)) // 2):
#        text_str += " "
#        text_str += "\x00"

#    tickcount_ptr = p.get_pointer(
#        base_addr + 0x3F94F90, offsets=[0x48, 0x12877C0, 0x2320]
#    )
#    text_ptr = p.get_pointer(
#        base_addr + 0x3F94F90, offsets=[0x48, 0x12877C0, 0x2320 - 0xC8]
#    )
#    showtext_ptr = p.get_pointer(
#        base_addr + 0x3F94F90, offsets=[0x48, 0x12877C0, 0x2320 - 0x7]
#    )
#    p.write(
#        tickcount_ptr,
#        p.read(p.get_pointer(base_addr + 0x3F94F90, offsets=[0x48, 0x2B4178C])),
#    )
#    p.writeString(text_ptr, text_str)
#    p.write(showtext_ptr, 1)
#    showtext_ptr = p.get_pointer(
#        base_addr + 0x3F94F90, offsets=[0x48, 0x12877C0, 0x2320 - 0x7]
#    )


def hook(exe: str):
    """Continually attempt to get a handle of the defined process (exe). Returns Pymem object."""
    pm: Pymem = None
    while not pm: # Continually try to instantiate a new Pymem from the given exe name.
        try:
            pm = Pymem(exe)
            time.sleep(1)
        except Exception as e:
            if isinstance(e, pymem.exception.ProcessNotFound):
                continue
            elif isinstance(e, pymem.exception.CouldNotOpenProcess):
                console_output(f"Failed to attach to {exe}.")
                break
            else:
                console_output(f"{e}")
                break
        else:
            console_output(f"Attached to {exe} ({pm.process_id})!")
            return pm

def hook_dll(process: Pymem, dll: str):
    """Continually attempt to hook to the given dll under process. Returns MODULEINFO object."""
    module: MODULEINFO = None
    while not module:
        try:
            module = pymem.process.module_from_name(process.process_handle, dll)
            if module == None:
                break
            time.sleep(1)
        except Exception as e:
            console_output(f"{e}")
            break
        else:
            console_output(f"Found {dll} ({hex(module.lpBaseOfDll)})!")
            return module


# Function to check that we're still hooked to MCC
def check_hook(p: Pymem):
    """Check that process (p) is still hooked. Returns True or False."""
    try:
        ret = p.base_address
    except:
        return False
    else:
        return True

def check_module(p: Pymem, m: MODULEINFO, dll: str):
    """Check that the given module (m) is currently accessible by the process (p). Returns True or False."""
    try:
        m_current: MODULEINFO = pymem.process.module_from_name(p.process_handle, dll)
        if m_current == None:
            return False
    except Exception as e:
        console_output(f"{e}")
        return False
    else:
        return m_current.lpBaseOfDll == m.lpBaseOfDll

def start_handling_breakpoints(process: Pymem, dll: MODULEINFO):
    handle_breakpoints(process.process_id, dll.lpBaseOfDll, dll.lpBaseOfDll + 0x55C2D9, 0, 0, 0) # Handle breakpoint debug functions