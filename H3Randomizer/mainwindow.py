from tkinter import *
import os, sys, json, logging
from tkinter.scrolledtext import ScrolledText

VERSION = '0.1.2a'

config_data = {
    "randomize_weapons": 0,
    "seed": "haloruns.com",
    "randomize_seed": False
}

root = Tk()
root.config(bg="#000")
root.title(f"Halo 3 Randomizer {VERSION}")
root.geometry("640x480")
root.minsize(640,480)

iconfile = "icon.ico"
if not hasattr(sys, "frozen"):
    iconfile = os.path.join(os.path.dirname(__file__), iconfile) 
else:  
    iconfile = os.path.join(sys.prefix, iconfile)

root.iconbitmap(iconfile)

main_window_options_frame = Frame(root, width=640, height=300, background="#202020")
main_window_options_frame.pack(expand=False, fill=BOTH)
main_window_output_frame = Frame(root, width=640, height=280, background="#202020")
main_window_output_frame.pack(expand=True, fill=BOTH)
main_window_output = ScrolledText(main_window_output_frame, state="disabled", bg="#202020", fg="#cccccc")
main_window_output.pack(padx=20,pady=20, expand=True, fill=BOTH)

weapon_randomizer_setting = IntVar()
weapon_randomizer_checkbox = Checkbutton(main_window_options_frame, text="Randomize Weapons?", variable=weapon_randomizer_setting, onvalue=1, offvalue=0, bg="#202020", fg="#cccccc", selectcolor="#202020", activebackground="#202020", activeforeground="#cccccc")
weapon_randomizer_checkbox.grid(column=0,row=0)

seed_label = Label(main_window_options_frame, text="Seed: ", bg="#202020", fg="#cccccc")
seed_label.grid(column=1, row=0)

seed_setting = StringVar()
seed_textbox = Entry(main_window_options_frame, bg="#202020", fg="#cccccc", disabledbackground="#101010", disabledforeground="#404040", width=40, state="normal", insertbackground="#cccccc", textvariable=seed_setting)
seed_textbox.grid(column=2,row=0)

disable_seed_textbox = True
def configure_seed_box():
    global disable_seed_textbox
    if disable_seed_textbox:
        seed_textbox.configure(state="disabled")
    else:
        seed_textbox.configure(state="normal")
    disable_seed_textbox = not disable_seed_textbox

seed_randomizer_setting = BooleanVar()
seed_randomizer_checkbox = Checkbutton(main_window_options_frame, text="Randomize Seed? (Single Player)", variable=seed_randomizer_setting, onvalue=1, offvalue=0, bg="#202020", fg="#cccccc", selectcolor="#202020", activebackground="#202020", activeforeground="#cccccc", command=lambda:configure_seed_box())
seed_randomizer_checkbox.grid(column=3,row=0)

def on_closing():
    print("Main window closed; Shutting down Halo 3 Randomizer.")
    
    # Save config on exit
    with open("config.json", "w+") as f:
        json.dump(config_data, f)
    
    os._exit(0)

def frontend_gui():
    with open("config.json", "r+" if os.path.exists("config.json") else "w+") as f:
        try:
            json_object = json.load(f)
        except:
            json_object = '{"randomize_weapons": 0, "seed": "haloruns.com", "randomize_seed": false}'
    
    try:
        config_data['randomize_weapons'] = json_object['randomize_weapons']
        if json_object['randomize_weapons'] != 0:
            weapon_randomizer_checkbox.select()
    except:
        pass

    try:
        config_data['seed'] = json_object['seed']
        seed_textbox.insert(0, config_data["seed"])
    except:
        pass

    try:
        config_data['randomize_seed'] = json_object['randomize_seed']
        if json_object['randomize_seed'] != 0:
            seed_randomizer_checkbox.select()
            configure_seed_box()
    except:
        pass
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

def console_output(text: str, nl: bool = True):
    print(text)
    logging.info(text)
    main_window_output.config(state="normal")
    main_window_output.insert(END, f"{text}\n")
    main_window_output.config(state="disabled")
    main_window_output.see("end")

def disable_frame(frame):
    for child in frame.winfo_children():
        child.configure(state="disabled")


def enable_frame(frame):
    for child in frame.winfo_children():
        child.configure(state="normal")