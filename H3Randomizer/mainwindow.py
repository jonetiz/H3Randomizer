from sre_constants import GROUPREF_UNI_IGNORE
from tkinter import *
import os
from tkinter.scrolledtext import ScrolledText

class GUI:
    root = Tk()
    root.config(bg="#303030")
    title = "Window Title"
    dimensions = "400x300"
    def __init__(self, *args, **kwargs):
        self.title = kwargs.get('title')
        self.dimensions = kwargs.get('dimensions')
        self.root.title(kwargs.get('title'))
        self.root.geometry = kwargs.get('dimensions')
        self.root.resizable(kwargs.get('resizable')[0], kwargs.get('resizable')[1])
    
class GUI_TextBox:
    obj: Text
    initial_state: str
    def __init__(self, *args, **kwargs):
        self.obj = Text(kwargs.get('parent').root)
        self.initial_state = kwargs.get('state')
        self.obj.config(state=kwargs.get('state'), bg="#202020", fg="#cccccc")
        self.obj.pack(padx=20,pady=20)
    def add_text(self, text: str, nl: bool = True):
        if self.initial_state == "disabled":
            self.obj.config(state="normal")
            self.obj.insert(END, f"{text}\n" if nl else f"{text}")
            self.obj.config(state="disabled")
        else:
            self.obj.insert(END, text)
        self.obj.see("end")

class GUI_ScrolledTextBox (GUI_TextBox):
    obj: ScrolledText
    def __init__(self, *args, **kwargs):
        self.obj = ScrolledText(kwargs.get('parent').root)
        self.initial_state = kwargs.get('state')
        self.obj.config(state=kwargs.get('state'), bg="#202020", fg="#cccccc")
        self.obj.pack(padx=20,pady=20,expand=True,fill=BOTH,side=LEFT)
        
main_window = GUI(title="Halo 3 Randomizer (DEV)", dimensions="640x480", resizable=(False, False))
main_window_output = GUI_ScrolledTextBox(parent=main_window, state="disabled")

def on_closing():
    print("Main window closed; Shutting down Halo 3 Randomizer.")
    os._exit(0)

def frontend_gui():
    while True:
        main_window.root.protocol("WM_DELETE_WINDOW", on_closing)
        main_window.root.mainloop()

def console_output(text: str, nl: bool = True):
    print(text)
    main_window_output.add_text(text, nl)