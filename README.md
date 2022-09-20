# Halo 3 Character and Weapon Randomizer
Program that randomizes characters and their weapons in Halo 3 for Halo: The Master Chief Collection. Intended for use in randomized speedruns, or casual playthroughs with random enemies. Feel free to adapt or modify the code. I am more than happy to accept improvements in the form of pull requests.

![image](https://user-images.githubusercontent.com/5671812/190297057-3b03bac0-055b-413c-b650-94cfb1de35ed.png)

# End-User Usage
ATTENTION: This program uses some very exerpimental or "hacky" methods to accomplish it's goals. Please use at your own risk, and know that any project contributors are not responsible for any potential damages. Feel free to go through the source code at your leisure.
## Requirements
- 64-bit Windows Operating System (Should be required for MCC anyway)
- Halo: MCC for PC (Steam only supported currently)

## Usage
*For self-build instructions, see [Build Instructions](https://github.com/jonetiz/H3Randomizer/blob/master/README.md#build-instructions) below.*
1. Go to [Releases](https://github.com/jonetiz/H3randomizer/releases/).
2. Download the latest or desired release.
3. Place h3randomizer.exe in it's own directory (it will create files).
4. Launch the game without Anti-Cheat.
5. Run the .exe file as Administrator and it should automatically hook to the game.

# Project Contribution
## Requirements
- Visual Studio 2022
  - Python Development Module
  - C++ Development Module
- Python 3.9 or Later (3.10.6 preferred)
- Additional Requirements:
  - [pymem](https://pymem.readthedocs.io/en/latest/) - used for basic memory access - install via `pip install pymem`
  - [pyinstaller](https://pyinstaller.org/en/stable/) - used to build executable - install via `pip install pyinstaller`
  - [pybind11](https://pybind11.readthedocs.io/en/stable/) - C++ <--> Python binding - installation instructions in link
  - tkinter - used for GUI - included in modern python

## Development Process
Having Visual Studio 2022 with the Python and C++ development workflows and all other requirements, simply open the visual studio solution. I've only set things up for Debug configuration, and x64 is required.

## Build Instructions
1. Right-click "H3Randomizer_CPP in the Solution Explorer and click "Build".
  - This places a few files in H3Randomizer/x64
2. Copy the generated "/x64/Debug/H3Randomizer_CPP.pyd" file to "/H3Randomizer/" (the python project folder).
3. Open a command prompt/powershell in "/H3Randomizer/"
4. `pyinstaller main.spec`
5. Build should be placed as an exe file in /H3Randomizer/dist
