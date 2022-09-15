# Halo 3 Randomizer for MCC
# Swaps enemies and/or weapons (user defined) with random ones in the Halo 3
# campaign.
# Work in Progress
from pymem import Pymem

from mainwindow import *
from h3randomizer import *

def main(process: Pymem = None):
    g_current_randomizer = Halo3("MCC-Win64-Shipping.exe", "halo3.dll")

if __name__ == "__main__":
    thread_backend = threading.Thread(target=main)
    thread_backend.start()
    #main()
    frontend_gui()