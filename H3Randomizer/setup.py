from distutils.core import setup
import py2exe

setup(
    name="h3randomizer",
    version="0.1.0",
    author="Jonathan Etiz",
    author_email="ac13xero@gmail.com",
    url="https://github.com/jonetiz/h3randomizer",
    description="Halo 3 Randomizer for speedruns",
    long_description="",
    python_requires=">=3.9",
    windows=['main.py'],
    py_modules=['h3randomizer', 'mainwindow'],
    options = {"py2exe" : {"includes" : "H3Randomizer_CPP"}}
)