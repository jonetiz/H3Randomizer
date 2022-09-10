# Halo 3 Randomizer for MCC
# Swaps enemies and/or weapons (user defined) with random ones in the Halo 3
# campaign.
# Work in Progress
import enum
from pkgutil import ModuleInfo
import random
import time
import threading
import pymem.process
from pymem import Pymem
import pymem.exception
from pymem.ressources.structure import MODULEINFO
import asyncio

from H3Randomizer_CPP import *
from h3randomizer import *
from mainwindow import *

INVALID_ACTORS = ["dervish", "marine_johnson", "miranda", "truth", "monitor", "cortana", "marine_johnson_boss", "marine_johnson_halo", "monitor_combat"] # Actors that we don't want to randomize

def main(process: Pymem = None):
    if not check_hook(process): # Allow skipping process hooking if we already have a valid process handle
        console_output(f"Waiting for Halo: The Master Chief Collection...") # Print this string once when we attempt to hook
        while not process:
            try:
                process = hook("MCC-Win64-Shipping.exe")
            except:
                continue
            else:
                break # hook will print "Attached to MCC-Win64-Shipping.exe!"

    h3_dll: MODULEINFO = None
    console_output("Waiting for halo3.dll...")
    while not h3_dll:
        try:
            if check_hook(process): # Ensure we still have process hook, if not this while will break and check_hook loop below will throw back to main()
                h3_dll = hook_dll(process, "halo3.dll")
                if h3_dll == None:
                    raise Exception("Did not find halo3.dll!")
        except:
            continue
        else:
            break # hook_dll will print "Found halo3.dll!"
    initial_loop: bool = True
    thread_backend_cpp = threading.Thread(target=start_handling_breakpoints, args=(process, h3_dll))
    while check_hook(process): # Continually ensure we have a handle on process and DLL
        if check_module(process, h3_dll, "halo3.dll"): # Ensure address of h3_dll and the currently loaded halo3.dll are the same
            if initial_loop:
                update_breakpoints(process.process_id, h3_dll.lpBaseOfDll + 0x55C2D9, 0, 0, 0) # Set initial breakpoints
                console_output("Set breakpoints!")
                thread_backend_cpp.start()
                initial_loop = False
            #start_handling_breakpoints(process, h3_dll)
        else:
            console_output("Lost handle to halo3.dll! Retrying hook...")
            time.sleep(1)
            main(process)
    else:
        console_output("Lost handle to MCC! Retrying hook...")
        time.sleep(1)
        main()
if __name__ == "__main__":
    thread_backend = threading.Thread(target=main)
    thread_backend.start()
    frontend_gui()