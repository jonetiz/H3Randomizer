# Halo 3 Randomizer for MCC
# Swaps enemies and/or weapons (user defined) with random ones in the Halo 3
# campaign.
# Work in Progress
from pymem import Pymem

from mainwindow import *
from h3randomizer import *

import logging

def main():
    logging.basicConfig(
        filename= f"logs/h3randomizer_{int(datetime.now().timestamp())}.log",
        filemode='a',
        format='%(asctime)s [%(levelname)s]: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG)

    logging.info("Running H3 Randomizer")

    g_current_randomizer = Halo3("MCC-Win64-Shipping.exe", "halo3.dll")

if __name__ == "__main__":
    thread_backend = threading.Thread(target=main)
    thread_backend.start()
    frontend_gui()