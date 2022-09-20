from pymem import Pymem

from mainwindow import *
from h3randomizer import *

import logging, os

def main():
    if not os.path.exists("logs"):
        os.mkdir("logs")
    logging.basicConfig(
        filename= f"logs/h3randomizer_{int(datetime.now().timestamp())}.log",
        filemode='a',
        format='%(asctime)s [%(levelname)s]: %(message)s',
        datefmt='%H:%M:%S',
        level=logging.DEBUG)

    logging.info(f"Starting H3 Randomizer, version {VERSION}")

    g_current_randomizer = Halo3("MCC-Win64-Shipping.exe", "halo3.dll")

if __name__ == "__main__":
    thread_backend = threading.Thread(target=main)
    thread_backend.start()
    frontend_gui()